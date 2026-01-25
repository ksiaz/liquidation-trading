"""Live Position Tracker - Direct API, No Database.

Simple, clean architecture:
- WebSocket for real-time prices
- Direct API calls for positions
- In-memory state only
- No caching, no database, no delays
"""

import asyncio
import json
import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
import httpx
import websockets


@dataclass
class Position:
    """Live position data with real liquidation risk."""
    wallet: str
    coin: str
    side: str  # LONG or SHORT
    size: float
    entry_price: float
    current_price: float
    liq_price: float  # Isolated margin liq price (where liquidations cluster)
    leverage: float
    notional: float
    pnl: float
    distance_pct: float  # Distance to isolated liq price
    # Account-level fields
    account_value: float = 0.0
    margin_used: float = 0.0
    margin_ratio: float = 0.0  # margin_used / account_value (higher = more risk)
    account_equity: float = 0.0  # Available equity buffer
    real_liq_price: float = 0.0  # Account-based liq price (where THIS account liquidates)
    real_distance_pct: float = 0.0  # Distance to real account liquidation
    # Liq touch tracking
    liq_touched: bool = False  # True if price crossed liq level recently
    liq_breached: bool = False  # True if price went PAST liq (liquidation likely happened)
    recent_high: float = 0.0  # Recent candle high (for shorts)
    recent_low: float = 0.0  # Recent candle low (for longs)

    @property
    def at_risk(self) -> bool:
        """Real risk: high margin utilization AND close to isolated liq."""
        return self.margin_ratio > 0.5 and 0 < self.distance_pct < 10.0

    @property
    def risk_score(self) -> float:
        """Combined risk score: margin_ratio * (1 / distance_pct)."""
        if self.distance_pct <= 0:
            return 0
        return self.margin_ratio * (100 / self.distance_pct)

    @property
    def status(self) -> str:
        """Position status string."""
        if self.liq_breached:
            return "LIQUIDATED?"
        elif self.liq_touched:
            return "LIQ_TOUCHED"
        elif self.distance_pct < 1:
            return "CRITICAL"
        elif self.distance_pct < 3:
            return "WARNING"
        else:
            return "WATCH"


class LiveTracker:
    """Real-time position and liquidation tracker."""

    def __init__(
        self,
        wallets: List[str] = None,
        on_update: Optional[Callable] = None,
        on_new_wallet: Optional[Callable] = None,
        auto_discover: bool = True,
        discovery_interval: float = 30.0,
        min_account_value: float = 50000,
    ):
        """
        Args:
            wallets: Initial wallet addresses to track
            on_update: Callback when positions update (positions: List[Position])
            on_new_wallet: Callback when new wallet discovered (wallet: str, account_value: float)
            auto_discover: Enable continuous wallet discovery
            discovery_interval: Seconds between discovery scans
            min_account_value: Minimum account value to track
        """
        self.wallets = set(wallets or [])
        self.on_update = on_update
        self.on_new_wallet = on_new_wallet
        self.auto_discover = auto_discover
        self.discovery_interval = discovery_interval
        self.min_account_value = min_account_value

        # State
        self._prices: Dict[str, float] = {}
        self._positions: List[Position] = []
        self._running = False
        self._ws_task = None
        self._poll_task = None
        self._discovery_task = None

        # Discovery state - track which coins we've scanned recently
        self._discovery_coin_index = 0

    def get_positions(self, max_distance: float = 5.0, min_margin_ratio: float = 0.0) -> List[Position]:
        """Get positions within max_distance% of liquidation.

        Args:
            max_distance: Maximum distance to liquidation (%)
            min_margin_ratio: Minimum margin utilization to include (0-1)
        """
        return [
            p for p in self._positions
            if 0 < p.distance_pct <= max_distance and p.margin_ratio >= min_margin_ratio
        ]

    def get_risky_positions(self, min_margin_ratio: float = 0.5, max_distance: float = 20.0) -> List[Position]:
        """Get positions with real liquidation risk.

        Filters for:
        - High margin utilization (using most of account equity)
        - Reasonable distance to liquidation

        Sorted by risk_score (highest risk first).
        """
        risky = [
            p for p in self._positions
            if p.margin_ratio >= min_margin_ratio and 0 < p.distance_pct <= max_distance
        ]
        return sorted(risky, key=lambda p: -p.risk_score)

    def get_all_positions(self) -> List[Position]:
        """Get all tracked positions."""
        return self._positions.copy()

    async def start(self):
        """Start live tracking."""
        self._running = True

        # Initial price fetch
        await self._fetch_prices()

        # Build tasks
        tasks = [
            asyncio.create_task(self._ws_loop()),
            asyncio.create_task(self._poll_loop()),
        ]
        self._ws_task = tasks[0]
        self._poll_task = tasks[1]

        # Add continuous discovery if enabled
        if self.auto_discover:
            self._discovery_task = asyncio.create_task(self._discovery_loop())
            tasks.append(self._discovery_task)

        await asyncio.gather(*tasks)

    def stop(self):
        """Stop tracking."""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._poll_task:
            self._poll_task.cancel()

    async def _fetch_prices(self):
        """Fetch all mid prices."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'allMids'},
                timeout=10
            )
            data = response.json()
            self._prices = {k: float(v) for k, v in data.items()}

    async def _fetch_recent_high_low(self, coin: str, minutes: int = 15) -> tuple:
        """Fetch recent high/low from candles.

        Returns (high, low) for the last N minutes.
        """
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - (minutes * 60 * 1000)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://api.hyperliquid.xyz/info',
                    json={
                        'type': 'candleSnapshot',
                        'req': {
                            'coin': coin,
                            'interval': '1m',
                            'startTime': start_time,
                            'endTime': end_time
                        }
                    },
                    timeout=10
                )
                candles = response.json()

            if isinstance(candles, list) and candles:
                highs = [float(c.get('h', 0)) for c in candles]
                lows = [float(c.get('l', float('inf'))) for c in candles]
                return max(highs), min(lows)
        except Exception:
            pass
        return 0.0, float('inf')

    async def _fetch_wallet_positions(self, wallet: str) -> List[Position]:
        """Fetch positions for a single wallet with both isolated and real liq prices."""
        positions = []

        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'clearinghouseState', 'user': wallet},
                timeout=10
            )
            state = response.json()

        # Extract account-level margin info
        margin = state.get('marginSummary', {})
        account_value = float(margin.get('accountValue', 0))
        margin_used = float(margin.get('totalMarginUsed', 0))

        # Skip accounts with no value
        if account_value <= 0:
            return positions

        margin_ratio = margin_used / account_value if account_value > 0 else 0
        account_equity = account_value - margin_used

        for p in state.get('assetPositions', []):
            pos = p.get('position', {})
            coin = pos.get('coin', '')
            sz = float(pos.get('szi', 0))

            if sz == 0:
                continue

            entry = float(pos.get('entryPx', 0)) if pos.get('entryPx') else 0
            if entry == 0:
                continue

            side = 'LONG' if sz > 0 else 'SHORT'
            current_price = self._prices.get(coin, 0)

            if current_price == 0:
                continue

            leverage_data = pos.get('leverage', {})
            leverage = float(leverage_data.get('value', 0)) if isinstance(leverage_data, dict) else 0
            if leverage == 0:
                leverage = 20  # Default assumption

            notional = abs(sz) * current_price
            pnl = float(pos.get('unrealizedPnl', 0))
            size_abs = abs(sz)

            # 1. ISOLATED LIQ PRICE - where liquidations cluster (standard formula)
            # This is useful for identifying price levels where OTHER positions liquidate
            if side == 'LONG':
                isolated_liq = entry * (1 - 0.9 / leverage)
                isolated_liq = max(0, isolated_liq)
                isolated_dist = ((current_price - isolated_liq) / current_price) * 100 if isolated_liq > 0 else 100
            else:
                isolated_liq = entry * (1 + 0.9 / leverage)
                isolated_dist = ((isolated_liq - current_price) / current_price) * 100

            # 2. REAL LIQ PRICE - where THIS account actually liquidates (account-based)
            # Based on total account equity, not just this position's margin
            max_loss = account_value * 0.9  # Conservative: 90% of account can be lost

            if side == 'LONG':
                real_liq = entry - (max_loss / size_abs) if size_abs > 0 else 0
                real_liq = max(0, real_liq)
                real_dist = ((current_price - real_liq) / current_price) * 100 if real_liq > 0 else 100
            else:
                real_liq = entry + (max_loss / size_abs) if size_abs > 0 else float('inf')
                real_dist = ((real_liq - current_price) / current_price) * 100

            # Skip zombie positions - negative distance means price already passed liq level
            # These are cross-margin positions that haven't liquidated due to account buffer
            if isolated_dist < 0:
                continue

            # Check if liq level was touched (only for positions within 5%)
            liq_touched = False
            liq_breached = False
            recent_high = 0.0
            recent_low = float('inf')

            if isolated_dist < 5:
                # Fetch recent candles for close positions
                try:
                    recent_high, recent_low = await self._fetch_recent_high_low(coin, minutes=15)

                    if side == 'LONG':
                        # For longs, check if low went below liq
                        if recent_low <= isolated_liq:
                            liq_breached = True
                            liq_touched = True
                        elif recent_low <= isolated_liq * 1.01:  # Within 1% of liq
                            liq_touched = True
                    else:
                        # For shorts, check if high went above liq
                        if recent_high >= isolated_liq:
                            liq_breached = True
                            liq_touched = True
                        elif recent_high >= isolated_liq * 0.99:  # Within 1% of liq
                            liq_touched = True
                except Exception:
                    pass

            positions.append(Position(
                wallet=wallet,
                coin=coin,
                side=side,
                size=size_abs,
                entry_price=entry,
                current_price=current_price,
                liq_price=isolated_liq,
                leverage=leverage,
                notional=notional,
                pnl=pnl,
                distance_pct=isolated_dist,
                account_value=account_value,
                margin_used=margin_used,
                margin_ratio=margin_ratio,
                account_equity=account_equity,
                real_liq_price=real_liq,
                real_distance_pct=real_dist,
                liq_touched=liq_touched,
                liq_breached=liq_breached,
                recent_high=recent_high,
                recent_low=recent_low
            ))

        return positions

    async def _discovery_loop(self):
        """Continuously discover new wallets from trades."""
        # Comprehensive coin list - rotate through these
        coins = [
            'BTC', 'ETH', 'SOL', 'DOGE', 'XRP', 'ADA', 'AVAX', 'DOT', 'LINK', 'UNI',
            'NOT', 'WIF', 'PEPE', 'BONK', 'SHIB', 'FLOKI', 'MEME', 'TURBO', 'BRETT',
            'SUI', 'APT', 'SEI', 'INJ', 'TIA', 'OP', 'ARB', 'MATIC', 'NEAR',
            'STX', 'KAS', 'RENDER', 'FET', 'TAO', 'ONDO', 'JUP', 'PYTH',
            'WLD', 'BLUR', 'JTO', 'STRK', 'MANTA', 'DYM', 'ALT', 'PIXEL',
            'ORDI', 'SATS', 'RATS', '1000SATS', 'BOME', 'SLERF', 'MEW',
            'ENA', 'ETHFI', 'W', 'TNSR', 'SAGA', 'REZ', 'BB', 'IO', 'ZK',
            'POPCAT', 'MOG', 'GOAT', 'PNUT', 'ACT', 'NEIRO', 'MOODENG',
            'HYPE', 'VIRTUAL', 'AI16Z', 'ZEREBRO', 'GRIFFAIN', 'AIXBT',
            'TRUMP', 'FARTCOIN', 'SPX', 'CHILLGUY', 'PENGU', 'PUDGY',
        ]

        while self._running:
            try:
                # Pick next batch of coins (5 at a time to avoid rate limits)
                batch_size = 5
                start_idx = self._discovery_coin_index
                end_idx = start_idx + batch_size
                batch = coins[start_idx:end_idx]

                if not batch:
                    self._discovery_coin_index = 0
                    batch = coins[:batch_size]

                self._discovery_coin_index = (end_idx) % len(coins)

                # Discover from this batch
                await self._discover_from_coins(batch)

                await asyncio.sleep(self.discovery_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Discovery error: {e}")
                await asyncio.sleep(10)

    async def _discover_from_coins(self, coins: List[str]):
        """Discover wallets from trades on specific coins."""
        async with httpx.AsyncClient() as client:
            for coin in coins:
                try:
                    response = await client.post(
                        'https://api.hyperliquid.xyz/info',
                        json={'type': 'recentTrades', 'coin': coin},
                        timeout=10
                    )
                    trades = response.json()

                    price = self._prices.get(coin, 0)
                    if price == 0:
                        continue

                    for trade in trades:
                        sz = float(trade.get('sz', 0))
                        trade_value = sz * price

                        # Only check wallets from trades > $5k
                        if trade_value >= 5000:
                            users = trade.get('users', [])
                            for user in users:
                                if user and user.startswith('0x') and user not in self.wallets:
                                    # Check if wallet has significant value
                                    await self._check_and_add_wallet(client, user)

                except Exception:
                    pass

    async def _check_and_add_wallet(self, client: httpx.AsyncClient, wallet: str):
        """Check wallet value and add if significant."""
        try:
            response = await client.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'clearinghouseState', 'user': wallet},
                timeout=5
            )
            state = response.json()

            margin = state.get('marginSummary', {})
            account_value = float(margin.get('accountValue', 0))

            if account_value >= self.min_account_value:
                self.wallets.add(wallet)
                print(f"[DISCOVERED] {wallet[:16]}... (${account_value:,.0f})")

                if self.on_new_wallet:
                    self.on_new_wallet(wallet, account_value)

        except Exception:
            pass

    async def _poll_loop(self):
        """Poll wallet positions periodically."""
        while self._running:
            try:
                all_positions = []

                for wallet in list(self.wallets):  # Copy to avoid mutation during iteration
                    try:
                        positions = await self._fetch_wallet_positions(wallet)
                        all_positions.extend(positions)
                    except Exception as e:
                        print(f"Error fetching {wallet[:10]}...: {e}")

                # Sort by distance
                all_positions.sort(key=lambda p: p.distance_pct)

                # Only update if we got reasonable data (at least 5 positions or more than half of current)
                # This prevents flickering when API calls fail
                min_positions = max(5, len(self._positions) // 2) if self._positions else 0
                if len(all_positions) >= min_positions or not self._positions:
                    self._positions = all_positions
                else:
                    # Skip bad update - likely API error
                    print(f"[LiveTracker] Skipping bad update: {len(all_positions)} vs {len(self._positions)} (min={min_positions})")

                # Callback
                if self.on_update:
                    self.on_update(self._positions)

                await asyncio.sleep(2)  # Poll every 2 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Poll error: {e}")
                await asyncio.sleep(5)

    async def _ws_loop(self):
        """WebSocket loop for real-time price updates."""
        while self._running:
            try:
                async with websockets.connect('wss://api.hyperliquid.xyz/ws') as ws:
                    # Subscribe to all mids
                    await ws.send(json.dumps({
                        'method': 'subscribe',
                        'subscription': {'type': 'allMids'}
                    }))

                    async for msg in ws:
                        if not self._running:
                            break

                        try:
                            data = json.loads(msg)
                            if data.get('channel') == 'allMids':
                                mids = data.get('data', {}).get('mids', {})
                                for coin, price in mids.items():
                                    self._prices[coin] = float(price)

                                # Update position prices
                                self._update_position_prices()
                        except:
                            pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                await asyncio.sleep(2)

    def _update_position_prices(self):
        """Update position prices and distances from current prices."""
        for pos in self._positions:
            current_price = self._prices.get(pos.coin, pos.current_price)
            if current_price == 0:
                continue

            pos.current_price = current_price
            pos.notional = pos.size * current_price

            # Recalculate distance
            if pos.side == 'LONG':
                pos.distance_pct = ((current_price - pos.liq_price) / current_price) * 100
            else:
                pos.distance_pct = ((pos.liq_price - current_price) / current_price) * 100


class LiveTrackerSync:
    """Synchronous wrapper for LiveTracker - for use in non-async code."""

    def __init__(
        self,
        wallets: List[str] = None,
        auto_discover: bool = True,
        min_account_value: float = 50000,
    ):
        self.initial_wallets = wallets or DEFAULT_WHALES
        self.auto_discover = auto_discover
        self.min_account_value = min_account_value
        self._tracker: Optional[LiveTracker] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self):
        """Start tracker in background thread."""
        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._tracker = LiveTracker(
                wallets=self.initial_wallets,
                auto_discover=self.auto_discover,
                min_account_value=self.min_account_value,
            )
            self._loop.run_until_complete(self._tracker.start())

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        time.sleep(2)  # Let it initialize

    def stop(self):
        """Stop tracker."""
        if self._tracker:
            self._tracker.stop()

    def get_positions(self, max_distance: float = 5.0, min_margin_ratio: float = 0.0) -> List[Position]:
        """Get positions within distance of liquidation."""
        if self._tracker:
            return self._tracker.get_positions(max_distance, min_margin_ratio)
        return []

    def get_risky_positions(self, min_margin_ratio: float = 0.5, max_distance: float = 20.0) -> List[Position]:
        """Get positions with REAL liquidation risk (high margin utilization)."""
        if self._tracker:
            return self._tracker.get_risky_positions(min_margin_ratio, max_distance)
        return []

    def get_at_risk(self) -> List[Position]:
        """Get positions at high risk (>50% margin used AND <10% from liq)."""
        return [p for p in self.get_positions(10.0) if p.at_risk]

    def get_wallet_count(self) -> int:
        """Get number of tracked wallets."""
        if self._tracker:
            return len(self._tracker.wallets)
        return 0


# Default whale wallets - seeds for discovery
# Add known whales, vaults, and active traders here
DEFAULT_WHALES = [
    # Large whales found from trading
    '0x010461c14e146ac35fe42271bdc1134ee31c703a',  # $80M whale

    # Hyperliquid vaults (public addresses)
    '0x1291e94a21c2a348c241dae52a32ff9290a3f233',  # HLP vault
    '0x2df1c51e09aecf9cacb7bc98cb1742757f163df7',  # Liquidator

    # Known active traders (from leaderboards/trades)
    '0xf9109ada2f73c62e9889b45453065f0d99260a2d',  # Active BTC trader
    '0x3037d61eb6ce0fb533311cb76a837080efd5c9ab',  # Active trader
    '0xd72cfd2424e26ba32e46b7b2aff95eff34247a71',  # Active trader
    '0x219317d2156854500fb131fd7779ded05d2d46b3',  # Active trader
    '0xab4b26979cd896171c57c5f40308e5290e776d9c',  # Active trader
]


async def discover_wallets_from_trades(coins: List[str] = None, min_size_usd: float = 10000) -> List[str]:
    """Discover wallet addresses from large trades.

    Args:
        coins: List of coins to check (default: major coins)
        min_size_usd: Minimum trade size in USD to consider

    Returns:
        List of unique wallet addresses
    """
    if coins is None:
        coins = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP', 'NOT', 'WIF', 'PEPE']

    wallets = set()

    async with httpx.AsyncClient() as client:
        # Get prices first
        response = await client.post(
            'https://api.hyperliquid.xyz/info',
            json={'type': 'allMids'},
            timeout=10
        )
        prices = {k: float(v) for k, v in response.json().items()}

        for coin in coins:
            try:
                response = await client.post(
                    'https://api.hyperliquid.xyz/info',
                    json={'type': 'recentTrades', 'coin': coin},
                    timeout=10
                )
                trades = response.json()

                price = prices.get(coin, 0)
                if price == 0:
                    continue

                for trade in trades:
                    sz = float(trade.get('sz', 0))
                    trade_value = sz * price

                    if trade_value >= min_size_usd:
                        users = trade.get('users', [])
                        for user in users:
                            if user and user.startswith('0x'):
                                wallets.add(user)

            except Exception as e:
                print(f"Error fetching {coin} trades: {e}")

    return list(wallets)


async def discover_wallets_with_positions(wallets: List[str], min_value: float = 50000) -> List[str]:
    """Filter wallets to those with significant positions.

    Args:
        wallets: List of wallet addresses to check
        min_value: Minimum account value to keep

    Returns:
        List of wallets with significant positions
    """
    significant = []

    async with httpx.AsyncClient() as client:
        for wallet in wallets:
            try:
                response = await client.post(
                    'https://api.hyperliquid.xyz/info',
                    json={'type': 'clearinghouseState', 'user': wallet},
                    timeout=5
                )
                state = response.json()

                margin = state.get('marginSummary', {})
                account_value = float(margin.get('accountValue', 0))

                if account_value >= min_value:
                    significant.append(wallet)

            except:
                pass

    return significant


async def discover_whales(min_account_value: float = 100000) -> List[str]:
    """Discover whale wallets automatically.

    1. Get wallets from recent large trades
    2. Filter to those with significant account values

    Returns:
        List of whale wallet addresses
    """
    print("Discovering wallets from trades...")
    candidates = await discover_wallets_from_trades(min_size_usd=5000)
    print(f"Found {len(candidates)} candidates")

    print("Filtering by account value...")
    whales = await discover_wallets_with_positions(candidates, min_value=min_account_value)
    print(f"Found {len(whales)} whales (>${min_account_value:,.0f} accounts)")

    return whales


def print_positions(positions: List[Position]):
    """Pretty print positions."""
    print(f"\n{'='*70}")
    print(f"LIVE POSITIONS - {time.strftime('%H:%M:%S')}")
    print(f"{'='*70}")

    if not positions:
        print("No positions near liquidation")
        return

    # Separate past-liq from near-liq
    past_liq = [p for p in positions if p.distance_pct < 0]
    near_liq = [p for p in positions if 0 < p.distance_pct < 5]

    if past_liq:
        print(f"\n🔴 PAST LIQUIDATION (cross-margin absorbing):")
        print(f"{'Dist':>7} | {'Coin':8} {'Side':5} | {'Notional':>12} | {'Lev':>4} | {'PnL':>10}")
        print("-" * 70)
        for p in past_liq[:5]:
            print(f"{p.distance_pct:>+6.2f}% | {p.coin:8} {p.side:5} | ${p.notional:>11,.0f} | {p.leverage:>3.0f}x | ${p.pnl:>+9,.0f}")

    if near_liq:
        print(f"\n{'Dist':>6} | {'Coin':8} {'Side':5} | {'Notional':>12} | {'Lev':>4} | {'PnL':>10}")
        print("-" * 70)
        for p in near_liq[:20]:
            risk = "⚠️" if p.at_risk else "  "
            print(f"{p.distance_pct:>5.2f}%{risk}| {p.coin:8} {p.side:5} | ${p.notional:>11,.0f} | {p.leverage:>3.0f}x | ${p.pnl:>+9,.0f}")


async def main():
    """Demo: Run live tracker with continuous auto-discovery."""
    print("=" * 60)
    print("LIVE POSITION TRACKER (Continuous Discovery)")
    print("=" * 60)
    print()
    print("- Positions polled every 2 seconds")
    print("- Prices updated via WebSocket (real-time)")
    print("- New wallets discovered every 30 seconds")
    print("- 70+ coins scanned for large trades")
    print()

    def on_update(positions):
        near_liq = [p for p in positions if p.distance_pct < 5]
        if near_liq:
            print_positions(near_liq)

    tracker = LiveTracker(
        wallets=DEFAULT_WHALES,
        on_update=on_update,
        auto_discover=True,
        discovery_interval=15.0,  # Faster discovery
        min_account_value=25000,  # Lower threshold = more wallets
    )

    print(f"Starting with {len(DEFAULT_WHALES)} seed wallet(s)...")
    print("=" * 60)

    try:
        await tracker.start()
    except KeyboardInterrupt:
        tracker.stop()


async def quick_scan():
    """One-time scan without websocket - just show current state."""
    print("Quick scan - positions near liquidation...")

    # Discover
    whales = await discover_whales(min_account_value=50000)
    all_wallets = list(set(DEFAULT_WHALES + whales))

    # Create tracker
    tracker = LiveTracker(wallets=all_wallets)
    await tracker._fetch_prices()

    # Fetch all positions
    all_positions = []
    for wallet in all_wallets:
        try:
            positions = await tracker._fetch_wallet_positions(wallet)
            all_positions.extend(positions)
        except Exception as e:
            pass

    # Sort and display
    all_positions.sort(key=lambda p: p.distance_pct)
    near_liq = [p for p in all_positions if 0 < p.distance_pct < 5]

    print_positions(near_liq)

    return near_liq


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--scan':
        asyncio.run(quick_scan())
    else:
        asyncio.run(main())

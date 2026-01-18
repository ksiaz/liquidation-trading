"""
WebSocket-based real-time position tracking with sub-50ms latency.

Architecture:
- Multiple WS connections (10 users per connection limit)
- Position-centric indexing (by market, not wallet)
- Precomputed trigger prices (no math on hot path)
- Price-driven detection (scan only affected market on tick)

This is a HEADLESS risk engine. UI reads from shared state.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Callable, Any
from collections import defaultdict
import websockets
import logging

from runtime.hyperliquid.shared_state import (
    get_shared_state, SharedPositionState, PositionSnapshot, DangerAlert
)

logger = logging.getLogger(__name__)

WS_URL = 'wss://api.hyperliquid.xyz/ws'


@dataclass
class TrackedPosition:
    """Position with precomputed trigger prices for fast detection."""
    wallet: str
    coin: str
    side: str  # 'LONG' or 'SHORT'
    size: float
    entry_price: float
    liq_price: float
    notional: float
    leverage: float

    # Precomputed trigger prices (no math on hot path)
    trigger_2pct: float = 0.0  # Price at 2% from liq
    trigger_1pct: float = 0.0  # Price at 1% from liq
    trigger_05pct: float = 0.0  # Price at 0.5% from liq

    # Current state (updated on price tick)
    current_price: float = 0.0
    distance_pct: float = 100.0

    # Flags
    in_danger_zone: bool = False

    def __post_init__(self):
        """Precompute trigger prices once on position creation."""
        self._compute_triggers()

    def _compute_triggers(self):
        """Precompute price levels for fast comparison."""
        if self.liq_price <= 0:
            return

        if self.side == 'LONG':
            # Long: danger when price drops toward liq_price
            self.trigger_2pct = self.liq_price * 1.02
            self.trigger_1pct = self.liq_price * 1.01
            self.trigger_05pct = self.liq_price * 1.005
        else:
            # Short: danger when price rises toward liq_price
            self.trigger_2pct = self.liq_price * 0.98
            self.trigger_1pct = self.liq_price * 0.99
            self.trigger_05pct = self.liq_price * 0.995

    def check_danger(self, price: float) -> int:
        """
        Ultra-fast danger check. No division, just comparison.
        Returns: 0=safe, 1=watch(2%), 2=warning(1%), 3=critical(0.5%)
        """
        if self.side == 'LONG':
            # Zombie check: if price is below liq_price, position is already breached
            if price <= self.liq_price:
                return 0  # Already liquidated, not in danger zone
            if price <= self.trigger_05pct:
                return 3
            if price <= self.trigger_1pct:
                return 2
            if price <= self.trigger_2pct:
                return 1
        else:
            # Zombie check: if price is above liq_price, position is already breached
            if price >= self.liq_price:
                return 0  # Already liquidated, not in danger zone
            if price >= self.trigger_05pct:
                return 3
            if price >= self.trigger_1pct:
                return 2
            if price >= self.trigger_2pct:
                return 1
        return 0


@dataclass
class DangerSignal:
    """Signal emitted when position enters danger zone."""
    wallet: str
    coin: str
    side: str
    size: float
    notional: float
    liq_price: float
    current_price: float
    distance_pct: float
    danger_level: int  # 1=watch, 2=warning, 3=critical
    timestamp: float = field(default_factory=time.time)


@dataclass
class AccountSummary:
    """Cross-margin account summary for proper liquidation price calculation."""
    wallet: str
    account_value: float  # Total equity from crossMarginSummary
    total_notional: float  # Sum of all position notionals
    total_margin_used: float  # Margin used across all positions
    updated_at: float = 0.0


class WSPositionTracker:
    """
    Manages multiple WebSocket connections for user state tracking.

    Key design principles:
    1. Position-centric indexing (by market, not wallet)
    2. Price-driven detection (on tick, scan only that market)
    3. Precomputed trigger prices (no math on hot path)
    4. Headless - UI reads from shared state
    """

    MAX_USERS_PER_CONN = 10  # Hyperliquid limit
    MIN_CONNECTIONS = 5
    MAX_CONNECTIONS = 15

    def __init__(
        self,
        on_signal: Optional[Callable[[DangerSignal], None]] = None,
        on_position_update: Optional[Callable[[str, Dict], None]] = None
    ):
        self._running = False
        self._on_signal = on_signal
        self._on_position_update = on_position_update

        # Shared state for UI decoupling
        self._shared_state = get_shared_state()

        # Connection management
        self._connections: Dict[int, asyncio.Task] = {}
        self._conn_wallets: Dict[int, List[str]] = {}  # conn_id -> wallets
        self._wallet_to_conn: Dict[str, int] = {}  # wallet -> conn_id
        self._conn_websockets: Dict[int, Any] = {}  # conn_id -> WebSocket instance
        self._subscribe_queue: Dict[int, List[str]] = defaultdict(list)  # conn_id -> wallets to subscribe

        # POSITION-CENTRIC indexing (key optimization)
        self._market_positions: Dict[str, Dict[str, TrackedPosition]] = defaultdict(dict)
        # market_positions["JTO"][wallet] = TrackedPosition

        # Also keep wallet-centric for updates
        self._wallet_positions: Dict[str, Dict[str, TrackedPosition]] = defaultdict(dict)
        # wallet_positions[wallet][coin] = TrackedPosition

        # Price state (shared across connections)
        self._mid_prices: Dict[str, float] = {}
        self._price_lock = asyncio.Lock()

        # Danger tracking
        self._danger_positions: Dict[str, TrackedPosition] = {}  # key = wallet:coin

        # Account summaries for cross-margin liquidation calculation
        # Key = wallet address, Value = AccountSummary with equity/margin data
        self._account_summaries: Dict[str, AccountSummary] = {}

        # Liquidation tracking - positions that were closed while in danger zone
        # Key = "wallet:coin", Value = timestamp when detected
        self._liquidated_positions: Dict[str, float] = {}
        self._liquidation_cooldown = 300  # 5 minutes - don't re-add liquidated positions

        # Stats
        self._stats = {
            'ws_messages': 0,
            'price_updates': 0,
            'position_updates': 0,
            'signals_emitted': 0,
            'last_latency_ms': 0
        }

    @property
    def positions_by_market(self) -> Dict[str, Dict[str, TrackedPosition]]:
        """Read-only access to market-indexed positions."""
        return self._market_positions

    @property
    def danger_positions(self) -> Dict[str, TrackedPosition]:
        """Read-only access to positions in danger zone."""
        return self._danger_positions

    @property
    def mid_prices(self) -> Dict[str, float]:
        """Read-only access to current prices."""
        return self._mid_prices

    @property
    def stats(self) -> Dict[str, Any]:
        """Performance stats."""
        return self._stats

    async def start(self, initial_wallets: List[str]):
        """Start tracking positions for initial wallet set."""
        self._running = True

        # Calculate initial connections needed
        num_conns = min(
            max(self.MIN_CONNECTIONS, (len(initial_wallets) + 9) // 10),
            self.MAX_CONNECTIONS
        )

        # Distribute wallets across connections
        for i in range(num_conns):
            start_idx = i * self.MAX_USERS_PER_CONN
            end_idx = start_idx + self.MAX_USERS_PER_CONN
            wallet_batch = initial_wallets[start_idx:end_idx]

            if wallet_batch:
                self._conn_wallets[i] = wallet_batch
                for w in wallet_batch:
                    self._wallet_to_conn[w] = i

                # Start connection task
                self._connections[i] = asyncio.create_task(
                    self._run_connection(i, wallet_batch)
                )

        logger.info(f"[WSTracker] Started {num_conns} connections for {len(initial_wallets)} wallets")

    async def stop(self):
        """Stop all connections gracefully."""
        self._running = False

        for task in self._connections.values():
            task.cancel()

        await asyncio.gather(*self._connections.values(), return_exceptions=True)
        self._connections.clear()
        logger.info("[WSTracker] Stopped all connections")

    async def subscribe_wallet(self, wallet: str) -> bool:
        """Add wallet to tracking. Returns True if added."""
        wallet = wallet.lower()
        if wallet in self._wallet_to_conn:
            return False  # Already tracked

        # Find connection with room
        for conn_id, wallets in self._conn_wallets.items():
            if len(wallets) < self.MAX_USERS_PER_CONN:
                wallets.append(wallet)
                self._wallet_to_conn[wallet] = conn_id
                # Queue subscribe message for this connection
                self._subscribe_queue[conn_id].append(wallet)
                logger.info(f"[WSTracker] Queued wallet {wallet[:10]}... for conn {conn_id}")
                return True

        # All connections full - would need to add new connection
        if len(self._connections) < self.MAX_CONNECTIONS:
            new_conn_id = max(self._connections.keys()) + 1 if self._connections else 0
            self._conn_wallets[new_conn_id] = [wallet]
            self._wallet_to_conn[wallet] = new_conn_id
            self._connections[new_conn_id] = asyncio.create_task(
                self._run_connection(new_conn_id, [wallet])
            )
            logger.info(f"[WSTracker] Created new conn {new_conn_id} for wallet {wallet[:10]}...")
            return True

        return False  # At capacity

    def get_tracked_wallets(self) -> List[str]:
        """Get list of all wallets currently tracked on WebSocket."""
        return list(self._wallet_to_conn.keys())

    async def unsubscribe_wallet(self, wallet: str) -> bool:
        """Remove wallet from tracking."""
        if wallet not in self._wallet_to_conn:
            return False

        conn_id = self._wallet_to_conn.pop(wallet)
        self._conn_wallets[conn_id].remove(wallet)

        # Remove from position indices
        if wallet in self._wallet_positions:
            for coin in list(self._wallet_positions[wallet].keys()):
                if wallet in self._market_positions.get(coin, {}):
                    del self._market_positions[coin][wallet]
            del self._wallet_positions[wallet]

        # TODO: Send unsubscribe message to connection
        return True

    async def _run_connection(self, conn_id: int, wallets: List[str]):
        """Single WebSocket connection handling up to 10 users."""
        retry_count = 0

        while self._running:
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=30,
                    ping_timeout=60,
                    close_timeout=10
                ) as ws:
                    retry_count = 0  # Reset on successful connect
                    self._conn_websockets[conn_id] = ws  # Store WS reference for dynamic subscription
                    print(f"[WSTracker] Conn {conn_id} CONNECTED with {len(wallets)} wallets")

                    # Subscribe to allMids (price feed)
                    await ws.send(json.dumps({
                        'method': 'subscribe',
                        'subscription': {'type': 'allMids'}
                    }))

                    # Subscribe to each user's state and events
                    for wallet in wallets:
                        await self._send_wallet_subscriptions(ws, wallet)

                    # Message loop with periodic queue check
                    async for msg in ws:
                        if not self._running:
                            break

                        # Process any queued subscriptions for this connection
                        await self._process_subscribe_queue(conn_id, ws)

                        start_time = time.perf_counter()
                        await self._handle_message(msg)
                        self._stats['last_latency_ms'] = (time.perf_counter() - start_time) * 1000
                        self._stats['ws_messages'] += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                delay = min(2 ** retry_count, 60)
                logger.warning(f"[WSTracker] Conn {conn_id} error: {e}, retry in {delay}s")
                await asyncio.sleep(delay)
            finally:
                # Clean up WebSocket reference on disconnect
                if conn_id in self._conn_websockets:
                    del self._conn_websockets[conn_id]

    async def _send_wallet_subscriptions(self, ws, wallet: str):
        """Send subscription messages for a wallet (webData2 + userEvents)."""
        # Position updates
        await ws.send(json.dumps({
            'method': 'subscribe',
            'subscription': {'type': 'webData2', 'user': wallet}
        }))
        # Liquidation events (definitive confirmation)
        await ws.send(json.dumps({
            'method': 'subscribe',
            'subscription': {'type': 'userEvents', 'user': wallet}
        }))

    async def _process_subscribe_queue(self, conn_id: int, ws):
        """Process any queued wallet subscriptions for this connection."""
        if conn_id not in self._subscribe_queue:
            return

        queue = self._subscribe_queue[conn_id]
        while queue:
            wallet = queue.pop(0)
            try:
                await self._send_wallet_subscriptions(ws, wallet)
                print(f"[WSTracker] Subscribed to wallet {wallet[:10]}... on conn {conn_id}")
            except Exception as e:
                logger.error(f"[WSTracker] Failed to subscribe {wallet[:10]}...: {e}")
                # Put back in queue for retry
                queue.insert(0, wallet)
                break

    async def _handle_message(self, msg: str):
        """Route message to appropriate handler."""
        try:
            data = json.loads(msg)
            channel = data.get('channel')

            if channel == 'allMids':
                await self._handle_price_update(data.get('data', {}))
            elif channel == 'webData2':
                await self._handle_position_update(data.get('data', {}))
            elif channel == 'userEvents':
                await self._handle_user_events(data.get('data', {}))
        except Exception as e:
            logger.error(f"[WSTracker] Message error: {e}")

    async def _handle_price_update(self, data: Dict):
        """
        Handle price update - THE HOT PATH.
        On price tick, scan only positions in that market.
        """
        mids = data.get('mids', {})
        if not mids:
            return

        self._stats['price_updates'] += 1

        # Log every 100 updates with danger count
        if self._stats['price_updates'] % 100 == 0:
            danger_count = len(self._danger_positions)
            total_positions = sum(len(p) for p in self._market_positions.values())
            print(f"[WSTracker] Price updates: {self._stats['price_updates']}, positions: {total_positions}, danger: {danger_count}")

            # Debug: Show closest positions to liquidation
            if self._stats['price_updates'] == 100:
                closest = []
                for coin, positions in self._market_positions.items():
                    for wallet, pos in positions.items():
                        if pos.liq_price > 0 and pos.current_price > 0:
                            if pos.side == 'LONG':
                                dist = ((pos.current_price - pos.liq_price) / pos.current_price) * 100
                            else:
                                dist = ((pos.liq_price - pos.current_price) / pos.current_price) * 100
                            closest.append((coin, pos.side, dist, pos.notional, pos.liq_price, pos.trigger_2pct))
                closest.sort(key=lambda x: x[2])
                print("[WSTracker] Top 5 closest positions:")
                for c in closest[:5]:
                    print(f"  {c[0]} {c[1]} dist={c[2]:.2f}% notional=${c[3]:,.0f} liq={c[4]:.4f} trigger2%={c[5]:.4f}")

        # Update prices and scan affected markets
        prices_batch = {}
        coins_to_scan = []

        for coin, price_str in mids.items():
            if price_str is None:
                continue
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                continue

            old_price = self._mid_prices.get(coin, 0)
            self._mid_prices[coin] = price
            prices_batch[coin] = price

            # Track coins with meaningful price changes for danger scan
            if old_price == 0 or abs(price - old_price) / old_price >= 0.0001:
                coins_to_scan.append((coin, price))

        # Batch update mid prices to shared state
        if prices_batch:
            self._shared_state.update_mid_prices(prices_batch)

        # Scan only coins with meaningful price changes
        for coin, price in coins_to_scan:

            # POSITION-CENTRIC: Only scan positions in THIS market
            positions = self._market_positions.get(coin, {})
            if not positions:
                continue

            # Fast scan - just comparisons, no math
            positions_to_remove = []
            for wallet, pos in positions.items():
                danger_level = pos.check_danger(price)
                key = f"{wallet}:{coin}"

                # ALWAYS update price, notional, and distance for ALL positions
                pos.current_price = price
                pos.notional = pos.size * price

                # Calculate distance for ALL positions (needed for UI sorting)
                if pos.liq_price > 0:
                    if pos.side == 'LONG':
                        pos.distance_pct = ((price - pos.liq_price) / price) * 100
                    else:
                        pos.distance_pct = ((pos.liq_price - price) / price) * 100

                # LIQUIDATION DETECTION: If price reached/crossed liq price, remove immediately
                # distance <= 0 means liq price was touched or breached
                if pos.distance_pct <= 0:
                    positions_to_remove.append((wallet, coin, key, pos.distance_pct))
                    continue  # Don't update shared state for liquidated positions

                # Update shared state snapshot
                snapshot = PositionSnapshot(
                    wallet=wallet,
                    coin=coin,
                    side=pos.side,
                    size=pos.size,
                    notional=pos.notional,
                    entry_price=pos.entry_price,
                    liq_price=pos.liq_price,
                    current_price=pos.current_price,
                    distance_pct=pos.distance_pct,
                    leverage=pos.leverage,
                    danger_level=danger_level,
                    updated_at=time.time()
                )
                self._shared_state.update_position(snapshot)

                if danger_level > 0:
                    pos.in_danger_zone = True

                    # Track danger position
                    was_in_danger = key in self._danger_positions
                    self._danger_positions[key] = pos

                    # Emit signal if newly entered danger or level increased
                    # Only emit if we have meaningful data (notional > $1000)
                    if (not was_in_danger or danger_level > 1) and pos.notional >= 1000:
                        self._emit_signal(pos, danger_level)
                else:
                    # No longer in danger
                    pos.in_danger_zone = False
                    if key in self._danger_positions:
                        del self._danger_positions[key]

            # Remove liquidated positions from all indices
            for wallet, coin, key, dist in positions_to_remove:
                if wallet in self._wallet_positions and coin in self._wallet_positions[wallet]:
                    del self._wallet_positions[wallet][coin]
                if coin in self._market_positions and wallet in self._market_positions[coin]:
                    del self._market_positions[coin][wallet]
                if key in self._danger_positions:
                    del self._danger_positions[key]
                self._shared_state.remove_position(wallet, coin)
                # Add to liquidation cooldown to prevent re-adding from stale webData2
                self._liquidated_positions[key] = time.time()
                print(f"[WSTracker] ⚠️ LIQUIDATED - Removed: {wallet[:10]}...:{coin} (distance was {dist:.2f}%)")

    def _calculate_cross_margin_liq_price(
        self, wallet: str, entry_price: float, size: float, leverage: float
    ) -> float:
        """
        Calculate liquidation price for cross-margin position using account-level data.

        Formula from Hyperliquid docs:
        liq_price = price - side × margin_available / position_size / (1 - maintenance_lev × side)

        Where:
        - margin_available = account_value - maintenance_margin_required
        - maintenance_margin_required ≈ 5% of total notional

        Falls back to leverage-based estimate if account data unavailable.
        """
        summary = self._account_summaries.get(wallet)

        if not summary or summary.account_value <= 0:
            # Fallback: estimate from leverage (less accurate)
            buffer = 0.9  # 90% of theoretical max to be conservative
            if size > 0:  # LONG
                return entry_price * (1 - buffer / leverage)
            else:  # SHORT
                return entry_price * (1 + buffer / leverage)

        # Calculate margin available
        # Maintenance margin is ~5% of total notional (varies by asset)
        maintenance_margin = abs(summary.total_notional) * 0.05
        margin_available = summary.account_value - maintenance_margin

        if margin_available <= 0:
            # No spare margin - position is already close to liquidation
            # Fall back to very tight estimate
            if size > 0:
                return entry_price * 0.99  # 1% below entry
            else:
                return entry_price * 1.01  # 1% above entry

        # Apply the formula
        side = 1 if size > 0 else -1
        maintenance_lev = 0.05  # 5% maintenance = 20x max leverage at liquidation

        try:
            liq_price = entry_price - side * margin_available / abs(size) / (1 - maintenance_lev * side)
            # Sanity check: liq price must be positive and reasonable
            if liq_price <= 0:
                return entry_price * (0.5 if size > 0 else 1.5)
            return liq_price
        except (ZeroDivisionError, ValueError):
            # Fallback on math errors
            if size > 0:
                return entry_price * 0.9
            else:
                return entry_price * 1.1

    async def _handle_position_update(self, data: Dict):
        """Handle webData2 user state update."""
        user = data.get('user')
        clearinghouse = data.get('clearinghouseState')

        if not user or not clearinghouse:
            return

        self._stats['position_updates'] += 1

        # Extract cross-margin summary for proper liquidation calculation
        cross_margin = clearinghouse.get('crossMarginSummary', {})
        if cross_margin:
            try:
                account_value = float(cross_margin.get('accountValue', 0))
                total_ntl = float(cross_margin.get('totalNtlPos', 0))
                total_margin = float(cross_margin.get('totalMarginUsed', 0))

                self._account_summaries[user] = AccountSummary(
                    wallet=user,
                    account_value=account_value,
                    total_notional=total_ntl,
                    total_margin_used=total_margin,
                    updated_at=time.time()
                )
            except (ValueError, TypeError):
                pass  # Keep existing summary if parsing fails

        # Track which coins this wallet has
        new_coins: Set[str] = set()

        for asset in clearinghouse.get('assetPositions', []):
            pos_data = asset.get('position', {})
            coin = pos_data.get('coin', '')

            # Safe float conversion with defaults
            szi_raw = pos_data.get('szi')
            if szi_raw is None:
                continue
            try:
                szi = float(szi_raw)
            except (ValueError, TypeError):
                continue

            if abs(szi) < 0.0001 or not coin:
                continue

            new_coins.add(coin)

            # Safe float conversions
            try:
                api_liq_price = pos_data.get('liquidationPx')
                liq_price = float(api_liq_price) if api_liq_price else 0
                entry_price = float(pos_data.get('entryPx') or 0)
            except (ValueError, TypeError):
                continue

            if entry_price <= 0:
                continue

            current_price = self._mid_prices.get(coin, 0)

            # Get leverage
            leverage_data = pos_data.get('leverage', {})
            try:
                leverage = float(leverage_data.get('value', 20)) if isinstance(leverage_data, dict) else 20
            except (ValueError, TypeError):
                leverage = 20
            if leverage <= 0:
                leverage = 20

            # If API returns no liq price (null), calculate using account-level data
            # This happens for cross-margin positions or well-collateralized positions
            if liq_price <= 0:
                liq_price = self._calculate_cross_margin_liq_price(
                    wallet=user,
                    entry_price=entry_price,
                    size=szi,
                    leverage=leverage
                )

            # Check if this position was recently liquidated - don't re-add during cooldown
            key = f"{user}:{coin}"
            if key in self._liquidated_positions:
                liq_time = self._liquidated_positions[key]
                if time.time() - liq_time < self._liquidation_cooldown:
                    continue  # Still in cooldown, skip this position
                else:
                    # Cooldown expired, allow position (it's a new position)
                    del self._liquidated_positions[key]

            # Skip zombie positions (already breached)
            if current_price > 0:
                if szi > 0 and current_price < liq_price:  # Long below liq
                    continue
                if szi < 0 and current_price > liq_price:  # Short above liq
                    continue

            # Check if liq price changed (for debugging)
            old_pos = self._wallet_positions.get(user, {}).get(coin)
            if old_pos and abs(old_pos.liq_price - liq_price) > 0.0001:
                pct_change = ((liq_price - old_pos.liq_price) / old_pos.liq_price) * 100
                print(f"[WSTracker] 📊 LIQ PRICE CHANGED: {coin} {old_pos.liq_price:.6f} → {liq_price:.6f} ({pct_change:+.2f}%)")

            # Create/update position
            position = TrackedPosition(
                wallet=user,
                coin=coin,
                side='LONG' if szi > 0 else 'SHORT',
                size=abs(szi),
                entry_price=entry_price,
                liq_price=liq_price,
                notional=abs(szi) * current_price if current_price > 0 else 0,
                leverage=leverage,
                current_price=current_price
            )

            # Update both indices
            self._wallet_positions[user][coin] = position
            self._market_positions[coin][user] = position

            # Write to shared state (for UI)
            snapshot = PositionSnapshot(
                wallet=user,
                coin=coin,
                side=position.side,
                size=position.size,
                notional=position.notional,
                entry_price=position.entry_price,
                liq_price=position.liq_price,
                current_price=position.current_price,
                distance_pct=position.distance_pct,
                leverage=position.leverage,
                danger_level=position.check_danger(position.current_price) if position.current_price > 0 else 0,
                updated_at=time.time()
            )
            self._shared_state.update_position(snapshot)

        # Remove closed positions
        old_coins = set(self._wallet_positions.get(user, {}).keys())
        for closed_coin in old_coins - new_coins:
            key = f"{user}:{closed_coin}"

            # Check if this was a danger zone position - if so, it was likely liquidated
            was_in_danger = key in self._danger_positions
            if was_in_danger:
                self._liquidated_positions[key] = time.time()
                print(f"[WSTracker] 💀 FORCE LIQUIDATED: {user[:10]}...:{closed_coin} (was in danger zone)")

            if closed_coin in self._wallet_positions.get(user, {}):
                del self._wallet_positions[user][closed_coin]
            if user in self._market_positions.get(closed_coin, {}):
                del self._market_positions[closed_coin][user]

            # Remove from danger tracking
            if was_in_danger:
                del self._danger_positions[key]

            # Remove from shared state
            self._shared_state.remove_position(user, closed_coin)

        # Callback for external processing
        if self._on_position_update:
            self._on_position_update(user, clearinghouse)

    async def _handle_user_events(self, data: Dict):
        """
        Handle userEvents - DEFINITIVE liquidation confirmation.

        This is the authoritative source for liquidation events.
        When we receive a liquidation event, the position is 100% liquidated.
        """
        user = data.get('user', '')
        if not user:
            return

        # Check for liquidation event
        if 'liquidation' in data:
            liq_data = data['liquidation']

            # Extract liquidated positions
            liquidated_positions = liq_data.get('liquidatedPositions', [])
            notional = float(liq_data.get('liquidated_ntl_pos', 0))

            print(f"\n{'='*60}")
            print(f"[WSTracker] 💀 LIQUIDATION CONFIRMED via userEvents")
            print(f"[WSTracker] User: {user[:16]}...")
            print(f"[WSTracker] Notional: ${notional:,.0f}")

            # Remove each liquidated position
            for liq_pos in liquidated_positions:
                coin = liq_pos.get('coin', '')
                size = float(liq_pos.get('szi', 0))

                if not coin:
                    continue

                side = 'LONG' if size > 0 else 'SHORT'
                print(f"[WSTracker] Position: {coin} {side} size={abs(size):,.2f}")

                key = f"{user}:{coin}"

                # Remove from all indices
                if user in self._wallet_positions and coin in self._wallet_positions[user]:
                    del self._wallet_positions[user][coin]
                if coin in self._market_positions and user in self._market_positions[coin]:
                    del self._market_positions[coin][user]
                if key in self._danger_positions:
                    del self._danger_positions[key]

                # Remove from shared state
                self._shared_state.remove_position(user, coin)

                # Add to liquidation cooldown
                self._liquidated_positions[key] = time.time()

            print(f"{'='*60}\n")

            # Track stats
            self._stats['liquidations_confirmed'] = self._stats.get('liquidations_confirmed', 0) + 1

    def _emit_signal(self, pos: TrackedPosition, danger_level: int):
        """Emit danger signal to shared state and callback."""
        signal = DangerSignal(
            wallet=pos.wallet,
            coin=pos.coin,
            side=pos.side,
            size=pos.size,
            notional=pos.notional,
            liq_price=pos.liq_price,
            current_price=pos.current_price,
            distance_pct=pos.distance_pct,
            danger_level=danger_level
        )

        self._stats['signals_emitted'] += 1

        # Write alert to shared state (for UI)
        alert = DangerAlert(
            wallet=pos.wallet,
            coin=pos.coin,
            side=pos.side,
            notional=pos.notional,
            distance_pct=pos.distance_pct,
            danger_level=danger_level,
            liq_price=pos.liq_price,
            current_price=pos.current_price,
            timestamp=time.time()
        )
        self._shared_state.add_alert(alert)

        # Callback for fade executor (not UI)
        if self._on_signal:
            try:
                self._on_signal(signal)
            except Exception as e:
                logger.error(f"[WSTracker] Signal callback error: {e}")

    def get_positions_for_market(self, coin: str) -> List[TrackedPosition]:
        """Get all tracked positions for a market (sorted by distance)."""
        positions = list(self._market_positions.get(coin, {}).values())
        positions.sort(key=lambda p: p.distance_pct)
        return positions

    def get_positions_for_wallet(self, wallet: str) -> List[TrackedPosition]:
        """Get all positions for a wallet."""
        return list(self._wallet_positions.get(wallet, {}).values())

    def get_all_danger_positions(self) -> List[TrackedPosition]:
        """Get all positions in danger zone (sorted by distance)."""
        positions = list(self._danger_positions.values())
        positions.sort(key=lambda p: p.distance_pct)
        return positions

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection and performance stats."""
        return {
            'connections': len(self._connections),
            'wallets_tracked': len(self._wallet_to_conn),
            'markets_tracked': len(self._market_positions),
            'positions_tracked': sum(len(p) for p in self._market_positions.values()),
            'danger_positions': len(self._danger_positions),
            'recent_liquidations': len(self._liquidated_positions),
            **self._stats
        }

    def get_recent_liquidations(self, since_seconds: float = 300) -> List[Dict[str, Any]]:
        """Get positions liquidated within the last N seconds."""
        cutoff = time.time() - since_seconds
        results = []
        for key, liq_time in self._liquidated_positions.items():
            if liq_time >= cutoff:
                parts = key.split(':')
                if len(parts) == 2:
                    results.append({
                        'wallet': parts[0],
                        'coin': parts[1],
                        'liquidated_at': liq_time,
                        'seconds_ago': time.time() - liq_time
                    })
        return sorted(results, key=lambda x: x['liquidated_at'], reverse=True)

    def cleanup_old_liquidations(self):
        """Remove liquidation entries older than cooldown period."""
        cutoff = time.time() - self._liquidation_cooldown
        old_keys = [k for k, t in self._liquidated_positions.items() if t < cutoff]
        for key in old_keys:
            del self._liquidated_positions[key]
        if old_keys:
            print(f"[WSTracker] Cleaned up {len(old_keys)} old liquidation entries")


class WalletPrioritizer:
    """
    Dynamically manage which wallets get WebSocket vs REST tracking.

    Rebalances every N seconds to ensure wallets closest to liquidation
    are on WebSocket connections for fastest updates.
    """

    def __init__(
        self,
        ws_tracker: WSPositionTracker,
        rest_poll_callback: Optional[Callable[[List[str]], None]] = None
    ):
        self.ws_tracker = ws_tracker
        self._rest_poll_callback = rest_poll_callback

        self._all_wallets: Set[str] = set()  # All known wallets
        self._ws_wallets: Set[str] = set()  # Currently on WebSocket
        self._rest_wallets: Set[str] = set()  # Polled via REST

        # Scoring
        self._wallet_scores: Dict[str, float] = {}  # wallet -> min_distance

    async def set_wallet_universe(self, wallets: List[str]):
        """Set the full universe of wallets to track."""
        self._all_wallets = set(wallets)
        await self.rebalance()

    async def add_wallet(self, wallet: str):
        """Add wallet to universe."""
        self._all_wallets.add(wallet)

    async def remove_wallet(self, wallet: str):
        """Remove wallet from tracking."""
        self._all_wallets.discard(wallet)
        if wallet in self._ws_wallets:
            await self.ws_tracker.unsubscribe_wallet(wallet)
            self._ws_wallets.discard(wallet)
        self._rest_wallets.discard(wallet)

    async def rebalance(self):
        """
        Rebalance which wallets are on WS vs REST.

        Called every 5s to adjust based on current positions.
        Wallets closest to liquidation get WS priority.
        """
        # Score wallets by minimum distance to liquidation
        scored: List[tuple] = []

        for wallet in self._all_wallets:
            positions = self.ws_tracker.get_positions_for_wallet(wallet)

            if positions:
                min_dist = min(p.distance_pct for p in positions)
                max_notional = max(p.notional for p in positions)
            else:
                # No known positions - use REST to discover
                min_dist = 100.0
                max_notional = 0

            # Score: lower is higher priority
            # Prioritize by distance, then by position size
            score = min_dist - (max_notional / 1_000_000)  # $1M = -1 to score
            scored.append((wallet, score, min_dist))

        # Sort by score (lowest first = highest priority)
        scored.sort(key=lambda x: x[1])

        # Calculate how many wallets can be on WS
        max_ws_wallets = self.ws_tracker.MAX_CONNECTIONS * self.ws_tracker.MAX_USERS_PER_CONN

        # Top wallets go to WS, rest to REST
        new_ws_wallets = set()
        new_rest_wallets = set()

        for i, (wallet, score, min_dist) in enumerate(scored):
            if i < max_ws_wallets and min_dist < 20:  # Only WS if within 20%
                new_ws_wallets.add(wallet)
            else:
                new_rest_wallets.add(wallet)

        # Calculate changes
        wallets_to_add_ws = new_ws_wallets - self._ws_wallets
        wallets_to_remove_ws = self._ws_wallets - new_ws_wallets

        # Apply changes (avoid thrashing - only change if significant)
        if len(wallets_to_add_ws) > 2 or len(wallets_to_remove_ws) > 2:
            # Significant rebalance needed
            for wallet in wallets_to_remove_ws:
                await self.ws_tracker.unsubscribe_wallet(wallet)

            for wallet in wallets_to_add_ws:
                await self.ws_tracker.subscribe_wallet(wallet)

            self._ws_wallets = new_ws_wallets
            self._rest_wallets = new_rest_wallets

            logger.info(
                f"[Prioritizer] Rebalanced: {len(self._ws_wallets)} WS, "
                f"{len(self._rest_wallets)} REST (+{len(wallets_to_add_ws)}, -{len(wallets_to_remove_ws)})"
            )

        # Trigger REST poll for non-WS wallets
        if self._rest_poll_callback and self._rest_wallets:
            self._rest_poll_callback(list(self._rest_wallets))

    def get_status(self) -> Dict[str, Any]:
        """Get prioritizer status."""
        return {
            'total_wallets': len(self._all_wallets),
            'ws_wallets': len(self._ws_wallets),
            'rest_wallets': len(self._rest_wallets),
            'ws_list': list(self._ws_wallets)[:10],  # First 10 for debug
        }


class HybridPositionTracker:
    """
    High-level tracker combining WebSocket (priority) and REST (fallback).

    This is the main entry point for the application.
    """

    def __init__(
        self,
        on_signal: Optional[Callable[[DangerSignal], None]] = None,
        on_position_update: Optional[Callable[[str, Dict], None]] = None
    ):
        self._on_signal = on_signal
        self._on_position_update = on_position_update

        # WebSocket tracker for priority wallets
        self.ws_tracker = WSPositionTracker(
            on_signal=on_signal,
            on_position_update=on_position_update
        )

        # Prioritizer for dynamic wallet assignment
        self.prioritizer = WalletPrioritizer(
            self.ws_tracker,
            rest_poll_callback=self._on_rest_poll_needed
        )

        self._rest_wallets_queue: List[str] = []
        self._running = False

    def _on_rest_poll_needed(self, wallets: List[str]):
        """Called when REST polling is needed for wallets."""
        self._rest_wallets_queue = wallets

    async def start(self, initial_wallets: List[str]):
        """Start hybrid tracking."""
        self._running = True

        # Start with ALL danger wallets on WS for fastest detection
        # Don't artificially limit - positions close to liquidation need real-time tracking
        max_ws_wallets = min(len(initial_wallets), 100)  # Reasonable limit for WS connections
        await self.ws_tracker.start(initial_wallets[:max_ws_wallets])

        # Set full wallet universe
        await self.prioritizer.set_wallet_universe(initial_wallets)

        # Start rebalance loop
        asyncio.create_task(self._rebalance_loop())

        logger.info(f"[HybridTracker] Started with {len(initial_wallets)} wallets ({max_ws_wallets} on WS)")

    async def stop(self):
        """Stop hybrid tracking."""
        self._running = False
        await self.ws_tracker.stop()

    async def _rebalance_loop(self):
        """Periodically rebalance WS vs REST wallets."""
        cleanup_counter = 0
        while self._running:
            try:
                await self.prioritizer.rebalance()

                # Cleanup old liquidation entries every 60 seconds (12 iterations)
                cleanup_counter += 1
                if cleanup_counter >= 12:
                    self.ws_tracker.cleanup_old_liquidations()
                    cleanup_counter = 0

            except Exception as e:
                logger.error(f"[HybridTracker] Rebalance error: {e}")

            await asyncio.sleep(5)  # Rebalance every 5 seconds

    def get_rest_wallets_to_poll(self) -> List[str]:
        """Get wallets that need REST polling (for external poller)."""
        return self._rest_wallets_queue

    def get_all_danger_positions(self) -> List[TrackedPosition]:
        """Get all positions in danger zone."""
        return self.ws_tracker.get_all_danger_positions()

    def get_positions_for_market(self, coin: str) -> List[TrackedPosition]:
        """Get positions for a specific market."""
        return self.ws_tracker.get_positions_for_market(coin)

    def get_status(self) -> Dict[str, Any]:
        """Get full status."""
        return {
            'ws_tracker': self.ws_tracker.get_connection_stats(),
            'prioritizer': self.prioritizer.get_status(),
            'rest_queue_size': len(self._rest_wallets_queue),
            'recent_liquidations': self.ws_tracker.get_recent_liquidations(300)  # Last 5 min
        }

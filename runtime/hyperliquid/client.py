"""
Hyperliquid API Client

WebSocket and REST client for Hyperliquid exchange.
Handles connection management, subscription, and data parsing.

API Documentation: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
"""

import asyncio
import json
import time
import logging
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass
import aiohttp

from .types import (
    HyperliquidPosition,
    PositionEvent,
    PositionEventType,
    PositionSide,
    WalletState
)


# API Endpoints
MAINNET_API_URL = "https://api.hyperliquid.xyz"
MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
TESTNET_WS_URL = "wss://api.hyperliquid-testnet.xyz/ws"


@dataclass
class ClientConfig:
    """Configuration for Hyperliquid client."""
    use_testnet: bool = False
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    ping_interval: float = 30.0
    request_timeout: float = 10.0


class HyperliquidClient:
    """
    Hyperliquid API Client.

    Provides:
    - REST API calls for clearinghouseState, meta, etc.
    - WebSocket subscriptions for real-time updates
    - Position parsing and normalization
    """

    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig()
        self._logger = logging.getLogger("HyperliquidClient")

        # Select endpoints based on config
        if self.config.use_testnet:
            self._api_url = TESTNET_API_URL
            self._ws_url = TESTNET_WS_URL
        else:
            self._api_url = MAINNET_API_URL
            self._ws_url = MAINNET_WS_URL

        # Connection state
        self._running = False
        self._ws = None
        self._session: Optional[aiohttp.ClientSession] = None

        # Callbacks for different event types
        self._on_position_update: Optional[Callable] = None
        self._on_trade: Optional[Callable] = None
        self._on_liquidation: Optional[Callable] = None
        self._on_all_mids: Optional[Callable] = None
        self._on_orderbook: Optional[Callable] = None

        # Order book cache for absorption analysis
        self._orderbooks: Dict[str, Dict] = {}  # coin -> {bids: [], asks: []}

        # Tracked wallets
        self._tracked_wallets: List[str] = []

        # WebSocket limit - Hyperliquid only allows 10 users per connection
        self._ws_wallet_limit: int = 10
        self._ws_subscribed_wallets: List[str] = []  # Currently subscribed via WS

        # Cache for mid prices
        self._mid_prices: Dict[str, float] = {}

        # Coins to subscribe for real-time trades (for liquidation detection)
        self._trade_coins: List[str] = ["BTC", "ETH", "SOL", "NOT"]

        # Real-time position cache (updated from WebSocket, not database)
        self._positions: Dict[str, Dict] = {}  # wallet -> {coin: position_data}

    async def start(self):
        """Start the client and open session."""
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout)
        )

    async def stop(self):
        """Stop the client and close connections."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()

    # =========================================================================
    # REST API Methods
    # =========================================================================

    async def get_clearinghouse_state(self, wallet_address: str) -> Optional[WalletState]:
        """
        Get clearinghouse state for a wallet.

        API: POST /info {"type": "clearinghouseState", "user": "0x..."}

        Returns:
            WalletState with all positions, or None on error
        """
        try:
            payload = {
                "type": "clearinghouseState",
                "user": wallet_address
            }

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    self._logger.warning(f"clearinghouseState failed: {response.status}")
                    return None

                data = await response.json()
                return self._parse_clearinghouse_state(wallet_address, data)

        except Exception as e:
            self._logger.error(f"clearinghouseState error: {e}")
            return None

    async def get_all_mids(self) -> Dict[str, float]:
        """
        Get all mid prices.

        API: POST /info {"type": "allMids"}

        Returns:
            Dict of coin -> mid price
        """
        try:
            payload = {"type": "allMids"}

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return {}

                data = await response.json()
                mids = {}
                # API returns flat dict {coin: price_str}
                for coin, price_str in data.items():
                    try:
                        mids[coin] = float(price_str)
                    except:
                        pass
                return mids

        except Exception as e:
            self._logger.error(f"allMids error: {e}")
            return {}

    async def get_meta(self) -> Optional[Dict]:
        """
        Get exchange metadata (available coins, etc).

        API: POST /info {"type": "meta"}
        """
        try:
            payload = {"type": "meta"}

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return None
                return await response.json()

        except Exception as e:
            self._logger.error(f"meta error: {e}")
            return None

    async def get_asset_volumes(self) -> Dict[str, float]:
        """
        Get 24h notional volume for all assets.

        API: POST /info {"type": "metaAndAssetCtxs"}

        Returns:
            Dict of coin -> 24h notional volume in USD
        """
        try:
            payload = {"type": "metaAndAssetCtxs"}

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return {}

                data = await response.json()
                volumes = {}

                # Response is [meta, assetCtxs]
                if isinstance(data, list) and len(data) >= 2:
                    meta = data[0]
                    asset_ctxs = data[1]

                    # Get coin names from meta.universe
                    universe = meta.get('universe', [])
                    coin_names = [asset.get('name', '') for asset in universe]

                    # Match with asset contexts
                    for i, ctx in enumerate(asset_ctxs):
                        if i < len(coin_names):
                            coin = coin_names[i]
                            try:
                                volumes[coin] = float(ctx.get('dayNtlVlm', 0))
                            except:
                                pass

                return volumes

        except Exception as e:
            self._logger.error(f"assetVolumes error: {e}")
            return {}

    async def get_recent_trades(self, coin: str) -> List[Dict]:
        """
        Get recent trades for a coin.

        API: POST /info {"type": "recentTrades", "coin": "BTC"}

        Returns list of trades with 'users' field containing wallet addresses.
        """
        try:
            payload = {"type": "recentTrades", "coin": coin}

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return []
                return await response.json()

        except Exception as e:
            self._logger.error(f"recentTrades error: {e}")
            return []

    async def discover_whales_from_trades(
        self,
        coins: List[str] = None,
        min_trade_value: float = 100_000.0
    ) -> List[Dict]:
        """
        Discover whale addresses from recent large trades.

        Args:
            coins: List of coins to check (default: major coins)
            min_trade_value: Minimum USD value to consider whale trade

        Returns:
            List of {address, trade_value, coin, side} for discovered whales
        """
        if coins is None:
            coins = ["BTC", "ETH", "SOL", "HYPE", "XRP", "DOGE"]

        discovered = []
        seen_addresses = set()

        for coin in coins:
            try:
                trades = await self.get_recent_trades(coin)

                for trade in trades:
                    px = float(trade.get('px', 0))
                    sz = float(trade.get('sz', 0))
                    value = px * sz
                    users = trade.get('users', [])
                    side = "BUY" if trade.get('side') == 'B' else "SELL"

                    if value >= min_trade_value:
                        for addr in users:
                            if addr and addr not in seen_addresses:
                                seen_addresses.add(addr)
                                discovered.append({
                                    'address': addr,
                                    'trade_value': value,
                                    'coin': coin,
                                    'side': side
                                })

                await asyncio.sleep(0.05)  # Rate limit

            except Exception as e:
                self._logger.debug(f"Trade discovery error for {coin}: {e}")

        return discovered

    def set_liquidation_callback(self, callback: Callable):
        """Set callback for liquidation events."""
        self._on_liquidation = callback

    def set_trade_callback(self, callback: Callable):
        """Set callback for trade events."""
        self._on_trade = callback

    # =========================================================================
    # WebSocket Methods
    # =========================================================================

    async def run_websocket(self):
        """
        Main WebSocket loop with automatic reconnection.

        Subscribes to:
        - allMids: Real-time price updates
        - webData2: Position updates for tracked wallets
        """
        import websockets

        reconnect_delay = self.config.reconnect_delay

        while self._running:
            try:
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=60,
                    close_timeout=10
                ) as ws:
                    self._ws = ws
                    self._logger.info(f"Connected to Hyperliquid WebSocket: {self._ws_url}")
                    reconnect_delay = self.config.reconnect_delay  # Reset on success

                    # Subscribe to allMids (real-time prices)
                    await self._subscribe_all_mids(ws)

                    # Subscribe to real-time trades (fastest liquidation detection)
                    await self._subscribe_trades(ws, self._trade_coins)

                    # Subscribe to real-time liquidation events (OI changes)
                    await self._subscribe_liquidations(ws)

                    # Subscribe to L2 order books for absorption analysis
                    await self._subscribe_orderbooks(ws)

                    # Subscribe to tracked wallets (limited to 10 by Hyperliquid)
                    # Remaining wallets are polled via REST API
                    self._ws_subscribed_wallets = self._tracked_wallets[:self._ws_wallet_limit]
                    for wallet in self._ws_subscribed_wallets:
                        await self._subscribe_wallet(ws, wallet)

                    if len(self._tracked_wallets) > self._ws_wallet_limit:
                        self._logger.info(
                            f"WebSocket tracking {len(self._ws_subscribed_wallets)} wallets "
                            f"(limit: {self._ws_wallet_limit}), "
                            f"{len(self._tracked_wallets) - self._ws_wallet_limit} via REST polling"
                        )

                    # Message loop
                    async for message in ws:
                        await self._handle_message(message)

            except Exception as e:
                self._logger.warning(f"WebSocket error: {e}, reconnecting in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.config.max_reconnect_delay)

    async def _subscribe_all_mids(self, ws):
        """Subscribe to all mid prices."""
        subscription = {
            "method": "subscribe",
            "subscription": {"type": "allMids"}
        }
        await ws.send(json.dumps(subscription))
        self._logger.debug("Subscribed to allMids")

    async def _subscribe_liquidations(self, ws):
        """Subscribe to activeAssetCtx for major coins to get real-time context updates.

        activeAssetCtx provides: mark price, open interest, funding rate, volume.
        Changes in open interest indicate liquidations occurred.
        """
        # Major coins to track for liquidation cascade detection
        major_coins = ["BTC", "ETH", "SOL", "DOGE", "XRP", "AVAX", "LINK", "ARB", "OP", "SUI"]

        for coin in major_coins:
            subscription = {
                "method": "subscribe",
                "subscription": {"type": "activeAssetCtx", "coin": coin}
            }
            await ws.send(json.dumps(subscription))

        self._logger.info(f"Subscribed to activeAssetCtx for {len(major_coins)} coins")

    async def _subscribe_orderbooks(self, ws):
        """Subscribe to L2 order books for major coins.

        L2 book provides bid/ask depth for absorption analysis:
        - Thin book at liquidation level = cascade continues
        - Thick book = cascade absorbed, reversal likely
        """
        # Subscribe to books for all major coins (matches activeAssetCtx)
        orderbook_coins = ["BTC", "ETH", "SOL", "DOGE", "XRP", "AVAX", "LINK", "ARB", "OP", "SUI"]

        for coin in orderbook_coins:
            subscription = {
                "method": "subscribe",
                "subscription": {"type": "l2Book", "coin": coin}
            }
            await ws.send(json.dumps(subscription))

        self._logger.info(f"Subscribed to l2Book for {len(orderbook_coins)} coins")

    async def _subscribe_trades(self, ws, coins: List[str] = None):
        """Subscribe to real-time trades for specified coins.

        This is the FASTEST way to detect liquidations - trades appear instantly.
        """
        if coins is None:
            coins = ["BTC", "ETH", "SOL", "DOGE", "XRP", "NOT"]  # Default coins

        for coin in coins:
            subscription = {
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": coin}
            }
            await ws.send(json.dumps(subscription))

        self._logger.info(f"Subscribed to trades for {len(coins)} coins (real-time)")

    async def subscribe_to_trades(self, coin: str):
        """Dynamically subscribe to trades for a specific coin."""
        if self._ws:
            subscription = {
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": coin}
            }
            await self._ws.send(json.dumps(subscription))
            self._logger.info(f"Subscribed to trades for {coin}")

    async def subscribe_to_user_events(self, wallet_address: str):
        """Subscribe to user events (includes liquidation events) for a wallet.

        WsUserEvent includes: fills, funding, liquidation, nonUserCancel
        Liquidation events contain: liquidator, liquidated_user, liquidated_ntl_pos
        """
        if self._ws:
            subscription = {
                "method": "subscribe",
                "subscription": {"type": "userEvents", "user": wallet_address}
            }
            await self._ws.send(json.dumps(subscription))
            self._logger.info(f"Subscribed to userEvents for {wallet_address[:10]}...")

    async def _subscribe_wallet(self, ws, wallet_address: str):
        """Subscribe to position updates for a wallet."""
        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "webData2",
                "user": wallet_address
            }
        }
        await ws.send(json.dumps(subscription))
        self._logger.debug(f"Subscribed to webData2 for {wallet_address[:10]}...")

    async def _handle_message(self, message: str):
        """Parse and route incoming WebSocket message."""
        try:
            data = json.loads(message)
            channel = data.get('channel')

            if channel == 'allMids':
                await self._handle_all_mids(data.get('data', {}))
            elif channel == 'webData2':
                await self._handle_web_data(data.get('data', {}))
            elif channel == 'activeAssetCtx':
                await self._handle_liquidation(data.get('data', {}))
            elif channel == 'l2Book':
                await self._handle_orderbook(data.get('data', {}))
            elif channel == 'trades':
                await self._handle_trades(data.get('data', []))
            elif channel == 'userEvents':
                await self._handle_user_events(data.get('data', {}))
            elif channel == 'subscriptionResponse':
                self._logger.debug(f"Subscription confirmed: {data.get('data', {})}")
            elif channel == 'error':
                self._logger.error(f"WebSocket error: {data}")

        except json.JSONDecodeError:
            self._logger.warning(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            self._logger.error(f"Message handling error: {e}")

    async def _handle_all_mids(self, data: Dict):
        """Handle allMids update."""
        mids = data.get('mids', {})
        for coin, price_str in mids.items():
            try:
                self._mid_prices[coin] = float(price_str)
            except:
                pass

        if self._on_all_mids:
            await self._on_all_mids(self._mid_prices)

    async def _handle_web_data(self, data: Dict):
        """Handle webData2 (position updates) for a wallet.

        Updates real-time position cache and triggers callbacks.
        """
        # webData2 contains clearinghouseState in real-time
        user = data.get('user')
        if not user:
            return

        clearinghouse = data.get('clearinghouseState')
        if clearinghouse:
            # Update real-time position cache
            positions = {}
            for asset in clearinghouse.get('assetPositions', []):
                pos = asset.get('position', {})
                coin = pos.get('coin', '')
                szi = float(pos.get('szi', 0))

                if abs(szi) > 0 and coin:
                    current_price = self._mid_prices.get(coin, 0)
                    entry_price = float(pos.get('entryPx', 0))
                    liq_price = float(pos.get('liquidationPx', 0)) if pos.get('liquidationPx') else 0
                    side = 'LONG' if szi > 0 else 'SHORT'

                    # Calculate distance to liquidation
                    distance_pct = 999.0
                    if current_price > 0 and liq_price > 0:
                        if side == 'LONG':
                            distance_pct = ((current_price - liq_price) / current_price) * 100
                        else:
                            distance_pct = ((liq_price - current_price) / current_price) * 100

                    positions[coin] = {
                        'coin': coin,
                        'side': side,
                        'size': abs(szi),
                        'entry_price': entry_price,
                        'liquidation_price': liq_price,
                        'current_price': current_price,
                        'distance_to_liq_pct': distance_pct,
                        'position_value': float(pos.get('positionValue', 0)),
                        'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                        'timestamp': time.time()
                    }

            # Store in cache
            self._positions[user] = positions

            # Detect position closures (liquidations)
            prev_positions = getattr(self, '_prev_positions_ws', {}).get(user, {})
            for coin in prev_positions:
                if coin not in positions:
                    self._logger.warning(
                        f"[WS_POSITION_CLOSED] {user[:10]}... {coin} position CLOSED!"
                    )

            # Store for next comparison
            if not hasattr(self, '_prev_positions_ws'):
                self._prev_positions_ws = {}
            self._prev_positions_ws[user] = positions.copy()

            # Call position update callback
            wallet_state = self._parse_clearinghouse_state(user, clearinghouse)
            if wallet_state and self._on_position_update:
                await self._on_position_update(wallet_state)

    async def _handle_liquidation(self, data: Dict):
        """Handle activeAssetCtx (real-time asset context updates).

        Detects liquidations by tracking open interest changes:
        - OI drop = positions liquidated (longs or shorts closed)
        - Large OI drops signal cascade events
        """
        import time

        # Initialize OI tracking if not present
        if not hasattr(self, '_prev_open_interest'):
            self._prev_open_interest = {}

        # Parse the activeAssetCtx data
        ctx = data.get('ctx', data)
        if not ctx:
            return

        coin = ctx.get('coin', data.get('coin'))
        if not coin:
            return

        # Extract current values
        try:
            current_oi = float(ctx.get('openInterest', 0))
            mark_price = float(ctx.get('markPx', 0)) if ctx.get('markPx') else None
            funding = ctx.get('funding')
            volume = ctx.get('dayNtlVlm')
        except (ValueError, TypeError):
            return

        # Calculate OI change (negative = liquidations)
        prev_oi = self._prev_open_interest.get(coin, current_oi)
        oi_change = current_oi - prev_oi
        oi_change_pct = (oi_change / prev_oi * 100) if prev_oi > 0 else 0
        self._prev_open_interest[coin] = current_oi

        # Build event structure
        event = {
            'timestamp': time.time(),
            'coin': coin,
            'mark_price': mark_price,
            'open_interest': current_oi,
            'oi_change': oi_change,
            'oi_change_pct': oi_change_pct,
            'funding_rate': funding,
            'day_volume': volume,
            'is_liquidation_signal': oi_change < 0 and abs(oi_change_pct) > 0.1
        }

        # Log significant OI drops (likely liquidation cascade)
        if event['is_liquidation_signal'] and abs(oi_change_pct) > 0.5:
            self._logger.warning(
                f"[CASCADE_SIGNAL] {coin}: OI dropped {oi_change_pct:.2f}% "
                f"(${abs(oi_change):,.0f}) @ {mark_price}"
            )

        # Call the callback if set
        if self._on_liquidation:
            try:
                await self._on_liquidation(event)
            except Exception as e:
                self._logger.error(f"Liquidation callback error: {e}")

    async def _handle_orderbook(self, data: Dict):
        """Handle L2 order book update.

        Parses bid/ask levels and computes absorption metrics:
        - Depth at each price level (cumulative $ value)
        - Thin/thick detection for cascade analysis
        """
        import time

        coin = data.get('coin')
        if not coin:
            return

        levels = data.get('levels', [[], []])
        if len(levels) < 2:
            return

        bids = levels[0]  # [[price, size, numOrders], ...]
        asks = levels[1]

        # Parse and compute depth
        parsed_bids = []
        parsed_asks = []
        cumulative_bid = 0.0
        cumulative_ask = 0.0

        # Get current mid price for $ value calculation
        mid_price = self._mid_prices.get(coin, 0)
        if mid_price == 0 and bids and asks:
            try:
                # l2Book format: {"px": "price", "sz": "size", "n": numOrders}
                mid_price = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
            except (ValueError, KeyError, IndexError):
                pass

        # Process bids (buy orders - support below)
        for level in bids[:20]:  # Top 20 levels
            try:
                # l2Book format: {"px": "price", "sz": "size", "n": numOrders}
                price = float(level["px"])
                size = float(level["sz"])
                value = size * price
                cumulative_bid += value
                pct_from_mid = ((price / mid_price) - 1) * 100 if mid_price > 0 else 0
                parsed_bids.append({
                    'price': price,
                    'size': size,
                    'value': value,
                    'cumulative': cumulative_bid,
                    'pct_from_mid': pct_from_mid
                })
            except (ValueError, KeyError, IndexError):
                continue

        # Process asks (sell orders - resistance above)
        for level in asks[:20]:  # Top 20 levels
            try:
                # l2Book format: {"px": "price", "sz": "size", "n": numOrders}
                price = float(level["px"])
                size = float(level["sz"])
                value = size * price
                cumulative_ask += value
                pct_from_mid = ((price / mid_price) - 1) * 100 if mid_price > 0 else 0
                parsed_asks.append({
                    'price': price,
                    'size': size,
                    'value': value,
                    'cumulative': cumulative_ask,
                    'pct_from_mid': pct_from_mid
                })
            except (ValueError, KeyError, IndexError):
                continue

        # Store parsed orderbook
        # Compute spread using l2Book format
        spread_pct = 0.0
        if bids and asks and mid_price > 0:
            try:
                spread_pct = ((float(asks[0]["px"]) - float(bids[0]["px"])) / mid_price * 100)
            except (ValueError, KeyError, IndexError):
                pass

        self._orderbooks[coin] = {
            'timestamp': time.time(),
            'coin': coin,
            'mid_price': mid_price,
            'bids': parsed_bids,
            'asks': parsed_asks,
            'total_bid_depth': cumulative_bid,
            'total_ask_depth': cumulative_ask,
            'spread_pct': spread_pct
        }

        # Call callback if set
        if self._on_orderbook:
            try:
                await self._on_orderbook(self._orderbooks[coin])
            except Exception as e:
                self._logger.error(f"Orderbook callback error: {e}")

    async def _handle_trades(self, data: List[Dict]):
        """Handle real-time trades stream.

        Trades data format:
        [{
            "coin": "SOL",
            "side": "B" or "A",  # B=Buy, A=Sell
            "px": "150.50",
            "sz": "10.5",
            "time": 1699999999999,
            "hash": "0x...",
            "users": ["0x...", "0x..."]  # [maker, taker]
        }]

        For liquidation detection:
        - Large sell trades at support = long liquidations
        - Large buy trades at resistance = short liquidations
        - Check if trade involves tracked wallets
        """
        if not data:
            return

        for trade in data:
            coin = trade.get('coin', '')
            side = trade.get('side', '')
            px = float(trade.get('px', 0))
            sz = float(trade.get('sz', 0))
            value = px * sz
            users = trade.get('users', [])
            trade_time = trade.get('time', time.time() * 1000)

            # Build trade event
            trade_event = {
                'timestamp': trade_time / 1000,  # Convert ms to seconds
                'coin': coin,
                'side': 'BUY' if side == 'B' else 'SELL',
                'price': px,
                'size': sz,
                'value': value,
                'users': users,
                'hash': trade.get('hash', '')
            }

            # Check if trade involves a tracked wallet (potential liquidation)
            for wallet in self._tracked_wallets:
                if any(wallet.lower() == u.lower() for u in users):
                    trade_event['involves_tracked'] = True
                    trade_event['tracked_wallet'] = wallet
                    self._logger.warning(
                        f"[TRADE] Tracked wallet trade: {coin} {trade_event['side']} "
                        f"{sz} @ ${px:,.2f} (${value:,.0f})"
                    )
                    break

            # Call trade callback if set
            if self._on_trade:
                try:
                    await self._on_trade(trade_event)
                except Exception as e:
                    self._logger.error(f"Trade callback error: {e}")

    async def _handle_user_events(self, data: Dict):
        """Handle user events including liquidations.

        WsUserEvent types:
        - {"fills": [WsFill]}
        - {"funding": WsUserFunding}
        - {"liquidation": WsLiquidation}
        - {"nonUserCancel": [WsNonUserCancel]}

        WsLiquidation contains:
        - lid: liquidation ID
        - liquidator: executor address
        - liquidated_user: affected user
        - liquidated_ntl_pos: position notional value
        - liquidated_account_value: remaining account value
        """
        user = data.get('user', '')

        # Check for liquidation event
        if 'liquidation' in data:
            liq_data = data['liquidation']
            liq_event = {
                'type': 'LIQUIDATION',
                'timestamp': time.time(),
                'user': user,
                'liquidation_id': liq_data.get('lid'),
                'liquidator': liq_data.get('liquidator'),
                'liquidated_user': liq_data.get('liquidated_user', user),
                'notional_value': float(liq_data.get('liquidated_ntl_pos', 0)),
                'account_value': float(liq_data.get('liquidated_account_value', 0)),
                'positions': liq_data.get('liquidatedPositions', [])
            }

            self._logger.warning(
                f"[LIQUIDATION] User {user[:10]}... liquidated! "
                f"Value: ${liq_event['notional_value']:,.0f} "
                f"Liquidator: {liq_event['liquidator'][:10] if liq_event['liquidator'] else 'N/A'}..."
            )

            # Call liquidation callback
            if self._on_liquidation:
                try:
                    await self._on_liquidation(liq_event)
                except Exception as e:
                    self._logger.error(f"Liquidation callback error: {e}")

        # Check for fills (could indicate position reduction/closure)
        if 'fills' in data:
            fills = data['fills']
            for fill in fills:
                fill_event = {
                    'type': 'FILL',
                    'timestamp': time.time(),
                    'user': user,
                    'coin': fill.get('coin'),
                    'side': fill.get('side'),
                    'px': float(fill.get('px', 0)),
                    'sz': float(fill.get('sz', 0)),
                    'crossed': fill.get('crossed', False),  # Market order crossed spread
                    'fee': float(fill.get('fee', 0))
                }

                # Crossed orders at high speed often indicate liquidation
                if fill_event['crossed']:
                    self._logger.info(
                        f"[FILL] {user[:10]}... crossed fill: {fill_event['coin']} "
                        f"{fill_event['side']} {fill_event['sz']} @ ${fill_event['px']:,.2f}"
                    )

    def get_orderbook(self, coin: str) -> Optional[Dict]:
        """Get cached orderbook for a coin."""
        return self._orderbooks.get(coin)

    def get_depth_at_level(self, coin: str, pct_from_mid: float) -> Dict:
        """Get cumulative depth at a specific % distance from mid price.

        Args:
            coin: Asset symbol
            pct_from_mid: Percentage from mid (negative = bids, positive = asks)

        Returns:
            Dict with bid_depth and ask_depth at that level
        """
        book = self._orderbooks.get(coin)
        if not book:
            return {'bid_depth': 0, 'ask_depth': 0}

        bid_depth = 0
        ask_depth = 0

        # Find cumulative depth at the level
        for bid in book['bids']:
            if bid['pct_from_mid'] >= pct_from_mid:
                bid_depth = bid['cumulative']

        for ask in book['asks']:
            if ask['pct_from_mid'] <= abs(pct_from_mid):
                ask_depth = ask['cumulative']
            else:
                break

        return {'bid_depth': bid_depth, 'ask_depth': ask_depth}

    # =========================================================================
    # Wallet Tracking
    # =========================================================================

    def add_tracked_wallet(self, wallet_address: str):
        """Add a wallet to track for position updates.

        Note: Hyperliquid WebSocket limits to 10 users per connection.
        First 10 wallets get real-time WebSocket updates.
        Additional wallets are tracked via REST API polling.
        """
        if wallet_address not in self._tracked_wallets:
            self._tracked_wallets.append(wallet_address)
            mode = "WS" if len(self._tracked_wallets) <= self._ws_wallet_limit else "REST"
            self._logger.info(f"Tracking wallet: {wallet_address[:10]}... ({mode})")

    def remove_tracked_wallet(self, wallet_address: str):
        """Remove a wallet from tracking."""
        if wallet_address in self._tracked_wallets:
            self._tracked_wallets.remove(wallet_address)

    def set_position_callback(self, callback: Callable):
        """Set callback for position updates."""
        self._on_position_update = callback

    def set_mids_callback(self, callback: Callable):
        """Set callback for mid price updates."""
        self._on_all_mids = callback

    def set_orderbook_callback(self, callback: Callable):
        """Set callback for orderbook updates."""
        self._on_orderbook = callback

    def set_trade_callback(self, callback: Callable):
        """Set callback for real-time trade events."""
        self._on_trade = callback

    def set_trade_coins(self, coins: List[str]):
        """Set coins to subscribe for real-time trades."""
        self._trade_coins = coins

    def add_trade_coin(self, coin: str):
        """Add a coin to real-time trade subscription."""
        if coin not in self._trade_coins:
            self._trade_coins.append(coin)
            # If WebSocket is connected, subscribe immediately
            if self._ws:
                asyncio.create_task(self.subscribe_to_trades(coin))

    def get_mid_price(self, coin: str) -> Optional[float]:
        """Get cached mid price for a coin."""
        return self._mid_prices.get(coin)

    def get_all_mid_prices(self) -> Dict[str, float]:
        """Get all cached mid prices (real-time from WebSocket)."""
        return self._mid_prices.copy()

    def get_cached_position(self, wallet: str, coin: str) -> Optional[Dict]:
        """Get real-time cached position from WebSocket updates."""
        wallet_positions = self._positions.get(wallet, {})
        return wallet_positions.get(coin)

    def get_all_cached_positions(self) -> Dict[str, Dict]:
        """Get all real-time cached positions."""
        return self._positions.copy()

    # =========================================================================
    # Parsing Helpers
    # =========================================================================

    def _parse_clearinghouse_state(self, wallet_address: str, data: Dict) -> Optional[WalletState]:
        """
        Parse clearinghouseState response into WalletState.

        Response structure:
        {
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "entryPx": "43250.0",
                        "liquidationPx": "41000.0",
                        "leverage": {"type": "isolated", "value": 10},
                        "marginUsed": "2162.5",
                        "positionValue": "21625.0",
                        "szi": "0.5",  # Signed size
                        "unrealizedPnl": "100.0"
                    }
                }
            ],
            "crossMarginSummary": {
                "accountValue": "50000.0",
                "totalMarginUsed": "5000.0"
            },
            "withdrawable": "45000.0"
        }
        """
        # Safe float conversion (handles None values)
        def safe_float(val, default=0.0):
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        try:
            positions = {}
            timestamp = time.time()

            for asset in data.get('assetPositions', []):
                pos = asset.get('position', {})
                if not pos:
                    continue

                coin = pos.get('coin', '')
                if not coin:
                    continue

                # Parse leverage (can be dict or float or None)
                leverage_data = pos.get('leverage')
                if leverage_data is None:
                    leverage = 1.0
                elif isinstance(leverage_data, dict):
                    leverage = float(leverage_data.get('value') or 1)
                else:
                    leverage = float(leverage_data) if leverage_data else 1.0

                position = HyperliquidPosition(
                    wallet_address=wallet_address,
                    coin=coin,
                    entry_price=safe_float(pos.get('entryPx')),
                    position_size=safe_float(pos.get('szi')),  # Signed
                    leverage=leverage,
                    liquidation_price=safe_float(pos.get('liquidationPx')),
                    margin_used=safe_float(pos.get('marginUsed')),
                    unrealized_pnl=safe_float(pos.get('unrealizedPnl')),
                    position_value=safe_float(pos.get('positionValue')),
                    timestamp=timestamp,
                    raw_position=pos  # HLP24: Store raw API response
                )

                # Only include non-zero positions
                if position.abs_size > 0:
                    positions[coin] = position

            # Parse account summary
            margin_summary = data.get('crossMarginSummary') or {}

            return WalletState(
                address=wallet_address,
                positions=positions,
                account_value=safe_float(margin_summary.get('accountValue')),
                total_margin_used=safe_float(margin_summary.get('totalMarginUsed')),
                withdrawable=safe_float(data.get('withdrawable')),
                last_updated=timestamp,
                raw_summary=margin_summary  # HLP24: Store raw API response
            )

        except Exception as e:
            self._logger.error(f"Parse clearinghouseState error: {e}")
            return None

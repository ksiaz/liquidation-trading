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

        # Tracked wallets
        self._tracked_wallets: List[str] = []

        # WebSocket limit - Hyperliquid only allows 10 users per connection
        self._ws_wallet_limit: int = 10
        self._ws_subscribed_wallets: List[str] = []  # Currently subscribed via WS

        # Cache for mid prices
        self._mid_prices: Dict[str, float] = {}

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

                    # Subscribe to allMids
                    await self._subscribe_all_mids(ws)

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
        """Subscribe to liquidation feed."""
        subscription = {
            "method": "subscribe",
            "subscription": {"type": "activeAssetCtx"}
        }
        await ws.send(json.dumps(subscription))
        self._logger.debug("Subscribed to liquidations")

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
        """Handle webData2 (position updates) for a wallet."""
        # webData2 contains clearinghouseState in real-time
        user = data.get('user')
        if not user:
            return

        clearinghouse = data.get('clearinghouseState')
        if clearinghouse:
            wallet_state = self._parse_clearinghouse_state(user, clearinghouse)
            if wallet_state and self._on_position_update:
                await self._on_position_update(wallet_state)

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

    def get_mid_price(self, coin: str) -> Optional[float]:
        """Get cached mid price for a coin."""
        return self._mid_prices.get(coin)

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
                    timestamp=timestamp
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
                last_updated=timestamp
            )

        except Exception as e:
            self._logger.error(f"Parse clearinghouseState error: {e}")
            return None

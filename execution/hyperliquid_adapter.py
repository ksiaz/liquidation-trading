"""
EP-4 Hyperliquid Exchange Adapter - Real Implementation

Replaces MockedExchangeAdapter with actual Hyperliquid API calls.

Features:
- Dynamic asset metadata fetching (indices, tick sizes, step sizes)
- Proper price/size formatting using exchange precision
- EIP-712 wallet signing for order submission
- Exponential backoff retry logic

Authority: EP-4 Execution Policy Specification
"""

import time
import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Literal, Tuple
from enum import Enum
from threading import Lock
import aiohttp

# Optional SDK import (for reference - we implement directly for control)
try:
    from eth_account import Account
    HAS_ETH_ACCOUNT = True
except ImportError:
    HAS_ETH_ACCOUNT = False
    Account = None


# ==============================================================================
# Exchange Configuration
# ==============================================================================

@dataclass(frozen=True)
class ExchangeConstraints:
    """
    Exchange-specific mechanical constraints.
    Cannot imply: strategy, optimization, interpretation.
    """
    min_order_size: float
    max_order_size: float
    step_size: float  # Quantity increment (derived from szDecimals)
    tick_size: float  # Price increment
    max_leverage: float
    margin_mode: Literal["CROSS", "ISOLATED"]


@dataclass
class AssetMetadata:
    """Metadata for a single asset from exchange."""
    name: str
    index: int
    sz_decimals: int  # Size decimals
    max_leverage: int
    only_isolated: bool

    @property
    def step_size(self) -> float:
        """Calculate step size from sz_decimals."""
        return 10 ** (-self.sz_decimals)


# ==============================================================================
# Exchange Response Types
# ==============================================================================

class ExchangeResponseCode(Enum):
    """Exchange response codes."""
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ExchangeResponse:
    """
    Opaque exchange response.
    No interpretation allowed.
    """
    response_code: ExchangeResponseCode
    order_id: Optional[str]
    message: str
    timestamp: float


# ==============================================================================
# Hyperliquid Exchange Adapter
# ==============================================================================

class HyperliquidExchangeAdapter:
    """
    Real Hyperliquid exchange adapter.

    On initialization:
    1. Fetches asset metadata from exchange
    2. Builds asset index mapping
    3. Caches tick/step sizes for formatting

    On order execution:
    1. Validates constraints using real exchange metadata
    2. Formats price/size to exchange precision
    3. Submits order via REST API
    4. Returns structured response
    """

    # API Endpoints
    MAINNET_API_URL = "https://api.hyperliquid.xyz"
    TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        use_testnet: bool = False,
        logger: Optional[logging.Logger] = None,
        # Retry settings
        max_retries: int = 3,
        retry_base_delay_ms: int = 100,
        retry_max_delay_ms: int = 2000,
        retry_backoff_factor: float = 2.0,
        request_timeout: float = 10.0,
    ):
        """
        Initialize Hyperliquid adapter.

        Args:
            private_key: EVM private key for signing (hex string with 0x prefix)
            wallet_address: Wallet address for vault operations
            use_testnet: Use testnet instead of mainnet
            logger: Logger instance
            max_retries: Maximum retry attempts
            retry_base_delay_ms: Initial retry delay
            retry_max_delay_ms: Maximum retry delay
            retry_backoff_factor: Exponential backoff factor
            request_timeout: HTTP request timeout in seconds
        """
        self._private_key = private_key
        self._wallet_address = wallet_address
        self._use_testnet = use_testnet
        self._logger = logger or logging.getLogger(__name__)

        # API endpoint
        self._api_url = self.TESTNET_API_URL if use_testnet else self.MAINNET_API_URL

        # Retry settings
        self._max_retries = max_retries
        self._retry_base_delay_ms = retry_base_delay_ms
        self._retry_max_delay_ms = retry_max_delay_ms
        self._retry_backoff_factor = retry_backoff_factor
        self._request_timeout = request_timeout

        # Asset metadata (populated on init)
        self._assets: Dict[str, AssetMetadata] = {}  # name -> metadata
        self._asset_by_index: Dict[int, AssetMetadata] = {}  # index -> metadata
        self._metadata_loaded = False
        self._metadata_lock = Lock()

        # Call counter
        self._call_count = 0

        # HTTP session (created on first use)
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self) -> bool:
        """
        Initialize adapter by fetching exchange metadata.

        Must be called before executing orders.

        Returns:
            True if initialization succeeded
        """
        try:
            await self._fetch_metadata()
            self._logger.info(
                f"HyperliquidExchangeAdapter initialized: "
                f"{len(self._assets)} assets loaded from "
                f"{'testnet' if self._use_testnet else 'mainnet'}"
            )
            return True
        except Exception as e:
            self._logger.error(f"Failed to initialize adapter: {e}")
            return False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._request_timeout)
            )
        return self._session

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_metadata(self):
        """Fetch asset metadata from exchange."""
        session = await self._get_session()

        async with session.post(
            f"{self._api_url}/info",
            json={"type": "meta"},
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"Failed to fetch metadata: HTTP {response.status}")

            data = await response.json()

        # Parse universe
        universe = data.get("universe", [])
        if not universe:
            raise RuntimeError("Empty universe in metadata response")

        with self._metadata_lock:
            self._assets.clear()
            self._asset_by_index.clear()

            for idx, asset in enumerate(universe):
                name = asset.get("name", "")
                if not name:
                    continue

                metadata = AssetMetadata(
                    name=name,
                    index=idx,
                    sz_decimals=int(asset.get("szDecimals", 0)),
                    max_leverage=int(asset.get("maxLeverage", 50)),
                    only_isolated=bool(asset.get("onlyIsolated", False))
                )

                self._assets[name] = metadata
                self._asset_by_index[idx] = metadata

            self._metadata_loaded = True

    def get_asset_index(self, symbol: str) -> int:
        """
        Get asset index for symbol.

        Args:
            symbol: Asset symbol (e.g., "BTC", "ETH")

        Returns:
            Asset index for Hyperliquid API

        Raises:
            ValueError: If symbol not found
        """
        with self._metadata_lock:
            if symbol in self._assets:
                return self._assets[symbol].index
        raise ValueError(f"Unknown asset: {symbol}")

    def get_asset_metadata(self, symbol: str) -> Optional[AssetMetadata]:
        """Get metadata for an asset."""
        with self._metadata_lock:
            return self._assets.get(symbol)

    def format_size(self, symbol: str, size: float) -> str:
        """
        Format size for exchange submission.

        Uses sz_decimals from exchange metadata for precision.

        Args:
            symbol: Asset symbol
            size: Raw size value

        Returns:
            Formatted size string
        """
        with self._metadata_lock:
            metadata = self._assets.get(symbol)

        if metadata is None:
            # Fallback: use 4 decimals
            return f"{size:.4f}"

        # Round to step size
        step = metadata.step_size
        rounded = round(size / step) * step

        # Format with exact decimals
        return f"{rounded:.{metadata.sz_decimals}f}"

    def format_price(self, symbol: str, price: float) -> str:
        """
        Format price for exchange submission.

        Hyperliquid uses 5 significant figures for prices.

        Args:
            symbol: Asset symbol
            price: Raw price value

        Returns:
            Formatted price string
        """
        if price == 0:
            return "0"

        # Hyperliquid uses 5 significant figures
        # Determine number of decimal places needed
        if price >= 10000:
            # e.g., 95000 -> "95000"
            return f"{price:.0f}"
        elif price >= 1000:
            # e.g., 9500.5 -> "9500.5"
            return f"{price:.1f}"
        elif price >= 100:
            # e.g., 950.55 -> "950.55"
            return f"{price:.2f}"
        elif price >= 10:
            # e.g., 95.555 -> "95.555"
            return f"{price:.3f}"
        elif price >= 1:
            # e.g., 9.5555 -> "9.5555"
            return f"{price:.4f}"
        elif price >= 0.1:
            # e.g., 0.95555 -> "0.95555"
            return f"{price:.5f}"
        else:
            # Small prices: use 6 decimals
            return f"{price:.6f}"

    def get_constraints(self, symbol: str) -> ExchangeConstraints:
        """
        Get exchange constraints for a symbol.

        Args:
            symbol: Asset symbol

        Returns:
            ExchangeConstraints with tick/step sizes
        """
        with self._metadata_lock:
            metadata = self._assets.get(symbol)

        if metadata is None:
            # Fallback constraints
            return ExchangeConstraints(
                min_order_size=0.0001,
                max_order_size=1_000_000,
                step_size=0.0001,
                tick_size=0.01,
                max_leverage=50,
                margin_mode="CROSS"
            )

        return ExchangeConstraints(
            min_order_size=metadata.step_size,
            max_order_size=1_000_000,  # Exchange-specific per asset
            step_size=metadata.step_size,
            tick_size=0.01,  # Hyperliquid uses 5 sig figs
            max_leverage=metadata.max_leverage,
            margin_mode="ISOLATED" if metadata.only_isolated else "CROSS"
        )

    def validate_order(
        self,
        *,
        symbol: str,
        size: float,
        price: Optional[float] = None
    ) -> Optional[str]:
        """
        Validate order against exchange constraints.

        Args:
            symbol: Asset symbol
            size: Order size
            price: Order price (optional for market orders)

        Returns:
            Error message if invalid, None if valid
        """
        with self._metadata_lock:
            metadata = self._assets.get(symbol)

        if metadata is None:
            return f"Unknown asset: {symbol}"

        # Validate size
        step = metadata.step_size
        if size < step:
            return f"Size {size} below minimum {step}"

        # Check step size alignment
        steps = size / step
        if abs(steps - round(steps)) > 1e-8:
            return f"Size {size} not aligned to step {step}"

        return None

    async def execute_order(
        self,
        *,
        action_id: str,
        order_params: dict,
        timestamp: float
    ) -> ExchangeResponse:
        """
        Execute order on Hyperliquid.

        Args:
            action_id: Action identifier for tracking
            order_params: Order parameters with keys:
                - symbol: Asset symbol
                - side: "BUY" or "SELL"
                - size: Order size
                - order_type: "MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"
                - price: Limit price (optional)
                - stop_price: Stop trigger price (optional)
                - reduce_only: Whether this is a reduce-only order
            timestamp: Execution timestamp

        Returns:
            ExchangeResponse with status and order_id
        """
        self._call_count += 1

        # Validate metadata loaded
        if not self._metadata_loaded:
            await self.initialize()

        symbol = order_params.get("symbol", "")

        # Validate order
        validation_error = self.validate_order(
            symbol=symbol,
            size=order_params.get("size", 0),
            price=order_params.get("price")
        )
        if validation_error:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.REJECTED,
                order_id=None,
                message=f"Validation failed: {validation_error}",
                timestamp=timestamp
            )

        # Build order payload
        try:
            payload = self._build_order_payload(order_params)
        except Exception as e:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.REJECTED,
                order_id=None,
                message=f"Failed to build payload: {e}",
                timestamp=timestamp
            )

        # Sign payload if private key available
        if self._private_key:
            payload = self._sign_payload(payload)

        # Submit with retry
        return await self._submit_with_retry(payload, action_id, timestamp)

    def _build_order_payload(self, order_params: dict) -> dict:
        """Build Hyperliquid order payload."""
        symbol = order_params["symbol"]
        side = order_params.get("side", "BUY")
        size = order_params.get("size", 0)
        order_type = order_params.get("order_type", "MARKET")
        price = order_params.get("price")
        stop_price = order_params.get("stop_price")
        reduce_only = order_params.get("reduce_only", False)

        # Get asset index
        asset_idx = self.get_asset_index(symbol)

        # Format size
        size_str = self.format_size(symbol, size)

        # Determine order type structure
        if order_type == "MARKET":
            order_type_struct = {"limit": {"tif": "Ioc"}}
            # For market orders, use expected price
            expected_price = order_params.get("expected_price", price or 0)
            price_str = self.format_price(symbol, expected_price) if expected_price else "0"
        elif order_type == "LIMIT":
            order_type_struct = {"limit": {"tif": "Gtc"}}
            price_str = self.format_price(symbol, price) if price else "0"
        elif order_type == "POST_ONLY":
            order_type_struct = {"limit": {"tif": "Alo"}}
            price_str = self.format_price(symbol, price) if price else "0"
        elif order_type == "IOC":
            order_type_struct = {"limit": {"tif": "Ioc"}}
            price_str = self.format_price(symbol, price) if price else "0"
        elif order_type in ("STOP_MARKET", "STOP_LIMIT"):
            # Determine if TP or SL
            expected_price = order_params.get("expected_price", 0)
            is_tp = (
                (side == "SELL" and stop_price > expected_price) or
                (side == "BUY" and stop_price < expected_price)
            ) if expected_price else False

            if order_type == "STOP_MARKET":
                order_type_struct = {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": self.format_price(symbol, stop_price),
                        "tpsl": "tp" if is_tp else "sl"
                    }
                }
                price_str = self.format_price(symbol, stop_price)
            else:
                order_type_struct = {
                    "trigger": {
                        "isMarket": False,
                        "triggerPx": self.format_price(symbol, stop_price),
                        "limitPx": self.format_price(symbol, price),
                        "tpsl": "tp" if is_tp else "sl"
                    }
                }
                price_str = self.format_price(symbol, price) if price else "0"
        else:
            order_type_struct = {"limit": {"tif": "Gtc"}}
            price_str = self.format_price(symbol, price) if price else "0"

        # Build order
        order = {
            "a": asset_idx,
            "b": side == "BUY",
            "p": price_str,
            "s": size_str,
            "r": reduce_only,
            "t": order_type_struct,
        }

        # Build action
        action = {
            "type": "order",
            "orders": [order],
            "grouping": "na"
        }

        # Build payload
        nonce = int(time.time() * 1000)
        payload = {
            "action": action,
            "nonce": nonce,
        }

        return payload

    def _sign_payload(self, payload: dict) -> dict:
        """Sign payload with EIP-712."""
        if not HAS_ETH_ACCOUNT:
            self._logger.warning(
                "eth_account not installed - orders will be rejected. "
                "Install with: pip install eth-account"
            )
            return payload

        if not self._private_key:
            self._logger.warning("No private key configured - orders will be rejected")
            return payload

        try:
            import json

            # Hyperliquid EIP-712 domain
            domain = {
                "name": "Exchange",
                "version": "1",
                "chainId": 42161,  # Arbitrum
                "verifyingContract": "0x0000000000000000000000000000000000000000"
            }

            action = payload.get("action", {})
            nonce = payload.get("nonce", int(time.time() * 1000))

            # Create message for signing
            message = {
                "action": json.dumps(action, separators=(',', ':')),
                "nonce": nonce
            }

            types = {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                "Agent": [
                    {"name": "action", "type": "string"},
                    {"name": "nonce", "type": "uint64"}
                ]
            }

            # Sign with eth_account
            account = Account.from_key(self._private_key)
            signed = account.sign_typed_data(
                domain_data=domain,
                message_types={"Agent": types["Agent"]},
                message_data=message
            )

            # Add signature
            payload["signature"] = {
                "r": hex(signed.r),
                "s": hex(signed.s),
                "v": signed.v
            }
            if self._wallet_address:
                payload["vaultAddress"] = self._wallet_address

            return payload

        except Exception as e:
            self._logger.error(f"Signing failed: {e}")
            return payload

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay_ms = self._retry_base_delay_ms * (
            self._retry_backoff_factor ** attempt
        )
        delay_ms = min(delay_ms, self._retry_max_delay_ms)
        return delay_ms / 1000.0

    async def _submit_with_retry(
        self,
        payload: dict,
        action_id: str,
        timestamp: float
    ) -> ExchangeResponse:
        """Submit order with exponential backoff retry."""
        last_error = None

        for attempt in range(self._max_retries):
            try:
                session = await self._get_session()

                async with session.post(
                    f"{self._api_url}/exchange",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    data = await response.json()

                    if response.status == 200 and data.get("status") == "ok":
                        # Extract order ID
                        response_data = data.get("response", {})
                        order_id = None

                        if "data" in response_data:
                            statuses = response_data["data"].get("statuses", [])
                            if statuses:
                                status = statuses[0]
                                if "resting" in status:
                                    order_id = str(status["resting"]["oid"])
                                elif "filled" in status:
                                    order_id = str(status["filled"]["oid"])

                        return ExchangeResponse(
                            response_code=ExchangeResponseCode.ACKNOWLEDGED,
                            order_id=order_id or f"HL_{action_id}_{self._call_count}",
                            message="Order acknowledged",
                            timestamp=timestamp
                        )
                    else:
                        # Non-retryable rejection
                        error_msg = data.get("response", str(data))
                        return ExchangeResponse(
                            response_code=ExchangeResponseCode.REJECTED,
                            order_id=None,
                            message=f"Rejected: {error_msg}",
                            timestamp=timestamp
                        )

            except aiohttp.ClientError as e:
                last_error = f"Network error: {e}"
                self._logger.warning(
                    f"Retry {attempt + 1}/{self._max_retries}: {last_error}"
                )
            except asyncio.TimeoutError:
                last_error = "Request timeout"
                self._logger.warning(
                    f"Retry {attempt + 1}/{self._max_retries}: {last_error}"
                )
            except Exception as e:
                last_error = str(e)
                self._logger.warning(
                    f"Retry {attempt + 1}/{self._max_retries}: {last_error}"
                )

            # Exponential backoff before retry
            if attempt < self._max_retries - 1:
                delay = self._calculate_retry_delay(attempt)
                await asyncio.sleep(delay)

        # All retries exhausted
        return ExchangeResponse(
            response_code=ExchangeResponseCode.TIMEOUT,
            order_id=None,
            message=f"All retries failed: {last_error}",
            timestamp=timestamp
        )

    async def cancel_orders(
        self,
        *,
        action_id: str,
        symbol: Optional[str] = None,
        order_ids: Optional[List[int]] = None,
        timestamp: float
    ) -> ExchangeResponse:
        """
        Cancel orders on Hyperliquid.

        Args:
            action_id: Action identifier
            symbol: Symbol to cancel (for all orders on symbol)
            order_ids: Specific order IDs to cancel
            timestamp: Execution timestamp

        Returns:
            ExchangeResponse
        """
        self._call_count += 1

        if not self._metadata_loaded:
            await self.initialize()

        # Build cancel payload
        if order_ids:
            # Cancel specific orders
            if not symbol:
                return ExchangeResponse(
                    response_code=ExchangeResponseCode.REJECTED,
                    order_id=None,
                    message="Symbol required for order cancellation",
                    timestamp=timestamp
                )

            asset_idx = self.get_asset_index(symbol)
            cancels = [{"a": asset_idx, "o": oid} for oid in order_ids]
            action = {
                "type": "cancel",
                "cancels": cancels
            }
        else:
            # Cancel all orders (optionally filtered by symbol)
            action = {"type": "cancelAll"}

        nonce = int(time.time() * 1000)
        payload = {
            "action": action,
            "nonce": nonce
        }

        if self._private_key:
            payload = self._sign_payload(payload)

        try:
            session = await self._get_session()

            async with session.post(
                f"{self._api_url}/exchange",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                data = await response.json()

                if response.status == 200 and data.get("status") == "ok":
                    return ExchangeResponse(
                        response_code=ExchangeResponseCode.ACKNOWLEDGED,
                        order_id=None,
                        message="Orders cancelled",
                        timestamp=timestamp
                    )
                else:
                    return ExchangeResponse(
                        response_code=ExchangeResponseCode.REJECTED,
                        order_id=None,
                        message=f"Cancel failed: {data}",
                        timestamp=timestamp
                    )

        except Exception as e:
            return ExchangeResponse(
                response_code=ExchangeResponseCode.TIMEOUT,
                order_id=None,
                message=f"Cancel error: {e}",
                timestamp=timestamp
            )

    def get_call_count(self) -> int:
        """Get number of exchange calls made."""
        return self._call_count

    def get_all_assets(self) -> List[str]:
        """Get list of all available asset symbols."""
        with self._metadata_lock:
            return list(self._assets.keys())


# ==============================================================================
# Synchronous Wrapper (for non-async contexts)
# ==============================================================================

class SyncHyperliquidAdapter:
    """
    Synchronous wrapper for HyperliquidExchangeAdapter.

    Uses asyncio.run() for each call - suitable for simple use cases.
    For high-frequency use, prefer the async adapter directly.
    """

    def __init__(self, **kwargs):
        self._async_adapter = HyperliquidExchangeAdapter(**kwargs)
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the adapter."""
        if not self._initialized:
            self._initialized = asyncio.run(self._async_adapter.initialize())
        return self._initialized

    def execute_order(
        self,
        *,
        action_id: str,
        order_params: dict,
        timestamp: float
    ) -> ExchangeResponse:
        """Execute order synchronously."""
        if not self._initialized:
            self.initialize()
        return asyncio.run(
            self._async_adapter.execute_order(
                action_id=action_id,
                order_params=order_params,
                timestamp=timestamp
            )
        )

    def cancel_orders(
        self,
        *,
        action_id: str,
        symbol: Optional[str] = None,
        order_ids: Optional[List[int]] = None,
        timestamp: float
    ) -> ExchangeResponse:
        """Cancel orders synchronously."""
        if not self._initialized:
            self.initialize()
        return asyncio.run(
            self._async_adapter.cancel_orders(
                action_id=action_id,
                symbol=symbol,
                order_ids=order_ids,
                timestamp=timestamp
            )
        )

    def get_constraints(self, symbol: str) -> ExchangeConstraints:
        """Get exchange constraints for a symbol."""
        if not self._initialized:
            self.initialize()
        return self._async_adapter.get_constraints(symbol)

    def format_price(self, symbol: str, price: float) -> str:
        """Format price for exchange."""
        return self._async_adapter.format_price(symbol, price)

    def format_size(self, symbol: str, size: float) -> str:
        """Format size for exchange."""
        return self._async_adapter.format_size(symbol, size)

    def get_asset_index(self, symbol: str) -> int:
        """Get asset index for symbol."""
        if not self._initialized:
            self.initialize()
        return self._async_adapter.get_asset_index(symbol)

    def get_call_count(self) -> int:
        """Get number of exchange calls made."""
        return self._async_adapter.get_call_count()

    def close(self):
        """Close the adapter."""
        asyncio.run(self._async_adapter.close())


# ==============================================================================
# Constraint Validation (for compatibility with ep4_exchange_adapter)
# ==============================================================================

class ExchangeConstraintViolation(Exception):
    """Raised when exchange constraints are violated."""
    pass


def validate_exchange_constraints(
    *,
    quantity: float,
    price: Optional[float],
    constraints: ExchangeConstraints
) -> None:
    """
    Validate action against exchange constraints.

    No rounding. No fixing. Pass or fail only.

    Args:
        quantity: Order quantity
        price: Order price (None for market orders)
        constraints: Exchange constraints

    Raises:
        ExchangeConstraintViolation: If constraints violated
    """
    # Validate quantity bounds
    if quantity < constraints.min_order_size:
        raise ExchangeConstraintViolation(
            f"Quantity {quantity} < min {constraints.min_order_size}"
        )

    if quantity > constraints.max_order_size:
        raise ExchangeConstraintViolation(
            f"Quantity {quantity} > max {constraints.max_order_size}"
        )

    # Validate step size
    if constraints.step_size > 0:
        steps = quantity / constraints.step_size
        if not (abs(steps - round(steps)) < 1e-8):
            raise ExchangeConstraintViolation(
                f"Quantity {quantity} not multiple of step size {constraints.step_size}"
            )

    # Validate tick size (if limit order)
    if price is not None and constraints.tick_size > 0:
        ticks = price / constraints.tick_size
        if not (abs(ticks - round(ticks)) < 1e-8):
            raise ExchangeConstraintViolation(
                f"Price {price} not multiple of tick size {constraints.tick_size}"
            )

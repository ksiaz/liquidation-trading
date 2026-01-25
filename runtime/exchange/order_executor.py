"""
HLP18: Order Executor.

Handles order construction, submission, and lifecycle management.

Order submission flow:
1. Validate order request
2. Check slippage limits
3. Submit to exchange
4. Track until fill/cancel/reject
5. Log execution details

Hardenings:
- E1: Exponential backoff for retries (prevents retry storms)
- E2: Proper wallet signing for Hyperliquid
- E3: Partial fill handling with cancel-resubmit
- E4: Post-fill stop placement
"""

import time
import asyncio
import logging
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from threading import RLock
from enum import Enum
import aiohttp

# E2: Optional eth_account for signing (graceful fallback if not installed)
try:
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    HAS_ETH_ACCOUNT = True
except ImportError:
    HAS_ETH_ACCOUNT = False
    Account = None

from .types import (
    OrderType,
    OrderSide,
    OrderStatus,
    OrderRequest,
    OrderResponse,
    OrderFill,
    OrderUpdate,
    ExecutionMetrics,
    ExecutionLog,
    FillType,
)


class StopOrderState(Enum):
    """X1: Stop order lifecycle states."""
    PENDING_PLACEMENT = "PENDING_PLACEMENT"  # Registered, waiting for entry fill
    PLACED = "PLACED"                        # Successfully placed on exchange
    TRIGGERED = "TRIGGERED"                  # Stop triggered, awaiting fill
    FILLED = "FILLED"                        # Stop order filled
    CANCELLED = "CANCELLED"                  # Stop cancelled (by user or system)
    FAILED = "FAILED"                        # Failed to place after retries


@dataclass
class StopOrderStatus:
    """X1: Complete stop order status for tracking."""
    entry_order_id: str
    stop_order_id: Optional[str]
    state: StopOrderState
    stop_price: float
    symbol: str
    side: str
    size: float
    placement_attempts: int = 0
    last_error: Optional[str] = None
    placed_at_ns: Optional[int] = None
    triggered_at_ns: Optional[int] = None
    filled_at_ns: Optional[int] = None
    fill_price: Optional[float] = None


@dataclass
class ExecutorConfig:
    """Configuration for order executor."""
    # Timeouts
    market_order_timeout_ms: int = 5_000   # 5 seconds for market orders
    limit_order_timeout_ms: int = 300_000  # 5 minutes for limit orders
    stop_placement_timeout_ms: int = 1_000 # 1 second to place stop after fill

    # Slippage limits (percentage)
    default_max_slippage_pct: float = 0.5  # 50 bps
    cascade_max_slippage_pct: float = 1.0  # 100 bps for cascade entries

    # E3: Partial fill thresholds and handling
    min_fill_pct: float = 0.8   # Accept fills >= 80%
    cascade_min_fill_pct: float = 0.5  # Accept fills >= 50% during cascade
    partial_fill_timeout_ms: int = 10_000  # Cancel partial after 10s
    partial_resubmit_enabled: bool = True  # Resubmit remaining size
    max_partial_resubmits: int = 2  # Max resubmit attempts

    # E1: Retry settings with exponential backoff
    max_retries: int = 3
    retry_base_delay_ms: int = 100      # Initial delay
    retry_max_delay_ms: int = 2000      # Cap delay at 2 seconds
    retry_backoff_factor: float = 2.0   # Exponential factor

    # X2-A: Stop placement retry settings
    stop_max_retries: int = 3           # Max stop placement attempts
    stop_retry_base_delay_ms: int = 200 # Initial delay for stop retry
    stop_retry_max_delay_ms: int = 2000 # Cap delay at 2 seconds

    # API settings
    api_url: str = "https://api.hyperliquid.xyz"
    testnet_api_url: str = "https://api.hyperliquid-testnet.xyz"
    use_testnet: bool = False
    request_timeout: float = 10.0


class OrderExecutor:
    """
    Executes orders on Hyperliquid exchange.

    Responsibilities:
    - Order construction for Hyperliquid API format
    - Order submission with retry logic
    - Pending order tracking
    - Timeout detection
    - Fill notification handling
    - Execution logging
    """

    def __init__(
        self,
        config: ExecutorConfig = None,
        private_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        logger: logging.Logger = None
    ):
        self._config = config or ExecutorConfig()
        self._private_key = private_key
        self._wallet_address = wallet_address
        self._logger = logger or logging.getLogger(__name__)

        # API endpoint
        self._api_url = (
            self._config.testnet_api_url
            if self._config.use_testnet
            else self._config.api_url
        )

        # Pending orders
        self._pending_orders: Dict[str, OrderRequest] = {}
        self._order_updates: Dict[str, OrderUpdate] = {}
        self._order_submission_times: Dict[str, int] = {}

        # Metrics
        self._metrics = ExecutionMetrics()

        # Execution log
        self._execution_log: List[ExecutionLog] = []

        # Callbacks
        self._on_fill: Optional[Callable[[OrderFill], None]] = None
        self._on_update: Optional[Callable[[OrderUpdate], None]] = None

        # HTTP session (initialized on first use)
        self._session: Optional[aiohttp.ClientSession] = None

        # E3: Partial fill tracking
        self._partial_resubmit_counts: Dict[str, int] = {}

        # E4: Stop placement tracking
        self._pending_stop_placements: Dict[str, Dict] = {}  # order_id -> stop config
        self._placed_stops: Dict[str, str] = {}  # entry_order_id -> stop_order_id

        # X1: Stop order lifecycle tracking
        self._stop_order_status: Dict[str, StopOrderStatus] = {}  # entry_order_id -> status
        self._stop_order_by_stop_id: Dict[str, str] = {}  # stop_order_id -> entry_order_id

        # X2-B: Callback for stop placement failure (caller can emit BLOCK)
        self._on_stop_failure: Optional[Callable[[str, str, str], None]] = None  # (entry_id, symbol, error)

        # X1: Callback for stop lifecycle events
        self._on_stop_triggered: Optional[Callable[[StopOrderStatus], None]] = None
        self._on_stop_filled: Optional[Callable[[StopOrderStatus], None]] = None
        self._on_stop_cancelled: Optional[Callable[[StopOrderStatus], None]] = None

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _calculate_retry_delay(self, attempt: int) -> float:
        """E1: Calculate exponential backoff delay for retry attempt.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay_ms = self._config.retry_base_delay_ms * (
            self._config.retry_backoff_factor ** attempt
        )
        delay_ms = min(delay_ms, self._config.retry_max_delay_ms)
        return delay_ms / 1000.0  # Convert to seconds

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout)
            )
        return self._session

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def submit_order(self, request: OrderRequest) -> OrderResponse:
        """
        Submit an order to Hyperliquid.

        Args:
            request: Order request with all parameters

        Returns:
            OrderResponse with success/failure and order_id
        """
        submit_ts = self._now_ns()

        with self._lock:
            # Validate request
            validation_error = self._validate_request(request)
            if validation_error:
                self._log_execution('order_rejected', request, error=validation_error)
                self._metrics.add_order(success=False, rejected=True)
                return OrderResponse(
                    success=False,
                    client_order_id=request.client_order_id,
                    status=OrderStatus.REJECTED,
                    error_message=validation_error
                )

        # Build Hyperliquid order payload
        payload = self._build_order_payload(request)

        # Submit order
        response = await self._submit_to_exchange(payload, request)

        with self._lock:
            if response.success:
                # Track pending order
                self._pending_orders[response.order_id] = request
                self._order_submission_times[response.order_id] = submit_ts

                # Initialize order update
                self._order_updates[response.order_id] = OrderUpdate(
                    order_id=response.order_id,
                    client_order_id=request.client_order_id,
                    symbol=request.symbol,
                    status=OrderStatus.SUBMITTED,
                    remaining_size=request.size,
                    timestamp_ns=submit_ts
                )

                self._log_execution('order_submitted', request, order_id=response.order_id)
                self._metrics.add_order(success=True)
            else:
                self._log_execution('order_rejected', request, error=response.error_message)
                self._metrics.add_order(success=False, rejected=True)

        return response

    def _validate_request(self, request: OrderRequest) -> Optional[str]:
        """Validate order request. Returns error message or None."""
        if not request.symbol:
            return "Symbol required"

        if request.size <= 0:
            return "Size must be positive"

        if request.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT, OrderType.POST_ONLY):
            if request.price is None or request.price <= 0:
                return f"Price required for {request.order_type.value} order"

        if request.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            if request.stop_price is None or request.stop_price <= 0:
                return f"Stop price required for {request.order_type.value} order"

        return None

    def _build_order_payload(self, request: OrderRequest) -> Dict:
        """
        Build Hyperliquid order payload.

        API format:
        {
            "action": {
                "type": "order",
                "orders": [{
                    "a": asset_index,
                    "b": is_buy,
                    "p": price_str,
                    "s": size_str,
                    "r": reduce_only,
                    "t": {"limit": {"tif": "Gtc"}} or {"trigger": {...}}
                }],
                "grouping": "na"
            },
            "nonce": timestamp_ms,
            "signature": {...}
        }
        """
        # Determine order type structure
        order_type_struct = self._build_order_type_struct(request)

        # Build order entry
        order = {
            "a": self._get_asset_index(request.symbol),
            "b": request.side == OrderSide.BUY,
            "p": self._format_price(request.price or request.expected_price or 0),
            "s": self._format_size(request.size),
            "r": request.reduce_only,
            "t": order_type_struct,
        }

        # Build action
        action = {
            "type": "order",
            "orders": [order],
            "grouping": "na"
        }

        # Build full payload
        nonce = int(time.time() * 1000)
        payload = {
            "action": action,
            "nonce": nonce,
        }

        return payload

    def _build_order_type_struct(self, request: OrderRequest) -> Dict:
        """Build order type structure for Hyperliquid."""
        if request.order_type == OrderType.MARKET:
            # Market order: use IOC with aggressive price
            return {"limit": {"tif": "Ioc"}}

        elif request.order_type == OrderType.LIMIT:
            tif = "Alo" if request.post_only else "Gtc"
            return {"limit": {"tif": tif}}

        elif request.order_type == OrderType.POST_ONLY:
            return {"limit": {"tif": "Alo"}}

        elif request.order_type == OrderType.IOC:
            return {"limit": {"tif": "Ioc"}}

        elif request.order_type == OrderType.STOP_MARKET:
            # Stop market: trigger + IOC
            is_tp = (
                (request.side == OrderSide.SELL and request.stop_price > (request.expected_price or 0)) or
                (request.side == OrderSide.BUY and request.stop_price < (request.expected_price or float('inf')))
            )
            return {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": self._format_price(request.stop_price),
                    "tpsl": "tp" if is_tp else "sl"
                }
            }

        elif request.order_type == OrderType.STOP_LIMIT:
            is_tp = (
                (request.side == OrderSide.SELL and request.stop_price > (request.expected_price or 0)) or
                (request.side == OrderSide.BUY and request.stop_price < (request.expected_price or float('inf')))
            )
            return {
                "trigger": {
                    "isMarket": False,
                    "triggerPx": self._format_price(request.stop_price),
                    "limitPx": self._format_price(request.price),
                    "tpsl": "tp" if is_tp else "sl"
                }
            }

        # Default to limit GTC
        return {"limit": {"tif": "Gtc"}}

    def _get_asset_index(self, symbol: str) -> int:
        """Get Hyperliquid asset index for symbol."""
        # Common mappings - should be loaded from exchange meta
        asset_map = {
            "BTC": 0, "ETH": 1, "SOL": 2, "DOGE": 3, "XRP": 4,
            "AVAX": 5, "LINK": 6, "ARB": 7, "OP": 8, "SUI": 9,
            "ATOM": 10, "APT": 11, "INJ": 12, "SEI": 13, "TIA": 14,
        }
        return asset_map.get(symbol, 0)

    def _format_price(self, price: float) -> str:
        """Format price for Hyperliquid API."""
        if price == 0:
            return "0"
        # Use appropriate precision based on price magnitude
        if price >= 1000:
            return f"{price:.1f}"
        elif price >= 1:
            return f"{price:.2f}"
        else:
            return f"{price:.6f}"

    def _format_size(self, size: float) -> str:
        """Format size for Hyperliquid API."""
        if size >= 1:
            return f"{size:.4f}"
        else:
            return f"{size:.6f}"

    async def _submit_to_exchange(
        self,
        payload: Dict,
        request: OrderRequest
    ) -> OrderResponse:
        """Submit order payload to Hyperliquid API with E1 exponential backoff."""
        # Sign payload if private key available
        if self._private_key:
            payload = self._sign_payload(payload)

        last_error = None

        # E1: Retry loop with exponential backoff
        for attempt in range(self._config.max_retries):
            try:
                session = await self._get_session()

                async with session.post(
                    f"{self._api_url}/exchange",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    data = await response.json()

                    if response.status == 200 and data.get("status") == "ok":
                        # Extract order ID from response
                        response_data = data.get("response", {})
                        order_id = None

                        if "data" in response_data:
                            statuses = response_data["data"].get("statuses", [])
                            if statuses and len(statuses) > 0:
                                status = statuses[0]
                                if "resting" in status:
                                    order_id = str(status["resting"]["oid"])
                                elif "filled" in status:
                                    order_id = str(status["filled"]["oid"])

                        return OrderResponse(
                            success=True,
                            order_id=order_id or request.client_order_id,
                            client_order_id=request.client_order_id,
                            status=OrderStatus.SUBMITTED,
                            raw_response=data
                        )
                    else:
                        # Non-retryable rejection (e.g., insufficient margin)
                        error_msg = data.get("response", str(data))
                        return OrderResponse(
                            success=False,
                            client_order_id=request.client_order_id,
                            status=OrderStatus.REJECTED,
                            error_code=str(response.status),
                            error_message=str(error_msg),
                            raw_response=data
                        )

            except aiohttp.ClientError as e:
                last_error = f"Network error: {e}"
                self._logger.warning(
                    f"E1: Retry {attempt + 1}/{self._config.max_retries} "
                    f"for {request.symbol}: {last_error}"
                )
            except asyncio.TimeoutError:
                last_error = "Request timeout"
                self._logger.warning(
                    f"E1: Retry {attempt + 1}/{self._config.max_retries} "
                    f"for {request.symbol}: {last_error}"
                )
            except Exception as e:
                last_error = str(e)
                self._logger.warning(
                    f"E1: Retry {attempt + 1}/{self._config.max_retries} "
                    f"for {request.symbol}: {last_error}"
                )

            # E1: Exponential backoff before next retry
            if attempt < self._config.max_retries - 1:
                delay = self._calculate_retry_delay(attempt)
                self._logger.info(f"E1: Waiting {delay:.3f}s before retry")
                await asyncio.sleep(delay)

        # All retries exhausted
        self._logger.error(
            f"E1: All {self._config.max_retries} retries failed for {request.symbol}"
        )
        return OrderResponse(
            success=False,
            client_order_id=request.client_order_id,
            status=OrderStatus.FAILED,
            error_message=f"All retries failed: {last_error}"
        )

    def _sign_payload(self, payload: Dict) -> Dict:
        """
        E2: Sign order payload with private key using EIP-712.

        Hyperliquid uses EIP-712 typed data signing.
        Requires eth_account library for production use.

        Args:
            payload: Order payload to sign

        Returns:
            Signed payload with signature field
        """
        if not HAS_ETH_ACCOUNT:
            self._logger.warning(
                "E2: eth_account not installed - signing disabled. "
                "Install with: pip install eth-account"
            )
            return payload

        if not self._private_key:
            self._logger.warning("E2: No private key configured - signing disabled")
            return payload

        try:
            # Hyperliquid EIP-712 domain
            domain = {
                "name": "Exchange",
                "version": "1",
                "chainId": 42161,  # Arbitrum
                "verifyingContract": "0x0000000000000000000000000000000000000000"
            }

            # Build typed data for signing
            # Hyperliquid uses a specific message format
            action = payload.get("action", {})
            nonce = payload.get("nonce", int(time.time() * 1000))

            # Create message hash for Hyperliquid
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

            typed_data = {
                "types": types,
                "primaryType": "Agent",
                "domain": domain,
                "message": message
            }

            # Sign with eth_account
            account = Account.from_key(self._private_key)
            signed = account.sign_typed_data(
                domain_data=domain,
                message_types={"Agent": types["Agent"]},
                message_data=message
            )

            # Add signature to payload
            payload["signature"] = {
                "r": hex(signed.r),
                "s": hex(signed.s),
                "v": signed.v
            }
            payload["vaultAddress"] = self._wallet_address

            self._logger.debug(f"E2: Signed payload for {self._wallet_address[:10]}...")
            return payload

        except Exception as e:
            self._logger.error(f"E2: Signing failed: {e}")
            # Return unsigned payload - exchange will reject
            return payload

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Order ID to cancel
            symbol: Symbol of the order

        Returns:
            True if cancel submitted successfully
        """
        payload = {
            "action": {
                "type": "cancel",
                "cancels": [{
                    "a": self._get_asset_index(symbol),
                    "o": int(order_id)
                }]
            },
            "nonce": int(time.time() * 1000)
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
                    with self._lock:
                        if order_id in self._order_updates:
                            self._order_updates[order_id].status = OrderStatus.CANCELED
                        self._pending_orders.pop(order_id, None)
                    return True

                return False

        except Exception as e:
            self._logger.error(f"Error canceling order {order_id}: {e}")
            return False

    def handle_fill(self, fill: OrderFill) -> bool:
        """
        Handle a fill notification from WebSocket or polling.

        E4: Returns True if stop placement is pending (caller should await place_stop_for_fill).

        Args:
            fill: Fill event details

        Returns:
            True if stop placement is pending for this fill
        """
        stop_pending = False

        with self._lock:
            order_id = fill.order_id

            if order_id not in self._order_updates:
                self._logger.warning(f"Fill for unknown order: {order_id}")
                return False

            update = self._order_updates[order_id]
            update.fills.append(fill)
            update.filled_size += fill.size
            update.remaining_size -= fill.size

            # Calculate average price
            total_value = sum(f.price * f.size for f in update.fills)
            total_size = sum(f.size for f in update.fills)
            update.average_price = total_value / total_size if total_size > 0 else 0

            # Determine status
            if update.remaining_size <= 0:
                update.status = OrderStatus.FILLED
                self._pending_orders.pop(order_id, None)

                # E4: Check if stop placement is pending
                if order_id in self._pending_stop_placements:
                    stop_pending = True
            else:
                update.status = OrderStatus.PARTIAL

            update.timestamp_ns = fill.timestamp_ns

            # Calculate metrics
            request = self._pending_orders.get(order_id)
            if request and request.expected_price:
                slippage_bps = abs(fill.price - request.expected_price) / request.expected_price * 10000
                submit_time = self._order_submission_times.get(order_id, fill.timestamp_ns)
                latency_ms = (fill.timestamp_ns - submit_time) / 1_000_000
                self._metrics.add_fill(slippage_bps, latency_ms, partial=update.status == OrderStatus.PARTIAL)

                self._log_execution(
                    'order_filled',
                    request,
                    order_id=order_id,
                    fill_price=fill.price,
                    slippage_bps=slippage_bps,
                    latency_ms=latency_ms
                )

            # Notify callback
            if self._on_fill:
                self._on_fill(fill)

        # E4: Log if stop placement pending
        if stop_pending:
            self._logger.info(
                f"E4: Entry {order_id} filled, stop placement pending"
            )

        return stop_pending

    def handle_order_update(self, update: OrderUpdate):
        """Handle order status update from WebSocket."""
        with self._lock:
            if update.order_id in self._order_updates:
                existing = self._order_updates[update.order_id]
                existing.status = update.status
                existing.filled_size = update.filled_size
                existing.remaining_size = update.remaining_size
                existing.timestamp_ns = update.timestamp_ns

                if update.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
                    self._pending_orders.pop(update.order_id, None)

            if self._on_update:
                self._on_update(update)

    def check_timeouts(self) -> List[str]:
        """
        Check for timed out orders.

        Returns:
            List of order IDs that have timed out
        """
        now_ns = self._now_ns()
        timed_out = []

        with self._lock:
            for order_id, submit_time in list(self._order_submission_times.items()):
                if order_id not in self._pending_orders:
                    continue

                request = self._pending_orders[order_id]
                elapsed_ms = (now_ns - submit_time) / 1_000_000

                timeout_ms = (
                    self._config.market_order_timeout_ms
                    if request.order_type == OrderType.MARKET
                    else self._config.limit_order_timeout_ms
                )

                if elapsed_ms > timeout_ms:
                    timed_out.append(order_id)
                    self._metrics.add_order(success=False, timeout=True)
                    self._log_execution(
                        'order_timeout',
                        request,
                        order_id=order_id,
                        error=f"Timeout after {elapsed_ms:.0f}ms"
                    )

        return timed_out

    async def check_partial_fills(self) -> List[Tuple[str, float]]:
        """
        E3: Check for stale partial fills and handle them.

        Returns:
            List of (order_id, remaining_size) that need attention
        """
        now_ns = self._now_ns()
        partials = []

        with self._lock:
            for order_id, update in list(self._order_updates.items()):
                if update.status != OrderStatus.PARTIAL:
                    continue

                submit_time = self._order_submission_times.get(order_id, now_ns)
                elapsed_ms = (now_ns - submit_time) / 1_000_000

                if elapsed_ms > self._config.partial_fill_timeout_ms:
                    request = self._pending_orders.get(order_id)
                    if request:
                        fill_pct = update.filled_size / request.size
                        min_pct = (
                            self._config.cascade_min_fill_pct
                            if request.is_cascade else self._config.min_fill_pct
                        )

                        if fill_pct >= min_pct:
                            # Acceptable partial - cancel remaining
                            self._logger.info(
                                f"E3: Partial fill {fill_pct*100:.1f}% >= min "
                                f"{min_pct*100:.1f}% for {order_id}, accepting"
                            )
                            partials.append((order_id, 0))  # 0 = don't resubmit
                        else:
                            # Need more fill - cancel and resubmit
                            remaining = update.remaining_size
                            resubmit_count = self._partial_resubmit_counts.get(order_id, 0)

                            if (self._config.partial_resubmit_enabled and
                                    resubmit_count < self._config.max_partial_resubmits):
                                self._logger.info(
                                    f"E3: Partial fill {fill_pct*100:.1f}% < min "
                                    f"{min_pct*100:.1f}% for {order_id}, will resubmit {remaining}"
                                )
                                partials.append((order_id, remaining))
                            else:
                                self._logger.warning(
                                    f"E3: Partial fill {fill_pct*100:.1f}% for {order_id}, "
                                    f"max resubmits reached, abandoning"
                                )
                                partials.append((order_id, 0))

        return partials

    async def handle_partial_fill(
        self,
        order_id: str,
        remaining_size: float
    ) -> Optional[OrderResponse]:
        """
        E3: Handle a partial fill by canceling and optionally resubmitting.

        Args:
            order_id: Order ID with partial fill
            remaining_size: Size to resubmit (0 = just cancel)

        Returns:
            OrderResponse for resubmitted order, or None
        """
        with self._lock:
            request = self._pending_orders.get(order_id)
            update = self._order_updates.get(order_id)

        if not request or not update:
            return None

        # Cancel remaining order
        cancelled = await self.cancel_order(order_id, request.symbol)
        if not cancelled:
            self._logger.error(f"E3: Failed to cancel partial {order_id}")
            return None

        self._log_execution(
            'partial_fill_cancelled',
            request,
            order_id=order_id,
            fill_price=update.average_price
        )

        # Resubmit if needed
        if remaining_size > 0:
            # Create new request for remaining size
            from copy import copy
            new_request = OrderRequest(
                symbol=request.symbol,
                side=request.side,
                size=remaining_size,
                order_type=request.order_type,
                price=request.price,
                stop_price=request.stop_price,
                expected_price=request.expected_price,
                reduce_only=request.reduce_only,
                post_only=request.post_only,
                client_order_id=f"{request.client_order_id}_R",
                strategy_id=request.strategy_id,
                event_id=request.event_id,
                is_cascade=request.is_cascade
            )

            # Track resubmit count
            with self._lock:
                self._partial_resubmit_counts[order_id] = (
                    self._partial_resubmit_counts.get(order_id, 0) + 1
                )

            self._logger.info(
                f"E3: Resubmitting {remaining_size} for {request.symbol}"
            )
            return await self.submit_order(new_request)

        return None

    def get_pending_orders(self) -> Dict[str, OrderUpdate]:
        """Get all pending orders."""
        with self._lock:
            return {
                oid: update
                for oid, update in self._order_updates.items()
                if update.status in (OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIAL)
            }

    def get_order_update(self, order_id: str) -> Optional[OrderUpdate]:
        """Get update for a specific order."""
        with self._lock:
            return self._order_updates.get(order_id)

    def get_metrics(self) -> ExecutionMetrics:
        """Get execution metrics."""
        with self._lock:
            return self._metrics

    def set_fill_callback(self, callback: Callable[[OrderFill], None]):
        """Set callback for fill events."""
        self._on_fill = callback

    def set_update_callback(self, callback: Callable[[OrderUpdate], None]):
        """Set callback for order updates."""
        self._on_update = callback

    def set_stop_failure_callback(self, callback: Callable[[str, str, str], None]):
        """X2-B: Set callback for stop placement failure after all retries.

        Callback receives: (entry_order_id, symbol, error_message)
        Caller should use this to emit BLOCK mandate for unprotected position.
        """
        self._on_stop_failure = callback

    def set_stop_triggered_callback(self, callback: Callable[[StopOrderStatus], None]):
        """X1: Set callback for stop order triggered."""
        self._on_stop_triggered = callback

    def set_stop_filled_callback(self, callback: Callable[[StopOrderStatus], None]):
        """X1: Set callback for stop order filled."""
        self._on_stop_filled = callback

    def set_stop_cancelled_callback(self, callback: Callable[[StopOrderStatus], None]):
        """X1: Set callback for stop order cancelled."""
        self._on_stop_cancelled = callback

    def register_stop_for_entry(
        self,
        entry_order_id: str,
        stop_config: Dict
    ):
        """
        E4: Register a stop loss to be placed after entry fills.

        Args:
            entry_order_id: Order ID of the entry order
            stop_config: Stop configuration with keys:
                - stop_price: Stop trigger price
                - symbol: Trading symbol
                - side: Stop order side (opposite of entry)
                - size: Stop size (usually same as entry)
        """
        with self._lock:
            self._pending_stop_placements[entry_order_id] = stop_config
            self._logger.info(
                f"E4: Registered stop for entry {entry_order_id}: "
                f"stop @ {stop_config.get('stop_price')}"
            )

    async def place_stop_for_fill(self, entry_order_id: str, fill: OrderFill) -> Optional[OrderResponse]:
        """
        E4 + X2-A: Place stop loss after entry fill with retry logic.

        X2-A: Retries with exponential backoff if placement fails.
        X2-B: Calls stop_failure callback if all retries exhausted.
        X1: Tracks stop order lifecycle status.

        Args:
            entry_order_id: Order ID of the filled entry
            fill: Fill details

        Returns:
            OrderResponse for stop order, or None if not configured
        """
        with self._lock:
            stop_config = self._pending_stop_placements.pop(entry_order_id, None)

        if not stop_config:
            return None

        # Create stop order request
        stop_side = OrderSide.SELL if stop_config.get('side') == 'SELL' else OrderSide.BUY
        stop_request = OrderRequest(
            symbol=stop_config['symbol'],
            side=stop_side,
            size=stop_config.get('size', fill.size),
            order_type=OrderType.STOP_MARKET,
            stop_price=stop_config['stop_price'],
            expected_price=fill.price,
            reduce_only=True,
            client_order_id=f"{entry_order_id}_SL",
            strategy_id=stop_config.get('strategy_id'),
            event_id=stop_config.get('event_id')
        )

        # X1: Initialize stop order status
        stop_status = StopOrderStatus(
            entry_order_id=entry_order_id,
            stop_order_id=None,
            state=StopOrderState.PENDING_PLACEMENT,
            stop_price=stop_config['stop_price'],
            symbol=stop_config['symbol'],
            side=stop_config.get('side', 'SELL'),
            size=stop_config.get('size', fill.size),
            placement_attempts=0
        )

        with self._lock:
            self._stop_order_status[entry_order_id] = stop_status

        self._logger.info(
            f"E4: Placing stop for filled entry {entry_order_id}: "
            f"{stop_request.symbol} {stop_request.side.value} @ {stop_request.stop_price}"
        )

        # X2-A: Retry loop with exponential backoff
        last_error = None
        for attempt in range(self._config.stop_max_retries):
            stop_status.placement_attempts = attempt + 1

            response = await self.submit_order(stop_request)

            if response.success:
                # X1: Update status to PLACED
                with self._lock:
                    stop_status.stop_order_id = response.order_id
                    stop_status.state = StopOrderState.PLACED
                    stop_status.placed_at_ns = self._now_ns()
                    self._placed_stops[entry_order_id] = response.order_id
                    self._stop_order_by_stop_id[response.order_id] = entry_order_id
                    self._stop_order_status[entry_order_id] = stop_status

                self._logger.info(
                    f"E4: Stop placed successfully: {response.order_id} (attempt {attempt + 1})"
                )
                return response

            # X2-A: Placement failed, prepare for retry
            last_error = response.error_message
            self._logger.warning(
                f"X2-A: Stop placement failed (attempt {attempt + 1}/{self._config.stop_max_retries}): "
                f"{last_error}"
            )

            # X2-A: Exponential backoff before retry (except on last attempt)
            if attempt < self._config.stop_max_retries - 1:
                delay_ms = self._config.stop_retry_base_delay_ms * (
                    self._config.retry_backoff_factor ** attempt
                )
                delay_ms = min(delay_ms, self._config.stop_retry_max_delay_ms)
                await asyncio.sleep(delay_ms / 1000.0)

        # X2-B: All retries exhausted - mark as FAILED and notify
        with self._lock:
            stop_status.state = StopOrderState.FAILED
            stop_status.last_error = last_error
            self._stop_order_status[entry_order_id] = stop_status

        self._logger.error(
            f"X2-B: CRITICAL - Stop placement FAILED after {self._config.stop_max_retries} attempts "
            f"for entry {entry_order_id}: {last_error}"
        )

        # X2-B: Notify caller of failure (they should emit BLOCK)
        if self._on_stop_failure:
            self._on_stop_failure(entry_order_id, stop_config['symbol'], last_error or "Unknown error")

        return OrderResponse(
            success=False,
            client_order_id=stop_request.client_order_id,
            status=OrderStatus.FAILED,
            error_message=f"Stop placement failed after {self._config.stop_max_retries} retries: {last_error}"
        )

    def get_stop_order_id(self, entry_order_id: str) -> Optional[str]:
        """E4: Get stop order ID for an entry order."""
        with self._lock:
            return self._placed_stops.get(entry_order_id)

    def get_stop_order_status(self, entry_order_id: str) -> Optional[StopOrderStatus]:
        """X1: Get complete stop order status for an entry."""
        with self._lock:
            return self._stop_order_status.get(entry_order_id)

    def handle_stop_triggered(self, stop_order_id: str):
        """X1: Handle stop order triggered event from exchange.

        Called when stop price is hit and order becomes active.

        Args:
            stop_order_id: The stop order ID that was triggered
        """
        with self._lock:
            entry_order_id = self._stop_order_by_stop_id.get(stop_order_id)
            if not entry_order_id:
                self._logger.warning(f"X1: Triggered stop {stop_order_id} not tracked")
                return

            status = self._stop_order_status.get(entry_order_id)
            if not status:
                return

            status.state = StopOrderState.TRIGGERED
            status.triggered_at_ns = self._now_ns()
            self._stop_order_status[entry_order_id] = status

        self._logger.info(f"X1: Stop triggered for entry {entry_order_id}: {stop_order_id}")

        if self._on_stop_triggered:
            self._on_stop_triggered(status)

    def handle_stop_filled(self, stop_order_id: str, fill_price: float):
        """X1: Handle stop order filled event from exchange.

        Args:
            stop_order_id: The stop order ID that was filled
            fill_price: The fill price
        """
        with self._lock:
            entry_order_id = self._stop_order_by_stop_id.get(stop_order_id)
            if not entry_order_id:
                self._logger.warning(f"X1: Filled stop {stop_order_id} not tracked")
                return

            status = self._stop_order_status.get(entry_order_id)
            if not status:
                return

            status.state = StopOrderState.FILLED
            status.filled_at_ns = self._now_ns()
            status.fill_price = fill_price
            self._stop_order_status[entry_order_id] = status

            # Clean up tracking
            self._placed_stops.pop(entry_order_id, None)

        self._logger.info(
            f"X1: Stop filled for entry {entry_order_id}: {stop_order_id} @ {fill_price}"
        )

        if self._on_stop_filled:
            self._on_stop_filled(status)

    def handle_stop_cancelled(self, stop_order_id: str, reason: str = ""):
        """X1: Handle stop order cancelled event from exchange.

        CRITICAL: Position is now unprotected!

        Args:
            stop_order_id: The stop order ID that was cancelled
            reason: Cancellation reason
        """
        with self._lock:
            entry_order_id = self._stop_order_by_stop_id.get(stop_order_id)
            if not entry_order_id:
                self._logger.warning(f"X1: Cancelled stop {stop_order_id} not tracked")
                return

            status = self._stop_order_status.get(entry_order_id)
            if not status:
                return

            status.state = StopOrderState.CANCELLED
            status.last_error = reason or "Cancelled"
            self._stop_order_status[entry_order_id] = status

            # Clean up tracking
            self._placed_stops.pop(entry_order_id, None)

        self._logger.error(
            f"X1: CRITICAL - Stop CANCELLED for entry {entry_order_id}: {stop_order_id} "
            f"(reason: {reason}) - POSITION UNPROTECTED"
        )

        if self._on_stop_cancelled:
            self._on_stop_cancelled(status)

        # X2-B: Also notify failure callback since position is unprotected
        if self._on_stop_failure:
            self._on_stop_failure(entry_order_id, status.symbol, f"Stop cancelled: {reason}")

    def get_unprotected_entries(self) -> List[str]:
        """X1: Get list of entry orders without active stop protection.

        Returns entries where stop is FAILED or CANCELLED.
        """
        unprotected = []
        with self._lock:
            for entry_id, status in self._stop_order_status.items():
                if status.state in (StopOrderState.FAILED, StopOrderState.CANCELLED):
                    unprotected.append(entry_id)
        return unprotected

    def _log_execution(
        self,
        event_type: str,
        request: OrderRequest,
        order_id: str = None,
        fill_price: float = None,
        slippage_bps: float = None,
        latency_ms: float = None,
        error: str = None
    ):
        """Log an execution event."""
        log_entry = ExecutionLog(
            event_type=event_type,
            timestamp_ns=self._now_ns(),
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=request.price or request.expected_price,
            fill_price=fill_price,
            slippage_bps=slippage_bps,
            latency_ms=latency_ms,
            error=error,
            details={
                'strategy_id': request.strategy_id,
                'event_id': request.event_id,
                'order_type': request.order_type.value,
            }
        )

        with self._lock:
            self._execution_log.append(log_entry)
            # Keep last 1000 entries
            if len(self._execution_log) > 1000:
                self._execution_log = self._execution_log[-1000:]

        # Log to logger
        if event_type == 'order_submitted':
            self._logger.info(
                f"ORDER SUBMITTED: {request.symbol} {request.side.value} "
                f"{request.size} @ {request.price or 'market'}"
            )
        elif event_type == 'order_filled':
            self._logger.info(
                f"ORDER FILLED: {request.symbol} {request.side.value} "
                f"{request.size} @ {fill_price} (slippage: {slippage_bps:.1f}bps, latency: {latency_ms:.1f}ms)"
            )
        elif event_type == 'order_rejected':
            self._logger.warning(f"ORDER REJECTED: {request.symbol} - {error}")
        elif event_type == 'order_timeout':
            self._logger.error(f"ORDER TIMEOUT: {request.symbol} - {error}")

    def get_execution_log(self, limit: int = 100) -> List[ExecutionLog]:
        """Get recent execution log entries."""
        with self._lock:
            return list(self._execution_log[-limit:])

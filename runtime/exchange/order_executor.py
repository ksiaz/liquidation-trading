"""
HLP18: Order Executor.

Handles order construction, submission, and lifecycle management.

Order submission flow:
1. Validate order request
2. Check slippage limits
3. Submit to exchange
4. Track until fill/cancel/reject
5. Log execution details
"""

import time
import logging
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from threading import RLock
from enum import Enum
import aiohttp

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

    # Partial fill thresholds
    min_fill_pct: float = 0.8   # Accept fills >= 80%
    cascade_min_fill_pct: float = 0.5  # Accept fills >= 50% during cascade

    # Retry settings
    max_retries: int = 3
    retry_delay_ms: int = 100

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

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

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
        """Submit order payload to Hyperliquid API."""
        # Sign payload if private key available
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
            self._logger.error(f"HTTP error submitting order: {e}")
            return OrderResponse(
                success=False,
                client_order_id=request.client_order_id,
                status=OrderStatus.FAILED,
                error_message=f"Network error: {e}"
            )
        except Exception as e:
            self._logger.error(f"Error submitting order: {e}")
            return OrderResponse(
                success=False,
                client_order_id=request.client_order_id,
                status=OrderStatus.FAILED,
                error_message=str(e)
            )

    def _sign_payload(self, payload: Dict) -> Dict:
        """
        Sign order payload with private key.

        Note: Actual signing requires eth_account library.
        This is a placeholder for the signing structure.
        """
        # Signing implementation would go here
        # For now, return payload as-is (will need wallet connection)
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

    def handle_fill(self, fill: OrderFill):
        """
        Handle a fill notification from WebSocket or polling.

        Args:
            fill: Fill event details
        """
        with self._lock:
            order_id = fill.order_id

            if order_id not in self._order_updates:
                self._logger.warning(f"Fill for unknown order: {order_id}")
                return

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

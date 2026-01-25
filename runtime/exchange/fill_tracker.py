"""
HLP18: Fill Tracker.

Monitors order fills via multiple methods:
1. WebSocket order updates (primary - fastest)
2. REST API polling (fallback)
3. Position monitoring (validation)

Detects partial fills and handles fill timeouts.

P3: Fill ID deduplication persisted across restarts.
"""

import time
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Set, TYPE_CHECKING
from enum import auto
from threading import RLock
from enum import Enum

import aiohttp

if TYPE_CHECKING:
    from runtime.persistence import ExecutionStateRepository

from .types import (
    OrderStatus,
    OrderFill,
    OrderUpdate,
    FillType,
    OrderSide,
)


@dataclass
class FillTrackerConfig:
    """Configuration for fill tracking."""
    # Polling intervals
    poll_interval_ms: int = 500    # Poll every 500ms
    active_poll_interval_ms: int = 100  # Poll every 100ms when orders pending

    # Timeout thresholds
    market_fill_timeout_ms: int = 5_000   # 5 seconds for market orders
    limit_fill_timeout_ms: int = 300_000  # 5 minutes for limit orders

    # API settings
    api_url: str = "https://api.hyperliquid.xyz"
    testnet_api_url: str = "https://api.hyperliquid-testnet.xyz"
    use_testnet: bool = False
    request_timeout: float = 5.0


class FillTracker:
    """
    Tracks order fills through multiple detection methods.

    Primary: WebSocket notifications
    Fallback: REST API polling
    Validation: Position change detection

    Ensures no fills are missed due to network issues.

    P3: Fill ID deduplication persisted via ExecutionStateRepository.
    """

    def __init__(
        self,
        config: FillTrackerConfig = None,
        wallet_address: Optional[str] = None,
        logger: logging.Logger = None,
        repository: Optional["ExecutionStateRepository"] = None
    ):
        self._config = config or FillTrackerConfig()
        self._wallet_address = wallet_address
        self._logger = logger or logging.getLogger(__name__)

        # P3: Persistence layer
        self._repository = repository

        # API endpoint
        self._api_url = (
            self._config.testnet_api_url
            if self._config.use_testnet
            else self._config.api_url
        )

        # Tracked orders
        self._tracked_orders: Dict[str, TrackingEntry] = {}
        self._order_fills: Dict[str, List[OrderFill]] = {}

        # P3: Global fill ID dedup set (loaded from persistence)
        self._global_seen_fill_ids: Set[str] = set()

        # Callbacks
        self._on_fill: Optional[Callable[[OrderFill], None]] = None
        self._on_status_change: Optional[Callable[[OrderUpdate], None]] = None
        self._on_timeout: Optional[Callable[[str], None]] = None

        # Polling state
        self._polling_task: Optional[asyncio.Task] = None
        self._running = False

        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None

        self._lock = RLock()

        # P3: Load persisted fill IDs on init
        if self._repository:
            self._load_persisted_fill_ids()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _load_persisted_fill_ids(self):
        """P3: Load persisted fill IDs on startup."""
        if not self._repository:
            return

        try:
            # Load fill IDs from last 24 hours
            self._global_seen_fill_ids = self._repository.load_recent_fill_ids(hours=24)
            self._logger.info(
                f"P3: Loaded {len(self._global_seen_fill_ids)} fill IDs from persistence"
            )
        except Exception as e:
            self._logger.error(f"P3: Failed to load persisted fill IDs: {e}")

    def _persist_fill_id(self, fill_id: str, symbol: str, order_id: str):
        """P3: Persist a fill ID to prevent reprocessing on restart."""
        if not self._repository:
            return

        try:
            self._repository.save_fill_id(fill_id, symbol, order_id)
        except Exception as e:
            self._logger.error(f"P3: Failed to persist fill ID {fill_id}: {e}")

    async def start(self):
        """Start fill tracking (begins polling loop)."""
        self._running = True
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout)
            )
        self._polling_task = asyncio.create_task(self._poll_loop())
        self._logger.info("FillTracker started")

    async def stop(self):
        """Stop fill tracking."""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
        self._logger.info("FillTracker stopped")

    def track_order(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        size: float,
        expected_price: Optional[float] = None,
        is_market: bool = True
    ):
        """
        Start tracking an order for fills.

        Args:
            order_id: Exchange order ID
            symbol: Trading pair
            side: Buy or sell
            size: Order size
            expected_price: Expected fill price for slippage calculation
            is_market: True for market orders (shorter timeout)
        """
        with self._lock:
            entry = TrackingEntry(
                order_id=order_id,
                symbol=symbol,
                side=side,
                original_size=size,
                remaining_size=size,
                expected_price=expected_price,
                is_market=is_market,
                submit_time_ns=self._now_ns()
            )
            self._tracked_orders[order_id] = entry
            self._order_fills[order_id] = []
            self._logger.debug(f"Tracking order {order_id}: {symbol} {side.value} {size}")

    def untrack_order(self, order_id: str):
        """Stop tracking an order."""
        with self._lock:
            self._tracked_orders.pop(order_id, None)
            # Keep fills for history

    def handle_ws_fill(self, data: Dict):
        """
        Handle fill notification from WebSocket.

        Expected data format (from Hyperliquid userEvents):
        {
            "fills": [{
                "coin": "BTC",
                "side": "B" or "A",
                "px": "50000.0",
                "sz": "0.1",
                "time": 1699999999999,
                "oid": 12345,
                "tid": 67890,
                "fee": "0.5",
                "crossed": true/false
            }]
        }
        """
        fills = data.get('fills', [])
        for fill_data in fills:
            self._process_fill(fill_data)

    def handle_ws_order_update(self, data: Dict):
        """
        Handle order status update from WebSocket.

        Expected data format:
        {
            "order": {
                "oid": 12345,
                "coin": "BTC",
                "side": "B",
                "sz": "0.1",
                "filled": "0.05",
                "status": "open" | "filled" | "canceled"
            }
        }
        """
        order_data = data.get('order', data)
        order_id = str(order_data.get('oid', order_data.get('order_id', '')))

        with self._lock:
            if order_id not in self._tracked_orders:
                return

            entry = self._tracked_orders[order_id]

            # Parse status
            status_str = order_data.get('status', '').lower()
            if status_str == 'filled':
                status = OrderStatus.FILLED
            elif status_str == 'canceled':
                status = OrderStatus.CANCELED
            elif status_str == 'rejected':
                status = OrderStatus.REJECTED
            else:
                status = OrderStatus.ACKNOWLEDGED

            # Parse fill amounts
            filled = float(order_data.get('filled', order_data.get('filledSz', 0)))
            remaining = entry.original_size - filled

            # Update entry
            entry.filled_size = filled
            entry.remaining_size = remaining
            entry.status = status
            entry.last_update_ns = self._now_ns()

            # Build update
            update = OrderUpdate(
                order_id=order_id,
                client_order_id=None,
                symbol=entry.symbol,
                status=status,
                filled_size=filled,
                remaining_size=remaining,
                timestamp_ns=entry.last_update_ns,
                fills=self._order_fills.get(order_id, [])
            )

            # Notify callback
            if self._on_status_change:
                self._on_status_change(update)

            # Clean up if terminal
            if status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
                self._tracked_orders.pop(order_id, None)

    def _process_fill(self, fill_data: Dict):
        """Process a single fill event."""
        order_id = str(fill_data.get('oid', ''))

        with self._lock:
            if order_id not in self._tracked_orders:
                self._logger.debug(f"Fill for untracked order: {order_id}")
                return

            entry = self._tracked_orders[order_id]

            # F1: Deduplication by fill ID (tid)
            fill_id = str(fill_data.get('tid', ''))

            # P3: Check global persisted set first (survives restarts)
            if fill_id and fill_id in self._global_seen_fill_ids:
                self._logger.debug(f"Duplicate fill ignored (persisted): {fill_id} for order {order_id}")
                return

            # F1: Check per-order set (runtime dedup)
            if fill_id and fill_id in entry.seen_fill_ids:
                self._logger.debug(f"Duplicate fill ignored: {fill_id} for order {order_id}")
                return

            if fill_id:
                entry.seen_fill_ids.add(fill_id)
                self._global_seen_fill_ids.add(fill_id)
                # P3: Persist fill ID for restart recovery
                self._persist_fill_id(fill_id, entry.symbol, order_id)

            # F2: Fill time source precedence (exchange time > local time)
            # Exchange 'time' is in milliseconds, local fallback only if missing
            exchange_time_ms = fill_data.get('time')
            if exchange_time_ms is not None:
                fill_time_ns = int(exchange_time_ms) * 1_000_000
            else:
                # Local time fallback - mark as potentially unreliable
                fill_time_ns = self._now_ns()
                self._logger.warning(f"Fill {fill_id}: No exchange time, using local time")

            # Create fill object
            fill = OrderFill(
                order_id=order_id,
                fill_id=fill_id or str(fill_time_ns),
                symbol=fill_data.get('coin', entry.symbol),
                side=entry.side,
                price=float(fill_data.get('px', 0)),
                size=float(fill_data.get('sz', 0)),
                fill_type=FillType.TAKER if fill_data.get('crossed', True) else FillType.MAKER,
                fee=float(fill_data.get('fee', 0)),
                timestamp_ns=fill_time_ns,
                cumulative_size=entry.filled_size + float(fill_data.get('sz', 0)),
                remaining_size=entry.remaining_size - float(fill_data.get('sz', 0))
            )

            # Update entry
            entry.filled_size = fill.cumulative_size
            entry.remaining_size = fill.remaining_size
            entry.last_fill_ns = fill_time_ns
            entry.last_update_ns = self._now_ns()

            # F3: Clear timeout flag on fill (order is alive)
            if entry.timeout_flagged:
                self._logger.info(f"Order {order_id}: Late fill arrived, clearing timeout flag")
                entry.timeout_flagged = False

            # Calculate slippage
            if entry.expected_price and entry.expected_price > 0:
                entry.slippage_bps = abs(fill.price - entry.expected_price) / entry.expected_price * 10000

            # Store fill
            self._order_fills[order_id].append(fill)

            # Update status
            if entry.remaining_size <= 0:
                entry.status = OrderStatus.FILLED
                self._tracked_orders.pop(order_id, None)
            else:
                entry.status = OrderStatus.PARTIAL

            self._logger.info(
                f"FILL: {entry.symbol} {entry.side.value} {fill.size} @ {fill.price} "
                f"(filled: {entry.filled_size}/{entry.original_size})"
            )

            # Notify callback
            if self._on_fill:
                self._on_fill(fill)

    async def _poll_loop(self):
        """Polling loop for order status."""
        while self._running:
            try:
                # Determine poll interval based on pending orders
                with self._lock:
                    has_pending = len(self._tracked_orders) > 0

                interval_ms = (
                    self._config.active_poll_interval_ms
                    if has_pending
                    else self._config.poll_interval_ms
                )

                await asyncio.sleep(interval_ms / 1000)

                if has_pending:
                    await self._poll_orders()
                    self._check_timeouts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(1)

    async def _poll_orders(self):
        """Poll order status from API."""
        if not self._wallet_address:
            return

        with self._lock:
            order_ids = list(self._tracked_orders.keys())

        if not order_ids:
            return

        try:
            # Query open orders
            payload = {
                "type": "openOrders",
                "user": self._wallet_address
            }

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return

                data = await response.json()

                # Build set of open order IDs
                open_orders: Set[str] = set()
                for order in data:
                    oid = str(order.get('oid', ''))
                    open_orders.add(oid)

                # Check tracked orders
                with self._lock:
                    for order_id in order_ids:
                        if order_id not in open_orders and order_id in self._tracked_orders:
                            # Order is no longer open - was filled or canceled
                            # Query fill history to determine
                            await self._check_order_fills(order_id)

        except Exception as e:
            self._logger.debug(f"Poll orders error: {e}")

    async def _check_order_fills(self, order_id: str):
        """Check fill history for a completed order."""
        if not self._wallet_address:
            return

        with self._lock:
            if order_id not in self._tracked_orders:
                return
            entry = self._tracked_orders[order_id]

        try:
            # Query fill history
            payload = {
                "type": "userFills",
                "user": self._wallet_address
            }

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return

                fills_data = await response.json()

                # Find fills for this order
                for fill_data in fills_data:
                    if str(fill_data.get('oid', '')) == order_id:
                        self._process_fill(fill_data)

        except Exception as e:
            self._logger.debug(f"Check order fills error: {e}")

    def _check_timeouts(self):
        """
        Check for timed out orders.

        F3: Timeout flags order but does not finalize unless:
        - Cancel has been confirmed
        - Order has partial fills (safe to close tracking)
        - Double-timeout (flagged twice with no fills between)
        """
        now_ns = self._now_ns()

        with self._lock:
            to_notify = []
            to_finalize = []

            for order_id, entry in list(self._tracked_orders.items()):
                elapsed_ms = (now_ns - entry.submit_time_ns) / 1_000_000

                timeout_ms = (
                    self._config.market_fill_timeout_ms
                    if entry.is_market
                    else self._config.limit_fill_timeout_ms
                )

                if elapsed_ms > timeout_ms:
                    if entry.timeout_flagged:
                        # F3: Double-timeout with no fills = finalize
                        to_finalize.append(order_id)
                        entry.status = OrderStatus.EXPIRED
                        self._logger.warning(
                            f"Order {order_id}: Double timeout, finalizing "
                            f"(filled: {entry.filled_size}/{entry.original_size})"
                        )
                    elif entry.cancel_confirmed:
                        # F3: Cancel confirmed = safe to finalize
                        to_finalize.append(order_id)
                        entry.status = OrderStatus.CANCELED
                        self._logger.info(f"Order {order_id}: Cancel confirmed, finalizing")
                    else:
                        # F3: First timeout = flag only, don't finalize
                        entry.timeout_flagged = True
                        to_notify.append(order_id)
                        self._logger.warning(
                            f"Order {order_id}: Timeout flagged (not finalized) "
                            f"- late fills may still arrive"
                        )

            # Notify timeouts (but keep tracking)
            for order_id in to_notify:
                if self._on_timeout:
                    self._on_timeout(order_id)

            # Finalize only confirmed cases
            for order_id in to_finalize:
                entry = self._tracked_orders.pop(order_id, None)
                if entry and self._on_timeout:
                    self._on_timeout(order_id)

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Get current status of a tracked order."""
        with self._lock:
            entry = self._tracked_orders.get(order_id)
            return entry.status if entry else None

    def get_fills(self, order_id: str) -> List[OrderFill]:
        """Get all fills for an order."""
        with self._lock:
            return list(self._order_fills.get(order_id, []))

    def get_pending_count(self) -> int:
        """Get number of orders being tracked."""
        with self._lock:
            return len(self._tracked_orders)

    def is_order_complete(self, order_id: str) -> bool:
        """Check if order is complete (filled, canceled, or timed out)."""
        with self._lock:
            if order_id not in self._tracked_orders:
                # No longer tracked = complete
                return order_id in self._order_fills
            return self._tracked_orders[order_id].status in (
                OrderStatus.FILLED,
                OrderStatus.CANCELED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED
            )

    def set_fill_callback(self, callback: Callable[[OrderFill], None]):
        """Set callback for fill events."""
        self._on_fill = callback

    def set_status_callback(self, callback: Callable[[OrderUpdate], None]):
        """Set callback for status changes."""
        self._on_status_change = callback

    def set_timeout_callback(self, callback: Callable[[str], None]):
        """Set callback for order timeouts."""
        self._on_timeout = callback

    def confirm_cancel(self, order_id: str):
        """
        Confirm that an order cancel was acknowledged by exchange.

        F3: This allows safe finalization after timeout.
        """
        with self._lock:
            if order_id in self._tracked_orders:
                self._tracked_orders[order_id].cancel_confirmed = True
                self._logger.debug(f"Cancel confirmed for order {order_id}")


@dataclass
class TrackingEntry:
    """Internal tracking entry for an order."""
    order_id: str
    symbol: str
    side: OrderSide
    original_size: float
    remaining_size: float
    expected_price: Optional[float] = None
    is_market: bool = True
    status: OrderStatus = OrderStatus.SUBMITTED

    submit_time_ns: int = 0
    last_update_ns: int = 0
    last_fill_ns: int = 0

    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    slippage_bps: float = 0.0

    # F1: Fill deduplication - prevent duplicate fill processing
    seen_fill_ids: Set[str] = field(default_factory=set)

    # F3: Timeout flag vs finalization
    timeout_flagged: bool = False
    cancel_confirmed: bool = False

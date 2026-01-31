"""
HLP18: Position Reconciliation.

Syncs local position state with exchange (source of truth).

The exchange is always authoritative. When discrepancies are found:
- Local has position, exchange doesn't: EMERGENCY - close immediately
- Exchange has position, local doesn't: Sync local, investigate
- Size mismatch: Trust exchange, adjust local and stops

Reconciliation runs:
- On startup
- After reconnection
- Periodically (every 30 seconds)
- On any suspected state corruption

Usage:
    reconciler = PositionReconciler(exchange_client, position_tracker)

    result = await reconciler.reconcile()
    if not result.is_clean:
        for action in result.actions_taken:
            print(f"Reconciliation action: {action}")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Protocol


class ReconciliationAction(Enum):
    """Actions taken during reconciliation."""
    NONE = auto()
    SYNCED_LOCAL = auto()           # Updated local to match exchange
    EMERGENCY_CLOSE = auto()        # Closed unknown local position
    ADJUSTED_SIZE = auto()          # Adjusted size to match exchange
    ADJUSTED_STOPS = auto()         # Updated stop orders
    CREATED_STOPS = auto()          # Created missing stop orders
    ALERTED = auto()                # Sent alert for investigation


@dataclass
class PositionSnapshot:
    """Snapshot of a position from either local or exchange."""
    symbol: str
    size: float
    side: str  # 'long' or 'short'
    entry_price: float
    unrealized_pnl: float = 0.0
    liquidation_price: Optional[float] = None
    stop_order_active: bool = False
    stop_price: Optional[float] = None


@dataclass
class ReconciliationDiff:
    """Difference found during reconciliation."""
    symbol: str
    diff_type: str  # 'local_only', 'exchange_only', 'size_mismatch', 'side_mismatch'
    local_position: Optional[PositionSnapshot]
    exchange_position: Optional[PositionSnapshot]
    severity: str  # 'critical', 'warning', 'info'
    message: str


@dataclass
class ReconciliationResult:
    """Result of reconciliation process."""
    timestamp: datetime
    is_clean: bool
    diffs_found: List[ReconciliationDiff] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Statistics
    local_positions: int = 0
    exchange_positions: int = 0
    positions_matched: int = 0
    positions_synced: int = 0
    emergency_closes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'is_clean': self.is_clean,
            'diffs_found': [
                {
                    'symbol': d.symbol,
                    'type': d.diff_type,
                    'severity': d.severity,
                    'message': d.message,
                }
                for d in self.diffs_found
            ],
            'actions_taken': self.actions_taken,
            'errors': self.errors,
            'local_positions': self.local_positions,
            'exchange_positions': self.exchange_positions,
            'positions_matched': self.positions_matched,
            'positions_synced': self.positions_synced,
            'emergency_closes': self.emergency_closes,
        }


class ExchangeClient(Protocol):
    """Protocol for exchange client."""

    async def get_positions(self) -> List[PositionSnapshot]:
        """Get all open positions from exchange."""
        ...

    async def close_position(self, symbol: str, market: bool = True) -> bool:
        """Close a position at market."""
        ...

    async def get_open_orders(self, symbol: str) -> List[Dict]:
        """Get open orders for a symbol."""
        ...

    async def place_stop_order(
        self, symbol: str, side: str, size: float, stop_price: float
    ) -> Optional[str]:
        """Place a stop order."""
        ...


class PositionTracker(Protocol):
    """Protocol for position tracker."""

    def get_all_positions(self) -> Dict[str, PositionSnapshot]:
        """Get all tracked positions."""
        ...

    def update_position(self, symbol: str, snapshot: PositionSnapshot):
        """Update a tracked position."""
        ...

    def remove_position(self, symbol: str):
        """Remove a position from tracking."""
        ...

    def add_position(self, snapshot: PositionSnapshot):
        """Add a position to tracking."""
        ...


class PositionReconciler:
    """
    Reconciles local position state with exchange.

    Exchange is the source of truth. Any discrepancy is resolved
    by trusting the exchange state.
    """

    def __init__(
        self,
        exchange_client: ExchangeClient,
        position_tracker: PositionTracker,
        logger: logging.Logger = None,
        size_tolerance: float = 0.0001,  # 0.01% size tolerance
        auto_create_stops: bool = True,
    ):
        """
        Initialize reconciler.

        Args:
            exchange_client: Client for exchange API
            position_tracker: Local position tracker
            logger: Logger instance
            size_tolerance: Tolerance for size matching (as ratio)
            auto_create_stops: Whether to auto-create missing stop orders
        """
        self._exchange = exchange_client
        self._tracker = position_tracker
        self._logger = logger or logging.getLogger(__name__)
        self._size_tolerance = size_tolerance
        self._auto_create_stops = auto_create_stops

        # Callbacks
        self._alert_callbacks: List = []

        # State
        self._last_reconcile: Optional[datetime] = None
        self._consecutive_failures: int = 0

    async def reconcile(self) -> ReconciliationResult:
        """
        Perform full reconciliation.

        Returns:
            ReconciliationResult with details of any actions taken
        """
        result = ReconciliationResult(
            timestamp=datetime.now(),
            is_clean=True,
        )

        try:
            # Get positions from both sources
            exchange_positions = await self._fetch_exchange_positions()
            local_positions = self._tracker.get_all_positions()

            result.exchange_positions = len(exchange_positions)
            result.local_positions = len(local_positions)

            # Build exchange position map
            exchange_map = {p.symbol: p for p in exchange_positions}
            local_symbols = set(local_positions.keys())
            exchange_symbols = set(exchange_map.keys())

            # Find positions only in local (CRITICAL - unknown exposure!)
            local_only = local_symbols - exchange_symbols
            for symbol in local_only:
                await self._handle_local_only(symbol, local_positions[symbol], result)

            # Find positions only on exchange (need to sync)
            exchange_only = exchange_symbols - local_symbols
            for symbol in exchange_only:
                await self._handle_exchange_only(symbol, exchange_map[symbol], result)

            # Check matched positions for discrepancies
            matched = local_symbols & exchange_symbols
            for symbol in matched:
                await self._handle_matched(
                    symbol,
                    local_positions[symbol],
                    exchange_map[symbol],
                    result,
                )
                result.positions_matched += 1

            # Update state
            self._last_reconcile = datetime.now()
            if result.is_clean:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1

        except Exception as e:
            self._logger.error(f"Reconciliation failed: {e}")
            result.errors.append(str(e))
            result.is_clean = False
            self._consecutive_failures += 1

        return result

    async def _fetch_exchange_positions(self) -> List[PositionSnapshot]:
        """Fetch positions from exchange with error handling."""
        try:
            return await self._exchange.get_positions()
        except Exception as e:
            self._logger.error(f"Failed to fetch exchange positions: {e}")
            raise

    async def _handle_local_only(
        self,
        symbol: str,
        local_pos: PositionSnapshot,
        result: ReconciliationResult,
    ):
        """
        Handle position that exists locally but not on exchange.

        This is CRITICAL - we think we have exposure but exchange says no.
        Could be:
        - Position was closed without our knowledge (stop hit, liquidation)
        - Stale local state after crash/restart
        - Bug in position tracking

        Action: Remove from local tracking, alert for investigation.
        """
        diff = ReconciliationDiff(
            symbol=symbol,
            diff_type='local_only',
            local_position=local_pos,
            exchange_position=None,
            severity='critical',
            message=f"Position exists locally but not on exchange: {local_pos.size} {symbol}",
        )
        result.diffs_found.append(diff)
        result.is_clean = False

        # Remove from local tracking
        self._tracker.remove_position(symbol)
        result.actions_taken.append(f"Removed ghost position: {symbol}")

        # Alert
        await self._send_alert(
            "POSITION_MISMATCH_LOCAL_ONLY",
            symbol,
            f"Local position {local_pos.size} {symbol} not found on exchange",
        )

        self._logger.critical(
            f"Ghost position detected: {symbol} exists locally but not on exchange. "
            f"Removed from tracking."
        )

    async def _handle_exchange_only(
        self,
        symbol: str,
        exchange_pos: PositionSnapshot,
        result: ReconciliationResult,
    ):
        """
        Handle position that exists on exchange but not locally.

        This is concerning - we have exposure we don't know about.
        Could be:
        - Manual trade on exchange
        - State lost after crash
        - Bug in position tracking

        Action: Sync to local state, create stop if needed, alert.
        """
        diff = ReconciliationDiff(
            symbol=symbol,
            diff_type='exchange_only',
            local_position=None,
            exchange_position=exchange_pos,
            severity='warning',
            message=f"Position exists on exchange but not locally: {exchange_pos.size} {symbol}",
        )
        result.diffs_found.append(diff)
        result.is_clean = False

        # Sync to local
        self._tracker.add_position(exchange_pos)
        result.actions_taken.append(f"Synced exchange position to local: {symbol}")
        result.positions_synced += 1

        # Create stop if needed and configured
        if self._auto_create_stops and not exchange_pos.stop_order_active:
            await self._create_emergency_stop(symbol, exchange_pos, result)

        # Alert
        await self._send_alert(
            "POSITION_MISMATCH_EXCHANGE_ONLY",
            symbol,
            f"Exchange position {exchange_pos.size} {symbol} not tracked locally",
        )

        self._logger.warning(
            f"Unknown exchange position detected: {symbol}. "
            f"Synced to local tracking."
        )

    async def _handle_matched(
        self,
        symbol: str,
        local_pos: PositionSnapshot,
        exchange_pos: PositionSnapshot,
        result: ReconciliationResult,
    ):
        """
        Handle position that exists in both local and exchange.

        Check for size or side mismatches.
        """
        # Check side mismatch (critical)
        if local_pos.side != exchange_pos.side:
            diff = ReconciliationDiff(
                symbol=symbol,
                diff_type='side_mismatch',
                local_position=local_pos,
                exchange_position=exchange_pos,
                severity='critical',
                message=f"Side mismatch for {symbol}: local={local_pos.side}, exchange={exchange_pos.side}",
            )
            result.diffs_found.append(diff)
            result.is_clean = False

            # Trust exchange
            self._tracker.update_position(symbol, exchange_pos)
            result.actions_taken.append(f"Fixed side mismatch for {symbol}")

            await self._send_alert(
                "POSITION_SIDE_MISMATCH",
                symbol,
                f"Local side {local_pos.side} != exchange side {exchange_pos.side}",
            )
            return

        # Check size mismatch
        size_diff = abs(local_pos.size - exchange_pos.size)
        if local_pos.size != 0:
            size_diff_pct = size_diff / abs(local_pos.size)
        else:
            size_diff_pct = 1.0 if exchange_pos.size != 0 else 0.0

        if size_diff_pct > self._size_tolerance:
            diff = ReconciliationDiff(
                symbol=symbol,
                diff_type='size_mismatch',
                local_position=local_pos,
                exchange_position=exchange_pos,
                severity='warning',
                message=f"Size mismatch for {symbol}: local={local_pos.size}, exchange={exchange_pos.size}",
            )
            result.diffs_found.append(diff)
            result.is_clean = False

            # Trust exchange
            self._tracker.update_position(symbol, exchange_pos)
            result.actions_taken.append(f"Adjusted size for {symbol}: {local_pos.size} -> {exchange_pos.size}")
            result.positions_synced += 1

            self._logger.warning(
                f"Size mismatch for {symbol}: local={local_pos.size}, exchange={exchange_pos.size}. "
                f"Updated to exchange value."
            )

        # Check stop order status
        if not exchange_pos.stop_order_active and self._auto_create_stops:
            await self._create_emergency_stop(symbol, exchange_pos, result)

    async def _create_emergency_stop(
        self,
        symbol: str,
        position: PositionSnapshot,
        result: ReconciliationResult,
    ):
        """Create an emergency stop order for a position."""
        try:
            # Calculate emergency stop (2% from current price as default)
            if position.side == 'long':
                stop_price = position.entry_price * 0.98
                stop_side = 'sell'
            else:
                stop_price = position.entry_price * 1.02
                stop_side = 'buy'

            order_id = await self._exchange.place_stop_order(
                symbol=symbol,
                side=stop_side,
                size=abs(position.size),
                stop_price=stop_price,
            )

            if order_id:
                result.actions_taken.append(f"Created emergency stop for {symbol} at {stop_price}")
                self._logger.info(f"Created emergency stop for {symbol}: {order_id}")
            else:
                result.errors.append(f"Failed to create stop for {symbol}")

        except Exception as e:
            self._logger.error(f"Failed to create emergency stop for {symbol}: {e}")
            result.errors.append(f"Stop creation failed for {symbol}: {e}")

    async def _send_alert(self, alert_type: str, symbol: str, message: str):
        """Send alert to registered callbacks."""
        for callback in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert_type, symbol, message)
                else:
                    callback(alert_type, symbol, message)
            except Exception as e:
                self._logger.error(f"Alert callback failed: {e}")

    def add_alert_callback(self, callback):
        """Add callback for reconciliation alerts."""
        self._alert_callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Get reconciler status."""
        return {
            'last_reconcile': self._last_reconcile.isoformat() if self._last_reconcile else None,
            'consecutive_failures': self._consecutive_failures,
            'auto_create_stops': self._auto_create_stops,
        }


async def run_periodic_reconciliation(
    reconciler: PositionReconciler,
    interval_sec: float = 30.0,
    logger: logging.Logger = None,
):
    """
    Run reconciliation periodically.

    Args:
        reconciler: Reconciler instance
        interval_sec: Seconds between reconciliations
        logger: Logger instance
    """
    logger = logger or logging.getLogger(__name__)

    while True:
        try:
            result = await reconciler.reconcile()

            if not result.is_clean:
                logger.warning(
                    f"Reconciliation found issues: {len(result.diffs_found)} diffs, "
                    f"{len(result.actions_taken)} actions taken"
                )
            else:
                logger.debug("Reconciliation clean")

        except Exception as e:
            logger.error(f"Periodic reconciliation failed: {e}")

        await asyncio.sleep(interval_sec)

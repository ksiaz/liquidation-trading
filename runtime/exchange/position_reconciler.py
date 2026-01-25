"""
HLP18: Position Reconciler.

Ensures local position state matches exchange state.

Exchange is ALWAYS the source of truth.

Reconciliation handles:
1. Unknown positions (close immediately)
2. Missing positions (reset local state)
3. Size mismatches (sync to exchange)
4. Stop order adjustment
"""

import time
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple
from threading import RLock

import aiohttp

from .types import (
    ReconciliationAction,
    ReconciliationResult,
    OrderSide,
)


@dataclass
class ReconcilerConfig:
    """Configuration for position reconciliation."""
    # Reconciliation frequency
    reconcile_interval_ms: int = 5_000  # Every 5 seconds
    post_order_delay_ms: int = 500      # After order event
    reconnect_reconcile: bool = True    # Reconcile on reconnection

    # Discrepancy thresholds
    size_tolerance_pct: float = 0.01    # 1% size difference = mismatch
    emergency_close: bool = True        # Auto-close unknown positions

    # API settings
    api_url: str = "https://api.hyperliquid.xyz"
    testnet_api_url: str = "https://api.hyperliquid-testnet.xyz"
    use_testnet: bool = False
    request_timeout: float = 10.0


@dataclass
class LocalPosition:
    """Local tracking of a position."""
    symbol: str
    side: OrderSide
    size: float
    entry_price: float
    stop_order_id: Optional[str] = None
    target_order_id: Optional[str] = None
    event_id: Optional[str] = None


class PositionReconciler:
    """
    Reconciles local position state with exchange.

    Key principle: Exchange is always right.

    On discrepancy:
    - Unknown position on exchange -> close immediately
    - Position missing on exchange -> clear local state
    - Size mismatch -> update local to match exchange

    Alerts operator on all discrepancies.
    """

    def __init__(
        self,
        config: ReconcilerConfig = None,
        wallet_address: Optional[str] = None,
        logger: logging.Logger = None
    ):
        self._config = config or ReconcilerConfig()
        self._wallet_address = wallet_address
        self._logger = logger or logging.getLogger(__name__)

        # API endpoint
        self._api_url = (
            self._config.testnet_api_url
            if self._config.use_testnet
            else self._config.api_url
        )

        # Local position state
        self._positions: Dict[str, LocalPosition] = {}

        # Reconciliation history
        self._results: List[ReconciliationResult] = []

        # Callbacks
        self._on_discrepancy: Optional[Callable[[ReconciliationResult], None]] = None
        self._on_emergency_close: Optional[Callable[[str, float], None]] = None

        # Background task
        self._reconcile_task: Optional[asyncio.Task] = None
        self._running = False

        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    async def start(self):
        """Start periodic reconciliation."""
        self._running = True
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout)
            )
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        self._logger.info("PositionReconciler started")

    async def stop(self):
        """Stop reconciliation."""
        self._running = False
        if self._reconcile_task:
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
        self._logger.info("PositionReconciler stopped")

    def set_local_position(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        entry_price: float,
        stop_order_id: str = None,
        target_order_id: str = None,
        event_id: str = None
    ):
        """Record a local position."""
        with self._lock:
            self._positions[symbol] = LocalPosition(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=entry_price,
                stop_order_id=stop_order_id,
                target_order_id=target_order_id,
                event_id=event_id
            )
            self._logger.info(f"Local position set: {symbol} {side.value} {size}")

    def clear_local_position(self, symbol: str):
        """Clear a local position."""
        with self._lock:
            if symbol in self._positions:
                del self._positions[symbol]
                self._logger.info(f"Local position cleared: {symbol}")

    def get_local_position(self, symbol: str) -> Optional[LocalPosition]:
        """Get local position for a symbol."""
        with self._lock:
            return self._positions.get(symbol)

    def get_all_local_positions(self) -> Dict[str, LocalPosition]:
        """Get all local positions."""
        with self._lock:
            return dict(self._positions)

    async def reconcile(self) -> List[ReconciliationResult]:
        """
        Perform position reconciliation.

        Returns list of discrepancies found and actions taken.
        """
        if not self._wallet_address:
            return []

        # Get exchange positions
        exchange_positions = await self._fetch_exchange_positions()

        results = []

        with self._lock:
            # Check exchange positions against local
            for symbol, exchange_pos in exchange_positions.items():
                local_pos = self._positions.get(symbol)

                if local_pos is None:
                    # Case 1: Unknown position on exchange
                    result = self._handle_unknown_position(symbol, exchange_pos)
                    results.append(result)

                elif not self._positions_match(local_pos, exchange_pos):
                    # Case 3: Size mismatch
                    result = self._handle_size_mismatch(symbol, local_pos, exchange_pos)
                    results.append(result)

            # Check local positions not on exchange
            for symbol, local_pos in list(self._positions.items()):
                if symbol not in exchange_positions:
                    # Case 2: Position missing on exchange
                    result = self._handle_missing_position(symbol, local_pos)
                    results.append(result)

        # Store results
        with self._lock:
            self._results.extend(results)
            # Keep last 100 results
            if len(self._results) > 100:
                self._results = self._results[-100:]

        return results

    async def _fetch_exchange_positions(self) -> Dict[str, Dict]:
        """Fetch current positions from exchange."""
        try:
            payload = {
                "type": "clearinghouseState",
                "user": self._wallet_address
            }

            async with self._session.post(
                f"{self._api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    self._logger.warning(f"Failed to fetch positions: {response.status}")
                    return {}

                data = await response.json()

                positions = {}
                for asset in data.get('assetPositions', []):
                    pos = asset.get('position', {})
                    coin = pos.get('coin', '')
                    szi = float(pos.get('szi', 0))

                    if coin and abs(szi) > 0:
                        positions[coin] = {
                            'symbol': coin,
                            'size': szi,
                            'side': OrderSide.BUY if szi > 0 else OrderSide.SELL,
                            'entry_price': float(pos.get('entryPx', 0)),
                            'liquidation_price': float(pos.get('liquidationPx', 0)) if pos.get('liquidationPx') else 0,
                            'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                        }

                return positions

        except Exception as e:
            self._logger.error(f"Error fetching positions: {e}")
            return {}

    def _positions_match(self, local: LocalPosition, exchange: Dict) -> bool:
        """Check if local and exchange positions match."""
        exchange_size = abs(exchange['size'])
        local_size = local.size

        # Check side
        exchange_side = OrderSide.BUY if exchange['size'] > 0 else OrderSide.SELL
        if local.side != exchange_side:
            return False

        # Check size within tolerance
        if local_size > 0:
            diff_pct = abs(exchange_size - local_size) / local_size
            if diff_pct > self._config.size_tolerance_pct:
                return False

        return True

    def _handle_unknown_position(self, symbol: str, exchange_pos: Dict) -> ReconciliationResult:
        """Handle position on exchange that we don't track locally."""
        size = exchange_pos['size']

        self._logger.error(
            f"UNKNOWN POSITION: {symbol} size={size} - not in local state"
        )

        result = ReconciliationResult(
            symbol=symbol,
            expected_size=0,
            actual_size=size,
            action=ReconciliationAction.EMERGENCY_CLOSE,
            discrepancy=abs(size),
            message=f"Unknown position detected - closing immediately"
        )

        # Notify callback for emergency close
        if self._on_emergency_close and self._config.emergency_close:
            self._on_emergency_close(symbol, size)

        if self._on_discrepancy:
            self._on_discrepancy(result)

        return result

    def _handle_missing_position(self, symbol: str, local_pos: LocalPosition) -> ReconciliationResult:
        """Handle position in local state but not on exchange."""
        self._logger.error(
            f"POSITION MISSING: {symbol} expected={local_pos.size} - not on exchange"
        )

        result = ReconciliationResult(
            symbol=symbol,
            expected_size=local_pos.size,
            actual_size=0,
            action=ReconciliationAction.RESET_STATE,
            discrepancy=local_pos.size,
            message=f"Position closed externally - resetting local state"
        )

        # Clear local position
        self._positions.pop(symbol, None)

        if self._on_discrepancy:
            self._on_discrepancy(result)

        return result

    def _handle_size_mismatch(
        self,
        symbol: str,
        local_pos: LocalPosition,
        exchange_pos: Dict
    ) -> ReconciliationResult:
        """Handle size mismatch between local and exchange."""
        exchange_size = abs(exchange_pos['size'])

        self._logger.warning(
            f"SIZE MISMATCH: {symbol} local={local_pos.size} exchange={exchange_size}"
        )

        result = ReconciliationResult(
            symbol=symbol,
            expected_size=local_pos.size,
            actual_size=exchange_size,
            action=ReconciliationAction.SYNC_LOCAL,
            discrepancy=abs(exchange_size - local_pos.size),
            message=f"Size mismatch - syncing to exchange"
        )

        # Update local position
        local_pos.size = exchange_size

        # Notify about potential stop adjustment
        if local_pos.stop_order_id:
            result.action = ReconciliationAction.ADJUST_STOP
            result.message = f"Size mismatch - syncing and adjusting stop order"

        if self._on_discrepancy:
            self._on_discrepancy(result)

        return result

    async def _reconcile_loop(self):
        """Background reconciliation loop."""
        while self._running:
            try:
                await asyncio.sleep(self._config.reconcile_interval_ms / 1000)
                results = await self.reconcile()

                for result in results:
                    if result.action != ReconciliationAction.NONE:
                        self._logger.warning(
                            f"Reconciliation: {result.symbol} - {result.action.name}: {result.message}"
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Reconciliation error: {e}")
                await asyncio.sleep(5)

    def trigger_reconcile(self):
        """Trigger an immediate reconciliation (e.g., after order event)."""
        if self._reconcile_task and not self._reconcile_task.done():
            # Schedule reconciliation soon
            asyncio.create_task(self._delayed_reconcile())

    async def _delayed_reconcile(self):
        """Reconcile after a short delay."""
        await asyncio.sleep(self._config.post_order_delay_ms / 1000)
        await self.reconcile()

    def get_results(self, limit: int = 50) -> List[ReconciliationResult]:
        """Get recent reconciliation results."""
        with self._lock:
            return list(self._results[-limit:])

    def get_mismatch_count(self) -> int:
        """Get count of mismatches detected."""
        with self._lock:
            return sum(
                1 for r in self._results
                if r.action != ReconciliationAction.NONE
            )

    def set_discrepancy_callback(self, callback: Callable[[ReconciliationResult], None]):
        """Set callback for discrepancy detection."""
        self._on_discrepancy = callback

    def set_emergency_close_callback(self, callback: Callable[[str, float], None]):
        """Set callback for emergency position close (symbol, size)."""
        self._on_emergency_close = callback

"""
P5: Startup Reconciliation.

Reconciles local persisted state with exchange state on startup.

This is CRITICAL for safe recovery after crashes:
1. Loads persisted positions from database
2. Queries exchange for actual positions
3. Detects and resolves discrepancies
4. Ensures local state matches exchange reality

Constitutional: Reports factual discrepancies, no interpretation.
"""

import time
import logging
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from enum import Enum

from runtime.position.types import Position, PositionState, Direction


class DiscrepancyType(Enum):
    """Types of state discrepancies."""
    GHOST_POSITION = "GHOST_POSITION"      # Local has position, exchange doesn't
    ORPHAN_POSITION = "ORPHAN_POSITION"    # Exchange has position, local doesn't
    SIZE_MISMATCH = "SIZE_MISMATCH"        # Both have position, sizes differ
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"  # Both have position, directions differ
    STATE_MISMATCH = "STATE_MISMATCH"      # Local in transitional state, exchange says different


class ReconciliationAction(Enum):
    """Actions to take for discrepancies."""
    SYNC_LOCAL_TO_EXCHANGE = "SYNC_LOCAL_TO_EXCHANGE"  # Update local to match exchange
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"     # Close unknown position on exchange
    RESET_TO_FLAT = "RESET_TO_FLAT"         # Reset local to FLAT
    MANUAL_REVIEW = "MANUAL_REVIEW"         # Requires human intervention
    NONE = "NONE"                           # No action needed


@dataclass
class Discrepancy:
    """Detected discrepancy between local and exchange state."""
    symbol: str
    type: DiscrepancyType
    local_state: Optional[str]
    local_size: Optional[float]
    local_direction: Optional[str]
    exchange_size: Optional[float]
    exchange_side: Optional[str]
    recommended_action: ReconciliationAction
    resolved: bool = False
    resolution_details: Optional[str] = None


@dataclass
class ReconciliationResult:
    """Result of startup reconciliation."""
    timestamp: float
    discrepancies_found: int
    discrepancies_resolved: int
    discrepancies_manual: int
    details: List[Discrepancy]
    success: bool
    error: Optional[str] = None


class StartupReconciler:
    """
    P5: Reconciles local state with exchange on startup.

    Safe recovery process:
    1. Load local persisted state
    2. Query exchange positions
    3. Compare and detect discrepancies
    4. Resolve discrepancies (sync local or flag for manual)
    5. Return reconciliation report

    Does NOT auto-trade or close positions without explicit config.
    """

    def __init__(
        self,
        logger: logging.Logger = None,
        auto_sync_local: bool = True,
        auto_close_orphans: bool = False,  # Conservative default
        size_tolerance_pct: float = 0.01   # 1% tolerance for size matching
    ):
        """Initialize reconciler.

        Args:
            logger: Logger instance
            auto_sync_local: Auto-update local state to match exchange
            auto_close_orphans: Auto-close positions exchange has but local doesn't
                               (DANGEROUS - default False)
            size_tolerance_pct: Tolerance for size comparison
        """
        self._logger = logger or logging.getLogger(__name__)
        self._auto_sync_local = auto_sync_local
        self._auto_close_orphans = auto_close_orphans
        self._size_tolerance = size_tolerance_pct

    async def reconcile(
        self,
        local_positions: Dict[str, Position],
        exchange_positions: List[Dict],
        position_repository=None,
        order_executor=None
    ) -> ReconciliationResult:
        """
        Perform startup reconciliation.

        Args:
            local_positions: Positions loaded from local database
            exchange_positions: Positions fetched from exchange API
            position_repository: Optional - for updating local state
            order_executor: Optional - for closing orphan positions

        Returns:
            ReconciliationResult with all discrepancies and resolutions
        """
        timestamp = time.time()
        discrepancies: List[Discrepancy] = []

        self._logger.info(
            f"P5: Starting reconciliation - {len(local_positions)} local, "
            f"{len(exchange_positions)} exchange positions"
        )

        # Build exchange position map
        exchange_map: Dict[str, Dict] = {}
        for pos in exchange_positions:
            symbol = pos.get('coin', pos.get('symbol', ''))
            if symbol:
                exchange_map[symbol] = pos

        # Check local positions against exchange
        for symbol, local_pos in local_positions.items():
            exchange_pos = exchange_map.get(symbol)

            if exchange_pos is None:
                # GHOST_POSITION: Local has position, exchange doesn't
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    type=DiscrepancyType.GHOST_POSITION,
                    local_state=local_pos.state.value,
                    local_size=float(local_pos.quantity) if local_pos.quantity else None,
                    local_direction=local_pos.direction.value if local_pos.direction else None,
                    exchange_size=None,
                    exchange_side=None,
                    recommended_action=ReconciliationAction.RESET_TO_FLAT
                ))
            else:
                # Both have position - check for mismatches
                discrepancy = self._compare_positions(symbol, local_pos, exchange_pos)
                if discrepancy:
                    discrepancies.append(discrepancy)

                # Remove from exchange map (processed)
                del exchange_map[symbol]

        # Check for orphan positions (exchange has, local doesn't)
        for symbol, exchange_pos in exchange_map.items():
            size = float(exchange_pos.get('szi', exchange_pos.get('size', 0)))
            if abs(size) > 0:  # Has actual position
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    type=DiscrepancyType.ORPHAN_POSITION,
                    local_state=None,
                    local_size=None,
                    local_direction=None,
                    exchange_size=abs(size),
                    exchange_side="LONG" if size > 0 else "SHORT",
                    recommended_action=(
                        ReconciliationAction.EMERGENCY_CLOSE
                        if self._auto_close_orphans
                        else ReconciliationAction.MANUAL_REVIEW
                    )
                ))

        # Resolve discrepancies
        resolved_count = 0
        manual_count = 0

        for disc in discrepancies:
            resolved, manual = await self._resolve_discrepancy(
                disc, position_repository, order_executor
            )
            if resolved:
                resolved_count += 1
            if manual:
                manual_count += 1

        success = manual_count == 0  # Success if no manual intervention needed

        result = ReconciliationResult(
            timestamp=timestamp,
            discrepancies_found=len(discrepancies),
            discrepancies_resolved=resolved_count,
            discrepancies_manual=manual_count,
            details=discrepancies,
            success=success,
            error=None if success else f"{manual_count} discrepancies require manual review"
        )

        self._logger.info(
            f"P5: Reconciliation complete - "
            f"found={len(discrepancies)}, resolved={resolved_count}, manual={manual_count}"
        )

        return result

    def _compare_positions(
        self,
        symbol: str,
        local: Position,
        exchange: Dict
    ) -> Optional[Discrepancy]:
        """Compare local and exchange position for mismatches."""
        # Parse exchange position
        exchange_size = float(exchange.get('szi', exchange.get('size', 0)))
        exchange_side = "LONG" if exchange_size > 0 else "SHORT" if exchange_size < 0 else None
        exchange_size = abs(exchange_size)

        local_size = float(local.quantity) if local.quantity else 0
        local_direction = local.direction.value if local.direction else None

        # Skip if both effectively empty
        if local_size < 0.0001 and exchange_size < 0.0001:
            return None

        # Check direction mismatch
        if local_direction and exchange_side and local_direction != exchange_side:
            return Discrepancy(
                symbol=symbol,
                type=DiscrepancyType.DIRECTION_MISMATCH,
                local_state=local.state.value,
                local_size=local_size,
                local_direction=local_direction,
                exchange_size=exchange_size,
                exchange_side=exchange_side,
                recommended_action=ReconciliationAction.MANUAL_REVIEW  # Dangerous to auto-fix
            )

        # Check size mismatch (beyond tolerance)
        if local_size > 0 and exchange_size > 0:
            size_diff_pct = abs(local_size - exchange_size) / max(local_size, exchange_size)
            if size_diff_pct > self._size_tolerance:
                return Discrepancy(
                    symbol=symbol,
                    type=DiscrepancyType.SIZE_MISMATCH,
                    local_state=local.state.value,
                    local_size=local_size,
                    local_direction=local_direction,
                    exchange_size=exchange_size,
                    exchange_side=exchange_side,
                    recommended_action=ReconciliationAction.SYNC_LOCAL_TO_EXCHANGE
                )

        # Check transitional state mismatches
        if local.state in (PositionState.ENTERING, PositionState.REDUCING, PositionState.CLOSING):
            # In transitional state but exchange shows settled position
            return Discrepancy(
                symbol=symbol,
                type=DiscrepancyType.STATE_MISMATCH,
                local_state=local.state.value,
                local_size=local_size,
                local_direction=local_direction,
                exchange_size=exchange_size,
                exchange_side=exchange_side,
                recommended_action=ReconciliationAction.SYNC_LOCAL_TO_EXCHANGE
            )

        return None

    async def _resolve_discrepancy(
        self,
        disc: Discrepancy,
        position_repository,
        order_executor
    ) -> Tuple[bool, bool]:
        """
        Resolve a single discrepancy.

        Returns:
            (resolved, requires_manual): Tuple of flags
        """
        if disc.recommended_action == ReconciliationAction.NONE:
            disc.resolved = True
            disc.resolution_details = "No action needed"
            return True, False

        if disc.recommended_action == ReconciliationAction.MANUAL_REVIEW:
            disc.resolved = False
            disc.resolution_details = "Requires manual review"
            self._logger.warning(
                f"P5: MANUAL REVIEW REQUIRED - {disc.symbol}: {disc.type.value} "
                f"(local={disc.local_direction} {disc.local_size}, "
                f"exchange={disc.exchange_side} {disc.exchange_size})"
            )
            return False, True

        if disc.recommended_action == ReconciliationAction.RESET_TO_FLAT:
            if self._auto_sync_local and position_repository:
                try:
                    flat_position = Position.create_flat(disc.symbol)
                    position_repository.save(flat_position)
                    disc.resolved = True
                    disc.resolution_details = "Reset local to FLAT (ghost position)"
                    self._logger.info(f"P5: Reset {disc.symbol} to FLAT (was ghost)")
                    return True, False
                except Exception as e:
                    disc.resolution_details = f"Failed to reset: {e}"
                    return False, True
            else:
                disc.resolution_details = "Auto-sync disabled or no repository"
                return False, True

        if disc.recommended_action == ReconciliationAction.SYNC_LOCAL_TO_EXCHANGE:
            if self._auto_sync_local and position_repository:
                try:
                    # Determine new state based on exchange
                    if disc.exchange_size and disc.exchange_size > 0:
                        # Exchange has position - sync to OPEN
                        direction = Direction.LONG if disc.exchange_side == "LONG" else Direction.SHORT
                        new_position = Position(
                            symbol=disc.symbol,
                            state=PositionState.OPEN,
                            direction=direction,
                            quantity=Decimal(str(disc.exchange_size)),
                            entry_price=None  # Unknown from exchange snapshot
                        )
                    else:
                        # Exchange has no position - reset to FLAT
                        new_position = Position.create_flat(disc.symbol)

                    position_repository.save(new_position)
                    disc.resolved = True
                    disc.resolution_details = f"Synced local to exchange: {new_position.state.value}"
                    self._logger.info(
                        f"P5: Synced {disc.symbol} to {new_position.state.value} "
                        f"({disc.exchange_side} {disc.exchange_size})"
                    )
                    return True, False
                except Exception as e:
                    disc.resolution_details = f"Failed to sync: {e}"
                    return False, True
            else:
                disc.resolution_details = "Auto-sync disabled or no repository"
                return False, True

        if disc.recommended_action == ReconciliationAction.EMERGENCY_CLOSE:
            if self._auto_close_orphans and order_executor:
                disc.resolution_details = "Auto-close orphans: NOT IMPLEMENTED (safety)"
                self._logger.error(
                    f"P5: ORPHAN POSITION on exchange - {disc.symbol}: "
                    f"{disc.exchange_side} {disc.exchange_size} - MANUAL CLOSE REQUIRED"
                )
                return False, True
            else:
                disc.resolution_details = "Auto-close disabled - requires manual intervention"
                self._logger.warning(
                    f"P5: Orphan position on exchange - {disc.symbol}: "
                    f"{disc.exchange_side} {disc.exchange_size}"
                )
                return False, True

        return False, True

    def generate_report(self, result: ReconciliationResult) -> str:
        """Generate human-readable reconciliation report."""
        lines = [
            "=" * 60,
            "P5: STARTUP RECONCILIATION REPORT",
            "=" * 60,
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result.timestamp))}",
            f"Status: {'SUCCESS' if result.success else 'REQUIRES ATTENTION'}",
            "",
            f"Discrepancies Found: {result.discrepancies_found}",
            f"Resolved: {result.discrepancies_resolved}",
            f"Requires Manual: {result.discrepancies_manual}",
            "",
        ]

        if result.details:
            lines.append("DETAILS:")
            lines.append("-" * 40)
            for disc in result.details:
                status = "✓" if disc.resolved else "⚠"
                lines.append(
                    f"  {status} {disc.symbol}: {disc.type.value}\n"
                    f"      Local: {disc.local_direction} {disc.local_size} ({disc.local_state})\n"
                    f"      Exchange: {disc.exchange_side} {disc.exchange_size}\n"
                    f"      Action: {disc.recommended_action.value}\n"
                    f"      Result: {disc.resolution_details or 'Pending'}"
                )
            lines.append("-" * 40)

        if result.error:
            lines.append(f"\nERROR: {result.error}")

        lines.append("=" * 60)

        return "\n".join(lines)

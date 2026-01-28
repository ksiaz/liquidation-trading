"""
EP-2 Strategy Test: Order Book Primitive Test Policy

TEMPORARY TEST POLICY for ghost trading verification.

Purpose: Generate test mandates using working order book primitives
         to verify the execution pipeline is functional.

Authority: Test/Verification only - NOT production strategy
"""

from dataclasses import dataclass
from typing import Optional
from runtime.position.types import PositionState


@dataclass(frozen=True)
class StrategyContext:
    """Immutable context for strategy execution."""
    context_id: str
    timestamp: float


@dataclass(frozen=True)
class PermissionOutput:
    """M6 permission result (from M6 scaffolding)."""
    result: str  # "ALLOWED" | "DENIED"
    mandate_id: str
    action_id: str
    reason_code: str
    timestamp: float


@dataclass(frozen=True)
class StrategyProposal:
    """Immutable strategy proposal for EP-3 arbitration."""
    strategy_id: str
    action_type: str  # Opaque string
    confidence: str  # Opaque label (NOT numeric)
    justification_ref: str  # Reference ID only
    timestamp: float
    direction: str = None  # "LONG" | "SHORT" for ENTRY


def generate_orderbook_test_proposal(
    *,
    resting_size,  # RestingSizeAtPrice | None
    order_consumption,  # OrderConsumption | None
    refill_event,  # RefillEvent | None
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None
) -> Optional[StrategyProposal]:
    """
    Test policy: Generate ENTRY mandate if consumption detected and no position.

    Structural condition: Order consumption occurred (structural fact).
    Action: Propose ENTRY if no position exists.

    This is a STUB for testing the execution pipeline.
    NOT a production strategy.
    """
    # Governance: Permission check
    if permission.result != "ALLOWED":
        return None

    # No position -> check for entry conditions
    if position_state is None:
        # Entry condition: Consumption event detected (structural fact)
        if order_consumption is not None:
            # Structural condition met: consumption occurred
            # Propose ENTRY
            return StrategyProposal(
                strategy_id="orderbook_test",
                action_type="ENTRY",
                confidence="TEST",
                justification_ref=f"consumption_{context.context_id}",
                timestamp=context.timestamp
            )

    # Position exists -> check for exit conditions
    else:
        # Exit condition: Refill event detected (structural fact)
        if refill_event is not None:
            # Structural condition met: refill occurred
            # Propose EXIT
            return StrategyProposal(
                strategy_id="orderbook_test",
                action_type="EXIT",
                confidence="TEST",
                justification_ref=f"refill_{context.context_id}",
                timestamp=context.timestamp
            )

    return None

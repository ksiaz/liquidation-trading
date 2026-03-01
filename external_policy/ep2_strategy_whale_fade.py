"""EP2 Whale Fade Strategy — fade whale accumulation+dump manipulation.

Stateless proposal generator following existing pattern.
Detects whale accumulation followed by sudden dump, then fades the dump
direction (mean reversion after artificial price dislocation).

Strategy ID: EP2-WHALE-FADE-V1
"""

from typing import Optional

from external_policy.ep2_strategy_geometry import (
    StrategyContext,
    PermissionOutput,
    StrategyProposal,
)
from runtime.position.types import PositionState
from runtime.whale.tracker import WhaleDumpSignal


STRATEGY_ID = "EP2-WHALE-FADE-V1"


def generate_whale_fade_proposal(
    *,
    symbol: str,
    whale_signal: WhaleDumpSignal,
    regime_metrics,
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None,
    regime_state=None,
) -> Optional[StrategyProposal]:
    """Generate whale fade entry proposal.

    Entry conditions (all must be true):
    1. whale_signal is not None (dump detected after accumulation)
    2. confidence >= 0.5
    3. regime_metrics is not None (data freshness)
    4. No existing position for this symbol
    5. Regime not DISABLED

    No DCA — single entry, no adds. Whale events are one-shot.

    Returns:
        StrategyProposal for ENTRY, or None if conditions not met.
    """
    # Permission gate
    if permission.result != "ALLOWED":
        return None

    # Data freshness
    if regime_metrics is None:
        return None

    # Regime gate: don't trade in DISABLED regime
    if regime_state is not None and hasattr(regime_state, 'name'):
        if regime_state.name == "DISABLED":
            return None

    # Position gate: no entry if already positioned
    if position_state is not None and position_state.name in ("ENTERING", "OPEN", "REDUCING"):
        return None

    # Confidence gate
    if whale_signal.confidence < 0.5:
        return None

    # Map confidence to label
    if whale_signal.confidence >= 0.8:
        confidence_label = "HIGH"
    elif whale_signal.confidence >= 0.6:
        confidence_label = "MEDIUM"
    else:
        confidence_label = "LOW"

    acc = whale_signal.accumulation
    print(
        f"[WHALE FADE] {symbol}: ENTRY {whale_signal.fade_direction} "
        f"conf={whale_signal.confidence:.2f} "
        f"dump=${whale_signal.dump_volume_usd:,.0f} in {whale_signal.dump_duration_sec:.0f}s "
        f"acc=${acc.total_volume_usd:,.0f} over {acc.duration_sec:.0f}s "
        f"pnl=${whale_signal.dump_closed_pnl:,.0f} "
        f"impact={acc.price_impact_bps:.0f}bp",
        flush=True,
    )

    return StrategyProposal(
        strategy_id=STRATEGY_ID,
        action_type="ENTRY",
        confidence=confidence_label,
        justification_ref=f"whale_dump_{whale_signal.dump_wallet[:8]}",
        timestamp=context.timestamp,
        direction=whale_signal.fade_direction,
    )

"""
Regime Classifier

Deterministic classification of market regime based on observable structural metrics.

Constitutional Authority:
- EXTERNAL_POLICY_CONSTITUTION.md Article III (Permitted Operations)
- EXTERNAL_POLICY_CONSTITUTION.md Article VII (Regime Mutual Exclusion)

Thresholds derived from market mechanics per EXTERNAL_POLICY_CONSTITUTION.md Article VI:
- VWAP distance: ATR-relative proximity (1.25 ATR for containment, 1.5 ATR for escape)
- ATR ratio: Volatility compression/expansion (0.80 for compression, 1.0 for expansion)
- Orderflow imbalance: Balance threshold (0.18 for balanced, 0.35 for dominant)
- Liquidation Z-score: Significance threshold (2.0 for low, 2.5 for high)

Hysteresis: Once a regime is established, relaxed thresholds keep it active.
This prevents chattering at threshold boundaries (e.g., orderflow oscillating
around 0.82 flipping SIDEWAYS↔DISABLED every few seconds with sparse HL fills).

Low-fill neutralization: When orderflow_fill_count < _MIN_OF_FILLS, orderflow
is treated as 0.5 (neutral). HL fills are sparse — a 60s window may have <10
taker fills, making the buy/sell ratio swing wildly between 0.0 and 1.0 on
each individual fill. This noise drove ~2000 SIDEWAYS↔DISABLED transitions
per session before this fix.

Entry thresholds = standard thresholds (must clearly qualify)
Hold thresholds = relaxed thresholds (must clearly DISqualify to leave)
"""

from typing import Optional

from .types import RegimeState, RegimeMetrics


# ─── Threshold Tables ────────────────────────────────────────────────
# Entry: used when transitioning INTO a regime (strict)
# Hold:  used when ALREADY in a regime (relaxed — harder to leave)

# Minimum fills required for orderflow to influence classification.
# Below this, orderflow is treated as 0.5 (neutral/balanced).
_MIN_OF_FILLS = 15

# SIDEWAYS entry / hold
_SW_VWAP_ENTRY = 1.25       # ≤ 1.25 × ATR_5m
_SW_VWAP_HOLD = 1.50        # ≤ 1.50 × ATR_5m (relax by 0.25 ATR)
_SW_ATR_RATIO_ENTRY = 0.80  # < 0.80
_SW_ATR_RATIO_HOLD = 0.95   # < 0.95 (relax by 0.15)
_SW_OF_DEV_ENTRY = 0.32     # |of - 0.5| < 0.32 → 0.18–0.82
_SW_OF_DEV_HOLD = 0.40      # |of - 0.5| < 0.40 → 0.10–0.90
_SW_LIQ_Z_ENTRY = 2.0       # < 2.0
_SW_LIQ_Z_HOLD = 2.5        # < 2.5

# EXPANSION entry / hold
_EX_VWAP_ENTRY = 1.50       # ≥ 1.50 × ATR_5m
_EX_VWAP_HOLD = 1.25        # ≥ 1.25 × ATR_5m (relax by 0.25 ATR)
_EX_ATR_RATIO_ENTRY = 1.00  # ≥ 1.00
_EX_ATR_RATIO_HOLD = 0.85   # ≥ 0.85 (relax by 0.15)
_EX_OF_DEV_ENTRY = 0.15     # |of - 0.5| ≥ 0.15
_EX_OF_DEV_HOLD = 0.10      # |of - 0.5| ≥ 0.10 (relax by 0.05)
_EX_LIQ_Z_ENTRY = 2.5       # ≥ 2.5
_EX_LIQ_Z_HOLD = 2.0        # ≥ 2.0


def classify_regime(
    metrics: RegimeMetrics,
    current_state: Optional[RegimeState] = None
) -> RegimeState:
    """
    Classify market regime based on observable structural metrics.

    Regimes are mutually exclusive. Only one regime can be active at a time.
    Returns DISABLED when no regime criteria are met.

    Hysteresis: when current_state is provided, uses relaxed thresholds
    for the active regime (harder to leave) and strict thresholds for
    entering a new regime.

    Args:
        metrics: Observable regime metrics
        current_state: Previous regime state (enables hysteresis)

    Returns:
        RegimeState: SIDEWAYS_ACTIVE, EXPANSION_ACTIVE, or DISABLED
    """
    # Neutralize noisy orderflow when fill count is too low
    if metrics.orderflow_fill_count < _MIN_OF_FILLS:
        metrics = RegimeMetrics(
            vwap_distance=metrics.vwap_distance,
            atr_5m=metrics.atr_5m,
            atr_30m=metrics.atr_30m,
            orderflow_imbalance=0.5,
            liquidation_zscore=metrics.liquidation_zscore,
            orderflow_fill_count=metrics.orderflow_fill_count,
        )

    # If currently in a regime, check if we should HOLD it (relaxed thresholds)
    if current_state == RegimeState.SIDEWAYS_ACTIVE:
        if _check_sideways_hold(metrics):
            return RegimeState.SIDEWAYS_ACTIVE
        # Lost SIDEWAYS — check if we jump to EXPANSION (strict entry)
        if _check_expansion_entry(metrics):
            return RegimeState.EXPANSION_ACTIVE
        return RegimeState.DISABLED

    if current_state == RegimeState.EXPANSION_ACTIVE:
        if _check_expansion_hold(metrics):
            return RegimeState.EXPANSION_ACTIVE
        # Lost EXPANSION — check if we jump to SIDEWAYS (strict entry)
        if _check_sideways_entry(metrics):
            return RegimeState.SIDEWAYS_ACTIVE
        return RegimeState.DISABLED

    # DISABLED or no previous state — use strict entry thresholds
    sideways = _check_sideways_entry(metrics)
    expansion = _check_expansion_entry(metrics)

    if sideways and expansion:
        return RegimeState.DISABLED
    if sideways:
        return RegimeState.SIDEWAYS_ACTIVE
    if expansion:
        return RegimeState.EXPANSION_ACTIVE
    return RegimeState.DISABLED


# ─── SIDEWAYS ────────────────────────────────────────────────────────

def _check_sideways_entry(metrics: RegimeMetrics) -> bool:
    """Check SIDEWAYS entry with strict thresholds."""
    if metrics.atr_30m <= 0:
        return False
    return (
        metrics.vwap_distance <= _SW_VWAP_ENTRY * metrics.atr_5m
        and metrics.atr_5m / metrics.atr_30m < _SW_ATR_RATIO_ENTRY
        and abs(metrics.orderflow_imbalance - 0.5) < _SW_OF_DEV_ENTRY
        and metrics.liquidation_zscore < _SW_LIQ_Z_ENTRY
    )


def _check_sideways_hold(metrics: RegimeMetrics) -> bool:
    """Check SIDEWAYS hold with relaxed thresholds (harder to leave)."""
    if metrics.atr_30m <= 0:
        return False
    return (
        metrics.vwap_distance <= _SW_VWAP_HOLD * metrics.atr_5m
        and metrics.atr_5m / metrics.atr_30m < _SW_ATR_RATIO_HOLD
        and abs(metrics.orderflow_imbalance - 0.5) < _SW_OF_DEV_HOLD
        and metrics.liquidation_zscore < _SW_LIQ_Z_HOLD
    )


# ─── EXPANSION ───────────────────────────────────────────────────────

def _check_expansion_entry(metrics: RegimeMetrics) -> bool:
    """Check EXPANSION entry with strict thresholds."""
    if metrics.atr_30m <= 0:
        return False
    return (
        metrics.vwap_distance >= _EX_VWAP_ENTRY * metrics.atr_5m
        and metrics.atr_5m / metrics.atr_30m >= _EX_ATR_RATIO_ENTRY
        and abs(metrics.orderflow_imbalance - 0.5) >= _EX_OF_DEV_ENTRY
        and metrics.liquidation_zscore >= _EX_LIQ_Z_ENTRY
    )


def _check_expansion_hold(metrics: RegimeMetrics) -> bool:
    """Check EXPANSION hold with relaxed thresholds (harder to leave)."""
    if metrics.atr_30m <= 0:
        return False
    return (
        metrics.vwap_distance >= _EX_VWAP_HOLD * metrics.atr_5m
        and metrics.atr_5m / metrics.atr_30m >= _EX_ATR_RATIO_HOLD
        and abs(metrics.orderflow_imbalance - 0.5) >= _EX_OF_DEV_HOLD
        and metrics.liquidation_zscore >= _EX_LIQ_Z_HOLD
    )

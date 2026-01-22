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

All thresholds are from market mechanics, NOT from backtest optimization.
"""

from .types import RegimeState, RegimeMetrics


def classify_regime(metrics: RegimeMetrics) -> RegimeState:
    """
    Classify market regime based on observable structural metrics.

    Regimes are mutually exclusive. Only one regime can be active at a time.
    Returns DISABLED when no regime criteria are met.

    Constitutional Compliance:
    - Deterministic classification (no randomness)
    - No confidence scoring
    - No quality ranking ("SIDEWAYS better than EXPANSION")
    - Thresholds from market mechanics (not backtest optimization)

    Args:
        metrics: Observable regime metrics

    Returns:
        RegimeState: SIDEWAYS_ACTIVE, EXPANSION_ACTIVE, or DISABLED
    """
    # Evaluate SIDEWAYS conditions
    sideways_conditions = _check_sideways_conditions(metrics)

    # Evaluate EXPANSION conditions
    expansion_conditions = _check_expansion_conditions(metrics)

    # Mutual exclusion: Only one regime can be active
    # If both sets of conditions met simultaneously (edge case), DISABLED
    if sideways_conditions and expansion_conditions:
        # Structural ambiguity - neither regime clearly established
        return RegimeState.DISABLED

    if sideways_conditions:
        return RegimeState.SIDEWAYS_ACTIVE

    if expansion_conditions:
        return RegimeState.EXPANSION_ACTIVE

    # No regime criteria met
    return RegimeState.DISABLED


def _check_sideways_conditions(metrics: RegimeMetrics) -> bool:
    """
    Check if SIDEWAYS regime conditions are met.

    SIDEWAYS regime indicates:
    - Price contained near VWAP (≤ 1.25 ATR)
    - Volatility compressed (ATR_5m < 0.80 × ATR_30m)
    - Orderflow balanced (imbalance < 0.18)
    - Liquidations subdued (zscore < 2.0)

    All conditions must be met (AND logic).

    Thresholds from market mechanics:
    - 1.25 ATR: Balance point for range-bound behavior
    - 0.80 ratio: Volatility compression indicator
    - 0.18 imbalance: Near-neutral orderflow (0.5 ± 0.32)
    - 2.0 zscore: Below 2-sigma threshold

    Returns:
        True if all SIDEWAYS conditions met
    """
    # Condition 1: VWAP containment
    vwap_contained = metrics.vwap_distance <= 1.25 * metrics.atr_5m

    # Condition 2: Volatility compression
    volatility_compressed = metrics.atr_5m / metrics.atr_30m < 0.80

    # Condition 3: Orderflow balanced
    orderflow_balanced = metrics.orderflow_imbalance < 0.18

    # Condition 4: Liquidations subdued
    liquidations_low = metrics.liquidation_zscore < 2.0

    # All conditions must be met
    return (
        vwap_contained
        and volatility_compressed
        and orderflow_balanced
        and liquidations_low
    )


def _check_expansion_conditions(metrics: RegimeMetrics) -> bool:
    """
    Check if EXPANSION regime conditions are met.

    EXPANSION regime indicates:
    - Price escaping VWAP (≥ 1.5 ATR)
    - Volatility expanding (ATR_5m ≥ 1.0 × ATR_30m)
    - Orderflow dominant (imbalance ≥ 0.35)
    - Liquidations elevated (zscore ≥ 2.5)

    All conditions must be met (AND logic).

    Thresholds from market mechanics:
    - 1.5 ATR: Breakout threshold for momentum behavior
    - 1.0 ratio: Volatility expansion indicator
    - 0.35 imbalance: One-sided flow (0.5 + 0.15 bias)
    - 2.5 zscore: Above 2.5-sigma threshold

    Returns:
        True if all EXPANSION conditions met
    """
    # Condition 1: VWAP escape
    vwap_escaped = metrics.vwap_distance >= 1.5 * metrics.atr_5m

    # Condition 2: Volatility expansion
    volatility_expanded = metrics.atr_5m / metrics.atr_30m >= 1.0

    # Condition 3: Orderflow dominant
    orderflow_dominant = metrics.orderflow_imbalance >= 0.35

    # Condition 4: Liquidations elevated
    liquidations_high = metrics.liquidation_zscore >= 2.5

    # All conditions must be met
    return (
        vwap_escaped
        and volatility_expanded
        and orderflow_dominant
        and liquidations_high
    )

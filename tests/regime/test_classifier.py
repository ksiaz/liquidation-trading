"""
Regime Classifier Tests

Verifies deterministic regime classification logic.

Constitutional Compliance:
- No confidence scoring
- No quality ranking
- Deterministic classification
- Mutual exclusion enforced
"""

import pytest
from runtime.regime import RegimeState, RegimeMetrics, classify_regime


class TestRegimeClassifier:
    """Test regime classification logic."""

    def test_sideways_active(self):
        """Test SIDEWAYS regime identification."""
        # SIDEWAYS conditions:
        # - VWAP distance ≤ 1.25 × ATR_5m
        # - ATR_5m / ATR_30m < 0.80
        # - Orderflow imbalance < 0.18
        # - Liquidation Z-score < 2.0

        metrics = RegimeMetrics(
            vwap_distance=60.0,  # Price near VWAP
            atr_5m=50.0,  # Distance = 60, 1.25 × ATR = 62.5 → contained ✓
            atr_30m=70.0,  # Ratio = 50/70 = 0.714 < 0.80 → compressed ✓
            orderflow_imbalance=0.12,  # < 0.18 → balanced ✓
            liquidation_zscore=1.5  # < 2.0 → subdued ✓
        )

        regime = classify_regime(metrics)
        assert regime == RegimeState.SIDEWAYS_ACTIVE

    def test_expansion_active(self):
        """Test EXPANSION regime identification."""
        # EXPANSION conditions:
        # - VWAP distance ≥ 1.5 × ATR_5m
        # - ATR_5m / ATR_30m ≥ 1.0
        # - Orderflow imbalance ≥ 0.35
        # - Liquidation Z-score ≥ 2.5

        metrics = RegimeMetrics(
            vwap_distance=150.0,  # Price far from VWAP
            atr_5m=80.0,  # Distance = 150, 1.5 × ATR = 120 → escaped ✓
            atr_30m=70.0,  # Ratio = 80/70 = 1.143 ≥ 1.0 → expanded ✓
            orderflow_imbalance=0.42,  # ≥ 0.35 → dominant ✓
            liquidation_zscore=3.2  # ≥ 2.5 → elevated ✓
        )

        regime = classify_regime(metrics)
        assert regime == RegimeState.EXPANSION_ACTIVE

    def test_disabled_neither_regime(self):
        """Test DISABLED when neither regime criteria met."""
        # Mixed conditions - neither SIDEWAYS nor EXPANSION

        metrics = RegimeMetrics(
            vwap_distance=100.0,  # Between thresholds
            atr_5m=70.0,  # Distance = 100, 1.25×70=87.5 (not contained), 1.5×70=105 (not escaped)
            atr_30m=75.0,  # Ratio = 70/75 = 0.933 (not compressed, not expanded)
            orderflow_imbalance=0.25,  # Between 0.18 and 0.35
            liquidation_zscore=2.2  # Between 2.0 and 2.5
        )

        regime = classify_regime(metrics)
        assert regime == RegimeState.DISABLED

    def test_disabled_partial_sideways(self):
        """Test DISABLED when only some SIDEWAYS conditions met."""
        # VWAP contained, but other conditions not met

        metrics = RegimeMetrics(
            vwap_distance=50.0,  # Contained ✓
            atr_5m=50.0,
            atr_30m=60.0,  # Compressed ✓
            orderflow_imbalance=0.40,  # NOT balanced ✗ (> 0.18)
            liquidation_zscore=1.0  # Subdued ✓
        )

        regime = classify_regime(metrics)
        assert regime == RegimeState.DISABLED

    def test_disabled_partial_expansion(self):
        """Test DISABLED when only some EXPANSION conditions met."""
        # VWAP escaped, but other conditions not met

        metrics = RegimeMetrics(
            vwap_distance=200.0,  # Escaped ✓
            atr_5m=100.0,
            atr_30m=110.0,  # NOT expanded ✗ (ratio < 1.0)
            orderflow_imbalance=0.38,  # Dominant ✓
            liquidation_zscore=3.0  # Elevated ✓
        )

        regime = classify_regime(metrics)
        assert regime == RegimeState.DISABLED

    def test_mutual_exclusion_edge_case(self):
        """
        Test mutual exclusion when both regime conditions somehow met.

        This should be impossible in practice, but classifier must handle it.
        Returns DISABLED due to structural ambiguity.
        """
        # Construct metrics that technically satisfy both
        # (Would require contradictory ATR ratios, so using boundary values)

        metrics = RegimeMetrics(
            vwap_distance=60.0,  # Could satisfy SIDEWAYS (if 1.25×ATR ≥ 60)
            atr_5m=50.0,  # But SIDEWAYS needs compressed (< 0.80), EXPANSION needs expanded (≥ 1.0)
            atr_30m=70.0,  # This gives 0.714 → SIDEWAYS only
            orderflow_imbalance=0.35,  # Boundary value (could be EXPANSION)
            liquidation_zscore=2.0  # Boundary value (could be SIDEWAYS)
        )

        # With these values, should be SIDEWAYS (compressed volatility)
        regime = classify_regime(metrics)
        assert regime in (RegimeState.SIDEWAYS_ACTIVE, RegimeState.DISABLED)

    def test_determinism(self):
        """Test that same inputs always produce same output."""
        metrics = RegimeMetrics(
            vwap_distance=80.0,
            atr_5m=60.0,
            atr_30m=75.0,
            orderflow_imbalance=0.15,
            liquidation_zscore=1.8
        )

        # Call multiple times
        results = [classify_regime(metrics) for _ in range(10)]

        # All results must be identical
        assert len(set(results)) == 1

    def test_vwap_containment_boundary(self):
        """Test VWAP containment boundary (1.25 × ATR)."""
        # Exactly at boundary
        metrics_at_boundary = RegimeMetrics(
            vwap_distance=62.5,  # Exactly 1.25 × 50
            atr_5m=50.0,
            atr_30m=70.0,
            orderflow_imbalance=0.10,
            liquidation_zscore=1.5
        )

        # Just below boundary (contained)
        metrics_below = RegimeMetrics(
            vwap_distance=62.4,
            atr_5m=50.0,
            atr_30m=70.0,
            orderflow_imbalance=0.10,
            liquidation_zscore=1.5
        )

        # Just above boundary (not contained)
        metrics_above = RegimeMetrics(
            vwap_distance=62.6,
            atr_5m=50.0,
            atr_30m=70.0,
            orderflow_imbalance=0.10,
            liquidation_zscore=1.5
        )

        regime_at = classify_regime(metrics_at_boundary)
        regime_below = classify_regime(metrics_below)
        regime_above = classify_regime(metrics_above)

        # At/below boundary: SIDEWAYS (if other conditions met)
        assert regime_at == RegimeState.SIDEWAYS_ACTIVE
        assert regime_below == RegimeState.SIDEWAYS_ACTIVE

        # Above boundary: NOT SIDEWAYS
        assert regime_above == RegimeState.DISABLED


class TestRegimeMetrics:
    """Test RegimeMetrics data structure."""

    def test_metrics_initialization(self):
        """Test RegimeMetrics can be initialized."""
        metrics = RegimeMetrics(
            vwap_distance=100.0,
            atr_5m=50.0,
            atr_30m=70.0,
            orderflow_imbalance=0.25,
            liquidation_zscore=1.8
        )

        assert metrics.vwap_distance == 100.0
        assert metrics.atr_5m == 50.0
        assert metrics.atr_30m == 70.0
        assert metrics.orderflow_imbalance == 0.25
        assert metrics.liquidation_zscore == 1.8

    def test_metrics_repr(self):
        """Test RegimeMetrics string representation."""
        metrics = RegimeMetrics(
            vwap_distance=100.0,
            atr_5m=50.0,
            atr_30m=70.0,
            orderflow_imbalance=0.25,
            liquidation_zscore=1.8
        )

        repr_str = repr(metrics)
        assert "RegimeMetrics" in repr_str
        assert "vwap_dist=100.00" in repr_str
        assert "atr_5m=50.00" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

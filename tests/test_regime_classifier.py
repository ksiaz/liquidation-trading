"""
Unit Tests for Regime Classifier Module

Tests implement requirements from PROMPT 4:
- SIDEWAYS conditions (ALL 4 must be met)
- EXPANSION conditions (ALL 4 must be met)
- DISABLED fallback
- NULL metric handling
- Transition logging
- Deterministic behavior

RULE: All tests are deterministic.
RULE: Regime is a GATE, not a signal.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.metrics.types import DerivedMetrics
from masterframe.regime_classifier import (
    RegimeType,
    RegimeState,
    RegimeTransition,
    RegimeClassifier,
)


class TestSidewaysConditions:
    """Test SIDEWAYS regime conditions."""
    
    def create_sideways_metrics(self) -> DerivedMetrics:
        """Create metrics that satisfy ALL SIDEWAYS conditions."""
        return DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,      # Will use for condition 1
            atr_30m=2.0,     # ATR ratio = 1.0/2.0 = 0.5 < 0.80 ✓
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,  # Imbalance = 0/200 = 0 < 0.18 ✓
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,  # < 2.0 ✓
            oi_delta=500.0,
        )
    
    def test_sideways_all_conditions_met(self):
        """All SIDEWAYS conditions met → SIDEWAYS regime."""
        classifier = RegimeClassifier()
        metrics = self.create_sideways_metrics()
        
        # Price close to VWAP: abs(100.5 - 100.0) = 0.5 ≤ 1.25*1.0 ✓
        price = 100.5
        
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.SIDEWAYS
        assert regime_state.all_conditions_met()
        assert classifier.get_current_regime() == RegimeType.SIDEWAYS
    
    def test_sideways_condition_1_failed(self):
        """SIDEWAYS condition 1 fails → DISABLED."""
        classifier = RegimeClassifier()
        metrics = self.create_sideways_metrics()
        
        # Price too far from VWAP: abs(105 - 100) = 5 > 1.25*1.0 ✗
        price = 105.0
        
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED
        assert not regime_state.condition_1_met
    
    def test_sideways_condition_2_failed(self):
        """SIDEWAYS condition 2 fails → DISABLED."""
        classifier = RegimeClassifier()
        metrics = self.create_sideways_metrics()
        
        # ATR ratio too high: 1.5/2.0 = 0.75, but set it to fail
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.8,  # Ratio = 1.8/2.0 = 0.9 >= 0.80 ✗
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        price = 100.5
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED
        assert not regime_state.condition_2_met
    
    def test_sideways_condition_3_failed(self):
        """SIDEWAYS condition 3 fails → DISABLED."""
        classifier = RegimeClassifier()
        
        # High volume imbalance: 150/200 = 0.25 >= 0.18 ✗
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=150.0,  # Imbalance = 50/200 = 0.25
            taker_sell_volume_30s=50.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        price = 100.5
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED
        assert not regime_state.condition_3_met
    
    def test_sideways_condition_4_failed(self):
        """SIDEWAYS condition 4 fails → DISABLED."""
        classifier = RegimeClassifier()
        metrics = self.create_sideways_metrics()
        
        # High liquidation z-score: 2.5 >= 2.0 ✗
        metrics = DerivedMetrics(
            timestamp=metrics.timestamp,
            vwap=metrics.vwap,
            atr_1m=metrics.atr_1m,
            atr_5m=metrics.atr_5m,
            atr_30m=metrics.atr_30m,
            taker_buy_volume_10s=metrics.taker_buy_volume_10s,
            taker_sell_volume_10s=metrics.taker_sell_volume_10s,
            taker_buy_volume_30s=metrics.taker_buy_volume_30s,
            taker_sell_volume_30s=metrics.taker_sell_volume_30s,
            liquidation_zscore=2.5,  # >= 2.0 ✗
            oi_delta=metrics.oi_delta,
        )
        
        price = 100.5
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED
        assert not regime_state.condition_4_met


class TestExpansionConditions:
    """Test EXPANSION regime conditions."""
    
    def create_expansion_metrics(self) -> DerivedMetrics:
        """Create metrics that satisfy ALL EXPANSION conditions."""
        return DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=2.0,      # Will use for condition 1
            atr_30m=1.5,     # ATR ratio = 2.0/1.5 = 1.33 >= 1.0 ✓
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=180.0,  # Imbalance = 130/200 = 0.65 >= 0.35 ✓
            taker_sell_volume_30s=20.0,
            liquidation_zscore=3.0,  # >= 2.5 ✓
            oi_delta=2000.0,  # > 1000 ✓
        )
    
    def test_expansion_all_conditions_met(self):
        """All EXPANSION conditions met → EXPANSION regime."""
        classifier = RegimeClassifier()
        metrics = self.create_expansion_metrics()
        
        # Price far from VWAP: abs(103.5 - 100.0) = 3.5 >= 1.5*2.0 ✓
        price = 103.5
        
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.EXPANSION
        assert regime_state.all_conditions_met()
        assert classifier.get_current_regime() == RegimeType.EXPANSION
    
    def test_expansion_condition_4_oi_delta_satisfies(self):
        """EXPANSION condition 4 satisfied by OI delta alone."""
        classifier = RegimeClassifier()
        
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=2.0,
            atr_30m=1.5,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=180.0,
            taker_sell_volume_30s=20.0,
            liquidation_zscore=1.0,  # < 2.5 (doesn't satisfy alone)
            oi_delta=2000.0,  # > 1000 ✓ (satisfies alone)
        )
        
        price = 103.5
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.EXPANSION
        assert regime_state.condition_4_met
    
    def test_expansion_condition_4_liq_zscore_satisfies(self):
        """EXPANSION condition 4 satisfied by liq zscore alone."""
        classifier = RegimeClassifier()
        
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=2.0,
            atr_30m=1.5,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=180.0,
            taker_sell_volume_30s=20.0,
            liquidation_zscore=3.0,  # >= 2.5 ✓
            oi_delta=500.0,  # < 1000 (doesn't satisfy alone)
        )
        
        price = 103.5
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.EXPANSION
        assert regime_state.condition_4_met
    
    def test_expansion_one_condition_failed(self):
        """One EXPANSION condition fails → DISABLED."""
        classifier = RegimeClassifier()
        metrics = self.create_expansion_metrics()
        
        # Price too close to VWAP: abs(100.5 - 100.0) = 0.5 < 1.5*2.0 ✗
        price = 100.5
        
        regime_state = classifier.classify(price, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED
        assert not regime_state.condition_1_met


class TestNullMetrics:
    """Test NULL metric handling."""
    
    def test_null_vwap_returns_disabled(self):
        """NULL VWAP → DISABLED."""
        classifier = RegimeClassifier()
        
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=None,  # NULL
            atr_1m=0.5,
            atr_5m=1.0,
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        regime_state = classifier.classify(100.0, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED
    
    def test_null_atr_returns_disabled(self):
        """NULL ATR → DISABLED."""
        classifier = RegimeClassifier()
        
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=None,  # NULL
            atr_5m=None,  # NULL
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        regime_state = classifier.classify(100.0, metrics, time.time())
        
        assert regime_state.regime == RegimeType.DISABLED


class TestRegimeTransitions:
    """Test regime transition logging."""
    
    def test_regime_transition_logged(self):
        """Regime change → transition logged."""
        classifier = RegimeClassifier()
        
        # Start with SIDEWAYS metrics
        sideways_metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        regime1 = classifier.classify(100.5, sideways_metrics, time.time())
        assert regime1.regime == RegimeType.SIDEWAYS
        
        # Change to EXPANSION metrics
        expansion_metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=2.0,
            atr_30m=1.5,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=180.0,
            taker_sell_volume_30s=20.0,
            liquidation_zscore=3.0,
            oi_delta=2000.0,
        )
        
        regime2 = classifier.classify(103.5, expansion_metrics, time.time())
        assert regime2.regime == RegimeType.EXPANSION
        
        # Check transition was logged
        history = classifier.get_transition_history()
        assert len(history) >= 2  # DISABLED → SIDEWAYS, SIDEWAYS → EXPANSION
        
        # Find the SIDEWAYS → EXPANSION transition
        sideways_to_expansion = [t for t in history if t.from_regime == RegimeType.SIDEWAYS]
        assert len(sideways_to_expansion) > 0
        assert sideways_to_expansion[0].to_regime == RegimeType.EXPANSION


class TestDeterministic:
    """Test deterministic behavior."""
    
    def test_same_inputs_same_regime(self):
        """Same inputs → same regime."""
        classifier1 = RegimeClassifier()
        classifier2 = RegimeClassifier()
        
        metrics = DerivedMetrics(
            timestamp=1704196800.0,  # Fixed timestamp
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        price = 100.5
        current_time = 1704196800.0
        
        regime1 = classifier1.classify(price, metrics, current_time)
        regime2 = classifier2.classify(price, metrics, current_time)
        
        assert regime1.regime == regime2.regime
        assert regime1.condition_1_met == regime2.condition_1_met
        assert regime1.condition_2_met == regime2.condition_2_met
        assert regime1.condition_3_met == regime2.condition_3_met
        assert regime1.condition_4_met == regime2.condition_4_met


class TestRegimeIsGate:
    """Test that regime is a gate, not a signal."""
    
    def test_regime_does_not_generate_trades(self):
        """Regime state does not contain trade signals."""
        classifier = RegimeClassifier()
        
        metrics = DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,
            atr_30m=2.0,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=100.0,
            taker_sell_volume_30s=100.0,
            liquidation_zscore=1.5,
            oi_delta=500.0,
        )
        
        regime_state = classifier.classify(100.5, metrics, time.time())
        
        # RegimeState should only have regime type and condition flags
        # No trade entry/exit signals
        assert hasattr(regime_state, 'regime')
        assert not hasattr(regime_state, 'entry_signal')
        assert not hasattr(regime_state, 'exit_signal')
        assert not hasattr(regime_state, 'position_size')


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])

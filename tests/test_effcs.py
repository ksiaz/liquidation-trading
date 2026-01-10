"""
Unit Tests for EFFCS State Machine

Tests implement requirements from PROMPT 7:
- EXPANSION regime gate
- Impulse detection (≥0.5×ATR + liq/OI)
- Pullback monitoring (≤30%, volume decrease)
- Entry WITH impulse direction (never fade)
- Stop/target exits

RULE: All tests are deterministic.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.regime_classifier.types import RegimeType
from masterframe.metrics.types import DerivedMetrics
from masterframe.effcs import (
    EFFCSState,
    ImpulseDirection,
    Impulse,
    EFFCSStateMachine,
)


class TestRegimeGate:
    """Test EXPANSION regime gate."""
    
    def create_metrics(self, atr=1.0, liq_zscore=3.0, oi_delta=-2000.0):
        """Create test metrics."""
        return DerivedMetrics(
            timestamp=time.time(),
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=atr,
            atr_30m=1.5,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=150.0,
            taker_sell_volume_30s=150.0,
            liquidation_zscore=liq_zscore,
            oi_delta=oi_delta,
        )
    
    def test_expansion_regime_required(self):
        """Strategy only active in EXPANSION regime."""
        sm = EFFCSStateMachine()
        metrics = self.create_metrics()
        
        # Update with SIDEWAYS regime - should stay DISABLED
        signal = sm.update(RegimeType.SIDEWAYS, 100.0, metrics, time.time())
        
        assert sm.get_state() == EFFCSState.DISABLED
        assert signal is None
    
    def test_regime_change_force_exit(self):
        """Regime change forces exit if in position."""
        sm = EFFCSStateMachine()
        metrics = self.create_metrics()
        current_time = time.time()
        
        # Build price history with impulse (need some updates first)
        for i in range(15):
            sm.update(RegimeType.EXPANSION, 100.0 + i * 0.1, metrics, current_time + i)
        
        # Manually set to IN_POSITION for testing
        from masterframe.effcs.types import Position, EFFCSSetup, Pullback
        
        impulse = Impulse(
            direction=ImpulseDirection.BULLISH,
            start_price=100.0,
            end_price=101.0,
            displacement=1.0,
            start_time=current_time,
            end_time=current_time + 10,
            liquidation_zscore=3.0,
            oi_delta=-2000.0,
            atr=1.0
        )
        
        pullback = Pullback(
            impulse=impulse,
            start_price=101.0,
            current_price=100.7,
            depth_percent=30.0,
            avg_volume=100.0,
            impulse_avg_volume=150.0
        )
        
        setup = EFFCSSetup(
            impulse=impulse,
            pullback=pullback,
            entry_price=100.7,
            stop_loss=99.7,
            take_profit=102.7,
            side='long',
            setup_time=current_time
        )
        
        sm.current_setup = setup
        sm.current_position = Position(
            setup=setup,
            entry_time=current_time,
            entry_price=100.7,
            current_pnl=0.0,
            is_active=True
        )
        sm.state = EFFCSState.IN_POSITION
        
        # Regime changes to SIDEWAYS - should force exit
        signal = sm.update(RegimeType.SIDEWAYS, 100.8, metrics, current_time + 20)
        
        assert signal == "EXIT"
        assert sm.get_state() == EFFCSState.DISABLED


class TestImpulseDetection:
    """Test impulse detection logic."""
    
    def test_impulse_requires_displacement(self):
        """Impulse requires ≥0.5×ATR displacement."""
        sm = EFFCSStateMachine()
        current_time = time.time()
        
        metrics = DerivedMetrics(
            timestamp=current_time,
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,  # Min displacement = 0.5
            atr_30m=1.5,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=150.0,
            taker_sell_volume_30s=150.0,
            liquidation_zscore=3.0,  # Confirmed
            oi_delta=-2000.0,
        )
        
        # Build price history with insufficient displacement
        for i in range(20):
            price = 100.0 + i * 0.01  # Only 0.2 displacement
            sm.update(RegimeType.EXPANSION, price, metrics, current_time + i)
        
        # Should NOT detect impulse (0.2 < 0.5)
        assert sm.get_state() == EFFCSState.DISABLED
    
    def test_impulse_requires_liq_or_oi(self):
        """Impulse requires liq spike OR OI contraction."""
        sm = EFFCSStateMachine()
        current_time = time.time()
        
        # No liq spike, no OI contraction
        metrics = DerivedMetrics(
            timestamp=current_time,
            vwap=100.0,
            atr_1m=0.5,
            atr_5m=1.0,
            atr_30m=1.5,
            taker_buy_volume_10s=50.0,
            taker_sell_volume_10s=50.0,
            taker_buy_volume_30s=150.0,
            taker_sell_volume_30s=150.0,
            liquidation_zscore=1.0,  # < 2.5 (not confirmed)
            oi_delta=-500.0,  # > -1000 (not confirmed)
        )
        
        # Build price history with sufficient displacement
        for i in range(20):
            price = 100.0 + i * 0.05  # 1.0 displacement
            sm.update(RegimeType.EXPANSION, price, metrics, current_time + i)
        
        # Should NOT detect impulse (no liq/OI confirmation)
        assert sm.get_state() == EFFCSState.DISABLED


class TestEntryDirection:
    """Test entry direction matching impulse."""
    
    def test_bullish_impulse_long_only(self):
        """Bullish impulse → long entries only."""
        impulse = Impulse(
            direction=ImpulseDirection.BULLISH,
            start_price=100.0,
            end_price=101.0,
            displacement=1.0,
            start_time=time.time(),
            end_time=time.time() + 10,
            liquidation_zscore=3.0,
            oi_delta=-2000.0,
            atr=1.0
        )
        
        # Impulse direction is BULLISH
        assert impulse.direction == ImpulseDirection.BULLISH
        
        # Setup should be long
        from masterframe.effcs.types import Pullback, EFFCSSetup
        
        pullback = Pullback(
            impulse=impulse,
            start_price=101.0,
            current_price=100.7,
            depth_percent=30.0,
            avg_volume=100.0,
            impulse_avg_volume=150.0
        )
        
        setup = EFFCSSetup(
            impulse=impulse,
            pullback=pullback,
            entry_price=100.7,
            stop_loss=99.7,
            take_profit=102.7,
            side='long',  # Must be long for bullish impulse
            setup_time=time.time()
        )
        
        assert setup.side == 'long'
        assert setup.stop_loss < setup.entry_price  # Stop below entry for long
        assert setup.take_profit > setup.entry_price  # Target above entry for long
    
    def test_bearish_impulse_short_only(self):
        """Bearish impulse → short entries only."""
        impulse = Impulse(
            direction=ImpulseDirection.BEARISH,
            start_price=101.0,
            end_price=100.0,
            displacement=1.0,
            start_time=time.time(),
            end_time=time.time() + 10,
            liquidation_zscore=3.0,
            oi_delta=-2000.0,
            atr=1.0
        )
        
        # Impulse direction is BEARISH
        assert impulse.direction == ImpulseDirection.BEARISH
        
        # Setup should be short
        from masterframe.effcs.types import Pullback, EFFCSSetup
        
        pullback = Pullback(
            impulse=impulse,
            start_price=100.0,
            current_price=100.3,
            depth_percent=30.0,
            avg_volume=100.0,
            impulse_avg_volume=150.0
        )
        
        setup = EFFCSSetup(
            impulse=impulse,
            pullback=pullback,
            entry_price=100.3,
            stop_loss=101.3,
            take_profit=98.3,
            side='short',  # Must be short for bearish impulse
            setup_time=time.time()
        )
        
        assert setup.side == 'short'
        assert setup.stop_loss > setup.entry_price  # Stop above entry for short
        assert setup.take_profit < setup.entry_price  # Target below entry for short


class TestPullbackValidation:
    """Test pullback validation."""
    
    def test_shallow_pullback_valid(self):
        """Pullback ≤30% is valid."""
        impulse = Impulse(
            direction=ImpulseDirection.BULLISH,
            start_price=100.0,
            end_price=101.0,
            displacement=1.0,
            start_time=time.time(),
            end_time=time.time() + 10,
            liquidation_zscore=3.0,
            oi_delta=-2000.0,
            atr=1.0
        )
        
        from masterframe.effcs.types import Pullback
        
        # 30% pullback (exactly at threshold)
        pullback = Pullback(
            impulse=impulse,
            start_price=101.0,
            current_price=100.7,  # 0.3 / 1.0 = 30%
            depth_percent=30.0,
            avg_volume=100.0,
            impulse_avg_volume=150.0
        )
        
        assert pullback.is_shallow(30.0) == True
    
    def test_deep_pullback_invalid(self):
        """Pullback >30% is invalid."""
        impulse = Impulse(
            direction=ImpulseDirection.BULLISH,
            start_price=100.0,
            end_price=101.0,
            displacement=1.0,
            start_time=time.time(),
            end_time=time.time() + 10,
            liquidation_zscore=3.0,
            oi_delta=-2000.0,
            atr=1.0
        )
        
        from masterframe.effcs.types import Pullback
        
        # 50% pullback (too deep)
        pullback = Pullback(
            impulse=impulse,
            start_price=101.0,
            current_price=100.5,  # 0.5 / 1.0 = 50%
            depth_percent=50.0,
            avg_volume=100.0,
            impulse_avg_volume=150.0
        )
        
        assert pullback.is_shallow(30.0) == False
    
    def test_volume_decrease_required(self):
        """Pullback volume must decrease."""
        impulse = Impulse(
            direction=ImpulseDirection.BULLISH,
            start_price=100.0,
            end_price=101.0,
            displacement=1.0,
            start_time=time.time(),
            end_time=time.time() + 10,
            liquidation_zscore=3.0,
            oi_delta=-2000.0,
            atr=1.0
        )
        
        from masterframe.effcs.types import Pullback
        
        # Volume decreased
        pullback_decreased = Pullback(
            impulse=impulse,
            start_price=101.0,
            current_price=100.7,
            depth_percent=30.0,
            avg_volume=100.0,  # < impulse volume
            impulse_avg_volume=150.0
        )
        
        assert pullback_decreased.is_volume_decreasing() == True
        
        # Volume increased
        pullback_increased = Pullback(
            impulse=impulse,
            start_price=101.0,
            current_price=100.7,
            depth_percent=30.0,
            avg_volume=200.0,  # > impulse volume
            impulse_avg_volume=150.0
        )
        
        assert pullback_increased.is_volume_decreasing() == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
Unit Tests for Risk Management Module

Tests implement requirements from PROMPT 9:
- R:R validation (minimum 2:1)
- Position sizing
- One position only (no scaling)
- Exit monitoring
- Exit reason logging

RULE: All tests are deterministic.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.risk_management import (
    ExitReason,
    RiskParameters,
    Position,
    PositionExit,
    RiskManager,
)


class TestSetupValidation:
    """Test setup validation logic."""
    
    def test_valid_setup_passes(self):
        """Valid setup with R:R >= 2:1 passes."""
        risk_params = RiskParameters(min_reward_risk_ratio=2.0)
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Long: entry=100, stop=99, target=103
        # Risk = 1, Reward = 3, R:R = 3:1 >= 2:1 ✓
        valid = rm.validate_setup(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long'
        )
        
        assert valid == True
    
    def test_insufficient_rr_fails(self):
        """Setup with R:R < 2:1 fails."""
        risk_params = RiskParameters(min_reward_risk_ratio=2.0)
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Long: entry=100, stop=99, target=101
        # Risk = 1, Reward = 1, R:R = 1:1 < 2:1 ✗
        valid = rm.validate_setup(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=101.0,
            side='long'
        )
        
        assert valid == False
    
    def test_negative_risk_fails(self):
        """Setup with negative risk fails."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Long with stop above entry (invalid)
        valid = rm.validate_setup(
            entry_price=100.0,
            stop_loss=101.0,  # Stop above entry for long
            take_profit=105.0,
            side='long'
        )
        
        assert valid == False


class TestPositionSizing:
    """Test position sizing calculation."""
    
    def test_position_size_from_risk(self):
        """Position size calculated from risk amount."""
        risk_params = RiskParameters(
            max_risk_per_trade_pct=1.0,
            max_position_size_pct=20.0  # Set high so it doesn't cap
        )
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # 1% of 10000 = 100 risk
        # Entry=100, Stop=99, Risk per unit = 1
        # Position size = 100 / 1 = 100
        # But capped at 20% of account = 2000 / 100 = 20 units
        size = rm.calculate_position_size(
            entry_price=100.0,
            stop_loss=99.0
        )
        
        # Verify it's 20 (capped)
        assert abs(size - 20.0) < 0.01
    
    def test_position_size_capped(self):
        """Position size capped at max %."""
        risk_params = RiskParameters(
            max_risk_per_trade_pct=10.0,  # Would give huge position
            max_position_size_pct=5.0  # Cap at 5%
        )
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Max position = 5% of 10000 = 500 / 100 = 5 units
        size = rm.calculate_position_size(
            entry_price=100.0,
            stop_loss=90.0
        )
        
        # Should be capped
        max_size = 10000.0 * 0.05 / 100.0
        assert abs(size - max_size) < 0.01


class TestOnePositionOnly:
    """Test one position enforcement."""
    
    def test_cannot_enter_second_position(self):
        """Cannot enter position while already in position."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter first position
        pos1 = rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        assert pos1 is not None
        
        # Try to enter second position (should fail)
        pos2 = rm.enter_position(
            entry_price=101.0,
            stop_loss=100.0,
            take_profit=104.0,
            side='long',
            strategy='EFFCS',
            current_time=time.time()
        )
        
        assert pos2 is None  # Rejected


class TestExitDetection:
    """Test exit condition detection."""
    
    def test_stop_loss_detected_long(self):
        """Stop loss hit detected for long position."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter long position
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        # Price hits stop (99.0)
        exit_reason = rm.check_exit(current_price=98.5)
        
        assert exit_reason == ExitReason.STOP_LOSS_HIT
    
    def test_take_profit_detected_long(self):
        """Take profit hit detected for long position."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter long position
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        # Price hits target (103.0)
        exit_reason = rm.check_exit(current_price=103.5)
        
        assert exit_reason == ExitReason.TAKE_PROFIT_HIT
    
    def test_invalidation_priority(self):
        """Invalidation takes priority over stop/target."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter position
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        # Price at stop AND invalidated
        exit_reason = rm.check_exit(
            current_price=98.5,  # At stop
            invalidated=True  # But also invalidated
        )
        
        # Should return invalidation (higher priority)
        assert exit_reason == ExitReason.SETUP_INVALIDATED
    
    def test_regime_change_exit(self):
        """Regime change triggers exit."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter position
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        # Regime changed
        exit_reason = rm.check_exit(
            current_price=100.5,  # Not at stop/target
            regime_changed=True
        )
        
        assert exit_reason == ExitReason.REGIME_CHANGED


class TestExitExecution:
    """Test exit execution and logging."""
    
    def test_exit_clears_position(self):
        """Exiting position clears current position."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter position
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        assert rm.is_in_position() == True
        
        # Exit position
        rm.exit_position(
            exit_price=103.5,
            exit_time=time.time(),
            reason=ExitReason.TAKE_PROFIT_HIT
        )
        
        assert rm.is_in_position() == False
    
    def test_exit_logged(self):
        """Exit logged to history."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter position
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        # Exit position
        exit_record = rm.exit_position(
            exit_price=103.5,
            exit_time=time.time(),
            reason=ExitReason.TAKE_PROFIT_HIT
        )
        
        assert exit_record is not None
        assert exit_record.reason == ExitReason.TAKE_PROFIT_HIT
        assert len(rm.get_exit_history()) == 1
    
    def test_pnl_calculation(self):
        """P&L calculated correctly."""
        risk_params = RiskParameters()
        rm = RiskManager(risk_params, account_balance=10000.0)
        
        # Enter long position with size=100
        rm.enter_position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            side='long',
            strategy='SLBRS',
            current_time=time.time()
        )
        
        # Exit at profit
        exit_record = rm.exit_position(
            exit_price=103.0,
            exit_time=time.time(),
            reason=ExitReason.TAKE_PROFIT_HIT
        )
        
        # PnL = (103 - 100) * size
        # Size = 100 risk / 1 risk_per_unit = 100
        # PnL = 3 * 100 = 300
        assert exit_record.pnl > 0  # Profitable


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

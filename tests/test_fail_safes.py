"""
Unit Tests for Fail-Safes & Cooldown Module

Tests implement requirements from PROMPT 10:
- Consecutive losses kill-switch (≥2)
- Daily drawdown kill-switch (≥5%)
- Win rate kill-switch (< 35% over last 20)
- Manual reset requirement
- Fail-closed design

RULE: All tests are deterministic.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.fail_safes import (
    KillSwitchReason,
    FailSafeConfig,
    KillSwitchEvent,
    FailSafeMonitor,
)
from masterframe.risk_management.types import PositionExit, Position, ExitReason


class TestConsecutiveLosses:
    """Test consecutive losses kill-switch."""
    
    def create_exit(self, pnl: float) -> PositionExit:
        """Create test exit record."""
        pos = Position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            size=10.0,
            side='long',
            entry_time=time.time(),
            strategy='SLBRS'
        )
        
        return PositionExit(
            exit_price=100.0 + pnl / 10.0,
            exit_time=time.time(),
            pnl=pnl,
            reason=ExitReason.TAKE_PROFIT_HIT,
            position=pos
        )
    
    def test_consecutive_losses_trigger(self):
        """2 consecutive losses trigger kill-switch."""
        config = FailSafeConfig(max_consecutive_losses=2)
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        current_time = time.time()
        
        # Loss 1
        exit1 = self.create_exit(pnl=-100.0)
        can_trade = monitor.update(9900.0, exit1, current_time)
        assert can_trade == True  # Still ok
        assert monitor.get_consecutive_losses() == 1
        
        # Loss 2 (trigger)
        exit2 = self.create_exit(pnl=-100.0)
        can_trade = monitor.update(9800.0, exit2, current_time + 1)
        assert can_trade == False  # Killed
        assert monitor.get_kill_status() == True
        assert monitor.get_kill_reason() == KillSwitchReason.CONSECUTIVE_LOSSES
    
    def test_win_resets_consecutive_losses(self):
        """Winning trade resets consecutive loss count."""
        config = FailSafeConfig(max_consecutive_losses=2)
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        current_time = time.time()
        
        # Loss
        exit1 = self.create_exit(pnl=-100.0)
        monitor.update(9900.0, exit1, current_time)
        assert monitor.get_consecutive_losses() == 1
        
        # Win (reset)
        exit2 = self.create_exit(pnl=200.0)
        monitor.update(10100.0, exit2, current_time + 1)
        assert monitor.get_consecutive_losses() == 0


class TestDailyDrawdown:
    """Test daily drawdown kill-switch."""
    
    def test_drawdown_trigger(self):
        """≥5% daily drawdown triggers kill-switch."""
        config = FailSafeConfig(max_daily_drawdown_pct=5.0)
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        current_time = time.time()
        
        # 4% drawdown (ok)
        can_trade = monitor.update(9600.0, None, current_time)
        assert can_trade == True
        
        # 5% drawdown (trigger)
        can_trade = monitor.update(9500.0, None, current_time + 1)
        assert can_trade == False
        assert monitor.get_kill_status() == True
        assert monitor.get_kill_reason() == KillSwitchReason.DAILY_DRAWDOWN
    
    def test_drawdown_calculation(self):
        """Drawdown % calculated correctly."""
        config = FailSafeConfig()
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        monitor.current_balance = 9500.0
        dd = monitor.get_daily_drawdown_pct()
        
        assert abs(dd - (-5.0)) < 0.01


class TestWinRate:
    """Test win rate kill-switch."""
    
    def create_exit(self, pnl: float) -> PositionExit:
        """Create test exit record."""
        pos = Position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            size=10.0,
            side='long',
            entry_time=time.time(),
            strategy='SLBRS'
        )
        
        return PositionExit(
            exit_price=100.0,
            exit_time=time.time(),
            pnl=pnl,
            reason=ExitReason.TAKE_PROFIT_HIT,
            position=pos
        )
    
    def test_win_rate_trigger(self):
        """Win rate < 35% over 20 trades triggers kill-switch."""
        config = FailSafeConfig(
            min_win_rate_pct=35.0,
            win_rate_sample_size=20,
            max_consecutive_losses=100  # High so it doesn't interfere
        )
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        current_time = time.time()
        balance = 10000.0
        
        # 6 wins, 14 losses = 30% win rate
        for i in range(20):
            pnl = 100.0 if i < 6 else -50.0
            balance += pnl
            exit_rec = self.create_exit(pnl)
            can_trade = monitor.update(balance, exit_rec, current_time + i)
        
        # Should be killed after 20th trade
        assert can_trade == False
        assert monitor.get_kill_status() == True
        assert monitor.get_kill_reason() == KillSwitchReason.LOW_WIN_RATE
    
    def test_win_rate_not_checked_until_enough_trades(self):
        """Win rate not checked until N trades."""
        config = FailSafeConfig(
            min_win_rate_pct=35.0,
            win_rate_sample_size=20,
            max_consecutive_losses=100,  # High so it doesn't interfere
            max_daily_drawdown_pct=100.0  # High so it doesn't interfere
        )
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        current_time = time.time()
        
        # 10 losses (but only 10 trades, not enough)
        for i in range(10):
            exit_rec = self.create_exit(pnl=-50.0)
            can_trade = monitor.update(9500.0 - i * 50, exit_rec, current_time + i)
        
        # Should NOT be killed yet
        assert can_trade == True
        assert monitor.get_kill_status() == False


class TestManualReset:
    """Test manual reset requirement."""
    
    def test_manual_reset_required(self):
        """System stays killed until manual reset."""
        config = FailSafeConfig(max_consecutive_losses=2)
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        current_time = time.time()
        
        # Trigger kill
        pos = Position(
            entry_price=100.0, stop_loss=99.0, take_profit=103.0,
            size=10.0, side='long', entry_time=current_time, strategy='SLBRS'
        )
        
        for i in range(2):
            exit_rec = PositionExit(
                exit_price=99.0, exit_time=current_time + i,
                pnl=-100.0, reason=ExitReason.STOP_LOSS_HIT, position=pos
            )
            monitor.update(9800.0 - i * 100, exit_rec, current_time + i)
        
        assert monitor.get_kill_status() == True
        
        # Try to continue (should stay killed)
        can_trade = monitor.update(9800.0, None, current_time + 10)
        assert can_trade == False
        
        # Manual reset
        monitor.manual_reset()
        assert monitor.get_kill_status() == False
        
        # Can trade again
        can_trade = monitor.update(9800.0, None, current_time + 11)
        assert can_trade == True


class TestFailClosed:
    """Test fail-closed design."""
    
    def test_killed_blocks_trading(self):
        """Killed state blocks trading."""
        config = FailSafeConfig(max_consecutive_losses=1)
        monitor = FailSafeMonitor(config, starting_balance=10000.0)
        
        # Trigger kill
        pos = Position(
            entry_price=100.0, stop_loss=99.0, take_profit=103.0,
            size=10.0, side='long', entry_time=time.time(), strategy='SLBRS'
        )
        exit_rec = PositionExit(
            exit_price=99.0, exit_time=time.time(),
            pnl=-100.0, reason=ExitReason.STOP_LOSS_HIT, position=pos
        )
        
        can_trade = monitor.update(9900.0, exit_rec, time.time())
        
        # Should block trading
        assert can_trade == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
Unit Tests for Logging & Audit Module

Tests implement requirements from PROMPT 11:
- All events logged
- Structured JSON format
- Timestamped
- Machine-readable

RULE: All tests are deterministic.
"""

import pytest
import time
import json
import os
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.logging import EventType, LogEvent, AuditLogger
from masterframe.regime_classifier.types import RegimeType
from masterframe.slbrs import SLBRSState
from masterframe.effcs import EFFCSState
from masterframe.risk_management.types import Position, PositionExit, ExitReason
from masterframe.fail_safes.types import KillSwitchEvent, KillSwitchReason


class TestEventLogging:
    """Test event logging."""
    
    def setup_method(self):
        """Setup test logger."""
        self.test_log_file = "test_audit.jsonl"
        # Clean up any existing test file
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)
        self.logger = AuditLogger(log_file=self.test_log_file)
    
    def teardown_method(self):
        """Cleanup test log file."""
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)
    
    def test_regime_change_logged(self):
        """Regime change events are logged."""
        self.logger.log_regime_change(
            old_regime=RegimeType.SIDEWAYS,
            new_regime=RegimeType.EXPANSION,
            conditions={"vwap_distance": 1.5, "atr_ratio": 1.0},
            timestamp=time.time()
        )
        
        events = self.logger.get_events_by_type(EventType.REGIME_CHANGE)
        assert len(events) == 1
        assert events[0].data["old_regime"] == "SIDEWAYS"
        assert events[0].data["new_regime"] == "EXPANSION"
    
    def test_slbrs_transition_logged(self):
        """SLBRS state transitions are logged."""
        self.logger.log_slbrs_transition(
            old_state=SLBRSState.SETUP_DETECTED,
            new_state=SLBRSState.FIRST_TEST,
            reason="Price entered block",
            timestamp=time.time()
        )
        
        events = self.logger.get_events_by_type(EventType.SLBRS_STATE_TRANSITION)
        assert len(events) == 1
        assert events[0].data["old_state"] == "SETUP_DETECTED"
        assert events[0].data["new_state"] == "FIRST_TEST"
        assert events[0].data["reason"] == "Price entered block"
    
    def test_effcs_transition_logged(self):
        """EFFCS state transitions are logged."""
        self.logger.log_effcs_transition(
            old_state=EFFCSState.IMPULSE_DETECTED,
            new_state=EFFCSState.PULLBACK_MONITORING,
            reason="Pullback started",
            timestamp=time.time()
        )
        
        events = self.logger.get_events_by_type(EventType.EFFCS_STATE_TRANSITION)
        assert len(events) == 1
        assert events[0].data["old_state"] == "IMPULSE_DETECTED"
        assert events[0].data["new_state"] == "PULLBACK_MONITORING"
    
    def test_setup_invalidation_logged(self):
        """Setup invalidations are logged."""
        self.logger.log_setup_invalidation(
            strategy="SLBRS",
            reason="Block broken",
            setup_id="block_123",
            timestamp=time.time()
        )
        
        events = self.logger.get_events_by_type(EventType.SETUP_INVALIDATION)
        assert len(events) == 1
        assert events[0].data["strategy"] == "SLBRS"
        assert events[0].data["reason"] == "Block broken"
    
    def test_trade_entry_logged(self):
        """Trade entries are logged."""
        pos = Position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            size=10.0,
            side='long',
            entry_time=time.time(),
            strategy='SLBRS'
        )
        
        self.logger.log_trade_entry(pos, time.time())
        
        events = self.logger.get_events_by_type(EventType.TRADE_ENTRY)
        assert len(events) == 1
        assert events[0].data["strategy"] == "SLBRS"
        assert events[0].data["side"] == "long"
        assert events[0].data["entry_price"] == 100.0
    
    def test_trade_exit_logged(self):
        """Trade exits are logged."""
        pos = Position(
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=103.0,
            size=10.0,
            side='long',
            entry_time=time.time(),
            strategy='SLBRS'
        )
        
        exit_rec = PositionExit(
            exit_price=103.0,
            exit_time=time.time(),
            pnl=300.0,
            reason=ExitReason.TAKE_PROFIT_HIT,
            position=pos
        )
        
        self.logger.log_trade_exit(exit_rec, time.time())
        
        events = self.logger.get_events_by_type(EventType.TRADE_EXIT)
        assert len(events) == 1
        assert events[0].data["pnl"] == 300.0
        assert events[0].data["reason"] == "TAKE_PROFIT_HIT"
    
    def test_kill_switch_logged(self):
        """Kill-switch triggers are logged."""
        kill_event = KillSwitchEvent(
            reason=KillSwitchReason.CONSECUTIVE_LOSSES,
            timestamp=time.time(),
            details="2 consecutive losses"
        )
        
        self.logger.log_kill_switch(kill_event, account_balance=9800.0)
        
        events = self.logger.get_events_by_type(EventType.KILL_SWITCH)
        assert len(events) == 1
        assert events[0].data["reason"] == "CONSECUTIVE_LOSSES"
        assert events[0].data["account_balance"] == 9800.0


class TestLogFormat:
    """Test log format requirements."""
    
    def setup_method(self):
        """Setup test logger."""
        self.test_log_file = "test_format.jsonl"
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)
        self.logger = AuditLogger(log_file=self.test_log_file)
    
    def teardown_method(self):
        """Cleanup."""
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)
    
    def test_log_format_json(self):
        """Logs are valid JSON."""
        self.logger.log_regime_change(
            old_regime=RegimeType.SIDEWAYS,
            new_regime=RegimeType.EXPANSION,
            conditions={},
            timestamp=time.time()
        )
        
        event = self.logger.get_events()[0]
        json_str = event.to_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "event_type" in parsed
        assert "timestamp" in parsed
    
    def test_log_timestamps(self):
        """Logs are timestamped."""
        ts = time.time()
        self.logger.log_regime_change(
            old_regime=RegimeType.SIDEWAYS,
            new_regime=RegimeType.EXPANSION,
            conditions={},
            timestamp=ts
        )
        
        event = self.logger.get_events()[0]
        assert abs(event.timestamp - ts) < 0.01
    
    def test_jsonl_file_format(self):
        """JSONL file format (one JSON per line)."""
        # Log multiple events
        self.logger.log_regime_change(
            old_regime=RegimeType.SIDEWAYS,
            new_regime=RegimeType.EXPANSION,
            conditions={},
            timestamp=time.time()
        )
        self.logger.log_slbrs_transition(
            old_state=SLBRSState.DISABLED,
            new_state=SLBRSState.SETUP_DETECTED,
            reason="Block found",
            timestamp=time.time()
        )
        
        # Read file
        with open(self.test_log_file, 'r') as f:
            lines = f.readlines()
        
        # Should have 2 lines
        assert len(lines) == 2
        
        # Each line should be valid JSON
        for line in lines:
            parsed = json.loads(line.strip())
            assert "event_type" in parsed
            assert "timestamp" in parsed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

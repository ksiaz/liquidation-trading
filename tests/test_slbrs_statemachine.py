"""
Unit Tests for SLBRS State Machine

Tests implement requirements from PROMPT 6:
- Exact state sequencing (no skipping)
- Entry ONLY in RETEST_ARMED
- Regime gate enforcement
- Stop loss / take profit exits
- One setup at a time

RULE: All tests are deterministic.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.regime_classifier.types import RegimeType
from masterframe.slbrs import (
    BlockType,
    LiquidityBlock,
    SLBRSStateMachine,
    SLBRSState,
    TradeSetup,
    Position,
)


class TestStateSequencing:
    """Test exact state sequence (no skipping)."""
    
    def create_absorption_block(self) -> LiquidityBlock:
        """Create test ABSORPTION block."""
        current_time = time.time()
        return LiquidityBlock(
            block_id="test_block_1",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.975,
            current_price=99.975,
            first_seen=current_time - 40,
            last_updated=current_time,
            is_tradable=True,
            is_invalidated=False,
        )
    
    def test_initial_state_disabled(self):
        """State machine starts in DISABLED."""
        sm = SLBRSStateMachine()
        assert sm.get_state() == SLBRSState.DISABLED
    
    def test_disabled_to_setup_detected(self):
        """DISABLED → SETUP_DETECTED when ABSORPTION block found."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        
        signal = sm.update(
            regime=RegimeType.SIDEWAYS,
            tradable_blocks=[block],
            current_price=100.5,
            current_time=time.time(),
            atr=1.0
        )
        
        assert sm.get_state() == SLBRSState.SETUP_DETECTED
        assert signal is None  # No entry yet
    
    def test_setup_to_first_test(self):
        """SETUP_DETECTED → FIRST_TEST when price enters block."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Setup detected
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, 1.0)
        assert sm.get_state() == SLBRSState.SETUP_DETECTED
        
        # Price enters block (99.95 - 100.0)
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, 1.0)
        
        assert sm.get_state() == SLBRSState.FIRST_TEST
        assert signal is None
    
    def test_first_test_to_retest_armed(self):
        """FIRST_TEST → RETEST_ARMED when price retraces."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Setup → first test
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, 1.0)
        sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, 1.0)
        assert sm.get_state() == SLBRSState.FIRST_TEST
        
        # Price retraces away (> 10 bps from block mid)
        # Block mid = (99.95 + 100.0) / 2 = 99.975
        # Need > 10 bps away: 99.975 * 0.001 = 0.099975
        signal = sm.update(RegimeType.SIDEWAYS, [], 100.10, current_time + 2, 1.0)
        
        assert sm.get_state() == SLBRSState.RETEST_ARMED
        assert signal is None
    
    def test_retest_armed_to_in_position(self):
        """RETEST_ARMED → IN_POSITION when retest occurs (ENTRY)."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Setup → first test → retest armed
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, 1.0)
        sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, 1.0)
        sm.update(RegimeType.SIDEWAYS, [], 100.10, current_time + 2, 1.0)
        assert sm.get_state() == SLBRSState.RETEST_ARMED
        
        # Price retests block (back in 99.95 - 100.0)
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.98, current_time + 3, 1.0)
        
        assert sm.get_state() == SLBRSState.IN_POSITION
        assert signal == "ENTER"
    
    def test_no_state_skipping(self):
        """Cannot skip states in sequence."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Start in DISABLED
        assert sm.get_state() == SLBRSState.DISABLED
        
        # Cannot jump to RETEST_ARMED without going through sequence
        # Must go: DISABLED → SETUP → FIRST_TEST → RETEST_ARMED
        
        # Step 1: DISABLED → SETUP_DETECTED
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, 1.0)
        assert sm.get_state() == SLBRSState.SETUP_DETECTED
        
        # Cannot skip to RETEST_ARMED - must go through FIRST_TEST
        # Price entering block should transition to FIRST_TEST
        sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, 1.0)
        assert sm.get_state() == SLBRSState.FIRST_TEST  # Not RETEST_ARMED


class TestEntryLogic:
    """Test entry conditions."""
    
    def create_absorption_block(self) -> LiquidityBlock:
        """Create test ABSORPTION block."""
        current_time = time.time()
        return LiquidityBlock(
            block_id="test_block_2",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.975,
            current_price=99.975,
            first_seen=current_time - 40,
            last_updated=current_time,
            is_tradable=True,
            is_invalidated=False,
        )
    
    def test_entry_only_in_retest_armed(self):
        """Entry signal ONLY in RETEST_ARMED state."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # No entry in DISABLED
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time, 1.0)
        assert signal != "ENTER"
        
        # No entry in SETUP_DETECTED
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, 1.0)
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, 1.0)
        assert signal != "ENTER"
        
        # No entry in FIRST_TEST
        assert sm.get_state() == SLBRSState.FIRST_TEST
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 2, 1.0)
        assert signal != "ENTER"
        
        # Move to RETEST_ARMED
        sm.update(RegimeType.SIDEWAYS, [], 100.10, current_time + 3, 1.0)
        assert sm.get_state() == SLBRSState.RETEST_ARMED
        
        # Entry ONLY in RETEST_ARMED
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.98, current_time + 4, 1.0)
        assert signal == "ENTER"
    
    def test_setup_parameters_calculated(self):
        """Setup calculates entry/stop/target correctly."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        atr = 1.0
        
        # Get to SETUP_DETECTED
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, atr)
        
        setup = sm.get_setup()
        assert setup is not None
        assert setup.side == 'long'  # bid block = long
        assert setup.entry_price == 99.975  # block initial price
        assert setup.stop_loss < block.price_min  # Stop below block
        assert setup.take_profit > setup.entry_price  # Target above entry


class TestRegimeGate:
    """Test regime gate enforcement."""
    
    def create_absorption_block(self) -> LiquidityBlock:
        """Create test ABSORPTION block."""
        current_time = time.time()
        return LiquidityBlock(
            block_id="test_block_3",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.975,
            current_price=99.975,
            first_seen=current_time - 40,
            last_updated=current_time,
            is_tradable=True,
            is_invalidated=False,
        )
    
    def test_regime_must_be_sideways(self):
        """Strategy only active in SIDEWAYS regime."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Update with EXPANSION regime - should stay DISABLED
        signal = sm.update(RegimeType.EXPANSION, [block], 100.5, current_time, 1.0)
        
        assert sm.get_state() == SLBRSState.DISABLED
        assert signal is None
    
    def test_regime_change_force_exit(self):
        """Regime change forces exit if in position."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Get to IN_POSITION
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, 1.0)
        sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, 1.0)
        sm.update(RegimeType.SIDEWAYS, [], 100.10, current_time + 2, 1.0)
        signal = sm.update(RegimeType.SIDEWAYS, [], 99.98, current_time + 3, 1.0)
        
        assert sm.get_state() == SLBRSState.IN_POSITION
        assert signal == "ENTER"
        
        # Regime changes to EXPANSION - should force exit
        signal = sm.update(RegimeType.EXPANSION, [], 100.0, current_time + 4, 1.0)
        
        assert signal == "EXIT"
        assert sm.get_state() == SLBRSState.DISABLED


class TestExitLogic:
    """Test exit conditions."""
    
    def create_absorption_block(self) -> LiquidityBlock:
        """Create test ABSORPTION block."""
        current_time = time.time()
        return LiquidityBlock(
            block_id="test_block_4",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.975,
            current_price=99.975,
            first_seen=current_time - 40,
            last_updated=current_time,
            is_tradable=True,
            is_invalidated=False,
        )
    
    def get_to_position(self, sm, block, current_time, atr=1.0):
        """Helper to get state machine to IN_POSITION."""
        sm.update(RegimeType.SIDEWAYS, [block], 100.5, current_time, atr)
        sm.update(RegimeType.SIDEWAYS, [], 99.97, current_time + 1, atr)
        sm.update(RegimeType.SIDEWAYS, [], 100.10, current_time + 2, atr)
        sm.update(RegimeType.SIDEWAYS, [], 99.98, current_time + 3, atr)
    
    def test_stop_loss_exit(self):
        """Stop loss hit → EXIT."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Get to position
        self.get_to_position(sm, block, current_time)
        assert sm.get_state() == SLBRSState.IN_POSITION
        
        setup = sm.get_setup()
        
        # Price hits stop (below stop for long)
        signal = sm.update(RegimeType.SIDEWAYS, [], setup.stop_loss - 0.01, current_time + 4, 1.0)
        
        assert signal == "EXIT"
        assert sm.get_state() == SLBRSState.DISABLED
    
    def test_take_profit_exit(self):
        """Take profit hit → EXIT."""
        sm = SLBRSStateMachine()
        block = self.create_absorption_block()
        current_time = time.time()
        
        # Get to position
        self.get_to_position(sm, block, current_time)
        assert sm.get_state() == SLBRSState.IN_POSITION
        
        setup = sm.get_setup()
        
        # Price hits target (above target for long)
        signal = sm.update(RegimeType.SIDEWAYS, [], setup.take_profit + 0.01, current_time + 4, 1.0)
        
        assert signal == "EXIT"
        assert sm.get_state() == SLBRSState.DISABLED


class TestOneSetupRule:
    """Test one setup at a time."""
    
    def test_one_active_setup_only(self):
        """Only one setup active at a time."""
        sm = SLBRSStateMachine()
        
        block1 = LiquidityBlock(
            block_id="block_1",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.975,
            current_price=99.975,
            first_seen=time.time() - 40,
            last_updated=time.time(),
            is_tradable=True,
            is_invalidated=False,
        )
        
        block2 = LiquidityBlock(
            block_id="block_2",
            zone_name='B',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1200.0,
            rolling_zone_avg=350.0,
            persistence_seconds=50.0,
            executed_volume=200.0,
            canceled_volume=120.0,
            cancel_to_trade_ratio=0.6,
            price_min=99.85,
            price_max=99.90,
            initial_price=99.875,
            current_price=99.875,
            first_seen=time.time() - 50,
            last_updated=time.time(),
            is_tradable=True,
            is_invalidated=False,
        )
        
        current_time = time.time()
        
        # First block creates setup
        sm.update(RegimeType.SIDEWAYS, [block1], 100.5, current_time, 1.0)
        first_setup = sm.get_setup()
        assert first_setup is not None
        assert first_setup.block.block_id == "block_1"
        
        # Second block offered - should NOT replace active setup
        sm.update(RegimeType.SIDEWAYS, [block2], 100.5, current_time + 1, 1.0)
        current_setup = sm.get_setup()
        assert current_setup.block.block_id == "block_1"  # Still first block


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
Unit Tests for Master Controller

Tests implement requirements from PROMPT 8:
- Mutual exclusion (SLBRS ⊕ EFFCS)
- Regime-based strategy routing
- Cooldown enforcement
- Controller-only activation

RULE: All tests are deterministic.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.regime_classifier.types import RegimeType
from masterframe.slbrs import SLBRSState
from masterframe.effcs import EFFCSState
from masterframe.controller import MasterController


class TestMutualExclusion:
    """Test SLBRS ⊕ EFFCS mutual exclusion."""
    
    def test_mutual_exclusion_invariant(self):
        """SLBRS and EFFCS never active simultaneously."""
        controller = MasterController()
        
        # Verify invariant holds initially
        assert controller.verify_mutual_exclusion() == True
        
        # After any operation, invariant must hold
        # (Can't easily test full update without complex setup,
        # but we can verify internal state)
        controller.active_strategy = 'SLBRS'
        controller.slbrs.state = SLBRSState.SETUP_DETECTED
        controller.effcs.state = EFFCSState.DISABLED
        
        assert controller.verify_mutual_exclusion() == True
        
        # Both active would violate
        controller.effcs.state = EFFCSState.IMPULSE_DETECTED
        assert controller.verify_mutual_exclusion() == False
    
    def test_sideways_enables_slbrs_only(self):
        """SIDEWAYS regime enables SLBRS, disables EFFCS."""
        controller = MasterController()
        
        controller._enforce_mutual_exclusion(RegimeType.SIDEWAYS)
        
        assert controller.get_active_strategy() == 'SLBRS'
    
    def test_expansion_enables_effcs_only(self):
        """EXPANSION regime enables EFFCS, disables SLBRS."""
        controller = MasterController()
        
        controller._enforce_mutual_exclusion(RegimeType.EXPANSION)
        
        assert controller.get_active_strategy() == 'EFFCS'
    
    def test_disabled_disables_both(self):
        """DISABLED regime disables both strategies."""
        controller = MasterController()
        
        controller._enforce_mutual_exclusion(RegimeType.DISABLED)
        
        assert controller.get_active_strategy() is None


class TestCooldownEnforcement:
    """Test cooldown blocks evaluations."""
    
    def test_no_cooldown_initially(self):
        """No cooldown at start."""
        controller = MasterController()
        current_time = time.time()
        
        in_cooldown = controller._check_cooldown(current_time)
        
        assert in_cooldown == False
        assert controller.is_in_cooldown() == False
    
    def test_cooldown_after_exit(self):
        """Cooldown starts after EXIT signal."""
        controller = MasterController()
        current_time = time.time()
        
        # Simulate exit
        controller._handle_signal('EXIT', current_time)
        
        # Should be in cooldown
        in_cooldown = controller._check_cooldown(current_time + 1)
        
        assert in_cooldown == True
        assert controller.is_in_cooldown() == True
    
    def test_cooldown_expires(self):
        """Cooldown expires after period."""
        controller = MasterController()
        current_time = time.time()
        
        # Simulate exit
        controller._handle_signal('EXIT', current_time)
        
        # Wait past cooldown period
        future_time = current_time + controller.COOLDOWN_SECONDS + 1
        in_cooldown = controller._check_cooldown(future_time)
        
        assert in_cooldown == False
        assert controller.is_in_cooldown() == False
    
    def test_cooldown_blocks_evaluation(self):
        """Cooldown blocks evaluations (returns None)."""
        controller = MasterController()
        current_time = time.time()
        
        # Set cooldown
        controller._handle_signal('EXIT', current_time)
        
        # Check cooldown blocks
        blocked = controller._check_cooldown(current_time + 1)
        
        assert blocked == True  # Evaluation blocked


class TestStrategyRouting:
    """Test correct strategy routing."""
    
    def test_active_strategy_tracked(self):
        """Active strategy name tracked correctly."""
        controller = MasterController()
        
        # Initially no active strategy
        assert controller.get_active_strategy() is None
        
        # Set SLBRS active
        controller._enforce_mutual_exclusion(RegimeType.SIDEWAYS)
        assert controller.get_active_strategy() == 'SLBRS'
        
        # Set EFFCS active
        controller._enforce_mutual_exclusion(RegimeType.EXPANSION)
        assert controller.get_active_strategy() == 'EFFCS'
        
        # Disable
        controller._enforce_mutual_exclusion(RegimeType.DISABLED)
        assert controller.get_active_strategy() is None
    
    def test_regime_tracked(self):
        """Current regime tracked correctly."""
        controller = MasterController()
        
        # Initially DISABLED
        assert controller.get_current_regime() == RegimeType.DISABLED
        
        # Can set regime
        controller.current_regime = RegimeType.SIDEWAYS
        assert controller.get_current_regime() == RegimeType.SIDEWAYS


class TestControllerState:
    """Test controller state management."""
    
    def test_initial_state(self):
        """Controller starts in correct state."""
        controller = MasterController()
        
        assert controller.get_active_strategy() is None
        assert controller.get_current_regime() == RegimeType.DISABLED
        assert controller.is_in_cooldown() == False
        assert controller.get_slbrs_state() == SLBRSState.DISABLED
        assert controller.get_effcs_state() == EFFCSState.DISABLED
    
    def test_reset_clears_state(self):
        """Reset clears all state."""
        controller = MasterController()
        
        # Set some state
        controller.active_strategy = 'SLBRS'
        controller.current_regime = RegimeType.SIDEWAYS
        controller.last_trade_exit_time = time.time()
        controller.in_cooldown = True
        
        # Reset
        controller.reset()
        
        # All cleared
        assert controller.get_active_strategy() is None
        assert controller.get_current_regime() == RegimeType.DISABLED
        assert controller.is_in_cooldown() == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

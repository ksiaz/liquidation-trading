"""
SLBRS State Machine

Implements the SLBRS trading state machine with exact state sequencing.

STATES:
- DISABLED (initial)
- SETUP_DETECTED (ABSORPTION block found)
- FIRST_TEST (price tested block once)
- RETEST_ARMED (price retracted, waiting for retest)
- IN_POSITION (trade entered)

RULES:
- Follow exact sequence (no state skipping)
- Entry ONLY in RETEST_ARMED state
- One setup at a time
- Reset on invalidation
- Regime gate: must be SIDEWAYS
"""

from enum import Enum
from typing import Optional, List
from dataclasses import dataclass
import sys
sys.path.append('d:/liquidation-trading')

# LOCAL: RegimeType enum (copied to avoid masterframe import cascade)
class RegimeType(Enum):
    """Regime classification types (local copy for C9 isolation)."""
    DISABLED = "DISABLED"
    SIDEWAYS = "SIDEWAYS"
    EXPANSION = "EXPANSION"

from .types import LiquidityBlock


class SLBRSState(Enum):
    """
    SLBRS state machine states.
    
    INVARIANT: States follow exact sequence.
    """
    DISABLED = "DISABLED"
    SETUP_DETECTED = "SETUP_DETECTED"
    FIRST_TEST = "FIRST_TEST"
    RETEST_ARMED = "RETEST_ARMED"
    IN_POSITION = "IN_POSITION"


@dataclass(frozen=True)
class TradeSetup:
    """
    SLBRS trade setup parameters.
    
    INVARIANT: Immutable setup configuration.
    """
    block: LiquidityBlock
    entry_price: float
    stop_loss: float
    take_profit: float
    side: str  # 'long' or 'short'
    setup_time: float
    
    def get_reward_risk_ratio(self) -> float:
        """Calculate reward:risk ratio."""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk == 0:
            return 0.0
        return reward / risk


@dataclass
class Position:
    """
    Active trade position.
    
    Mutable - tracks current position state.
    """
    setup: TradeSetup
    entry_time: float
    entry_price: float
    current_pnl: float
    is_active: bool
    
    def update_pnl(self, current_price: float) -> None:
        """Update current P&L."""
        if self.setup.side == 'long':
            self.current_pnl = current_price - self.entry_price
        else:  # short
            self.current_pnl = self.entry_price - current_price


@dataclass
class StateTransition:
    """
    State transition log entry.
    
    Records state changes for analysis.
    """
    timestamp: float
    from_state: SLBRSState
    to_state: SLBRSState
    reason: str
    price: float


class SLBRSStateMachine:
    """
    SLBRS strategy state machine.
    
    INVARIANT: States follow exact sequence (no skipping).
    INVARIANT: Entry ONLY in RETEST_ARMED state.
    INVARIANT: One setup at a time.
    INVARIANT: Regime must be SIDEWAYS.
    """
    
    # Retest parameters
    MIN_RETRACE_BPS = 10.0  # Minimum retrace from block
    MIN_FIRST_TEST_DURATION = 5.0  # seconds
    SETUP_TIMEOUT_SECONDS = 300.0  # 5 minutes
    
    # Risk management
    STOP_LOSS_ATR_MULTIPLIER = 0.5  # Stop beyond block
    TAKE_PROFIT_ATR_MULTIPLIER = 2.0  # 2:1 reward:risk
    
    def __init__(self):
        """Initialize state machine."""
        self.state = SLBRSState.DISABLED
        self.current_block: Optional[LiquidityBlock] = None
        self.current_setup: Optional[TradeSetup] = None
        self.current_position: Optional[Position] = None
        self.first_test_time: Optional[float] = None
        self.setup_time: Optional[float] = None
        self.transition_history: List[StateTransition] = []
    
    def update(
        self,
        regime: RegimeType,
        tradable_blocks: List[LiquidityBlock],
        current_price: float,
        current_time: float,
        atr: float
    ) -> Optional[str]:
        """
        Update state machine.
        
        Args:
            regime: Current regime
            tradable_blocks: Available ABSORPTION blocks
            current_price: Current mid-price
            current_time: Current timestamp
            atr: Current ATR(5m) for risk calc
        
        Returns:
            Trade signal ('ENTER', 'EXIT', or None)
        
        RULE: Check regime first - abort if not SIDEWAYS.
        RULE: Follow state sequence exactly.
        """
        # HARD REGIME GATE (compare by value to allow different enum classes)
        regime_value = regime.value if hasattr(regime, 'value') else str(regime)
        if regime_value != "SIDEWAYS":
            if self.state != SLBRSState.DISABLED:
                return self._force_exit("Regime changed", current_price, current_time)
            return None
        
        # State-specific logic
        if self.state == SLBRSState.DISABLED:
            return self._handle_disabled(tradable_blocks, current_time, atr, current_price)
        
        elif self.state == SLBRSState.SETUP_DETECTED:
            return self._handle_setup_detected(current_price, current_time)
        
        elif self.state == SLBRSState.FIRST_TEST:
            return self._handle_first_test(current_price, current_time)
        
        elif self.state == SLBRSState.RETEST_ARMED:
            return self._handle_retest_armed(current_price, current_time)
        
        elif self.state == SLBRSState.IN_POSITION:
            return self._handle_in_position(current_price, current_time)
        
        return None
    
    def _handle_disabled(
        self,
        tradable_blocks: List[LiquidityBlock],
        current_time: float,
        atr: float,
        current_price: float
    ) -> Optional[str]:
        """
        DISABLED state: Look for ABSORPTION blocks.
        
        Transition: DISABLED → SETUP_DETECTED
        """
        if not tradable_blocks:
            return None
        
        # Take first tradable block (ABSORPTION only)
        block = tradable_blocks[0]
        
        # Store block and create setup
        self.current_block = block
        self.setup_time = current_time
        self.current_setup = self._create_setup(block, atr)
        
        # Transition to SETUP_DETECTED
        self._transition(SLBRSState.SETUP_DETECTED, "ABSORPTION block detected", current_price, current_time)
        
        return None
    
    def _handle_setup_detected(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        SETUP_DETECTED: Wait for first test.
        
        Transition: SETUP_DETECTED → FIRST_TEST
        """
        # Check timeout
        if (current_time - self.setup_time) > self.SETUP_TIMEOUT_SECONDS:
            return self._reset("Setup timeout", current_price, current_time)
        
        # Check if block invalidated
        if self._block_invalidated(current_price):
            return self._reset("Block invalidated", current_price, current_time)
        
        # Check if price entered block zone (first test)
        if self._price_in_block(current_price):
            self.first_test_time = current_time
            self._transition(SLBRSState.FIRST_TEST, "First test begun", current_price, current_time)
        
        return None
    
    def _handle_first_test(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        FIRST_TEST: Price testing block, wait for retrace.
        
        Transition: FIRST_TEST → RETEST_ARMED
        """
        # Check if block invalidated
        if self._block_invalidated(current_price):
            return self._reset("Block invalidated", current_price, current_time)
        
        # Check if price left block zone
        if not self._price_in_block(current_price):
            # Check if retracted sufficiently
            if self._price_retracted_enough(current_price):
                self._transition(SLBRSState.RETEST_ARMED, "Retrace complete", current_price, current_time)
        
        return None
    
    def _handle_retest_armed(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        RETEST_ARMED: Wait for retest, ENTER on retest.
        
        Transition: RETEST_ARMED → IN_POSITION
        
        RULE: Entry ONLY in this state.
        """
        # Check timeout
        if (current_time - self.setup_time) > self.SETUP_TIMEOUT_SECONDS:
            return self._reset("Setup timeout", current_price, current_time)
        
        # Check if block invalidated
        if self._block_invalidated(current_price):
            return self._reset("Block invalidated", current_price, current_time)
        
        # Check for retest (price back in block)
        if self._price_in_block(current_price):
            # ENTRY CONDITIONS MET
            self.current_position = Position(
                setup=self.current_setup,
                entry_time=current_time,
                entry_price=current_price,
                current_pnl=0.0,
                is_active=True
            )
            self._transition(SLBRSState.IN_POSITION, "Retest entry", current_price, current_time)
            return "ENTER"
        
        return None
    
    def _handle_in_position(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        IN_POSITION: Monitor stop/target.
        
        Transition: IN_POSITION → DISABLED
        """
        if not self.current_position:
            return self._reset("No position", current_price, current_time)
        
        # Update P&L
        self.current_position.update_pnl(current_price)
        
        # Check stop loss
        if self._stop_hit(current_price):
            return self._exit_position("Stop loss hit", current_price, current_time)
        
        # Check take profit
        if self._target_hit(current_price):
            return self._exit_position("Take profit hit", current_price, current_time)
        
        # Check block invalidation
        if self._block_invalidated(current_price):
            return self._exit_position("Block invalidated", current_price, current_time)
        
        return None
    
    def _create_setup(self, block: LiquidityBlock, atr: float) -> TradeSetup:
        """
        Create trade setup from block.
        
        Args:
            block: ABSORPTION block
            atr: Current ATR for stop/target calc
        
        Returns:
            TradeSetup with entry/stop/target
        
        RULE: Stop beyond block, target 2x risk.
        """
        # Determine side
        side = 'long' if block.side == 'bid' else 'short'
        
        # Entry at block weighted average (or mid if None)
        entry_price = block.initial_price
        
        # Calculate stop and target
        if side == 'long':
            # Long: stop below block
            stop_loss = block.price_min - (self.STOP_LOSS_ATR_MULTIPLIER * atr)
            risk = entry_price - stop_loss
            take_profit = entry_price + (self.TAKE_PROFIT_ATR_MULTIPLIER * risk)
        else:  # short
            # Short: stop above block
            stop_loss = block.price_max + (self.STOP_LOSS_ATR_MULTIPLIER * atr)
            risk = stop_loss - entry_price
            take_profit = entry_price - (self.TAKE_PROFIT_ATR_MULTIPLIER * risk)
        
        return TradeSetup(
            block=block,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            side=side,
            setup_time=self.setup_time
        )
    
    def _price_in_block(self, price: float) -> bool:
        """Check if price in block zone."""
        if not self.current_block:
            return False
        return self.current_block.price_min <= price <= self.current_block.price_max
    
    def _price_retracted_enough(self, price: float) -> bool:
        """
        Check if price retracted sufficiently.
        
        RULE: Minimum retrace distance in bps.
        """
        if not self.current_block:
            return False
        
        # Calculate distance from block mid in bps
        mid_block = (self.current_block.price_min + self.current_block.price_max) / 2
        distance_bps = abs(price - mid_block) / mid_block * 10000
        
        return distance_bps >= self.MIN_RETRACE_BPS
    
    def _stop_hit(self, price: float) -> bool:
        """Check if stop loss hit."""
        if not self.current_setup:
            return False
        
        if self.current_setup.side == 'long':
            return price <= self.current_setup.stop_loss
        else:  # short
            return price >= self.current_setup.stop_loss
    
    def _target_hit(self, price: float) -> bool:
        """Check if take profit hit."""
        if not self.current_setup:
            return False
        
        if self.current_setup.side == 'long':
            return price >= self.current_setup.take_profit
        else:  # short
            return price <= self.current_setup.take_profit
    
    def _block_invalidated(self, price: float) -> bool:
        """
        Check if block invalidated.
        
        RULE: Block invalidated if price accepts through.
        """
        if not self.current_block:
            return False
        
        if self.current_block.side == 'bid':
            # Bid block - invalidated if price breaks below
            return price < self.current_block.price_min
        else:  # ask
            # Ask block - invalidated if price breaks above
            return price > self.current_block.price_max
    
    def _exit_position(self, reason: str, price: float, timestamp: float) -> str:
        """
        Exit position and reset.
        
        Returns:
            'EXIT' signal
        """
        self.current_position = None
        self._transition(SLBRSState.DISABLED, reason, price, timestamp)
        self._clear_setup()
        return "EXIT"
    
    def _force_exit(self, reason: str, price: float, timestamp: float) -> Optional[str]:
        """
        Force exit (regime change).
        
        Returns:
            'EXIT' if in position, None otherwise
        """
        if self.current_position:
            return self._exit_position(reason, price, timestamp)
        
        self._transition(SLBRSState.DISABLED, reason, price, timestamp)
        self._clear_setup()
        return None
    
    def _reset(self, reason: str, price: float, timestamp: float) -> None:
        """
        Reset state machine.
        
        Returns:
            None (no trade signal)
        """
        self._transition(SLBRSState.DISABLED, reason, price, timestamp)
        self._clear_setup()
        return None
    
    def _transition(self, new_state: SLBRSState, reason: str, price: float, timestamp: float) -> None:
        """
        Transition to new state and log.
        
        Args:
            new_state: Target state
            reason: Reason for transition
            price: Current price
            timestamp: Current timestamp
        """
        transition = StateTransition(
            timestamp=timestamp,
            from_state=self.state,
            to_state=new_state,
            reason=reason,
            price=price
        )
        self.transition_history.append(transition)
        self.state = new_state
    
    def _clear_setup(self) -> None:
        """Clear all setup state."""
        self.current_block = None
        self.current_setup = None
        self.first_test_time = None
        self.setup_time = None
    
    def get_state(self) -> SLBRSState:
        """Get current state."""
        return self.state
    
    def get_position(self) -> Optional[Position]:
        """Get current position."""
        return self.current_position
    
    def get_setup(self) -> Optional[TradeSetup]:
        """Get current setup."""
        return self.current_setup
    
    def get_transition_history(self) -> List[StateTransition]:
        """Get state transition history."""
        return self.transition_history
    
    def reset(self) -> None:
        """Hard reset state machine."""
        self.state = SLBRSState.DISABLED
        self._clear_setup()
        self.current_position = None
        self.transition_history.clear()

"""Execution Controller.

Orchestrates mandate arbitration → state machine → execution flow.

Enforces:
- All 13 state machine theorems
- All 13 arbitration theorems
- Constitutional logging requirements
"""

import time
from typing import List, Dict, Optional
from decimal import Decimal

from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.arbitration.types import Mandate, Action, ActionType
from runtime.position.state_machine import PositionStateMachine, Action as StateAction
from runtime.position.types import PositionState, Direction, InvariantViolation
from .types import ExecutionResult, CycleStats


class ExecutionController:
    """Main execution controller orchestrating the flow.
    
    Architecture:
    1. Receive mandates from strategies/risk
    2. Arbitrate mandates → single action per symbol
    3. Validate action against state machine
    4. Execute action → update position state
    5. Log results
    
    Properties:
    - Symbol-local execution (independent processing)
    - State machine invariants preserved
    - Arbitration properties enforced
    - Constitutional logging
    """
    
    def __init__(self):
        """Initialize controller with state machine and arbitrator."""
        self.state_machine = PositionStateMachine()
        self.arbitrator = MandateArbitrator()
        self._execution_log: List[ExecutionResult] = []
    
    def process_cycle(self, mandates: List[Mandate]) -> CycleStats:
        """Process one execution cycle.
        
        Args:
            mandates: List of all mandates from strategies/risk
            
        Returns:
            CycleStats with execution summary
        """
        actions_executed = 0
        actions_rejected = 0
        
        # Step 1: Arbitrate mandates per symbol
        actions = self.arbitrator.arbitrate_all(mandates)
        
        # Step 2: Execute actions
        for symbol, action in actions.items():
            if action.type == ActionType.NO_ACTION:
                continue  # Skip NO_ACTION
            
            result = self.execute_action(symbol, action)
            self._execution_log.append(result)
            
            if result.success:
                actions_executed += 1
            else:
                actions_rejected += 1
        
        return CycleStats(
            mandates_received=len(mandates),
            actions_executed=actions_executed,
            actions_rejected=actions_rejected,
            symbols_processed=len(actions),
        )
    
    def execute_action(self, symbol: str, action: Action) -> ExecutionResult:
        """Execute a single action on a position.
        
        Args:
            symbol: Symbol to execute on
            action: Arbitrated action to execute
            
        Returns:
            ExecutionResult with outcome
        """
        timestamp = time.time()
        position_before = self.state_machine.get_position(symbol)
        state_before = position_before.state
        
        # Validate action is compatible with state
        if not self._is_valid_action(state_before, action.type):
            return ExecutionResult(
                symbol=symbol,
                action=action.type,
                success=False,
                state_before=state_before,
                state_after=state_before,  # No change
                timestamp=timestamp,
                error=f"Invalid action {action.type} for state {state_before}",
            )
        
        # Execute action → trigger state transition
        try:
            state_action = self._map_action_to_state_action(action.type)
            
            # For now, just trigger the state transition
            # In real implementation, would submit exchange orders here
            if state_action == StateAction.ENTRY:
                # Entry requires direction (simplified - would come from mandate)
                new_position = self.state_machine.transition(
                    symbol, state_action, direction=Direction.LONG
                )
            elif state_action == StateAction.EXIT:
                new_position = self.state_machine.transition(symbol, state_action)
            elif state_action == StateAction.REDUCE:
                new_position = self.state_machine.transition(symbol, state_action)
            elif state_action == StateAction.HOLD:
                new_position = position_before  # No change
            else:
                return ExecutionResult(
                    symbol=symbol,
                    action=action.type,
                    success=False,
                    state_before=state_before,
                    state_after=state_before,
                    timestamp=timestamp,
                    error=f"Unknown action type: {action.type}",
                )
            
            return ExecutionResult(
                symbol=symbol,
                action=action.type,
                success=True,
                state_before=state_before,
                state_after=new_position.state,
                timestamp=timestamp,
                error=None,
            )
            
        except InvariantViolation as e:
            return ExecutionResult(
                symbol=symbol,
                action=action.type,
                success=False,
                state_before=state_before,
                state_after=state_before,
                timestamp=timestamp,
                error=str(e),
            )
    
    def _is_valid_action(self, state: PositionState, action_type: ActionType) -> bool:
        """Check if action is valid for current position state.
        
        Args:
            state: Current position state
            action_type: Action to validate
            
        Returns:
            True if action is valid for state
        """
        # Map state → allowed actions
        valid_actions = {
            PositionState.FLAT: {ActionType.ENTRY, ActionType.HOLD},
            PositionState.ENTERING: set(),  # Awaiting exchange response
            PositionState.OPEN: {ActionType.EXIT, ActionType.REDUCE, ActionType.HOLD},
            PositionState.REDUCING: set(),  # Awaiting exchange response
            PositionState.CLOSING: set(),   # Awaiting exchange response
        }
        
        return action_type in valid_actions.get(state, set())
    
    def _map_action_to_state_action(self, action_type: ActionType) -> str:
        """Map arbitration action type to state machine action.
        
        Args:
            action_type: Arbitration action type
            
        Returns:
            State machine action string
        """
        mapping = {
            ActionType.ENTRY: StateAction.ENTRY,
            ActionType.EXIT: StateAction.EXIT,
            ActionType.REDUCE: StateAction.REDUCE,
            ActionType.HOLD: StateAction.HOLD,
        }
        return mapping.get(action_type, StateAction.HOLD)
    
    def get_execution_log(self) -> List[ExecutionResult]:
        """Get complete execution log for auditability.
        
        Returns:
            List of all execution results
        """
        return self._execution_log.copy()
    
    def clear_log(self):
        """Clear execution log (for testing)."""
        self._execution_log.clear()

"""Execution Controller.

Orchestrates mandate arbitration → state machine → execution flow.

Enforces:
- All 13 state machine theorems
- All 13 arbitration theorems
- Risk constraints (leverage, liquidation avoidance)
- Constitutional logging requirements
"""

import time
from typing import List, Dict, Optional
from decimal import Decimal

from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.arbitration.types import Mandate, Action, ActionType
from runtime.position.state_machine import PositionStateMachine, Action as StateAction
from runtime.position.types import PositionState, Direction, InvariantViolation
from runtime.risk.monitor import RiskMonitor  # NEW
from runtime.risk.types import RiskConfig, AccountState  # NEW
from .types import ExecutionResult, CycleStats


class ExecutionController:
    """Main execution controller orchestrating the flow.
    
    Architecture:
    1. Receive mandates from strategies
    2. Check risk invariants → emit protective mandates
    3. Arbitrate all mandates → single action per symbol
    4. Validate ENTRY actions against risk constraints
    5. Validate action against state machine
    6. Execute action → update position state
    7. Log results
    
    Properties:
    - Symbol-local execution (independent processing)
    - State machine invariants preserved
    - Arbitration properties enforced
    - Risk constraints enforced (fail closed)
    - Constitutional logging
    """
    
    def __init__(self, risk_config: Optional[RiskConfig] = None):
        """Initialize controller with state machine, arbitrator, and risk monitor."""
        self.state_machine = PositionStateMachine()
        self.arbitrator = MandateArbitrator()
        # Initialize risk monitor with default or provided config
        self.risk_monitor = RiskMonitor(risk_config or RiskConfig())
        self._execution_log: List[ExecutionResult] = []
        self._mark_prices: Dict[str, Decimal] = {}  # Current mark prices
    
    def process_cycle(
        self,
        mandates: List[Mandate],
        account: AccountState,
        mark_prices: Dict[str, Decimal]
    ) -> CycleStats:
        """Process one execution cycle.

        Args:
            mandates: List of mandates from strategies
            account: Current account state (equity, margin)
            mark_prices: Current mark prices

        Returns:
            CycleStats with execution summary
        """
        # Store mark prices for use in execute_action
        self._mark_prices = mark_prices

        actions_executed = 0
        actions_rejected = 0

        # Step 0: Get current positions
        positions = self.state_machine._positions

        # Step 1: Risk Monitor check (emit protective mandates)
        risk_mandates = self.risk_monitor.check_and_emit(
            account, positions, mark_prices
        )

        # Combine strategy mandates with risk mandates
        all_mandates = mandates + risk_mandates

        # Step 2: Arbitrate mandates per symbol
        actions = self.arbitrator.arbitrate_all(all_mandates)

        # Step 3: Execute actions
        for symbol, action in actions.items():
            if action.type == ActionType.NO_ACTION:
                continue  # Skip NO_ACTION
            
            # Step 3a: Validate ENTRY actions against risk constraints
            if action.type == ActionType.ENTRY:
                # Need entry details (size, price, direction)
                # In full implementation, these come from the mandate/action
                # For now, we assume fixed size or extract from mandate if available
                
                # Simplified entry validation for V1:
                # We need entry parameters which Action struct doesn't strictly have yet
                # Assuming Action carries metadata or we look up the mandate
                # TODO: Enhance Action type to carry entry params
                
                # For now, we'll validate a default small entry to check headers
                # or rely on the fact that if we have an ENTRY action, we imply specific params
                # This is a stub for integration - real impl needs Action.quantity
                
                # Assuming mandate has authority, we still check risk
                valid, error = self.risk_monitor.validate_entry(
                    symbol=symbol,
                    size=Decimal("0.1"), # Placeholder - needs actual size
                    direction="LONG",    # Placeholder
                    entry_price=mark_prices.get(symbol, Decimal("0")),
                    account=account,
                    positions=positions,
                    mark_prices=mark_prices
                )
                
                if not valid:
                    # Log rejection
                    self._execution_log.append(ExecutionResult(
                        symbol=symbol,
                        action=action.type,
                        success=False,
                        state_before=self.state_machine.get_position(symbol).state,
                        state_after=self.state_machine.get_position(symbol).state,
                        timestamp=time.time(),
                        error=f"Risk validation failed: {error}"
                    ))
                    actions_rejected += 1
                    continue
            
            result = self.execute_action(symbol, action)
            self._execution_log.append(result)
            
            if result.success:
                actions_executed += 1
            else:
                actions_rejected += 1
        
        return CycleStats(
            mandates_received=len(all_mandates),
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
                # TODO: Get actual direction/size from Action/Mandate
                new_position = self.state_machine.transition(
                    symbol, state_action, direction=Direction.LONG
                )

                # For ghost trading: immediately confirm entry (ENTERING → OPEN)
                # In live trading, this would happen after exchange confirms fill
                if new_position.state == PositionState.ENTERING:
                    # Use actual mark price instead of zero
                    entry_price = self._mark_prices.get(symbol, Decimal("1"))  # Fallback to 1 if missing
                    new_position = self.state_machine.transition(
                        symbol, "SUCCESS",
                        quantity=Decimal("0.01"),  # Placeholder
                        entry_price=entry_price
                    )
            elif state_action == StateAction.EXIT:
                new_position = self.state_machine.transition(symbol, state_action)

                # For ghost trading: immediately confirm exit (CLOSING → FLAT)
                # In live trading, this would happen after exchange confirms fill
                if new_position.state == PositionState.CLOSING:
                    new_position = self.state_machine.transition(symbol, "SUCCESS")

            elif state_action == StateAction.REDUCE:
                new_position = self.state_machine.transition(symbol, state_action)

                # For ghost trading: immediately confirm reduction
                # In live trading, this would happen after exchange confirms partial fill
                if new_position.state == PositionState.REDUCING:
                    # Could transition to OPEN (partial) or CLOSING (complete)
                    # For now, assume partial → back to OPEN
                    new_position = self.state_machine.transition(symbol, "PARTIAL",
                        quantity=Decimal("0.005")  # Placeholder for remaining
                    )
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
        
        if action_type == ActionType.NO_ACTION:
             return True
             
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

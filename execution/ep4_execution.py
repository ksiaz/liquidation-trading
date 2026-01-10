"""
EP-4 Execution - Main Execution Policy Layer v1.0

Deterministic execution orchestrator with 6-step pipeline.
Zero market interpretation. Fail-safe philosophy.

Authority: EP-4 Execution Policy Specification v1.0
"""

from dataclasses import dataclass
from typing import Optional, Literal
from enum import Enum
import json

from execution.ep4_action_schemas import (
    Action,
    OpenPositionAction,
    ClosePositionAction,
    AdjustPositionAction,
    CancelOrdersAction,
    NoOpAction,
    OrderType,
    validate_action_schema,
    SchemaValidationError
)
from execution.ep4_risk_gates import (
    RiskConfig,
    RiskContext,
    validate_all_risk_gates,
    RiskGateViolation
)
from execution.ep4_exchange_adapter import (
    MockedExchangeAdapter,
    ExchangeConstraints,
    ExchangeResponseCode,
    validate_exchange_constraints,
    ExchangeConstraintViolation
)


# ==============================================================================
# Input Types (from EP-3 and context)
# ==============================================================================

class DecisionCode(Enum):
    """Policy decision codes from EP-3."""
    AUTHORIZED_ACTION = "AUTHORIZED_ACTION"
    NO_ACTION = "NO_ACTION"
    REJECTED_ACTION = "REJECTED_ACTION"


@dataclass(frozen=True)
class PolicyDecision:
    """
    Policy decision from EP-3.
    EP-4 never questions this authority.
    """
    decision_code: DecisionCode
    action: Optional[Action]
    reason_code: str
    timestamp: float
    trace_id: str


@dataclass(frozen=True)
class ExecutionContext:
    """
    Execution context.
    Provided by caller, never inferred.
    """
    exchange: str  # e.g. "BINANCE_PERP"
    symbol: str
    account_id: str  # Opaque
    timestamp: float


# ==============================================================================
# Output Types
# ==============================================================================

class ExecutionResultCode(Enum):
    """Execution result codes."""
    SUCCESS = "SUCCESS"
    NOOP = "NOOP"
    REJECTED = "REJECTED"
    FAILED_SAFE = "FAILED_SAFE"


@dataclass(frozen=True)
class ExecutionResult:
    """
    Execution result.
    Immutable, auditable.
    """
    result_code: ExecutionResultCode
    action_id: Optional[str]
    trace_id: str
    timestamp: float
    reason_code: str
    audit_log: str  # JSON string


# ==============================================================================
# EP-4 Main Execution Orchestrator
# ==============================================================================

class ExecutionOrchestrator:
    """
    Main EP-4 execution orchestrator.
    
    Implements 6-step deterministic pipeline:
    1. Authorization Gate
    2. Schema Validation
    3. Risk Gates
    4. Exchange Constraints
    5. Execution Attempt
    6. Post-Execution Verification
    """
    
    def __init__(
        self,
        *,
        risk_config: RiskConfig,
        exchange_adapter: MockedExchangeAdapter
    ):
        """
        Initialize execution orchestrator.
        
        Args:
            risk_config: Risk configuration
            exchange_adapter: Exchange adapter
        """
        self._risk_config = risk_config
        self._exchange_adapter = exchange_adapter
    
    def execute_policy_decision(
        self,
        *,
        decision: PolicyDecision,
        context: ExecutionContext,
        risk_context: RiskContext
    ) -> ExecutionResult:
        """
        Execute policy decision through 6-step pipeline.
        
        Args:
            decision: Policy decision from EP-3
            context: Execution context
            risk_context: Risk context
        
        Returns:
            ExecutionResult (immutable)
        """
        audit_data = {
            "trace_id": decision.trace_id,
            "decision_code": decision.decision_code.value,
            "timestamp": context.timestamp,
            "pipeline_steps": []
        }
        
        try:
            # STEP 1: Authorization Gate (Absolute)
            audit_data["pipeline_steps"].append("authorization_gate")
            if decision.decision_code != DecisionCode.AUTHORIZED_ACTION:
                return self._create_result(
                    result_code=ExecutionResultCode.NOOP,
                    action_id=None,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code="UNAUTHORIZED_DECISION",
                    audit_data=audit_data
                )
            
            # Must have action if authorized
            if decision.action is None:
                return self._create_result(
                    result_code=ExecutionResultCode.REJECTED,
                    action_id=None,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code="MISSING_ACTION",
                    audit_data=audit_data
                )
            
            action = decision.action
            action_id = action.action_id
            audit_data["action_id"] = action_id
            audit_data["action_type"] = type(action).__name__
            
            # STEP 2: Schema Validation
            audit_data["pipeline_steps"].append("schema_validation")
            try:
                validate_action_schema(action)
            except SchemaValidationError as e:
                return self._create_result(
                    result_code=ExecutionResultCode.REJECTED,
                    action_id=action_id,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code=f"SCHEMA_INVALID: {str(e)}",
                    audit_data=audit_data
                )
            
            # STEP 3: Risk Gates
            audit_data["pipeline_steps"].append("risk_gates")
            try:
                # Extract quantity for risk validation
                quantity = self._extract_quantity(action)
                if quantity is not None:
                    validate_all_risk_gates(
                        quantity=quantity,
                        risk_config=self._risk_config,
                        risk_context=risk_context
                    )
            except RiskGateViolation as e:
                return self._create_result(
                    result_code=ExecutionResultCode.FAILED_SAFE,
                    action_id=action_id,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code=f"RISK_GATE_FAILED: {str(e)}",
                    audit_data=audit_data
                )
            
            # STEP 4: Exchange Constraints
            audit_data["pipeline_steps"].append("exchange_constraints")
            try:
                self._validate_constraints(action, risk_context.current_price)
            except ExchangeConstraintViolation as e:
                return self._create_result(
                    result_code=ExecutionResultCode.FAILED_SAFE,
                    action_id=action_id,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code=f"EXCHANGE_CONSTRAINT_VIOLATED: {str(e)}",
                    audit_data=audit_data
                )
            
            # STEP 5: Execution Attempt
            audit_data["pipeline_steps"].append("execution_attempt")
            exchange_response = self._execute_action(action, context.timestamp)
            audit_data["exchange_response"] = {
                "code": exchange_response.response_code.value,
                "order_id": exchange_response.order_id,
                "message": exchange_response.message
            }
            
            # STEP 6: Post-Execution Verification
            audit_data["pipeline_steps"].append("post_execution_verification")
            if exchange_response.response_code == ExchangeResponseCode.ACKNOWLEDGED:
                return self._create_result(
                    result_code=ExecutionResultCode.SUCCESS,
                    action_id=action_id,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code="EXECUTION_SUCCESS",
                    audit_data=audit_data
                )
            elif exchange_response.response_code == ExchangeResponseCode.REJECTED:
                return self._create_result(
                    result_code=ExecutionResultCode.FAILED_SAFE,
                    action_id=action_id,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code="EXCHANGE_REJECTED",
                    audit_data=audit_data
                )
            else:  # TIMEOUT or AMBIGUOUS
                return self._create_result(
                    result_code=ExecutionResultCode.FAILED_SAFE,
                    action_id=action_id,
                    trace_id=decision.trace_id,
                    timestamp=context.timestamp,
                    reason_code=f"EXCHANGE_{exchange_response.response_code.value}",
                    audit_data=audit_data
                )
        
        except Exception as e:
            # Unexpected failure → FAILED_SAFE
            audit_data["unexpected_error"] = str(e)
            return self._create_result(
                result_code=ExecutionResultCode.FAILED_SAFE,
                action_id=action_id if 'action_id' in locals() else None,
                trace_id=decision.trace_id,
                timestamp=context.timestamp,
                reason_code=f"UNEXPECTED_ERROR: {str(e)}",
                audit_data=audit_data
            )
    
    def _extract_quantity(self, action: Action) -> Optional[float]:
        """Extract quantity from action for risk validation."""
        if isinstance(action, OpenPositionAction):
            return action.quantity
        elif isinstance(action, ClosePositionAction):
            return action.quantity  # May be None
        elif isinstance(action, AdjustPositionAction):
            return action.delta_quantity
        else:
            return None
    
    def _validate_constraints(self, action: Action, current_price: float) -> None:
        """Validate action against exchange constraints."""
        constraints = self._exchange_adapter.get_constraints()
        
        if isinstance(action, OpenPositionAction):
            price = action.limit_price if action.order_type == OrderType.LIMIT else current_price
            validate_exchange_constraints(
                quantity=action.quantity,
                price=price,
                constraints=constraints
            )
        elif isinstance(action, ClosePositionAction):
            if action.quantity is not None:
                validate_exchange_constraints(
                    quantity=action.quantity,
                    price=current_price,
                    constraints=constraints
                )
    
    def _execute_action(self, action: Action, timestamp: float):
        """Execute action on exchange."""
        if isinstance(action, (OpenPositionAction, ClosePositionAction, AdjustPositionAction)):
            return self._exchange_adapter.execute_order(
                action_id=action.action_id,
                order_params={"action": action},  # Opaque
                timestamp=timestamp
            )
        elif isinstance(action, CancelOrdersAction):
            return self._exchange_adapter.cancel_orders(
                action_id=action.action_id,
                symbol=action.symbol,
                timestamp=timestamp
            )
        elif isinstance(action, NoOpAction):
            # NOOP always succeeds
            from execution.ep4_exchange_adapter import ExchangeResponse, ExchangeResponseCode
            return ExchangeResponse(
                response_code=ExchangeResponseCode.ACKNOWLEDGED,
                order_id=None,
                message="NOOP acknowledged",
                timestamp=timestamp
            )
        else:
            raise ValueError(f"Unknown action type: {type(action)}")
    
    def _create_result(
        self,
        *,
        result_code: ExecutionResultCode,
        action_id: Optional[str],
        trace_id: str,
        timestamp: float,
        reason_code: str,
        audit_data: dict
    ) -> ExecutionResult:
        """Create execution result with audit log."""
        audit_data["result_code"] = result_code.value
        audit_data["reason_code"] = reason_code
        
        return ExecutionResult(
            result_code=result_code,
            action_id=action_id,
            trace_id=trace_id,
            timestamp=timestamp,
            reason_code=reason_code,
            audit_log=json.dumps(audit_data, indent=2)
        )

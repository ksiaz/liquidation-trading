"""
EP-4 Execution Policy Layer v1.0

Deterministic execution orchestrator with fail-safe philosophy.
"""

from execution.ep4_execution import (
    ExecutionOrchestrator,
    PolicyDecision,
    DecisionCode,
    ExecutionContext,
    ExecutionResult,
    ExecutionResultCode
)
from execution.ep4_action_schemas import (
    Action,
    OpenPositionAction,
    ClosePositionAction,
    AdjustPositionAction,
    CancelOrdersAction,
    NoOpAction,
    Side,
    OrderType,
    TimeInForce
)
from execution.ep4_risk_gates import (
    RiskConfig,
    RiskContext,
    RiskGateViolation
)
from execution.ep4_exchange_adapter import (
    ExchangeConstraints,
    MockedExchangeAdapter,
    ExchangeResponse,
    ExchangeResponseCode
)

__all__ = [
    # Main orchestrator
    "ExecutionOrchestrator",
    "PolicyDecision",
    "DecisionCode",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionResultCode",
    # Actions
    "Action",
    "OpenPositionAction",
    "ClosePositionAction",
    "AdjustPositionAction",
    "CancelOrdersAction",
    "NoOpAction",
    "Side",
    "OrderType",
    "TimeInForce",
    # Risk
    "RiskConfig",
    "RiskContext",
    "RiskGateViolation",
    # Exchange
    "ExchangeConstraints",
    "MockedExchangeAdapter",
    "ExchangeResponse",
    "ExchangeResponseCode",
]

"""
EP-4 Execution Tests - Comprehensive Test Suite

Tests for EP-4 Execution Policy Layer v1.0
Covers: unit tests, integration tests, negative tests, determinism.

Authority: EP-4 Execution Policy Specification v1.0
"""

import pytest
from execution.ep4_execution import (
    ExecutionOrchestrator,
    PolicyDecision,
    DecisionCode,
    ExecutionContext,
    ExecutionResultCode
)
from execution.ep4_action_schemas import (
    OpenPositionAction,
    ClosePositionAction,
    AdjustPositionAction,
    CancelOrdersAction,
    NoOpAction,
    Side,
    OrderType,
    TimeInForce
)
from execution.ep4_risk_gates import RiskConfig, RiskContext
from execution.ep4_exchange_adapter import (
    MockedExchangeAdapter,
    ExchangeConstraints
)


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def risk_config():
    """Standard risk configuration."""
    return RiskConfig(
        max_position_size=100.0,
        max_notional=100000.0,  # High enough for tests
        max_leverage=5.0,
        max_actions_per_minute=10,
        cooldown_seconds=1.0
    )


@pytest.fixture
def exchange_constraints():
    """Standard exchange constraints."""
    return ExchangeConstraints(
        min_order_size=0.01,
        max_order_size=1000.0,
        step_size=0.01,
        tick_size=0.1,
        max_leverage=10.0,
        margin_mode="CROSS"
    )


@pytest.fixture
def exchange_adapter(exchange_constraints):
    """Mocked exchange adapter."""
    return MockedExchangeAdapter(exchange_constraints=exchange_constraints)


@pytest.fixture
def orchestrator(risk_config, exchange_adapter):
    """Execution orchestrator."""
    return ExecutionOrchestrator(
        risk_config=risk_config,
        exchange_adapter=exchange_adapter
    )


@pytest.fixture
def execution_context():
    """Standard execution context."""
    return ExecutionContext(
        exchange="BINANCE_PERP",
        symbol="BTCUSDT",
        account_id="TEST_ACCOUNT",
        timestamp=3000.0
    )


@pytest.fixture
def risk_context():
    """Standard risk context (low risk)."""
    return RiskContext(
        current_price=50000.0,
        account_balance=10000.0,
        current_position_size=0.0,
        actions_in_last_minute=0,
        time_since_last_action=10.0
    )


# ==============================================================================
# Unit Tests - Authorization Gate
# ==============================================================================

def test_authorization_gate_noop_on_no_action(orchestrator, execution_context, risk_context):
    """Step 1: NO_ACTION decision → NOOP result."""
    decision = PolicyDecision(
        decision_code=DecisionCode.NO_ACTION,
        action=None,
        reason_code="NO_PROPOSAL",
        timestamp=3000.0,
        trace_id="TRACE_001"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.NOOP
    assert result.reason_code == "UNAUTHORIZED_DECISION"


def test_authorization_gate_noop_on_rejected(orchestrator, execution_context, risk_context):
    """Step 1: REJECTED_ACTION decision → NOOP result."""
    decision = PolicyDecision(
        decision_code=DecisionCode.REJECTED_ACTION,
        action=None,
        reason_code="CONFLICT",
        timestamp=3000.0,
        trace_id="TRACE_002"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.NOOP


# ==============================================================================
# Unit Tests - Schema Validation
# ==============================================================================

def test_schema_validation_rejects_zero_quantity(orchestrator, execution_context, risk_context):
    """Step 2: Invalid schema (zero quantity) → REJECTED."""
    action = OpenPositionAction(
        action_id="ACTION_001",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=0.0,  # Invalid
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_003"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.REJECTED
    assert "SCHEMA_INVALID" in result.reason_code


def test_schema_validation_rejects_limit_without_price(orchestrator, execution_context, risk_context):
    """Step 2: LIMIT order without limit_price → REJECTED."""
    action = OpenPositionAction(
        action_id="ACTION_002",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        order_type=OrderType.LIMIT,
        limit_price=None  # Invalid for LIMIT order
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_004"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.REJECTED


# ==============================================================================
# Unit Tests - Risk Gates
# ==============================================================================

def test_risk_gate_fails_on_excessive_position_size(orchestrator, execution_context):
    """Step 3: Position size exceeds max → FAILED_SAFE."""
    action = OpenPositionAction(
        action_id="ACTION_003",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=200.0,  # Exceeds max_position_size (100.0)
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_005"
    )
    
    risk_context = RiskContext(
        current_price=50000.0,
        account_balance=10000.0,
        current_position_size=0.0,
        actions_in_last_minute=0,
        time_since_last_action=10.0
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.FAILED_SAFE
    assert "RISK_GATE_FAILED" in result.reason_code


def test_risk_gate_fails_on_cooldown_violation(orchestrator, execution_context):
    """Step 3: Cooldown not satisfied → FAILED_SAFE."""
    action = OpenPositionAction(
        action_id="ACTION_004",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_006"
    )
    
    risk_context = RiskContext(
        current_price=50000.0,
        account_balance=10000.0,
        current_position_size=0.0,
        actions_in_last_minute=0,
        time_since_last_action=0.5  # < cooldown_seconds (1.0)
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.FAILED_SAFE
    assert "RISK_GATE_FAILED" in result.reason_code


# ==============================================================================
# Integration Tests - Success Path
# ==============================================================================

def test_open_position_success(orchestrator, execution_context, risk_context):
    """Integration: Open position succeeds when all gates pass."""
    action = OpenPositionAction(
        action_id="ACTION_005",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_007"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.SUCCESS
    assert result.action_id == "ACTION_005"
    assert result.reason_code == "EXECUTION_SUCCESS"


def test_close_position_success(orchestrator, execution_context, risk_context):
    """Integration: Close position succeeds."""
    action = ClosePositionAction(
        action_id="ACTION_006",
        symbol="BTCUSDT",
        quantity=None  # Full close
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_008"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.SUCCESS


def test_noop_action_success(orchestrator, execution_context, risk_context):
    """Integration: NOOP action always succeeds."""
    action = NoOpAction(action_id="ACTION_007")
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_009"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.SUCCESS


# ==============================================================================
# Determinism Tests
# ==============================================================================

def test_determinism_identical_inputs(orchestrator, execution_context, risk_context):
    """Determinism: Identical inputs → identical results."""
    action = OpenPositionAction(
        action_id="ACTION_008",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_010"
    )
    
    result1 = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    # Reset exchange adapter state for clean comparison
    orchestrator2 = ExecutionOrchestrator(
        risk_config=orchestrator._risk_config,
        exchange_adapter=MockedExchangeAdapter(
            exchange_constraints=orchestrator._exchange_adapter.get_constraints()
        )
    )
    
    result2 = orchestrator2.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result1.result_code == result2.result_code
    assert result1.reason_code == result2.reason_code


# ==============================================================================
# Negative Tests
# ==============================================================================

def test_missing_action_when_authorized(orchestrator, execution_context, risk_context):
    """Negative: AUTHORIZED_ACTION but action is None → REJECTED."""
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=None,  # Invalid
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_011"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.REJECTED
    assert "MISSING_ACTION" in result.reason_code


def test_exchange_constraint_violation(orchestrator, execution_context, risk_context):
    """Negative: Quantity not multiple of step_size → FAILED_SAFE."""
    action = OpenPositionAction(
        action_id="ACTION_012",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=0.015,  # Not multiple of step_size (0.01) - smaller to avoid notional gate
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_012"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert result.result_code == ExecutionResultCode.FAILED_SAFE
    assert "EXCHANGE_CONSTRAINT_VIOLATED" in result.reason_code


#===============================================================================
# Audit Log Tests
# ==============================================================================

def test_audit_log_includes_trace_id(orchestrator, execution_context, risk_context):
    """Audit: All results include trace_id in audit log."""
    action = OpenPositionAction(
        action_id="ACTION_013",
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=1.0,
        order_type=OrderType.MARKET,
        limit_price=None
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_013"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert "TRACE_013" in result.audit_log
    assert result.trace_id == "TRACE_013"


def test_audit_log_includes_pipeline_steps(orchestrator, execution_context, risk_context):
    """Audit: Audit log includes pipeline steps executed."""
    action = NoOpAction(action_id="ACTION_014")
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        action=action,
        reason_code="APPROVED",
        timestamp=3000.0,
        trace_id="TRACE_014"
    )
    
    result = orchestrator.execute_policy_decision(
        decision=decision,
        context=execution_context,
        risk_context=risk_context
    )
    
    assert "pipeline_steps" in result.audit_log
    assert "authorization_gate" in result.audit_log

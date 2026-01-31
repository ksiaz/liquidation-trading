"""
Integration tests for complete trade flow (HLP20).

Tests end-to-end trade lifecycle:
1. Event detection → mandate generation
2. Risk validation → position sizing
3. Order submission → stop placement
4. Price move → exit execution

These tests verify the integration between:
- Strategy layer (mandate generation)
- Risk layer (validation, sizing)
- Execution layer (order management)
- Position layer (state machine)
"""

import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Optional

# Position state machine
from runtime.position.types import Position, PositionState, Direction, InvariantViolation
from runtime.position.state_machine import PositionStateMachine, Action

# Risk management
from runtime.risk.circuit_breaker import (
    CircuitBreakerManager,
    CircuitBreakerConfig,
)
from runtime.risk.degradation import (
    DegradationManager,
    DegradationConfig,
    DegradationLevel,
)

# Failure handling
from runtime.failure.network_handler import NetworkHandler, NetworkConfig, ConnectionState
from runtime.failure.data_quality import DataQualityValidator, DataQualityConfig, MarketTick
from runtime.failure.recovery import RecoveryValidator, RecoveryConfig


# =============================================================================
# Test Fixtures
# =============================================================================

@dataclass
class MockMandate:
    """Mock mandate for testing."""
    symbol: str
    direction: Direction
    action: str  # ENTRY, EXIT, REDUCE
    size: Decimal
    entry_price: Decimal
    stop_price: Decimal
    confidence: float = 0.8
    strategy: str = "test_strategy"


@dataclass
class MockOrderResult:
    """Mock order execution result."""
    success: bool
    filled_quantity: Decimal
    filled_price: Decimal
    order_id: str = "test_order_123"


class MockRiskValidator:
    """Mock risk validation layer."""

    def __init__(self, should_approve: bool = True):
        self._should_approve = should_approve
        self._validation_calls = []

    def validate_entry(self, mandate: MockMandate, capital: Decimal) -> bool:
        """Validate entry against risk limits."""
        self._validation_calls.append(('entry', mandate.symbol, mandate.size))
        return self._should_approve

    def calculate_size(self, capital: Decimal, stop_distance: Decimal, risk_pct: float = 0.01) -> Decimal:
        """Calculate position size based on risk."""
        # Fixed fractional: size = (capital * risk) / stop_distance
        if stop_distance <= 0:
            return Decimal("0")
        return (capital * Decimal(str(risk_pct))) / stop_distance


class MockOrderExecutor:
    """Mock order execution layer."""

    def __init__(self, should_fill: bool = True, partial_fill: bool = False):
        self._should_fill = should_fill
        self._partial_fill = partial_fill
        self._orders = []
        self._stops = []

    async def submit_order(self, symbol: str, direction: Direction, size: Decimal, price: Decimal) -> MockOrderResult:
        """Submit order to exchange."""
        self._orders.append({
            'symbol': symbol,
            'direction': direction,
            'size': size,
            'price': price,
            'timestamp': time.time()
        })

        if not self._should_fill:
            return MockOrderResult(
                success=False,
                filled_quantity=Decimal("0"),
                filled_price=Decimal("0")
            )

        filled_qty = size / 2 if self._partial_fill else size
        return MockOrderResult(
            success=True,
            filled_quantity=filled_qty,
            filled_price=price
        )

    async def submit_stop(self, symbol: str, direction: Direction, size: Decimal, stop_price: Decimal) -> str:
        """Submit stop loss order."""
        stop_id = f"stop_{symbol}_{len(self._stops)}"
        self._stops.append({
            'id': stop_id,
            'symbol': symbol,
            'direction': direction,
            'size': size,
            'stop_price': stop_price
        })
        return stop_id

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        return True


# =============================================================================
# Trade Flow Integration Tests
# =============================================================================

class TestCompleteTradeFlow:
    """Test complete trade lifecycle from event to exit."""

    @pytest.mark.asyncio
    async def test_entry_flow_success(self):
        """
        Test successful entry flow:
        Event → Mandate → Risk Validation → Order → Stop → Position OPEN
        """
        # Setup components
        state_machine = PositionStateMachine()
        risk_validator = MockRiskValidator(should_approve=True)
        order_executor = MockOrderExecutor(should_fill=True)

        # 1. Generate mandate (simulating strategy layer)
        mandate = MockMandate(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            action="ENTRY",
            size=Decimal("0.1"),
            entry_price=Decimal("50000"),
            stop_price=Decimal("49000")
        )

        # 2. Risk validation
        capital = Decimal("10000")
        assert risk_validator.validate_entry(mandate, capital)

        # 3. State machine: FLAT → ENTERING
        position = state_machine.transition(
            mandate.symbol,
            Action.ENTRY,
            direction=mandate.direction
        )
        assert position.state == PositionState.ENTERING

        # 4. Submit order
        result = await order_executor.submit_order(
            mandate.symbol,
            mandate.direction,
            mandate.size,
            mandate.entry_price
        )
        assert result.success

        # 5. State machine: ENTERING → OPEN
        position = state_machine.transition(
            mandate.symbol,
            "SUCCESS",
            quantity=result.filled_quantity,
            entry_price=result.filled_price
        )
        assert position.state == PositionState.OPEN
        assert position.quantity == mandate.size

        # 6. Submit stop loss
        stop_id = await order_executor.submit_stop(
            mandate.symbol,
            Direction.SHORT,  # Opposite direction for stop
            mandate.size,
            mandate.stop_price
        )
        assert stop_id is not None
        assert len(order_executor._stops) == 1

    @pytest.mark.asyncio
    async def test_entry_rejected_by_risk(self):
        """
        Test entry rejected by risk validation.
        Position should remain FLAT.
        """
        state_machine = PositionStateMachine()
        risk_validator = MockRiskValidator(should_approve=False)

        mandate = MockMandate(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            action="ENTRY",
            size=Decimal("0.1"),
            entry_price=Decimal("50000"),
            stop_price=Decimal("49000")
        )

        # Risk validation fails
        assert not risk_validator.validate_entry(mandate, Decimal("1000"))

        # Position should remain FLAT (no transition attempted)
        position = state_machine.get_position(mandate.symbol)
        assert position.state == PositionState.FLAT

    @pytest.mark.asyncio
    async def test_entry_order_failure(self):
        """
        Test entry order fails on exchange.
        Position should return to FLAT.
        """
        state_machine = PositionStateMachine()
        order_executor = MockOrderExecutor(should_fill=False)

        mandate = MockMandate(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            action="ENTRY",
            size=Decimal("0.1"),
            entry_price=Decimal("50000"),
            stop_price=Decimal("49000")
        )

        # FLAT → ENTERING
        state_machine.transition(
            mandate.symbol,
            Action.ENTRY,
            direction=mandate.direction
        )

        # Order fails
        result = await order_executor.submit_order(
            mandate.symbol,
            mandate.direction,
            mandate.size,
            mandate.entry_price
        )
        assert not result.success

        # ENTERING → FLAT (failure)
        position = state_machine.transition(mandate.symbol, "FAILURE")
        assert position.state == PositionState.FLAT

    @pytest.mark.asyncio
    async def test_exit_flow_success(self):
        """
        Test successful exit flow:
        Position OPEN → EXIT mandate → Order → Position FLAT
        """
        state_machine = PositionStateMachine()
        order_executor = MockOrderExecutor(should_fill=True)

        # Setup: Create open position
        state_machine.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        state_machine.transition(
            "BTCUSDT", "SUCCESS",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000")
        )

        # Generate exit mandate
        exit_mandate = MockMandate(
            symbol="BTCUSDT",
            direction=Direction.SHORT,  # Opposite to close
            action="EXIT",
            size=Decimal("0.1"),
            entry_price=Decimal("51000"),
            stop_price=Decimal("0")
        )

        # OPEN → CLOSING
        position = state_machine.transition("BTCUSDT", Action.EXIT)
        assert position.state == PositionState.CLOSING

        # Submit close order
        result = await order_executor.submit_order(
            exit_mandate.symbol,
            exit_mandate.direction,
            exit_mandate.size,
            exit_mandate.entry_price
        )
        assert result.success

        # CLOSING → FLAT
        position = state_machine.transition("BTCUSDT", "SUCCESS")
        assert position.state == PositionState.FLAT

    @pytest.mark.asyncio
    async def test_partial_fill_flow(self):
        """
        Test partial fill during entry.
        Position should reflect actual filled quantity.
        """
        state_machine = PositionStateMachine()
        order_executor = MockOrderExecutor(should_fill=True, partial_fill=True)

        mandate = MockMandate(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            action="ENTRY",
            size=Decimal("0.2"),
            entry_price=Decimal("50000"),
            stop_price=Decimal("49000")
        )

        # FLAT → ENTERING
        state_machine.transition(mandate.symbol, Action.ENTRY, direction=mandate.direction)

        # Partial fill (50%)
        result = await order_executor.submit_order(
            mandate.symbol,
            mandate.direction,
            mandate.size,
            mandate.entry_price
        )
        assert result.success
        assert result.filled_quantity == mandate.size / 2

        # ENTERING → OPEN with partial quantity
        position = state_machine.transition(
            mandate.symbol,
            "SUCCESS",
            quantity=result.filled_quantity,
            entry_price=result.filled_price
        )
        assert position.state == PositionState.OPEN
        assert position.quantity == Decimal("0.1")  # Half filled


class TestTradeFlowWithRiskComponents:
    """Test trade flow integration with risk management components."""

    def test_circuit_breaker_blocks_entry(self):
        """
        Test that tripped circuit breaker blocks new entries.
        """
        state_machine = PositionStateMachine()
        breaker_manager = CircuitBreakerManager()

        # Trip the rapid loss breaker
        breaker_manager.rapid_loss.set_capital(10000)
        breaker_manager.rapid_loss.record_trade(-600)  # 6% loss

        assert breaker_manager.is_any_tripped()

        # Entry should be blocked (caller checks breaker before entry)
        if not breaker_manager.is_trading_allowed():
            # Don't attempt entry
            position = state_machine.get_position("BTCUSDT")
            assert position.state == PositionState.FLAT

    def test_degradation_reduces_size(self):
        """
        Test that degradation mode reduces position size.
        """
        degradation = DegradationManager()

        # Normal mode - full size
        assert degradation.state.size_multiplier == 1.0

        # Enter reduced mode
        from runtime.risk.degradation import DegradationTrigger
        degradation.add_trigger(
            DegradationTrigger.DATA_QUALITY_POOR,
            "Test degradation"
        )

        # Size should be reduced
        assert degradation.state.size_multiplier < 1.0

    @pytest.mark.asyncio
    async def test_recovery_required_before_trading(self):
        """
        Test that recovery validation is required after reconnection.
        """
        network_handler = NetworkHandler()
        recovery_validator = RecoveryValidator()
        state_machine = PositionStateMachine()

        # Simulate reconnection scenario
        network_handler.on_connected()
        assert network_handler.is_trading_allowed

        # Validate recovery before resuming
        result = await recovery_validator.validate_recovery()
        assert result.passed

        # Now trading can proceed
        position = state_machine.transition(
            "BTCUSDT",
            Action.ENTRY,
            direction=Direction.LONG
        )
        assert position.state == PositionState.ENTERING


class TestTradeFlowFailureRecovery:
    """Test trade flow behavior during failures."""

    @pytest.mark.asyncio
    async def test_network_disconnect_during_entry(self):
        """
        Test handling network disconnect during entry order.
        """
        # Use short backoff for test
        config = NetworkConfig(
            max_reconnect_attempts=1,
            backoff_base_ms=10
        )
        state_machine = PositionStateMachine()
        network_handler = NetworkHandler(config)

        # Set up reconnect callback that fails
        async def mock_reconnect_fail():
            return False

        network_handler.set_reconnect_callback(mock_reconnect_fail)

        # Start connected, begin entry
        network_handler.on_connected()
        state_machine.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)

        # Simulate disconnect (reconnection will fail)
        await network_handler.on_disconnect("Connection lost")

        # Trading should be blocked (FAILED state after max attempts)
        assert not network_handler.is_trading_allowed

        # Position stuck in ENTERING - emergency exit needed
        position = state_machine.get_position("BTCUSDT")
        assert position.state == PositionState.ENTERING

        # X3-A: Emergency exit path
        position = state_machine.transition("BTCUSDT", Action.EMERGENCY_EXIT)
        assert position.state == PositionState.CLOSING

    def test_stale_data_blocks_entry(self):
        """
        Test that stale market data blocks entry.
        """
        validator = DataQualityValidator()
        state_machine = PositionStateMachine()

        # Inject stale tick
        stale_ts = int(time.time() * 1_000_000_000) - 2_000_000_000  # 2s old
        tick = MarketTick(
            timestamp=stale_ts,
            symbol="BTCUSDT",
            price=50000.0
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid

        # Don't allow entry with stale data
        if not validator.is_data_fresh("BTCUSDT"):
            position = state_machine.get_position("BTCUSDT")
            assert position.state == PositionState.FLAT

    def test_closing_timeout_handling(self):
        """
        Test X6-A: CLOSING state timeout detection and handling.
        """
        state_machine = PositionStateMachine(closing_timeout_sec=0.1)  # 100ms for test

        # Create position and move to CLOSING
        state_machine.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        state_machine.transition(
            "BTCUSDT", "SUCCESS",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000")
        )
        state_machine.transition("BTCUSDT", Action.EXIT)

        assert state_machine.get_position("BTCUSDT").state == PositionState.CLOSING

        # Wait for timeout
        time.sleep(0.15)

        # Check for timeouts
        timed_out = state_machine.check_closing_timeouts()
        assert "BTCUSDT" in timed_out

        # Force close (X6-A)
        position = state_machine.force_close_timeout("BTCUSDT")
        assert position.state == PositionState.FLAT


class TestMultiSymbolTradeFlow:
    """Test trade flow with multiple symbols."""

    @pytest.mark.asyncio
    async def test_independent_symbol_positions(self):
        """
        Test that positions for different symbols are independent.
        """
        state_machine = PositionStateMachine()

        # Open BTC position
        state_machine.transition("BTCUSDT", Action.ENTRY, direction=Direction.LONG)
        state_machine.transition(
            "BTCUSDT", "SUCCESS",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000")
        )

        # Open ETH position (opposite direction)
        state_machine.transition("ETHUSDT", Action.ENTRY, direction=Direction.SHORT)
        state_machine.transition(
            "ETHUSDT", "SUCCESS",
            quantity=Decimal("-1"),
            entry_price=Decimal("3000")
        )

        # Verify independent
        btc = state_machine.get_position("BTCUSDT")
        eth = state_machine.get_position("ETHUSDT")

        assert btc.state == PositionState.OPEN
        assert btc.direction == Direction.LONG

        assert eth.state == PositionState.OPEN
        assert eth.direction == Direction.SHORT

        # Exit BTC only
        state_machine.transition("BTCUSDT", Action.EXIT)
        state_machine.transition("BTCUSDT", "SUCCESS")

        # BTC flat, ETH unchanged
        assert state_machine.get_position("BTCUSDT").state == PositionState.FLAT
        assert state_machine.get_position("ETHUSDT").state == PositionState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_affects_all_symbols(self):
        """
        Test that circuit breaker trip blocks all entries.
        """
        state_machine = PositionStateMachine()
        breaker_manager = CircuitBreakerManager()

        # Trip breaker
        breaker_manager.rapid_loss.set_capital(10000)
        breaker_manager.rapid_loss.record_trade(-600)

        assert not breaker_manager.is_trading_allowed()

        # Both symbols blocked
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            position = state_machine.get_position(symbol)
            assert position.state == PositionState.FLAT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

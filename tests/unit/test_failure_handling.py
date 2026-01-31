"""
Unit tests for failure handling module (HLP16).

Tests:
- NetworkHandler: Reconnection, heartbeat, state transitions
- DataQualityValidator: Staleness, corruption, validation
- RecoveryValidator: Recovery checks, position reconciliation
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

from runtime.failure.network_handler import (
    NetworkConfig,
    NetworkHandler,
    ConnectionState,
    ReconnectionEvent,
)
from runtime.failure.data_quality import (
    DataQualityConfig,
    DataQualityValidator,
    ValidationResult,
    ValidationStatus,
    MarketTick,
)
from runtime.failure.recovery import (
    RecoveryConfig,
    RecoveryValidator,
    RecoveryResult,
    RecoveryCheck,
    RecoveryCheckType,
)


# =============================================================================
# NetworkHandler Tests
# =============================================================================

class TestNetworkHandler:
    """Tests for NetworkHandler."""

    def test_initial_state(self):
        """Handler starts disconnected."""
        handler = NetworkHandler()
        assert handler.state == ConnectionState.DISCONNECTED
        assert not handler.is_connected
        assert not handler.is_trading_allowed

    def test_on_connected(self):
        """Connection transitions to CONNECTED state."""
        handler = NetworkHandler()
        handler.on_connected()

        assert handler.state == ConnectionState.CONNECTED
        assert handler.is_connected
        assert handler.is_trading_allowed

    def test_trading_allowed_config(self):
        """Trading halt can be disabled via config."""
        config = NetworkConfig(halt_trading_on_disconnect=False)
        handler = NetworkHandler(config)

        # Trading allowed even when disconnected
        assert handler.is_trading_allowed

    @pytest.mark.asyncio
    async def test_disconnect_triggers_reconnection(self):
        """Disconnect starts reconnection process."""
        handler = NetworkHandler()
        handler.on_connected()  # Start connected

        reconnect_called = False

        async def mock_reconnect():
            nonlocal reconnect_called
            reconnect_called = True
            return True  # Success

        handler.set_reconnect_callback(mock_reconnect)

        # Disconnect
        await handler.on_disconnect("Test disconnect")

        # Should have attempted reconnection
        assert reconnect_called
        assert handler.state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_reconnection_backoff(self):
        """Reconnection uses exponential backoff."""
        config = NetworkConfig(
            backoff_base_ms=100,
            backoff_multiplier=2.0,
            max_reconnect_attempts=3
        )
        handler = NetworkHandler(config)
        handler.on_connected()

        attempt_count = 0

        async def mock_reconnect():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return False  # Fail first 2 attempts
            return True  # Succeed on 3rd

        handler.set_reconnect_callback(mock_reconnect)

        start = time.time()
        await handler.on_disconnect("Test")
        elapsed = time.time() - start

        assert attempt_count == 3
        # Should have waited: 100ms + 200ms = 300ms minimum
        assert elapsed >= 0.25  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_max_reconnect_attempts(self):
        """Handler enters FAILED state after max attempts."""
        config = NetworkConfig(
            max_reconnect_attempts=2,
            backoff_base_ms=10
        )
        handler = NetworkHandler(config)
        handler.on_connected()

        async def mock_reconnect():
            return False  # Always fail

        handler.set_reconnect_callback(mock_reconnect)

        await handler.on_disconnect("Test")

        assert handler.state == ConnectionState.FAILED
        events = handler.get_events()
        assert len(events) == 2
        assert all(not e.success for e in events)

    def test_heartbeat_timeout_tracking(self):
        """Heartbeat timeouts are tracked."""
        handler = NetworkHandler()
        handler.on_connected()

        # Send heartbeat
        handler.on_heartbeat_sent()

        # Get summary before response
        summary = handler.get_summary()
        # Note: consecutive_timeouts won't increment until monitor_heartbeat runs

        # Receive heartbeat
        handler.on_heartbeat_received()

        summary = handler.get_summary()
        assert summary['consecutive_heartbeat_timeouts'] == 0

    def test_sequence_gap_detection(self):
        """Sequence gaps are detected and recorded."""
        handler = NetworkHandler()
        handler.on_connected()

        # Normal sequence
        handler.on_message_received(sequence=1)
        handler.on_message_received(sequence=2)
        handler.on_message_received(sequence=3)

        assert len(handler.check_sequence_gaps()) == 0

        # Gap of 5
        handler.on_message_received(sequence=9)

        gaps = handler.check_sequence_gaps()
        assert len(gaps) == 1
        assert gaps[0] == (4, 9)

    def test_state_change_callback(self):
        """State change callback is called on transitions."""
        handler = NetworkHandler()

        transitions = []

        def on_change(old, new):
            transitions.append((old, new))

        handler.set_state_change_callback(on_change)
        handler.on_connected()

        assert len(transitions) == 1
        assert transitions[0] == (ConnectionState.DISCONNECTED, ConnectionState.CONNECTED)

    def test_reset_clears_state(self):
        """Reset clears all state."""
        handler = NetworkHandler()
        handler.on_connected()
        handler.on_message_received(sequence=1)
        handler.on_message_received(sequence=10)  # Gap

        handler.reset()

        assert handler.state == ConnectionState.DISCONNECTED
        assert len(handler.check_sequence_gaps()) == 0
        assert len(handler.get_events()) == 0


# =============================================================================
# DataQualityValidator Tests
# =============================================================================

class TestDataQualityValidator:
    """Tests for DataQualityValidator."""

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def test_valid_tick(self):
        """Valid tick passes validation."""
        validator = DataQualityValidator()
        ts = self._now_ns()

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            price=50000.0,
            bid=49999.0,
            ask=50001.0
        )

        result = validator.validate_tick(tick)
        assert result.is_valid
        assert result.status == ValidationStatus.VALID

    def test_stale_tick(self):
        """Stale tick is rejected."""
        config = DataQualityConfig(max_stale_ms=1000)
        validator = DataQualityValidator(config)

        # Tick from 2 seconds ago
        ts = self._now_ns() - 2_000_000_000

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            price=50000.0
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid
        assert result.status == ValidationStatus.STALE
        assert result.details['age_ms'] > 1000

    def test_future_timestamp_rejected(self):
        """Future timestamp is rejected."""
        config = DataQualityConfig(max_future_timestamp_ms=5000)
        validator = DataQualityValidator(config)

        # Tick 10 seconds in future
        ts = self._now_ns() + 10_000_000_000

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            price=50000.0
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid
        assert result.status == ValidationStatus.FUTURE_TIMESTAMP

    def test_negative_price_rejected(self):
        """Negative price is rejected."""
        validator = DataQualityValidator()
        ts = self._now_ns()

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            price=-100.0
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid
        assert result.status == ValidationStatus.INVALID_PRICE
        assert result.details['reason'] == 'negative_or_zero'

    def test_crossed_book_rejected(self):
        """Crossed orderbook (bid >= ask) is rejected."""
        validator = DataQualityValidator()
        ts = self._now_ns()

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            bid=50001.0,
            ask=50000.0  # Ask < Bid = crossed
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid
        assert result.status == ValidationStatus.INVALID_BOOK
        assert result.details['reason'] == 'bid_gte_ask'

    def test_excessive_spread_rejected(self):
        """Excessive spread is rejected."""
        config = DataQualityConfig(max_spread_pct=10.0)
        validator = DataQualityValidator(config)
        ts = self._now_ns()

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            bid=40000.0,
            ask=60000.0  # 40% spread
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid
        assert result.status == ValidationStatus.INVALID_BOOK
        assert result.details['reason'] == 'excessive_spread'

    def test_excessive_price_change_rejected(self):
        """Excessive price change in single tick is rejected."""
        config = DataQualityConfig(max_price_change_pct=50.0)
        validator = DataQualityValidator(config)
        ts = self._now_ns()

        # First tick
        tick1 = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
        result1 = validator.validate_tick(tick1)
        assert result1.is_valid

        # Second tick with 60% change
        tick2 = MarketTick(timestamp=ts + 1000, symbol="BTC", price=80000.0)
        result2 = validator.validate_tick(tick2)
        assert not result2.is_valid
        assert result2.status == ValidationStatus.CORRUPT
        assert result2.details['reason'] == 'excessive_change'

    def test_negative_oi_rejected(self):
        """Negative open interest is rejected."""
        validator = DataQualityValidator()
        ts = self._now_ns()

        tick = MarketTick(
            timestamp=ts,
            symbol="BTC",
            price=50000.0,
            open_interest=-1000.0
        )

        result = validator.validate_tick(tick)
        assert not result.is_valid
        assert result.status == ValidationStatus.CORRUPT
        assert result.details['reason'] == 'negative_oi'

    def test_corruption_rate_tracking(self):
        """Corruption rate is tracked correctly."""
        config = DataQualityConfig(
            corruption_window_size=10,
            min_samples_for_rate=5
        )
        validator = DataQualityValidator(config)
        ts = self._now_ns()

        # Send 5 valid, 5 invalid
        for i in range(5):
            tick = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
            validator.validate_tick(tick)

        for i in range(5):
            tick = MarketTick(timestamp=ts, symbol="BTC", price=-100.0)
            validator.validate_tick(tick)

        rate = validator.get_corruption_rate()
        assert rate == 0.5  # 50%

    def test_stale_symbols_tracking(self):
        """Stale symbols are tracked."""
        config = DataQualityConfig(max_stale_ms=500)
        validator = DataQualityValidator(config)

        # Stale tick
        ts = self._now_ns() - 1_000_000_000  # 1 second ago
        tick = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
        validator.validate_tick(tick)

        stale = validator.get_stale_symbols()
        assert "BTC" in stale

    def test_is_data_fresh(self):
        """is_data_fresh correctly reports freshness."""
        validator = DataQualityValidator()
        ts = self._now_ns()

        # No data yet
        assert not validator.is_data_fresh("BTC")

        # Add fresh tick
        tick = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
        validator.validate_tick(tick)

        assert validator.is_data_fresh("BTC")
        assert not validator.is_data_fresh("ETH")  # Never received

    def test_stale_callback(self):
        """Stale callback is invoked."""
        config = DataQualityConfig(max_stale_ms=500)
        validator = DataQualityValidator(config)

        stale_calls = []

        def on_stale(symbol, ts):
            stale_calls.append(symbol)

        validator.set_stale_callback(on_stale)

        # Stale tick
        ts = self._now_ns() - 1_000_000_000
        tick = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
        validator.validate_tick(tick)

        assert "BTC" in stale_calls

    def test_reset_clears_state(self):
        """Reset clears all state."""
        validator = DataQualityValidator()
        ts = self._now_ns()

        # Add some data
        tick = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
        validator.validate_tick(tick)

        validator.reset()

        summary = validator.get_summary()
        assert summary['total_validated'] == 0
        assert summary['corruption_count'] == 0
        assert summary['symbols_tracked'] == 0


# =============================================================================
# RecoveryValidator Tests
# =============================================================================

class TestRecoveryValidator:
    """Tests for RecoveryValidator."""

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    @pytest.mark.asyncio
    async def test_empty_recovery_passes(self):
        """Recovery with no getters configured passes."""
        validator = RecoveryValidator()
        result = await validator.validate_recovery()

        assert result.passed
        assert len(result.checks) > 0

    @pytest.mark.asyncio
    async def test_state_consistency_check(self):
        """State consistency check validates state structure."""
        validator = RecoveryValidator()

        # Valid state
        def get_valid_state():
            return {
                'version': 1,
                'timestamp': self._now_ns(),
                'positions': {}
            }

        validator.set_state_getter(get_valid_state)
        result = await validator.validate_recovery()

        consistency_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.STATE_CONSISTENCY
        )
        assert consistency_check.passed

    @pytest.mark.asyncio
    async def test_state_missing_fields_fails(self):
        """State with missing required fields fails."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.STATE_CONSISTENCY]
        )
        validator = RecoveryValidator(config)

        # Invalid state - missing 'positions'
        def get_invalid_state():
            return {
                'version': 1,
                'timestamp': self._now_ns()
                # Missing 'positions'
            }

        validator.set_state_getter(get_invalid_state)
        result = await validator.validate_recovery()

        consistency_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.STATE_CONSISTENCY
        )
        assert not consistency_check.passed
        assert 'positions' in consistency_check.details.get('missing_fields', [])

    @pytest.mark.asyncio
    async def test_position_reconciliation_success(self):
        """Position reconciliation passes when positions match."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.POSITION_RECONCILIATION]
        )
        validator = RecoveryValidator(config)

        positions = {
            'BTC': {'size': 1.0, 'side': 'LONG'},
            'ETH': {'size': 5.0, 'side': 'SHORT'}
        }

        def get_local():
            return positions.copy()

        async def get_exchange():
            return positions.copy()

        validator.set_position_getter(get_local)
        validator.set_exchange_getter(get_exchange)

        result = await validator.validate_recovery()

        recon_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.POSITION_RECONCILIATION
        )
        assert recon_check.passed
        assert len(recon_check.details.get('mismatches', [])) == 0

    @pytest.mark.asyncio
    async def test_position_reconciliation_unknown_position_fails(self):
        """Reconciliation fails when exchange has unknown position."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.POSITION_RECONCILIATION],
            require_zero_unknown_positions=True
        )
        validator = RecoveryValidator(config)

        def get_local():
            return {'BTC': {'size': 1.0}}

        async def get_exchange():
            return {
                'BTC': {'size': 1.0},
                'ETH': {'size': 5.0}  # Unknown to local!
            }

        validator.set_position_getter(get_local)
        validator.set_exchange_getter(get_exchange)

        result = await validator.validate_recovery()

        recon_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.POSITION_RECONCILIATION
        )
        assert not recon_check.passed
        assert len(recon_check.details.get('exchange_only', [])) == 1

    @pytest.mark.asyncio
    async def test_position_mismatch_fails(self):
        """Reconciliation fails when position sizes don't match."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.POSITION_RECONCILIATION],
            max_position_mismatch_pct=0.01  # 1%
        )
        validator = RecoveryValidator(config)

        def get_local():
            return {'BTC': {'size': 1.0}}

        async def get_exchange():
            return {'BTC': {'size': 1.5}}  # 50% mismatch

        validator.set_position_getter(get_local)
        validator.set_exchange_getter(get_exchange)

        result = await validator.validate_recovery()

        recon_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.POSITION_RECONCILIATION
        )
        assert not recon_check.passed
        assert len(recon_check.details.get('mismatches', [])) == 1

    @pytest.mark.asyncio
    async def test_stale_events_fail(self):
        """Validation fails when pending events are stale."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.EVENT_VALIDATION],
            max_event_age_ms=1000
        )
        validator = RecoveryValidator(config)

        def get_events():
            # Event from 5 seconds ago
            return [{
                'id': 'evt1',
                'timestamp': self._now_ns() - 5_000_000_000
            }]

        validator.set_event_getter(get_events)

        result = await validator.validate_recovery()

        event_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.EVENT_VALIDATION
        )
        assert not event_check.passed
        assert event_check.details.get('stale_events') == 1

    @pytest.mark.asyncio
    async def test_invalid_strategy_state_fails(self):
        """Validation fails when strategy state is invalid."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.STRATEGY_STATE]
        )
        validator = RecoveryValidator(config)

        def get_strategies():
            return {
                'geometry': {'state': 'SCANNING', 'timestamp': self._now_ns()},
                'cascade': {'state': 'INVALID_STATE', 'timestamp': self._now_ns()}
            }

        validator.set_strategy_getter(get_strategies)

        result = await validator.validate_recovery()

        strategy_check = next(
            c for c in result.checks
            if c.check_type == RecoveryCheckType.STRATEGY_STATE
        )
        assert not strategy_check.passed
        assert 'cascade' in strategy_check.details.get('invalid_strategies', [])

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Recovery validation retries on failure."""
        config = RecoveryConfig(
            required_checks=[RecoveryCheckType.STATE_CONSISTENCY],
            max_retry_attempts=3,
            retry_delay_ms=10
        )
        validator = RecoveryValidator(config)

        call_count = 0

        def get_state():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return None  # Fail first 2 times
            return {
                'version': 1,
                'timestamp': self._now_ns(),
                'positions': {}
            }

        validator.set_state_getter(get_state)

        result = await validator.validate_recovery()

        assert result.passed
        assert result.retry_count >= 1  # At least 1 retry before success

    @pytest.mark.asyncio
    async def test_recovery_history(self):
        """Recovery results are stored in history."""
        validator = RecoveryValidator()

        await validator.validate_recovery()
        await validator.validate_recovery()

        history = validator.get_recovery_history()
        assert len(history) == 2

        last = validator.get_last_recovery()
        assert last is not None
        assert last.passed

    def test_summary(self):
        """Summary returns correct information."""
        config = RecoveryConfig(
            required_checks=[
                RecoveryCheckType.STATE_CONSISTENCY,
                RecoveryCheckType.POSITION_RECONCILIATION
            ]
        )
        validator = RecoveryValidator(config)

        summary = validator.get_summary()
        assert summary['total_recoveries'] == 0
        assert 'STATE_CONSISTENCY' in summary['required_checks']
        assert 'POSITION_RECONCILIATION' in summary['required_checks']


# =============================================================================
# Integration Tests (Components working together)
# =============================================================================

class TestFailureHandlingIntegration:
    """Integration tests for failure handling components."""

    @pytest.mark.asyncio
    async def test_network_triggers_recovery(self):
        """Network reconnection triggers recovery validation."""
        network_handler = NetworkHandler()
        recovery_validator = RecoveryValidator()

        # Track if recovery was called
        recovery_called = False

        async def on_reconnect():
            return True

        async def mock_snapshot():
            nonlocal recovery_called
            result = await recovery_validator.validate_recovery()
            recovery_called = True
            return result.passed

        network_handler.set_reconnect_callback(on_reconnect)
        network_handler.set_snapshot_callback(mock_snapshot)
        network_handler.on_connected()

        # Disconnect and reconnect
        await network_handler.on_disconnect("Test")

        assert recovery_called
        assert network_handler.is_connected

    def test_data_quality_affects_network(self):
        """Data quality issues can trigger network concerns."""
        config = DataQualityConfig(
            max_stale_ms=500,
            max_corruption_rate=0.1
        )
        validator = DataQualityValidator(config)
        network_handler = NetworkHandler()

        stale_detected = False

        def on_stale(symbol, ts):
            nonlocal stale_detected
            stale_detected = True

        validator.set_stale_callback(on_stale)

        # Inject stale data
        ts = int(time.time() * 1_000_000_000) - 1_000_000_000
        tick = MarketTick(timestamp=ts, symbol="BTC", price=50000.0)
        validator.validate_tick(tick)

        assert stale_detected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

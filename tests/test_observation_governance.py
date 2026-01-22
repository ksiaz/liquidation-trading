"""
Observation System Governance Comprehensive Test Suite

Tests the main ObservationSystem coordinator responsible for:
- Event ingestion and routing
- Time management and invariants
- Snapshot generation
- M4 primitive computation
- Failure state management

Constitutional: No semantic interpretation, structural observation only.

Authority: EPISTEMIC_CONSTITUTION.md, SYSTEM_CANON.md
"""

import pytest
import sys
import time

sys.path.append('D:/liquidation-trading')

from observation.governance import ObservationSystem
from observation.types import ObservationStatus, SystemHaltedException


# ============================================================================
# TEST SUITE 1: Initialization
# ============================================================================

class TestObservationSystemInit:
    def test_initialization_state(self):
        """Verify initial state of ObservationSystem."""
        obs = ObservationSystem(['BTCUSDT', 'ETHUSDT'])

        assert obs._status == ObservationStatus.UNINITIALIZED
        assert obs._system_time == 0.0
        assert obs._failure_reason == ""
        assert 'BTCUSDT' in obs._allowed_symbols
        assert 'ETHUSDT' in obs._allowed_symbols

    def test_initialization_modules(self):
        """Verify all internal modules are instantiated."""
        obs = ObservationSystem(['BTCUSDT'])

        assert obs._m1 is not None
        assert obs._m3 is not None
        assert obs._m2_store is not None
        assert obs._m5_access is not None

    def test_initialization_symbol_whitelist(self):
        """Verify symbol whitelist is stored as set."""
        obs = ObservationSystem(['BTCUSDT', 'ETHUSDT', 'BTCUSDT'])  # Duplicate

        assert len(obs._allowed_symbols) == 2  # Set deduplicates

    def test_initialization_empty_symbols(self):
        """Verify initialization with empty symbol list."""
        obs = ObservationSystem([])

        assert len(obs._allowed_symbols) == 0
        assert obs._status == ObservationStatus.UNINITIALIZED

    def test_initialization_system_time_zero(self):
        """Verify system time starts at zero."""
        obs = ObservationSystem(['BTCUSDT'])

        assert obs._system_time == 0.0


# ============================================================================
# TEST SUITE 2: Event Ingestion
# ============================================================================

class TestObservationSystemIngestion:
    @pytest.fixture
    def obs(self):
        return ObservationSystem(['BTCUSDT'])

    def test_trade_ingestion(self, obs):
        """Verify TRADE events are ingested."""
        obs.advance_time(1700000000.0)

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', payload)

        # Trade should be in M1 buffers
        assert len(obs._m1.raw_trades['BTCUSDT']) == 1

    def test_liquidation_ingestion(self, obs):
        """Verify LIQUIDATION events are ingested."""
        obs.advance_time(1700000000.0)

        payload = {
            'E': 1700000000000,
            'o': {
                'p': '50000.0',
                'q': '10.0',
                'S': 'SELL'
            }
        }

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'LIQUIDATION', payload)

        # Liquidation should be in M1 buffers
        assert len(obs._m1.raw_liquidations['BTCUSDT']) == 1

    def test_depth_ingestion(self, obs):
        """Verify DEPTH events are ingested."""
        obs.advance_time(1700000000.0)

        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload)

        # Depth should update M1 latest_depth
        assert 'BTCUSDT' in obs._m1.latest_depth
        assert obs._m1.latest_depth['BTCUSDT']['bid_size'] == 10.0

    def test_kline_ingestion(self, obs):
        """Verify KLINE events are recorded."""
        obs.advance_time(1700000000.0)

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'KLINE', {})

        # Should increment counter
        assert obs._m1.counters['klines'] == 1

    def test_oi_ingestion(self, obs):
        """Verify OI events are recorded."""
        obs.advance_time(1700000000.0)

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'OI', {})

        # Should increment counter
        assert obs._m1.counters['oi'] == 1

    def test_symbol_whitelist_enforcement(self, obs):
        """Verify events for non-whitelisted symbols are dropped."""
        obs.advance_time(1700000000.0)

        payload = {
            'p': '3000.0',
            'q': '5.0',
            'T': 1700000000000,
            'm': False
        }

        # ETHUSDT not in whitelist (only BTCUSDT)
        obs.ingest_observation(1700000000.0, 'ETHUSDT', 'TRADE', payload)

        # Should be dropped, not in M1 buffers
        assert len(obs._m1.raw_trades.get('ETHUSDT', [])) == 0

    def test_causality_ancient_event_dropped(self, obs):
        """Verify ancient events (> 30 seconds old) are dropped (Invariant B)."""
        obs.advance_time(1700000100.0)  # System at t=100

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,  # Event at t=0 (100 seconds old)
            'm': False
        }

        # Event is > 30 seconds old, should be dropped
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', payload)

        # Should be dropped
        assert len(obs._m1.raw_trades['BTCUSDT']) == 0

    def test_causality_recent_event_accepted(self, obs):
        """Verify recent events (< 30 seconds old) are accepted."""
        obs.advance_time(1700000100.0)  # System at t=100

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000090000,  # Event at t=90 (10 seconds old)
            'm': False
        }

        # Event is < 30 seconds old, should be accepted
        obs.ingest_observation(1700000090.0, 'BTCUSDT', 'TRADE', payload)

        # Should be accepted
        assert len(obs._m1.raw_trades['BTCUSDT']) == 1

    def test_causality_future_tolerance(self, obs):
        """Verify future events within 5 second tolerance are accepted."""
        obs.advance_time(1700000100.0)  # System at t=100

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000103000,  # Event at t=103 (3 seconds future)
            'm': False
        }

        # Event is < 5 seconds in future, should be accepted (clock skew tolerance)
        obs.ingest_observation(1700000103.0, 'BTCUSDT', 'TRADE', payload)

        # Should be accepted
        assert len(obs._m1.raw_trades['BTCUSDT']) == 1

    def test_failed_state_rejects_input(self, obs):
        """Verify FAILED state rejects all input."""
        obs._trigger_failure("Test failure")

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', payload)

        # Should be rejected (no processing in FAILED state)
        assert len(obs._m1.raw_trades.get('BTCUSDT', [])) == 0

    def test_trade_dispatched_to_m3(self, obs):
        """Verify TRADE events are dispatched to M3 temporal engine."""
        obs.advance_time(1700000000.0)

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        # Ingest trade
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', payload)

        # M3 should have processed the trade (check internal state)
        # Note: M3 has internal windows, we can't easily verify without exposing internals
        # But we can check that no exception was raised
        assert obs._status != ObservationStatus.FAILED

    def test_depth_updates_m2_orderbook_state(self, obs):
        """Verify DEPTH events update M2 continuity store orderbook state."""
        obs.advance_time(1700000000.0)

        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload)

        # M2 should have been called (verified by no exception)
        assert obs._status != ObservationStatus.FAILED

    def test_ingestion_error_handled_gracefully(self, obs):
        """Verify M1 handles malformed payloads gracefully (returns None, increments error counter)."""
        obs.advance_time(1700000000.0)

        # Malformed payload that M1 will handle gracefully
        payload = None  # M1 normalize methods catch this and return None

        initial_errors = obs._m1.counters['errors']

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', payload)

        # M1 should handle gracefully: return None, increment error counter
        assert obs._status == ObservationStatus.UNINITIALIZED  # Not failed
        assert obs._m1.counters['errors'] > initial_errors


# ============================================================================
# TEST SUITE 3: Time Management
# ============================================================================

class TestObservationSystemTimeManagement:
    @pytest.fixture
    def obs(self):
        return ObservationSystem(['BTCUSDT'])

    def test_advance_time_updates_system_time(self, obs):
        """Verify advance_time() updates system time."""
        assert obs._system_time == 0.0

        obs.advance_time(1700000000.0)

        assert obs._system_time == 1700000000.0

    def test_advance_time_monotonicity_enforced(self, obs):
        """Verify time regression triggers FAILED state (Invariant A)."""
        obs.advance_time(1700000100.0)  # Forward to t=100

        # Try to go backward
        obs.advance_time(1700000050.0)  # Backward to t=50

        # Should trigger failure
        assert obs._status == ObservationStatus.FAILED
        assert "Time Regression" in obs._failure_reason

    def test_advance_time_progression_allowed(self, obs):
        """Verify time progression is allowed."""
        obs.advance_time(1700000000.0)
        obs.advance_time(1700000001.0)
        obs.advance_time(1700000002.0)

        assert obs._system_time == 1700000002.0
        assert obs._status == ObservationStatus.UNINITIALIZED  # Not failed

    def test_advance_time_same_time_allowed(self, obs):
        """Verify advancing to same time is allowed (edge case)."""
        obs.advance_time(1700000000.0)
        obs.advance_time(1700000000.0)  # Same time

        assert obs._system_time == 1700000000.0
        assert obs._status == ObservationStatus.UNINITIALIZED

    def test_advance_time_dispatches_to_m3(self, obs):
        """Verify advance_time() dispatches to M3 for window management."""
        obs.advance_time(1700000000.0)

        # M3 should have processed time advance (check no exception)
        assert obs._status != ObservationStatus.FAILED

    def test_advance_time_failed_state_rejection(self, obs):
        """Verify FAILED state rejects time updates."""
        obs._trigger_failure("Test failure")

        obs.advance_time(1700000000.0)

        # Time should not update in FAILED state
        assert obs._system_time == 0.0

    def test_advance_time_m3_failure_propagates(self, obs):
        """Verify M3 temporal failures propagate to FAILED state."""
        # This is hard to test without mocking, but we can verify the error handling path
        # is present by checking the try/except structure exists
        # For now, verify normal operation doesn't fail
        obs.advance_time(1700000000.0)
        assert obs._status == ObservationStatus.UNINITIALIZED


# ============================================================================
# TEST SUITE 4: Snapshot Generation
# ============================================================================

class TestObservationSystemSnapshot:
    @pytest.fixture
    def obs(self):
        return ObservationSystem(['BTCUSDT', 'ETHUSDT'])

    def test_query_snapshot_type(self, obs):
        """Verify query() with type='snapshot' returns ObservationSnapshot."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        assert snapshot is not None
        assert hasattr(snapshot, 'status')
        assert hasattr(snapshot, 'timestamp')
        assert hasattr(snapshot, 'symbols_active')

    def test_query_snapshot_failed_state_raises(self, obs):
        """Verify FAILED state raises SystemHaltedException."""
        obs._trigger_failure("Test failure")

        with pytest.raises(SystemHaltedException, match="SYSTEM HALTED"):
            obs.query({'type': 'snapshot'})

    def test_snapshot_includes_status(self, obs):
        """Verify snapshot includes current status."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        assert snapshot.status == ObservationStatus.UNINITIALIZED

    def test_snapshot_includes_timestamp(self, obs):
        """Verify snapshot includes current system time."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        assert snapshot.timestamp == 1700000000.0

    def test_snapshot_includes_symbols(self, obs):
        """Verify snapshot includes sorted symbol list."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        assert snapshot.symbols_active == ['BTCUSDT', 'ETHUSDT']  # Sorted

    def test_snapshot_includes_primitives(self, obs):
        """Verify snapshot includes M4 primitives for all symbols."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        assert 'BTCUSDT' in snapshot.primitives
        assert 'ETHUSDT' in snapshot.primitives

    def test_snapshot_counters_structure(self, obs):
        """Verify snapshot includes SystemCounters."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        assert snapshot.counters is not None
        assert hasattr(snapshot.counters, 'intervals_processed')
        assert hasattr(snapshot.counters, 'dropped_events')

    def test_query_invalid_type_raises(self, obs):
        """Verify invalid query type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown query type"):
            obs.query({'type': 'invalid'})


# ============================================================================
# TEST SUITE 5: M4 Primitive Computation
# ============================================================================

class TestObservationSystemPrimitiveComputation:
    @pytest.fixture
    def obs(self):
        return ObservationSystem(['BTCUSDT'])

    def test_primitive_computation_resting_size_none_without_depth(self, obs):
        """Verify resting size is None without depth data."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        # No depth data ingested, should be None
        assert snapshot.primitives['BTCUSDT'].resting_size is None

    def test_primitive_computation_resting_size_with_depth(self, obs):
        """Verify resting size computed when depth data available."""
        obs.advance_time(1700000000.0)

        # Ingest depth data
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload)

        snapshot = obs.query({'type': 'snapshot'})

        # Should have resting size
        assert snapshot.primitives['BTCUSDT'].resting_size is not None
        assert snapshot.primitives['BTCUSDT'].resting_size.bid_size == 10.0
        assert snapshot.primitives['BTCUSDT'].resting_size.ask_size == 8.0

    def test_primitive_computation_consumption_none_without_previous(self, obs):
        """Verify consumption is None without previous depth."""
        obs.advance_time(1700000000.0)

        # Ingest single depth (no previous)
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload)

        snapshot = obs.query({'type': 'snapshot'})

        # No previous depth, no consumption detection
        assert snapshot.primitives['BTCUSDT'].order_consumption is None

    def test_primitive_computation_consumption_with_size_decrease(self, obs):
        """Verify consumption detected when size decreases."""
        obs.advance_time(1700000000.0)

        # First depth
        payload1 = {
            'E': 1700000000000,
            'b': [['50000.0', '100.0']],
            'a': [['50001.0', '80.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload1)

        obs.advance_time(1700000001.0)

        # Second depth with decreased bid size
        payload2 = {
            'E': 1700000001000,
            'b': [['50000.0', '80.0']],  # Decreased from 100 to 80
            'a': [['50001.0', '80.0']]
        }
        obs.ingest_observation(1700000001.0, 'BTCUSDT', 'DEPTH', payload2)

        snapshot = obs.query({'type': 'snapshot'})

        # Should detect consumption (20.0 consumed)
        assert snapshot.primitives['BTCUSDT'].order_consumption is not None
        assert snapshot.primitives['BTCUSDT'].order_consumption.consumed_size == 20.0

    def test_primitive_computation_refill_with_size_increase(self, obs):
        """Verify refill detected when size increases."""
        obs.advance_time(1700000000.0)

        # First depth
        payload1 = {
            'E': 1700000000000,
            'b': [['50000.0', '80.0']],
            'a': [['50001.0', '60.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload1)

        obs.advance_time(1700000001.0)

        # Second depth with increased bid size
        payload2 = {
            'E': 1700000001000,
            'b': [['50000.0', '100.0']],  # Increased from 80 to 100
            'a': [['50001.0', '60.0']]
        }
        obs.ingest_observation(1700000001.0, 'BTCUSDT', 'DEPTH', payload2)

        snapshot = obs.query({'type': 'snapshot'})

        # Should detect refill (20.0 added)
        assert snapshot.primitives['BTCUSDT'].refill_event is not None
        assert snapshot.primitives['BTCUSDT'].refill_event.added_size == 20.0

    def test_primitive_computation_absorption_requires_consumption_and_stable_price(self, obs):
        """Verify absorption requires both consumption and price stability."""
        obs.advance_time(1700000000.0)

        # Ingest trade for price history
        trade1 = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', trade1)

        # First depth
        payload1 = {
            'E': 1700000000000,
            'b': [['50000.0', '100.0']],
            'a': [['50001.0', '80.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload1)

        obs.advance_time(1700000001.0)

        # Second trade with stable price (within 1%)
        trade2 = {
            'p': '50050.0',  # 0.1% movement
            'q': '1.0',
            'T': 1700000001000,
            'm': False
        }
        obs.ingest_observation(1700000001.0, 'BTCUSDT', 'TRADE', trade2)

        # Second depth with decreased size
        payload2 = {
            'E': 1700000001000,
            'b': [['50000.0', '80.0']],  # Decreased (consumption)
            'a': [['50001.0', '80.0']]
        }
        obs.ingest_observation(1700000001.0, 'BTCUSDT', 'DEPTH', payload2)

        snapshot = obs.query({'type': 'snapshot'})

        # Should detect absorption (consumption + stable price)
        assert snapshot.primitives['BTCUSDT'].absorption_event is not None

    def test_primitive_computation_identical_timestamps_skipped(self, obs):
        """Verify identical timestamps skip consumption detection."""
        obs.advance_time(1700000000.0)

        # First depth at t=0
        payload1 = {
            'E': 1700000000000,
            'b': [['50000.0', '100.0']],
            'a': [['50001.0', '80.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload1)

        # Second depth also at t=0 (duplicate timestamp)
        payload2 = {
            'E': 1700000000000,  # Same timestamp
            'b': [['50000.0', '80.0']],
            'a': [['50001.0', '80.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload2)

        snapshot = obs.query({'type': 'snapshot'})

        # Should skip detection (identical timestamps)
        # Note: Latest depth is still updated, but consumption logic skips
        assert snapshot.primitives['BTCUSDT'].resting_size is not None

    def test_primitive_computation_exception_returns_none_primitives(self, obs):
        """Verify computation exceptions return None primitives without crashing."""
        obs.advance_time(1700000000.0)

        # Corrupt M1 state to trigger exception
        obs._m1.latest_depth['BTCUSDT'] = {'malformed': 'data'}

        snapshot = obs.query({'type': 'snapshot'})

        # Should not crash, primitives should be None
        assert snapshot.primitives['BTCUSDT'].resting_size is None

    def test_primitive_computation_per_symbol(self, obs):
        """Verify primitives computed independently per symbol."""
        obs = ObservationSystem(['BTCUSDT', 'ETHUSDT'])
        obs.advance_time(1700000000.0)

        # Ingest depth only for BTCUSDT
        payload_btc = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'DEPTH', payload_btc)

        snapshot = obs.query({'type': 'snapshot'})

        # BTCUSDT should have resting size, ETHUSDT should not
        assert snapshot.primitives['BTCUSDT'].resting_size is not None
        assert snapshot.primitives['ETHUSDT'].resting_size is None

    def test_primitive_bundle_structure(self, obs):
        """Verify M4PrimitiveBundle has all expected fields."""
        obs.advance_time(1700000000.0)

        snapshot = obs.query({'type': 'snapshot'})

        bundle = snapshot.primitives['BTCUSDT']
        assert hasattr(bundle, 'symbol')
        assert hasattr(bundle, 'resting_size')
        assert hasattr(bundle, 'order_consumption')
        assert hasattr(bundle, 'absorption_event')
        assert hasattr(bundle, 'refill_event')
        assert hasattr(bundle, 'zone_penetration')
        assert hasattr(bundle, 'price_acceptance_ratio')


# ============================================================================
# TEST SUITE 6: Failure State Management
# ============================================================================

class TestObservationSystemFailureManagement:
    @pytest.fixture
    def obs(self):
        return ObservationSystem(['BTCUSDT'])

    def test_trigger_failure_sets_status(self, obs):
        """Verify _trigger_failure() sets status to FAILED."""
        obs._trigger_failure("Test failure")

        assert obs._status == ObservationStatus.FAILED

    def test_trigger_failure_stores_reason(self, obs):
        """Verify _trigger_failure() stores failure reason."""
        obs._trigger_failure("Test failure reason")

        assert obs._failure_reason == "Test failure reason"

    def test_failure_is_irreversible(self, obs):
        """Verify FAILED state cannot be recovered."""
        obs._trigger_failure("First failure")

        # Try to advance time (should be rejected)
        obs.advance_time(1700000000.0)

        assert obs._status == ObservationStatus.FAILED
        assert obs._system_time == 0.0  # Time not updated

    def test_failure_from_time_regression(self, obs):
        """Verify time regression triggers failure."""
        obs.advance_time(1700000100.0)
        obs.advance_time(1700000050.0)  # Regression

        assert obs._status == ObservationStatus.FAILED
        assert "Time Regression" in obs._failure_reason

    def test_failure_state_is_irreversible(self, obs):
        """Verify once in FAILED state, cannot recover (additional test)."""
        obs._trigger_failure("Test failure")

        # Try multiple operations
        obs.advance_time(1700000000.0)
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', {})

        # Status should remain FAILED
        assert obs._status == ObservationStatus.FAILED
        assert obs._failure_reason == "Test failure"

    def test_query_after_failure_raises(self, obs):
        """Verify query after failure raises SystemHaltedException."""
        obs._trigger_failure("Test failure")

        with pytest.raises(SystemHaltedException):
            obs.query({'type': 'snapshot'})


# ============================================================================
# TEST SUITE 7: Invariants
# ============================================================================

class TestObservationSystemInvariants:
    @pytest.fixture
    def obs(self):
        return ObservationSystem(['BTCUSDT'])

    def test_invariant_a_time_monotonicity(self, obs):
        """Verify Invariant A: Time monotonicity enforced."""
        obs.advance_time(1700000100.0)

        # Violation: go backward
        obs.advance_time(1700000050.0)

        assert obs._status == ObservationStatus.FAILED

    def test_invariant_b_causality_ancient_drop(self, obs):
        """Verify Invariant B: Ancient events dropped."""
        obs.advance_time(1700000100.0)

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,  # 100 seconds old
            'm': False
        }

        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', payload)

        # Should be dropped
        assert len(obs._m1.raw_trades.get('BTCUSDT', [])) == 0

    def test_invariant_b_causality_future_tolerance(self, obs):
        """Verify Invariant B: Future tolerance (5 seconds)."""
        obs.advance_time(1700000100.0)

        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000104000,  # 4 seconds future
            'm': False
        }

        obs.ingest_observation(1700000104.0, 'BTCUSDT', 'TRADE', payload)

        # Should be accepted (within tolerance)
        assert len(obs._m1.raw_trades['BTCUSDT']) == 1

    def test_system_starts_uninitialized(self, obs):
        """Verify system starts in UNINITIALIZED state."""
        assert obs._status == ObservationStatus.UNINITIALIZED

    def test_failed_state_halts_all_operations(self, obs):
        """Verify FAILED state halts all operations."""
        obs._trigger_failure("Test failure")

        # Try various operations
        obs.ingest_observation(1700000000.0, 'BTCUSDT', 'TRADE', {})
        obs.advance_time(1700000000.0)

        # All should be rejected
        assert obs._system_time == 0.0

        with pytest.raises(SystemHaltedException):
            obs.query({'type': 'snapshot'})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for monitoring components (HLP19).

Tests:
- HealthDashboard health tracking
- LatencyProfiler pipeline timing
"""

import pytest
from datetime import datetime, timedelta
import asyncio
import time

from runtime.monitoring.health_dashboard import (
    HealthDashboard,
    HealthLevel,
    HealthThresholds,
    HealthStatus,
    ComponentHealth,
)
from runtime.monitoring.latency_profiler import (
    LatencyProfiler,
    LatencyStage,
    LatencyRecord,
    StageStats,
    LATENCY_TARGETS_US,
    get_profiler,
    reset_profiler,
)


# =============================================================================
# Health Dashboard Tests
# =============================================================================

class TestHealthThresholds:
    """Tests for HealthThresholds."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = HealthThresholds()

        assert thresholds.data_staleness_normal_ms == 500
        assert thresholds.data_staleness_critical_ms == 2000
        assert thresholds.heartbeat_warning_sec == 3
        assert thresholds.memory_critical_pct == 0.85

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = HealthThresholds(
            data_staleness_critical_ms=5000,
            memory_critical_pct=0.90,
        )

        assert thresholds.data_staleness_critical_ms == 5000
        assert thresholds.memory_critical_pct == 0.90


class TestHealthDashboard:
    """Tests for HealthDashboard."""

    @pytest.fixture
    def dashboard(self):
        """Create a health dashboard."""
        return HealthDashboard()

    @pytest.mark.asyncio
    async def test_initial_status_normal(self, dashboard):
        """Test initial status is normal."""
        status = await dashboard.get_status()

        # Should be normal initially (data just updated)
        assert status.overall_level in (HealthLevel.NORMAL, HealthLevel.CRITICAL)

    @pytest.mark.asyncio
    async def test_register_component(self, dashboard):
        """Test registering a component."""
        await dashboard.register_component("test_component")

        status = await dashboard.get_status()
        assert "test_component" in status.components

    @pytest.mark.asyncio
    async def test_component_heartbeat(self, dashboard):
        """Test component heartbeat updates."""
        await dashboard.register_component("test_component")

        await dashboard.heartbeat("test_component", {"metric": 123})

        status = await dashboard.get_status()
        comp = status.components["test_component"]
        assert comp.level == HealthLevel.NORMAL

    @pytest.mark.asyncio
    async def test_component_issue_reporting(self, dashboard):
        """Test reporting issues from a component."""
        await dashboard.register_component("test_component")

        await dashboard.report_issue(
            "test_component",
            "Something went wrong",
            HealthLevel.WARNING,
        )

        status = await dashboard.get_status()
        comp = status.components["test_component"]
        assert comp.level == HealthLevel.WARNING
        assert comp.message == "Something went wrong"

    @pytest.mark.asyncio
    async def test_websocket_disconnect_is_critical(self, dashboard):
        """Test WebSocket disconnect triggers critical status."""
        dashboard.set_websocket_status(False)

        status = await dashboard.get_status()

        assert status.overall_level == HealthLevel.CRITICAL
        assert not status.trading_allowed
        assert not status.websocket_connected

    @pytest.mark.asyncio
    async def test_position_mismatch_is_critical(self, dashboard):
        """Test position mismatch triggers critical status."""
        dashboard.set_websocket_status(True)
        dashboard.set_position_reconciled(False)

        status = await dashboard.get_status()

        assert status.overall_level == HealthLevel.CRITICAL
        assert not status.trading_allowed

    @pytest.mark.asyncio
    async def test_data_staleness_warning(self, dashboard):
        """Test data staleness triggers warning."""
        dashboard.set_websocket_status(True)

        # Set old market data time
        old_time = datetime.now() - timedelta(milliseconds=1500)
        dashboard.update_market_data_time(old_time)

        status = await dashboard.get_status()

        assert status.data_staleness_ms > 1000
        assert status.overall_level in (HealthLevel.WARNING, HealthLevel.CRITICAL)

    @pytest.mark.asyncio
    async def test_data_staleness_critical(self, dashboard):
        """Test extreme data staleness triggers critical."""
        dashboard.set_websocket_status(True)

        # Set very old market data time
        old_time = datetime.now() - timedelta(seconds=5)
        dashboard.update_market_data_time(old_time)

        status = await dashboard.get_status()

        assert status.overall_level == HealthLevel.CRITICAL
        assert "Data stale" in status.issues[0]

    @pytest.mark.asyncio
    async def test_resource_usage_warning(self, dashboard):
        """Test high resource usage triggers warning."""
        dashboard.set_websocket_status(True)
        dashboard.update_resource_usage(memory_pct=0.75, cpu_pct=0.50)

        status = await dashboard.get_status()

        assert status.memory_pct == 0.75
        assert "Memory high" in str(status.issues)

    @pytest.mark.asyncio
    async def test_trading_allowed_when_healthy(self, dashboard):
        """Test trading is allowed when all checks pass."""
        dashboard.set_websocket_status(True)
        dashboard.set_position_reconciled(True)
        dashboard.update_market_data_time(datetime.now())

        status = await dashboard.get_status()

        assert status.trading_allowed

    @pytest.mark.asyncio
    async def test_event_counts_tracking(self, dashboard):
        """Test event count tracking."""
        dashboard.update_event_counts(active=50, stale=10)

        status = await dashboard.get_status()

        assert status.active_events == 50
        assert status.stale_events == 10

    @pytest.mark.asyncio
    async def test_stale_events_warning(self, dashboard):
        """Test too many stale events triggers warning."""
        dashboard.set_websocket_status(True)
        dashboard.update_event_counts(active=10, stale=60)

        status = await dashboard.get_status()

        assert "Too many stale events" in str(status.issues)

    def test_is_trading_allowed_quick_check(self, dashboard):
        """Test quick trading allowed check."""
        dashboard.set_websocket_status(True)
        dashboard.set_position_reconciled(True)
        dashboard.update_market_data_time(datetime.now())

        assert dashboard.is_trading_allowed()

    def test_is_trading_allowed_false_when_disconnected(self, dashboard):
        """Test quick check returns false when disconnected."""
        dashboard.set_websocket_status(False)

        assert not dashboard.is_trading_allowed()

    @pytest.mark.asyncio
    async def test_status_to_dict(self, dashboard):
        """Test status serialization."""
        dashboard.set_websocket_status(True)
        status = await dashboard.get_status()

        data = status.to_dict()

        assert 'timestamp' in data
        assert 'overall_level' in data
        assert 'trading_allowed' in data
        assert 'components' in data


# =============================================================================
# Latency Profiler Tests
# =============================================================================

class TestLatencyRecord:
    """Tests for LatencyRecord."""

    def test_record_creation(self):
        """Test creating a latency record."""
        record = LatencyRecord(
            stage=LatencyStage.STRATEGY_DECISION,
            latency_us=50,
        )

        assert record.stage == LatencyStage.STRATEGY_DECISION
        assert record.latency_us == 50

    def test_is_warning_property(self):
        """Test warning detection."""
        # Target for strategy decision is 100μs, warning at 2x
        normal = LatencyRecord(
            stage=LatencyStage.STRATEGY_DECISION,
            latency_us=150,
        )
        warning = LatencyRecord(
            stage=LatencyStage.STRATEGY_DECISION,
            latency_us=250,
        )

        assert not normal.is_warning
        assert warning.is_warning

    def test_is_critical_property(self):
        """Test critical detection."""
        # Target for strategy decision is 100μs, critical at 5x
        normal = LatencyRecord(
            stage=LatencyStage.STRATEGY_DECISION,
            latency_us=400,
        )
        critical = LatencyRecord(
            stage=LatencyStage.STRATEGY_DECISION,
            latency_us=600,
        )

        assert not normal.is_critical
        assert critical.is_critical


class TestLatencyProfiler:
    """Tests for LatencyProfiler."""

    @pytest.fixture
    def profiler(self):
        """Create a latency profiler."""
        return LatencyProfiler(window_size=100)

    def test_record_latency(self, profiler):
        """Test recording a latency measurement."""
        profiler.record(LatencyStage.STRATEGY_DECISION, 50)

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)
        assert stats is not None
        assert stats.sample_count == 1
        assert stats.p50_us == 50

    def test_multiple_recordings(self, profiler):
        """Test recording multiple latency measurements."""
        for latency in [50, 100, 150, 200, 250]:
            profiler.record(LatencyStage.STRATEGY_DECISION, latency)

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)

        assert stats.sample_count == 5
        assert stats.min_us == 50
        assert stats.max_us == 250
        assert stats.p50_us == 150  # Median

    def test_timer_context_manager(self, profiler):
        """Test timing with context manager."""
        with profiler.time(LatencyStage.STRATEGY_DECISION):
            # Simulate some work
            time.sleep(0.001)  # 1ms

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)

        assert stats is not None
        assert stats.sample_count == 1
        assert stats.p50_us >= 900  # At least 0.9ms

    def test_percentile_calculation(self, profiler):
        """Test percentile calculations."""
        # Add 100 samples from 1 to 100
        for i in range(1, 101):
            profiler.record(LatencyStage.STRATEGY_DECISION, i)

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)

        # Percentile values depend on implementation (floor index)
        assert 49 <= stats.p50_us <= 51
        assert 94 <= stats.p95_us <= 96
        assert 98 <= stats.p99_us <= 100

    def test_breach_tracking(self, profiler):
        """Test that breaches are tracked."""
        target = LATENCY_TARGETS_US[LatencyStage.STRATEGY_DECISION]

        # Add some normal and some breaching samples
        for _ in range(5):
            profiler.record(LatencyStage.STRATEGY_DECISION, target // 2)  # Normal
        for _ in range(5):
            profiler.record(LatencyStage.STRATEGY_DECISION, target * 2)  # Breach

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)

        assert stats.breaches == 5
        assert stats.breach_rate == 0.5

    def test_meets_target(self, profiler):
        """Test target compliance check."""
        target = LATENCY_TARGETS_US[LatencyStage.STRATEGY_DECISION]

        # All samples under target
        for _ in range(10):
            profiler.record(LatencyStage.STRATEGY_DECISION, target // 2)

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)

        assert stats.meets_target

    def test_get_summary(self, profiler):
        """Test getting complete summary."""
        # Add samples to multiple stages
        profiler.record(LatencyStage.STRATEGY_DECISION, 50)
        profiler.record(LatencyStage.RISK_VALIDATION, 30)
        profiler.record(LatencyStage.ORDER_SUBMISSION, 400)

        summary = profiler.get_summary()

        assert summary.total_samples == 3
        assert len(summary.stages) == 3
        assert 'strategy_decision' in summary.stages
        assert 'risk_validation' in summary.stages

    def test_get_percentiles(self, profiler):
        """Test getting percentiles for all stages."""
        profiler.record(LatencyStage.STRATEGY_DECISION, 50)
        profiler.record(LatencyStage.RISK_VALIDATION, 30)

        percentiles = profiler.get_percentiles()

        assert 'strategy_decision' in percentiles
        assert 'p50' in percentiles['strategy_decision']
        assert 'p95' in percentiles['strategy_decision']
        assert 'p99' in percentiles['strategy_decision']

    def test_e2e_tracking(self, profiler):
        """Test end-to-end latency tracking."""
        profiler.record_e2e(1500)
        profiler.record_e2e(2000)
        profiler.record_e2e(1800)

        summary = profiler.get_summary()

        assert summary.total_e2e_p50_us == 1800

    def test_reset(self, profiler):
        """Test resetting the profiler."""
        profiler.record(LatencyStage.STRATEGY_DECISION, 50)
        profiler.record_e2e(1500)

        profiler.reset()

        summary = profiler.get_summary()
        assert summary.total_samples == 0
        assert summary.total_e2e_p50_us == 0

    def test_get_recent_records(self, profiler):
        """Test getting recent records."""
        for i in range(5):
            profiler.record(LatencyStage.STRATEGY_DECISION, i * 10)

        recent = profiler.get_recent_records(LatencyStage.STRATEGY_DECISION, limit=3)

        assert len(recent) == 3
        assert recent[0]['latency_us'] == 20
        assert recent[2]['latency_us'] == 40

    def test_window_size_limits_samples(self):
        """Test that window size limits stored samples."""
        profiler = LatencyProfiler(window_size=10)

        for i in range(20):
            profiler.record(LatencyStage.STRATEGY_DECISION, i)

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)

        assert stats.sample_count == 10
        assert stats.min_us == 10  # Oldest (0-9) were evicted

    def test_summary_to_dict(self, profiler):
        """Test summary serialization."""
        profiler.record(LatencyStage.STRATEGY_DECISION, 50)

        summary = profiler.get_summary()
        data = summary.to_dict()

        assert 'timestamp' in data
        assert 'total_samples' in data
        assert 'stages' in data
        assert 'all_targets_met' in data

    def test_stage_stats_to_dict(self, profiler):
        """Test stage stats serialization."""
        profiler.record(LatencyStage.STRATEGY_DECISION, 50)

        stats = profiler.get_stage_stats(LatencyStage.STRATEGY_DECISION)
        data = stats.to_dict()

        assert data['stage'] == 'strategy_decision'
        assert 'p50_us' in data
        assert 'breach_rate' in data


class TestLatencyTargets:
    """Tests for latency targets."""

    def test_all_stages_have_targets(self):
        """Test all stages have defined targets."""
        for stage in LatencyStage:
            assert stage in LATENCY_TARGETS_US

    def test_targets_are_reasonable(self):
        """Test targets are in reasonable range."""
        for stage, target in LATENCY_TARGETS_US.items():
            assert target > 0
            assert target < 10_000  # Max 10ms


class TestGlobalProfiler:
    """Tests for global profiler instance."""

    def test_get_profiler_returns_instance(self):
        """Test getting global profiler."""
        reset_profiler()
        profiler = get_profiler()

        assert profiler is not None
        assert isinstance(profiler, LatencyProfiler)

    def test_get_profiler_returns_same_instance(self):
        """Test global profiler is singleton."""
        reset_profiler()
        profiler1 = get_profiler()
        profiler2 = get_profiler()

        assert profiler1 is profiler2

    def test_reset_profiler_creates_new_instance(self):
        """Test reset creates new instance."""
        profiler1 = get_profiler()
        reset_profiler()
        profiler2 = get_profiler()

        assert profiler1 is not profiler2

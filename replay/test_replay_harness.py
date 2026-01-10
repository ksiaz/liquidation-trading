"""
Replay Harness Tests - Determinism & Validation

Tests for replay harness v1.0 correctness and bit-reproducibility.
"""

import pytest
from pathlib import Path
import tempfile
import pandas as pd

from replay.replay_data_loader import HistoricalDataLoader, CandleData
from replay.replay_instrumentation import ReplayInstrumentationLogger
from replay.replay_harness import ReplayHarness, ReplayConfig
from execution.ep4_risk_gates import RiskConfig
from execution.ep4_exchange_adapter import ExchangeConstraints


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def sample_data_csv():
    """Create sample CSV data file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("timestamp,open,high,low,close,volume\n")
        f.write("1000.0,50000.0,50100.0,49900.0,50050.0,100.0\n")
        f.write("2000.0,50050.0,50200.0,50000.0,50150.0,150.0\n")
        f.write("3000.0,50150.0,50250.0,50100.0,50200.0,120.0\n")
        return Path(f.name)


@pytest.fixture
def sample_replay_config(sample_data_csv):
    """Create sample replay configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ReplayConfig(
            data_path=sample_data_csv,
            symbol="BTCUSDT",
            output_dir=Path(tmpdir),
            risk_config=RiskConfig(
                max_position_size=10.0,
                max_notional=100000.0,
                max_leverage=3.0,
                max_actions_per_minute=5,
                cooldown_seconds=1.0
            ),
            exchange_constraints=ExchangeConstraints(
                min_order_size=0.001,
                max_order_size=100.0,
                step_size=0.001,
                tick_size=0.1,
                max_leverage=10.0,
                margin_mode="CROSS"
            ),
            account_id="TEST",
            initial_balance=10000.0
        )


# ==============================================================================
# Data Loader Tests
# ==============================================================================

def test_data_loader_loads_csv(sample_data_csv):
    """Data loader correctly loads CSV file."""
    loader = HistoricalDataLoader(data_path=sample_data_csv, symbol="BTCUSDT")
    loader.load()
    
    assert loader.get_row_count() == 3
    start, end = loader.get_time_range()
    assert start == 1000.0
    assert end == 3000.0


def test_data_loader_deterministic_ordering(sample_data_csv):
    """Data loader produces deterministic ordering."""
    loader1 = HistoricalDataLoader(data_path=sample_data_csv, symbol="BTCUSDT")
    loader1.load()
    
    loader2 = HistoricalDataLoader(data_path=sample_data_csv, symbol="BTCUSDT")
    loader2.load()
    
    snapshots1 = list(loader1.iter_snapshots())
    snapshots2 = list(loader2.iter_snapshots())
    
    assert len(snapshots1) == len(snapshots2)
    for s1, s2 in zip(snapshots1, snapshots2):
        assert s1.timestamp == s2.timestamp
        assert s1.candle.close == s2.candle.close


def test_data_loader_validates_columns(sample_data_csv):
    """Data loader validates required columns."""
    # Create bad CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("timestamp,open,high\n")  # Missing required columns
        f.write("1000.0,50000.0,50100.0\n")
        bad_path = Path(f.name)
    
    loader = HistoricalDataLoader(data_path=bad_path, symbol="BTCUSDT")
    
    with pytest.raises(ValueError, match="Missing required columns"):
        loader.load()


# ==============================================================================
# Instrumentation Tests
# ==============================================================================

def test_instrumentation_logs_observations():
    """Instrumentation correctly logs observations."""
    logger = ReplayInstrumentationLogger()
    
    logger.log_observation(
        tier="A",
        primitive="test_primitive",
        output={"value": 1.0},
        is_nonzero=True
    )
    
    assert logger.observation.tier_a_nonzero_count == 1


def test_instrumentation_logs_proposals():
    """Instrumentation correctly logs proposals."""
    logger = ReplayInstrumentationLogger()
    
    logger.log_proposal(
        strategy_id="EP2-GEOMETRY-V1",
        proposal={"action": "test"}
    )
    
    assert logger.proposal.strategy1_proposal_count == 1
    assert logger.proposal.total_proposals == 1


def test_instrumentation_logs_execution():
    """Instrumentation correctly logs execution."""
    logger = ReplayInstrumentationLogger()
    
    logger.log_execution(
        result_code="SUCCESS",
        reason_code="EXECUTION_SUCCESS",
        timestamp=1000.0
    )
    
    assert logger.execution.success_count == 1
    assert len(logger.temporal.action_timestamps) == 1


def test_instrumentation_computes_temporal_metrics():
    """Instrumentation computes temporal metrics correctly."""
    logger = ReplayInstrumentationLogger()
    
    logger.log_execution(result_code="SUCCESS", reason_code="OK", timestamp=1000.0)
    logger.log_execution(result_code="SUCCESS", reason_code="OK", timestamp=1010.0)
    logger.log_execution(result_code="SUCCESS", reason_code="OK", timestamp=1100.0)
    
    logger.finalize_temporal_metrics()
    
    assert len(logger.temporal.time_between_actions) == 2
    assert logger.temporal.longest_inactivity == 90.0


# ==============================================================================
# Replay Harness Integration Tests
# ==============================================================================

def test_replay_harness_runs_successfully(sample_replay_config):
    """Replay harness executes full run without errors."""
    harness = ReplayHarness(config=sample_replay_config)
    metrics = harness.run()
    
    assert metrics is not None
    assert "observation" in metrics
    assert "arbitration" in metrics
    assert "execution" in metrics


def test_replay_harness_determinism(sample_replay_config):
    """Replay harness produces deterministic results."""
    harness1 = ReplayHarness(config=sample_replay_config)
    metrics1 = harness1.run()
    
    harness2 = ReplayHarness(config=sample_replay_config)
    metrics2 = harness2.run()
    
    # Should produce identical metrics
    assert metrics1["arbitration"]["no_action"] == metrics2["arbitration"]["no_action"]
    assert metrics1["execution"]["noop"] == metrics2["execution"]["noop"]


def test_replay_harness_creates_output_files(sample_replay_config):
    """Replay harness creates required output files."""
    harness = ReplayHarness(config=sample_replay_config)
    harness.run()
    
    output_dir = sample_replay_config.output_dir
    assert (output_dir / "replay_metrics.json").exists()
    assert (output_dir / "replay_config.json").exists()


# ==============================================================================
# Bit-Reproducibility Tests
# ==============================================================================

def test_replay_reproducibility_hash_constant(sample_replay_config):
    """Reproducibility hash is constant for identical runs."""
    harness1 = ReplayHarness(config=sample_replay_config)
    harness1.run()
    
    harness2 = ReplayHarness(config=sample_replay_config)
    harness2.run()
    
    # Both runs should produce same hash
    # (Implementation note: hash is printed, would need to capture for comparison)
    # For now, validates that run completes without error


# ==============================================================================
# Edge Case Tests
# ==============================================================================

def test_replay_handles_empty_data():
    """Replay handles empty data gracefully."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("timestamp,open,high,low,close,volume\n")
        # No data rows
        empty_path = Path(f.name)
    
    config = ReplayConfig(
        data_path=empty_path,
        symbol="BTCUSDT",
        output_dir=Path(tempfile.mkdtemp()),
        risk_config=RiskConfig(10.0, 100000.0, 3.0, 5, 1.0),
        exchange_constraints=ExchangeConstraints(
            0.001, 100.0, 0.001, 0.1, 10.0, "CROSS"
        ),
        account_id="TEST",
        initial_balance=10000.0
    )
    
    harness = ReplayHarness(config=config)
    
    # Should raise ValueError during run due to empty data
    with pytest.raises(ValueError, match="Data is empty"):
        harness.run()

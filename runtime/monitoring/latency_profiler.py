"""
HLP19: Latency Profiler.

Tracks latency through the 7-stage order pipeline:
1. Strategy decision (should be <100μs)
2. Risk validation (should be <50μs)
3. Position reservation (should be <10μs)
4. Order construction (should be <20μs)
5. Order submission (should be <500μs)
6. Exchange processing (should be <1ms)
7. Fill notification (should be <100μs)

Total target: <2ms end-to-end for execution path.

Provides:
- Per-stage latency tracking
- Percentile calculations (p50, p95, p99)
- Threshold alerting
- Historical analysis
"""

import time
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Deque, Tuple
import statistics


class LatencyStage(Enum):
    """Stages in the order execution pipeline."""
    STRATEGY_DECISION = "strategy_decision"
    RISK_VALIDATION = "risk_validation"
    POSITION_RESERVATION = "position_reservation"
    ORDER_CONSTRUCTION = "order_construction"
    ORDER_SUBMISSION = "order_submission"
    EXCHANGE_PROCESSING = "exchange_processing"
    FILL_NOTIFICATION = "fill_notification"


# Target latencies in microseconds
LATENCY_TARGETS_US: Dict[LatencyStage, int] = {
    LatencyStage.STRATEGY_DECISION: 100,
    LatencyStage.RISK_VALIDATION: 50,
    LatencyStage.POSITION_RESERVATION: 10,
    LatencyStage.ORDER_CONSTRUCTION: 20,
    LatencyStage.ORDER_SUBMISSION: 500,
    LatencyStage.EXCHANGE_PROCESSING: 1000,
    LatencyStage.FILL_NOTIFICATION: 100,
}

# Warning thresholds (multiples of target)
WARNING_THRESHOLD = 2.0   # 2x target = warning
CRITICAL_THRESHOLD = 5.0  # 5x target = critical


@dataclass
class LatencyRecord:
    """Single latency measurement."""
    stage: LatencyStage
    latency_us: int
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_warning(self) -> bool:
        target = LATENCY_TARGETS_US.get(self.stage, 100)
        return self.latency_us > target * WARNING_THRESHOLD

    @property
    def is_critical(self) -> bool:
        target = LATENCY_TARGETS_US.get(self.stage, 100)
        return self.latency_us > target * CRITICAL_THRESHOLD


@dataclass
class StageStats:
    """Statistics for a single stage."""
    stage: LatencyStage
    sample_count: int
    p50_us: int
    p95_us: int
    p99_us: int
    min_us: int
    max_us: int
    mean_us: float
    target_us: int
    breaches: int  # Number of samples exceeding target

    @property
    def breach_rate(self) -> float:
        """Percentage of samples exceeding target."""
        if self.sample_count == 0:
            return 0.0
        return self.breaches / self.sample_count

    @property
    def meets_target(self) -> bool:
        """Check if p95 meets target."""
        return self.p95_us <= self.target_us

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stage': self.stage.value,
            'sample_count': self.sample_count,
            'p50_us': self.p50_us,
            'p95_us': self.p95_us,
            'p99_us': self.p99_us,
            'min_us': self.min_us,
            'max_us': self.max_us,
            'mean_us': self.mean_us,
            'target_us': self.target_us,
            'breach_rate': self.breach_rate,
            'meets_target': self.meets_target,
        }


@dataclass
class LatencySummary:
    """Complete latency summary."""
    timestamp: datetime
    total_samples: int
    stages: Dict[str, StageStats]
    total_e2e_p50_us: int
    total_e2e_p95_us: int
    total_e2e_p99_us: int
    stages_meeting_target: int
    stages_total: int

    @property
    def all_targets_met(self) -> bool:
        return self.stages_meeting_target == self.stages_total

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_samples': self.total_samples,
            'total_e2e_p50_us': self.total_e2e_p50_us,
            'total_e2e_p95_us': self.total_e2e_p95_us,
            'total_e2e_p99_us': self.total_e2e_p99_us,
            'stages_meeting_target': self.stages_meeting_target,
            'stages_total': self.stages_total,
            'all_targets_met': self.all_targets_met,
            'stages': {k: v.to_dict() for k, v in self.stages.items()},
        }


class LatencyTimer:
    """Context manager for timing a pipeline stage."""

    def __init__(self, profiler: 'LatencyProfiler', stage: LatencyStage, metadata: Dict = None):
        self._profiler = profiler
        self._stage = stage
        self._metadata = metadata or {}
        self._start_ns: int = 0

    def __enter__(self):
        self._start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ns = time.perf_counter_ns() - self._start_ns
        elapsed_us = elapsed_ns // 1000
        self._profiler.record(self._stage, elapsed_us, self._metadata)
        return False  # Don't suppress exceptions


class LatencyProfiler:
    """
    Tracks latency through the order execution pipeline.

    Usage:
        profiler = LatencyProfiler()

        with profiler.time(LatencyStage.STRATEGY_DECISION):
            # Strategy decision code
            pass

        with profiler.time(LatencyStage.RISK_VALIDATION):
            # Risk validation code
            pass

        # Get stats
        summary = profiler.get_summary()
    """

    def __init__(
        self,
        window_size: int = 1000,
        logger: logging.Logger = None,
    ):
        """
        Initialize profiler.

        Args:
            window_size: Number of samples to keep per stage
            logger: Logger instance
        """
        self._window_size = window_size
        self._logger = logger or logging.getLogger(__name__)

        # Per-stage sample buffers
        self._samples: Dict[LatencyStage, Deque[LatencyRecord]] = {
            stage: deque(maxlen=window_size)
            for stage in LatencyStage
        }

        # End-to-end tracking
        self._e2e_samples: Deque[int] = deque(maxlen=window_size)

        # Breach tracking
        self._breach_callbacks: List = []

    def time(self, stage: LatencyStage, metadata: Dict = None) -> LatencyTimer:
        """
        Create a timer context manager for a stage.

        Args:
            stage: Pipeline stage to time
            metadata: Optional metadata to attach

        Returns:
            LatencyTimer context manager
        """
        return LatencyTimer(self, stage, metadata)

    def record(self, stage: LatencyStage, latency_us: int, metadata: Dict = None):
        """
        Record a latency measurement.

        Args:
            stage: Pipeline stage
            latency_us: Latency in microseconds
            metadata: Optional metadata
        """
        record = LatencyRecord(
            stage=stage,
            latency_us=latency_us,
            metadata=metadata or {},
        )

        self._samples[stage].append(record)

        # Check for breaches
        target = LATENCY_TARGETS_US.get(stage, 100)
        if latency_us > target * CRITICAL_THRESHOLD:
            self._logger.warning(
                f"Latency breach in {stage.value}: {latency_us}μs "
                f"(target: {target}μs, critical: {target * CRITICAL_THRESHOLD}μs)"
            )
            self._notify_breach(record)

    def record_e2e(self, total_latency_us: int):
        """Record end-to-end latency for a complete order."""
        self._e2e_samples.append(total_latency_us)

    def get_stage_stats(self, stage: LatencyStage) -> Optional[StageStats]:
        """Get statistics for a single stage."""
        samples = list(self._samples[stage])
        if not samples:
            return None

        latencies = [s.latency_us for s in samples]
        target = LATENCY_TARGETS_US.get(stage, 100)
        breaches = sum(1 for l in latencies if l > target)

        return StageStats(
            stage=stage,
            sample_count=len(latencies),
            p50_us=int(self._percentile(latencies, 50)),
            p95_us=int(self._percentile(latencies, 95)),
            p99_us=int(self._percentile(latencies, 99)),
            min_us=min(latencies),
            max_us=max(latencies),
            mean_us=statistics.mean(latencies),
            target_us=target,
            breaches=breaches,
        )

    def get_summary(self) -> LatencySummary:
        """Get complete latency summary."""
        stage_stats = {}
        stages_meeting = 0

        for stage in LatencyStage:
            stats = self.get_stage_stats(stage)
            if stats:
                stage_stats[stage.value] = stats
                if stats.meets_target:
                    stages_meeting += 1

        # E2E stats
        e2e_list = list(self._e2e_samples)
        if e2e_list:
            e2e_p50 = int(self._percentile(e2e_list, 50))
            e2e_p95 = int(self._percentile(e2e_list, 95))
            e2e_p99 = int(self._percentile(e2e_list, 99))
        else:
            e2e_p50 = e2e_p95 = e2e_p99 = 0

        total_samples = sum(len(self._samples[s]) for s in LatencyStage)

        return LatencySummary(
            timestamp=datetime.now(),
            total_samples=total_samples,
            stages=stage_stats,
            total_e2e_p50_us=e2e_p50,
            total_e2e_p95_us=e2e_p95,
            total_e2e_p99_us=e2e_p99,
            stages_meeting_target=stages_meeting,
            stages_total=len(LatencyStage),
        )

    def get_percentiles(self) -> Dict[str, Dict[str, int]]:
        """Get p50, p95, p99 for each stage."""
        result = {}
        for stage in LatencyStage:
            stats = self.get_stage_stats(stage)
            if stats:
                result[stage.value] = {
                    'p50': stats.p50_us,
                    'p95': stats.p95_us,
                    'p99': stats.p99_us,
                }
        return result

    def add_breach_callback(self, callback):
        """Add callback for latency breaches."""
        self._breach_callbacks.append(callback)

    def _notify_breach(self, record: LatencyRecord):
        """Notify callbacks of a breach."""
        for callback in self._breach_callbacks:
            try:
                callback(record)
            except Exception as e:
                self._logger.error(f"Breach callback failed: {e}")

    def _percentile(self, data: List[int], pct: float) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * pct / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    def reset(self):
        """Clear all samples."""
        for stage in LatencyStage:
            self._samples[stage].clear()
        self._e2e_samples.clear()

    def get_recent_records(self, stage: LatencyStage, limit: int = 10) -> List[Dict]:
        """Get recent records for a stage."""
        samples = list(self._samples[stage])[-limit:]
        return [
            {
                'latency_us': s.latency_us,
                'timestamp': s.timestamp.isoformat(),
                'is_warning': s.is_warning,
                'is_critical': s.is_critical,
                'metadata': s.metadata,
            }
            for s in samples
        ]


# Global profiler instance
_profiler: Optional[LatencyProfiler] = None


def get_profiler() -> LatencyProfiler:
    """Get global profiler instance."""
    global _profiler
    if _profiler is None:
        _profiler = LatencyProfiler()
    return _profiler


def reset_profiler():
    """Reset global profiler."""
    global _profiler
    _profiler = None

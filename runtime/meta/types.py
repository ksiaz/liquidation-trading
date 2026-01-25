"""
Meta-Monitoring Types.

Data structures for tracking design assumptions and system health.
Protects against bias by making implicit beliefs explicit and testable.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum, auto


class AssumptionStatus(Enum):
    """Status of a design assumption."""
    UNTESTED = auto()      # Never validated
    VALID = auto()         # Last test passed
    WARNING = auto()       # Degrading but not failed
    INVALID = auto()       # Failed validation
    EXPIRED = auto()       # Past validity period


class ModelHealthStatus(Enum):
    """Health status of a calibrated model/threshold."""
    HEALTHY = auto()       # Distribution matches expectations
    DRIFTING = auto()      # Gradual divergence detected
    BROKEN = auto()        # Significant divergence
    UNKNOWN = auto()       # Insufficient data


class SystemRegime(Enum):
    """Regime of the system's edge."""
    UNKNOWN = auto()       # Insufficient history
    EDGE_PRESENT = auto()  # System performing as designed
    EDGE_DECAYING = auto() # Performance degrading
    EDGE_GONE = auto()     # No detectable edge
    REGIME_CHANGE = auto() # Market structure changed


@dataclass
class Assumption:
    """
    An explicit design assumption that can be tested.

    Makes implicit beliefs explicit so they can be validated
    against reality and trigger actions when violated.
    """
    name: str
    description: str
    category: str  # 'market_structure', 'data_quality', 'execution', 'model'

    # Validation
    test_fn: Optional[Callable[[], bool]] = None
    test_description: str = ""

    # Status tracking
    status: AssumptionStatus = AssumptionStatus.UNTESTED
    last_tested_ns: Optional[int] = None
    last_result: Optional[bool] = None
    consecutive_failures: int = 0

    # Validity period
    valid_until_ns: Optional[int] = None
    requires_revalidation_after_ns: int = 7 * 24 * 3600 * 1_000_000_000  # 7 days

    # Actions on invalidation
    invalidation_action: str = ""  # What to do if assumption fails
    affected_components: List[str] = field(default_factory=list)

    # Metadata
    created_at_ns: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))

    def is_expired(self, now_ns: int = None) -> bool:
        """Check if assumption has expired."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        if self.valid_until_ns and now_ns > self.valid_until_ns:
            return True
        if self.last_tested_ns:
            age = now_ns - self.last_tested_ns
            if age > self.requires_revalidation_after_ns:
                return True
        return False

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'test_description': self.test_description,
            'status': self.status.name,
            'last_tested_ns': self.last_tested_ns,
            'last_result': self.last_result,
            'consecutive_failures': self.consecutive_failures,
            'valid_until_ns': self.valid_until_ns,
            'invalidation_action': self.invalidation_action,
            'affected_components': self.affected_components,
        }


@dataclass
class CalibratedParameter:
    """
    A parameter calibrated from historical data.

    Tracks when calibration was done and monitors for drift.
    """
    name: str
    value: float
    unit: str = ""

    # Calibration metadata
    calibrated_at_ns: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))
    calibrated_from_samples: int = 0
    calibration_source: str = ""  # e.g., "30d_cascade_data"

    # Expected distribution
    expected_mean: Optional[float] = None
    expected_std: Optional[float] = None
    acceptable_drift_pct: float = 0.20  # 20% drift triggers warning

    # Validity
    valid_until_ns: Optional[int] = None

    # Current health
    observed_mean: Optional[float] = None
    observed_std: Optional[float] = None
    drift_pct: float = 0.0
    health_status: ModelHealthStatus = ModelHealthStatus.UNKNOWN

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'value': self.value,
            'unit': self.unit,
            'calibrated_at_ns': self.calibrated_at_ns,
            'calibrated_from_samples': self.calibrated_from_samples,
            'expected_mean': self.expected_mean,
            'expected_std': self.expected_std,
            'drift_pct': self.drift_pct,
            'health_status': self.health_status.name,
        }


@dataclass
class DistributionSnapshot:
    """Snapshot of an observed distribution."""
    name: str
    timestamp_ns: int
    sample_count: int
    mean: float
    std: float
    min_val: float
    max_val: float
    p25: float
    p50: float
    p75: float
    p95: float

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'timestamp_ns': self.timestamp_ns,
            'sample_count': self.sample_count,
            'mean': self.mean,
            'std': self.std,
            'min': self.min_val,
            'max': self.max_val,
            'p25': self.p25,
            'p50': self.p50,
            'p75': self.p75,
            'p95': self.p95,
        }


@dataclass
class EdgeMetrics:
    """Metrics for tracking system edge."""
    timestamp_ns: int

    # Performance vs expectation
    expected_win_rate: float
    observed_win_rate: float
    win_rate_zscore: float  # How many std devs from expected

    expected_profit_factor: float
    observed_profit_factor: float

    # Edge indicators
    information_ratio: float  # Risk-adjusted return vs benchmark
    edge_decay_rate: float    # Rolling slope of performance

    # Sample info
    trade_count: int
    period_days: int

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'timestamp_ns': self.timestamp_ns,
            'expected_win_rate': self.expected_win_rate,
            'observed_win_rate': self.observed_win_rate,
            'win_rate_zscore': self.win_rate_zscore,
            'expected_profit_factor': self.expected_profit_factor,
            'observed_profit_factor': self.observed_profit_factor,
            'information_ratio': self.information_ratio,
            'edge_decay_rate': self.edge_decay_rate,
            'trade_count': self.trade_count,
            'period_days': self.period_days,
        }


@dataclass
class SystemHealthReport:
    """Comprehensive system health report."""
    timestamp_ns: int

    # Assumption health
    total_assumptions: int
    valid_assumptions: int
    invalid_assumptions: int
    expired_assumptions: int
    assumptions_needing_revalidation: List[str]

    # Model health
    total_parameters: int
    healthy_parameters: int
    drifting_parameters: int
    broken_parameters: int
    parameters_needing_recalibration: List[str]

    # System regime
    current_regime: SystemRegime
    regime_confidence: float
    days_in_regime: int

    # Overall assessment
    overall_health: str  # 'HEALTHY', 'DEGRADED', 'CRITICAL', 'UNKNOWN'
    recommended_actions: List[str]

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'timestamp_ns': self.timestamp_ns,
            'assumptions': {
                'total': self.total_assumptions,
                'valid': self.valid_assumptions,
                'invalid': self.invalid_assumptions,
                'expired': self.expired_assumptions,
                'needing_revalidation': self.assumptions_needing_revalidation,
            },
            'parameters': {
                'total': self.total_parameters,
                'healthy': self.healthy_parameters,
                'drifting': self.drifting_parameters,
                'broken': self.broken_parameters,
                'needing_recalibration': self.parameters_needing_recalibration,
            },
            'regime': {
                'current': self.current_regime.name,
                'confidence': self.regime_confidence,
                'days_in_regime': self.days_in_regime,
            },
            'overall_health': self.overall_health,
            'recommended_actions': self.recommended_actions,
        }

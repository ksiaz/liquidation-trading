"""
HLP23: Threshold Documentation.

Provides full provenance tracking for each threshold:
- Discovery method (grid_search, roc_analysis, manual)
- Training/validation periods
- Performance metrics
- Sensitivity analysis
- Review schedule

Every threshold should have documentation explaining:
1. Why this value was chosen
2. How it was discovered/validated
3. When it should be reviewed
4. What happens if it changes by ±10%
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum, auto


class DiscoveryMethod(Enum):
    """How the threshold was discovered."""
    GRID_SEARCH = auto()        # Exhaustive parameter search
    ROC_ANALYSIS = auto()       # ROC curve optimization
    WALK_FORWARD = auto()       # Walk-forward optimization
    BAYESIAN = auto()           # Bayesian optimization
    MANUAL = auto()             # Expert judgment
    LITERATURE = auto()         # From research papers
    DEFAULT = auto()            # Conservative default (not validated)


class ValidationStatus(Enum):
    """Validation state of threshold."""
    UNVALIDATED = auto()        # Not yet tested
    IN_SAMPLE_ONLY = auto()     # Optimized but not OOS tested
    VALIDATED = auto()          # Passed OOS validation
    DEGRADED = auto()           # Was validated, now underperforming
    REQUIRES_REVIEW = auto()    # Past review date


@dataclass
class PerformanceMetrics:
    """Performance metrics for a threshold value."""
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    n_trades: int = 0
    avg_trade_pnl: float = 0.0


@dataclass
class SensitivityResult:
    """Result of sensitivity analysis."""
    threshold_name: str
    base_value: float
    test_value: float
    change_pct: float
    sharpe_change_pct: float
    win_rate_change_pct: float
    is_stable: bool  # True if changes < 10%


@dataclass
class ThresholdDocumentation:
    """
    Full documentation for a threshold with provenance.

    Example:
        doc = ThresholdDocumentation(
            name='oi.spike_ratio',
            value=1.15,
            discovery_date=datetime(2024, 1, 15),
            discovery_method=DiscoveryMethod.GRID_SEARCH,
            training_period=(datetime(2023, 6, 1), datetime(2023, 12, 31)),
            performance=PerformanceMetrics(sharpe=1.5, win_rate=0.55, n_trades=150),
            oos_validation=PerformanceMetrics(sharpe=1.3, win_rate=0.52, n_trades=45),
            sensitivity={
                '+10%': SensitivityResult(..., sharpe_change=-5%),
                '-10%': SensitivityResult(..., sharpe_change=-8%),
            },
            rationale="OI spike of 15% captures 80% of cascade events with <20% false positives",
            next_review_date=datetime(2024, 4, 15),
        )
    """
    name: str
    value: float
    discovery_date: datetime
    discovery_method: DiscoveryMethod
    training_period: Tuple[datetime, datetime]
    performance: PerformanceMetrics
    oos_validation: Optional[PerformanceMetrics] = None
    sensitivity: Dict[str, SensitivityResult] = field(default_factory=dict)
    regime_stability: Dict[str, bool] = field(default_factory=dict)
    rationale: str = ""
    next_review_date: Optional[datetime] = None
    status: ValidationStatus = ValidationStatus.UNVALIDATED

    def is_validated(self) -> bool:
        """Check if threshold is validated."""
        return self.status == ValidationStatus.VALIDATED

    def needs_review(self) -> bool:
        """Check if threshold is past review date."""
        if self.next_review_date is None:
            return True
        return datetime.now() > self.next_review_date

    def get_oos_degradation(self) -> Optional[float]:
        """Calculate OOS degradation from training performance."""
        if self.oos_validation is None:
            return None
        if self.performance.sharpe_ratio == 0:
            return None
        return (
            (self.performance.sharpe_ratio - self.oos_validation.sharpe_ratio)
            / self.performance.sharpe_ratio
        )

    def is_sensitivity_stable(self) -> bool:
        """Check if threshold is stable to ±10% changes."""
        for result in self.sensitivity.values():
            if not result.is_stable:
                return False
        return True

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'value': self.value,
            'discovery_date': self.discovery_date.isoformat(),
            'discovery_method': self.discovery_method.name,
            'training_period': [
                self.training_period[0].isoformat(),
                self.training_period[1].isoformat(),
            ],
            'performance': {
                'sharpe_ratio': self.performance.sharpe_ratio,
                'win_rate': self.performance.win_rate,
                'profit_factor': self.performance.profit_factor,
                'max_drawdown': self.performance.max_drawdown,
                'n_trades': self.performance.n_trades,
                'avg_trade_pnl': self.performance.avg_trade_pnl,
            },
            'oos_validation': {
                'sharpe_ratio': self.oos_validation.sharpe_ratio,
                'win_rate': self.oos_validation.win_rate,
                'n_trades': self.oos_validation.n_trades,
            } if self.oos_validation else None,
            'sensitivity_stable': self.is_sensitivity_stable(),
            'rationale': self.rationale,
            'next_review_date': self.next_review_date.isoformat() if self.next_review_date else None,
            'status': self.status.name,
        }


class ThresholdRegistry:
    """
    Registry of all documented thresholds.

    Provides:
    - Storage and retrieval of threshold documentation
    - Validation status tracking
    - Review scheduling
    - Audit trail
    """

    def __init__(self):
        self._thresholds: Dict[str, ThresholdDocumentation] = {}
        self._history: List[Tuple[datetime, str, str, float, float]] = []  # (date, name, action, old, new)

    def register(self, doc: ThresholdDocumentation):
        """Register a threshold with documentation."""
        old_value = None
        if doc.name in self._thresholds:
            old_value = self._thresholds[doc.name].value

        self._thresholds[doc.name] = doc

        # Record in history
        self._history.append((
            datetime.now(),
            doc.name,
            'register' if old_value is None else 'update',
            old_value or 0.0,
            doc.value
        ))

    def get(self, name: str) -> Optional[ThresholdDocumentation]:
        """Get documentation for a threshold."""
        return self._thresholds.get(name)

    def get_value(self, name: str) -> Optional[float]:
        """Get current value for a threshold."""
        doc = self._thresholds.get(name)
        return doc.value if doc else None

    def is_validated(self, name: str) -> bool:
        """Check if threshold is validated."""
        doc = self._thresholds.get(name)
        return doc.is_validated() if doc else False

    def get_unvalidated(self) -> List[str]:
        """Get list of unvalidated thresholds."""
        return [
            name for name, doc in self._thresholds.items()
            if not doc.is_validated()
        ]

    def get_needs_review(self) -> List[str]:
        """Get list of thresholds that need review."""
        return [
            name for name, doc in self._thresholds.items()
            if doc.needs_review()
        ]

    def get_by_method(self, method: DiscoveryMethod) -> List[str]:
        """Get thresholds discovered by a specific method."""
        return [
            name for name, doc in self._thresholds.items()
            if doc.discovery_method == method
        ]

    def update_status(self, name: str, status: ValidationStatus):
        """Update validation status of a threshold."""
        if name in self._thresholds:
            old_status = self._thresholds[name].status
            self._thresholds[name].status = status
            self._history.append((
                datetime.now(),
                name,
                f'status:{old_status.name}->{status.name}',
                0.0,
                0.0
            ))

    def get_summary(self) -> Dict:
        """Get summary of registry state."""
        total = len(self._thresholds)
        validated = sum(1 for d in self._thresholds.values() if d.is_validated())
        needs_review = sum(1 for d in self._thresholds.values() if d.needs_review())

        by_method = {}
        for method in DiscoveryMethod:
            count = sum(
                1 for d in self._thresholds.values()
                if d.discovery_method == method
            )
            if count > 0:
                by_method[method.name] = count

        return {
            'total_thresholds': total,
            'validated': validated,
            'unvalidated': total - validated,
            'needs_review': needs_review,
            'by_discovery_method': by_method,
        }

    def get_history(self, name: str = None, limit: int = 100) -> List[Dict]:
        """Get change history, optionally filtered by name."""
        history = self._history
        if name:
            history = [h for h in history if h[1] == name]

        return [
            {
                'date': h[0].isoformat(),
                'name': h[1],
                'action': h[2],
                'old_value': h[3],
                'new_value': h[4],
            }
            for h in history[-limit:]
        ]

    def export_all(self) -> List[Dict]:
        """Export all threshold documentation."""
        return [doc.to_dict() for doc in self._thresholds.values()]

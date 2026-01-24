"""
HLP23 Threshold Store.

Versioned storage for threshold configurations with full provenance tracking.

Every threshold is documented with:
- Value and name
- Discovery method
- Performance metrics
- Validation status
- Review schedule
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum, auto
import json

from .threshold_discovery import DiscoveryMethod


class ThresholdStatus(Enum):
    """Status of a threshold configuration."""
    HYPOTHESIS = auto()  # Not yet validated
    VALIDATED = auto()  # Passed out-of-sample testing
    OVERFITTED = auto()  # Failed out-of-sample testing
    DEPRECATED = auto()  # Replaced by newer threshold
    ACTIVE = auto()  # Currently in use


@dataclass
class ThresholdConfig:
    """
    Complete threshold configuration with provenance.

    Tracks everything needed for auditability:
    - What the threshold is
    - How it was discovered
    - How well it performed
    - When to review it
    """
    # Identity
    name: str
    value: float

    # Provenance
    method: DiscoveryMethod
    date_set: str  # ISO format
    rationale: str

    # Performance (in-sample)
    sharpe_ratio: float
    win_rate: float
    trades_per_month: float

    # Validation (out-of-sample)
    validation_sharpe: Optional[float] = None
    validation_degradation_pct: Optional[float] = None
    status: ThresholdStatus = ThresholdStatus.HYPOTHESIS

    # Sensitivity
    sensitivity_range_pct: Optional[float] = None  # Performance change in ±10%
    is_robust: bool = False

    # Review schedule
    next_review_date: Optional[str] = None

    # Regime-specific (optional)
    regime: Optional[str] = None  # If threshold varies by regime

    # Metadata
    version: int = 1
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'value': self.value,
            'method': self.method.name,
            'date_set': self.date_set,
            'rationale': self.rationale,
            'sharpe_ratio': self.sharpe_ratio,
            'win_rate': self.win_rate,
            'trades_per_month': self.trades_per_month,
            'validation_sharpe': self.validation_sharpe,
            'validation_degradation_pct': self.validation_degradation_pct,
            'status': self.status.name,
            'sensitivity_range_pct': self.sensitivity_range_pct,
            'is_robust': self.is_robust,
            'next_review_date': self.next_review_date,
            'regime': self.regime,
            'version': self.version,
            'notes': self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThresholdConfig':
        """Create from dictionary."""
        return cls(
            name=data['name'],
            value=data['value'],
            method=DiscoveryMethod[data['method']],
            date_set=data['date_set'],
            rationale=data['rationale'],
            sharpe_ratio=data['sharpe_ratio'],
            win_rate=data['win_rate'],
            trades_per_month=data['trades_per_month'],
            validation_sharpe=data.get('validation_sharpe'),
            validation_degradation_pct=data.get('validation_degradation_pct'),
            status=ThresholdStatus[data.get('status', 'HYPOTHESIS')],
            sensitivity_range_pct=data.get('sensitivity_range_pct'),
            is_robust=data.get('is_robust', False),
            next_review_date=data.get('next_review_date'),
            regime=data.get('regime'),
            version=data.get('version', 1),
            notes=data.get('notes')
        )


@dataclass
class ThresholdSet:
    """
    A complete set of thresholds for a strategy.

    Groups related thresholds together with metadata.
    """
    strategy_name: str
    thresholds: Dict[str, ThresholdConfig]
    created_at: str
    version: int = 1
    description: Optional[str] = None

    def get(self, name: str) -> Optional[float]:
        """Get threshold value by name."""
        config = self.thresholds.get(name)
        return config.value if config else None

    def get_config(self, name: str) -> Optional[ThresholdConfig]:
        """Get full threshold config by name."""
        return self.thresholds.get(name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'strategy_name': self.strategy_name,
            'thresholds': {
                name: config.to_dict()
                for name, config in self.thresholds.items()
            },
            'created_at': self.created_at,
            'version': self.version,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThresholdSet':
        """Create from dictionary."""
        thresholds = {
            name: ThresholdConfig.from_dict(config_data)
            for name, config_data in data['thresholds'].items()
        }
        return cls(
            strategy_name=data['strategy_name'],
            thresholds=thresholds,
            created_at=data['created_at'],
            version=data.get('version', 1),
            description=data.get('description')
        )


class ThresholdStore:
    """
    Store for threshold configurations.

    Provides:
    - Versioned threshold storage
    - History tracking
    - Review scheduling
    - Export/import
    """

    def __init__(self, db):
        """
        Initialize store with database connection.

        Args:
            db: ResearchDatabase instance
        """
        self._db = db

    def save_threshold(self, config: ThresholdConfig) -> int:
        """
        Save a threshold configuration.

        Args:
            config: Threshold configuration

        Returns:
            Database ID of saved threshold
        """
        return self._db.log_threshold_config(
            name=config.name,
            value=config.value,
            method=config.method.name,
            date_set=config.date_set,
            rationale=config.rationale,
            sharpe_ratio=config.sharpe_ratio,
            win_rate=config.win_rate,
            trades_per_month=config.trades_per_month,
            validation_sharpe=config.validation_sharpe,
            validation_degradation_pct=config.validation_degradation_pct,
            status=config.status.name,
            is_robust=config.is_robust,
            next_review_date=config.next_review_date,
            regime=config.regime,
            version=config.version,
            notes=config.notes
        )

    def get_active_threshold(self, name: str, regime: str = None) -> Optional[ThresholdConfig]:
        """
        Get the active threshold for a name.

        Args:
            name: Threshold name
            regime: Optional regime filter

        Returns:
            Active threshold config or None
        """
        result = self._db.get_active_threshold(name, regime)
        if result:
            return ThresholdConfig.from_dict(result)
        return None

    def get_threshold_history(
        self,
        name: str,
        limit: int = 10
    ) -> List[ThresholdConfig]:
        """
        Get history of threshold values.

        Args:
            name: Threshold name
            limit: Maximum number of records

        Returns:
            List of historical threshold configs
        """
        results = self._db.get_threshold_history(name, limit)
        return [ThresholdConfig.from_dict(r) for r in results]

    def get_thresholds_due_for_review(self) -> List[ThresholdConfig]:
        """
        Get thresholds that need review.

        Returns:
            List of thresholds past their review date
        """
        results = self._db.get_thresholds_due_for_review()
        return [ThresholdConfig.from_dict(r) for r in results]

    def save_threshold_set(self, threshold_set: ThresholdSet) -> int:
        """
        Save a complete threshold set.

        Args:
            threshold_set: ThresholdSet to save

        Returns:
            Number of thresholds saved
        """
        count = 0
        for config in threshold_set.thresholds.values():
            self.save_threshold(config)
            count += 1
        return count

    def load_threshold_set(self, strategy_name: str) -> Optional[ThresholdSet]:
        """
        Load active thresholds for a strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            ThresholdSet or None
        """
        results = self._db.get_thresholds_for_strategy(strategy_name)
        if not results:
            return None

        thresholds = {}
        for r in results:
            config = ThresholdConfig.from_dict(r)
            thresholds[config.name] = config

        return ThresholdSet(
            strategy_name=strategy_name,
            thresholds=thresholds,
            created_at=datetime.now().isoformat(),
            version=1
        )

    def export_to_json(self, threshold_set: ThresholdSet, path: str):
        """
        Export threshold set to JSON file.

        Args:
            threshold_set: ThresholdSet to export
            path: File path
        """
        with open(path, 'w') as f:
            json.dump(threshold_set.to_dict(), f, indent=2)

    def import_from_json(self, path: str) -> ThresholdSet:
        """
        Import threshold set from JSON file.

        Args:
            path: File path

        Returns:
            ThresholdSet
        """
        with open(path, 'r') as f:
            data = json.load(f)
        return ThresholdSet.from_dict(data)


def create_threshold_config(
    name: str,
    value: float,
    method: DiscoveryMethod,
    rationale: str,
    sharpe: float = 0.0,
    win_rate: float = 0.0,
    trades_per_month: float = 0.0,
    review_days: int = 30,
    regime: str = None
) -> ThresholdConfig:
    """
    Helper to create a threshold config with defaults.

    Args:
        name: Threshold name
        value: Threshold value
        method: Discovery method
        rationale: Explanation
        sharpe: In-sample Sharpe ratio
        win_rate: In-sample win rate
        trades_per_month: Expected trades per month
        review_days: Days until next review
        regime: Optional regime

    Returns:
        ThresholdConfig
    """
    now = datetime.now()
    review_date = now + timedelta(days=review_days)

    return ThresholdConfig(
        name=name,
        value=value,
        method=method,
        date_set=now.isoformat(),
        rationale=rationale,
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        trades_per_month=trades_per_month,
        next_review_date=review_date.isoformat(),
        regime=regime,
        status=ThresholdStatus.HYPOTHESIS
    )


def create_conservative_threshold_set(strategy_name: str) -> ThresholdSet:
    """
    Create a threshold set with conservative defaults.

    These are starting points based on domain knowledge.
    All require validation before trusting.

    Args:
        strategy_name: Name of strategy

    Returns:
        ThresholdSet with conservative defaults
    """
    from .threshold_discovery import get_conservative_defaults

    defaults = get_conservative_defaults()
    thresholds = {}

    rationales = {
        'oi_spike_threshold': 'Normal OI varies ±10%. 18% is 1.8x normal movement.',
        'oi_collapse_threshold': '15% drop indicates forced liquidation pressure.',
        'oi_stability_threshold': '±5% considered normal market noise.',
        'funding_skew_threshold': 'Normal funding ±0.01%. 1.8% is 180x normal.',
        'funding_divergence_threshold': '5bps spread indicates cross-exchange opportunity.',
        'depth_asymmetry_threshold': 'Normal asymmetry 0.8-1.2. 1.6x is outside normal.',
        'match_score_minimum': 'Require 75% of conditions for quality setups.',
        'high_match_score': '85% indicates high-priority setup.',
        'daily_loss_limit': 'Conservative risk management.',
        'position_size_limit': 'Limit individual position risk.',
        'max_aggregate_exposure': 'Limit total portfolio risk.',
        'wave_count_min': 'Cascades typically have at least 3 waves.',
        'wave_count_max': 'Cascades rarely exceed 5 waves.',
        'wave_gap_seconds': '30 second gap separates distinct waves.',
        'absorption_ratio_threshold': '65% absorption indicates potential exhaustion.',
        'cascade_oi_drop_pct': '10% OI drop indicates cascade event.',
        'cascade_min_liquidations': 'Minimum 2 liquidations for cascade.',
    }

    for name, value in defaults.items():
        rationale = rationales.get(name, 'Conservative default based on market structure.')
        thresholds[name] = create_threshold_config(
            name=name,
            value=value,
            method=DiscoveryMethod.CONSERVATIVE_DEFAULT,
            rationale=rationale,
            review_days=30
        )

    return ThresholdSet(
        strategy_name=strategy_name,
        thresholds=thresholds,
        created_at=datetime.now().isoformat(),
        version=1,
        description='Conservative defaults based on HLP23 domain knowledge. All require validation.'
    )

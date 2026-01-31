"""
HLP23: Threshold Configuration.

Conservative default thresholds for all strategy parameters.

IMPORTANT: All thresholds are HYPOTHESES until validated.
Do not trust default values without:
1. Grid search optimization on historical data
2. Walk-forward out-of-sample validation
3. Sensitivity analysis (±10% should not degrade Sharpe >10%)

Usage:
    config = ThresholdConfig()

    # Check if threshold is validated
    if config.is_validated('oi_spike_ratio'):
        use_threshold(config.oi.spike_ratio)
    else:
        # Use more conservative value or skip
        pass
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from datetime import datetime


@dataclass
class OIThresholds:
    """Open Interest thresholds."""
    # Spike detection
    spike_ratio: float = 1.15           # 15% above baseline triggers alert
    spike_window_sec: int = 60          # Window for spike detection

    # Collapse detection
    collapse_ratio: float = 0.85        # 15% below baseline
    collapse_window_sec: int = 60       # Window for collapse detection

    # Elevation (sustained high OI)
    elevation_zscore: float = 2.0       # 2 std devs above mean
    elevation_lookback_sec: int = 3600  # 1 hour baseline

    # Velocity thresholds
    velocity_threshold: float = 0.001   # 0.1% per second
    acceleration_threshold: float = 0.0001  # Rate of velocity change


@dataclass
class FundingThresholds:
    """Funding rate thresholds."""
    # Skew detection
    skew_threshold: float = 0.0015      # 0.15% (15 bps) indicates directional bias
    extreme_skew: float = 0.005         # 0.5% (50 bps) extreme funding

    # Velocity
    velocity_threshold: float = 0.0001  # Per minute change rate

    # Divergence from baseline
    divergence_zscore: float = 2.0      # 2 std devs from mean
    baseline_lookback_hours: int = 24   # 24h rolling baseline


@dataclass
class DepthThresholds:
    """Orderbook depth thresholds."""
    # Asymmetry detection
    asymmetry_ratio: float = 1.5        # 1.5:1 bid:ask imbalance
    significant_asymmetry: float = 2.0  # 2:1 strong imbalance

    # Thinning detection
    thinning_pct: float = 0.50          # 50% depth reduction
    critical_thinning_pct: float = 0.80 # 80% depth gone

    # Depth levels to monitor
    depth_levels_pct: tuple = (0.5, 1.0, 2.0, 5.0)  # % from mid

    # Absorption detection
    absorption_ratio: float = 3.0       # Volume vs visible depth


@dataclass
class ConfidenceThresholds:
    """Signal confidence thresholds."""
    # Match scores
    minimum_match_score: float = 0.70   # 70% confidence minimum
    high_confidence_score: float = 0.85 # 85% high confidence

    # Signal agreement
    min_confirming_signals: int = 2     # At least 2 signals agree

    # Regime alignment
    require_regime_match: bool = True   # Strategy must match regime


@dataclass
class TimingThresholds:
    """Timing and duration thresholds."""
    # Armed state
    armed_timeout_sec: int = 120        # 2 min max armed duration
    armed_min_duration_sec: int = 5     # Min time in armed before trigger

    # Entry windows
    entry_window_sec: int = 30          # Max time to enter after trigger

    # Position hold times
    min_hold_sec: int = 10              # Minimum position hold
    max_hold_sec: int = 300             # 5 min max hold for scalps

    # Cooldown
    cooldown_sec: int = 300             # 5 min between same-symbol trades

    # Grace periods
    entry_grace_sec: int = 10           # No exit checks after entry


@dataclass
class ThresholdConfig:
    """
    Complete threshold configuration.

    All values are conservative defaults that prioritize:
    1. Avoiding false positives (missing good trades is OK)
    2. Capital preservation (no risky entries)
    3. Clear signals (high confidence required)

    Attributes:
        oi: Open interest thresholds
        funding: Funding rate thresholds
        depth: Orderbook depth thresholds
        confidence: Signal confidence thresholds
        timing: Timing thresholds
        _validated: Set of validated threshold names
    """
    oi: OIThresholds = field(default_factory=OIThresholds)
    funding: FundingThresholds = field(default_factory=FundingThresholds)
    depth: DepthThresholds = field(default_factory=DepthThresholds)
    confidence: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    timing: TimingThresholds = field(default_factory=TimingThresholds)

    # Track which thresholds have been validated
    _validated: Set[str] = field(default_factory=set)
    _validation_dates: Dict[str, datetime] = field(default_factory=dict)

    def mark_validated(self, threshold_name: str, validation_date: datetime = None):
        """Mark a threshold as validated."""
        self._validated.add(threshold_name)
        self._validation_dates[threshold_name] = validation_date or datetime.now()

    def is_validated(self, threshold_name: str) -> bool:
        """Check if threshold has been validated."""
        return threshold_name in self._validated

    def get_validation_date(self, threshold_name: str) -> Optional[datetime]:
        """Get when threshold was validated."""
        return self._validation_dates.get(threshold_name)

    def get_unvalidated(self) -> Set[str]:
        """Get set of unvalidated threshold names."""
        all_thresholds = self._get_all_threshold_names()
        return all_thresholds - self._validated

    def _get_all_threshold_names(self) -> Set[str]:
        """Get all threshold names for validation tracking."""
        names = set()

        # OI thresholds
        for name in ['spike_ratio', 'collapse_ratio', 'elevation_zscore',
                     'velocity_threshold', 'acceleration_threshold']:
            names.add(f'oi.{name}')

        # Funding thresholds
        for name in ['skew_threshold', 'extreme_skew', 'velocity_threshold',
                     'divergence_zscore']:
            names.add(f'funding.{name}')

        # Depth thresholds
        for name in ['asymmetry_ratio', 'significant_asymmetry',
                     'thinning_pct', 'critical_thinning_pct', 'absorption_ratio']:
            names.add(f'depth.{name}')

        # Confidence thresholds
        for name in ['minimum_match_score', 'high_confidence_score',
                     'min_confirming_signals']:
            names.add(f'confidence.{name}')

        # Timing thresholds
        for name in ['armed_timeout_sec', 'entry_window_sec',
                     'min_hold_sec', 'max_hold_sec', 'cooldown_sec']:
            names.add(f'timing.{name}')

        return names

    def get_threshold_value(self, path: str) -> Optional[float]:
        """Get threshold value by path (e.g., 'oi.spike_ratio')."""
        parts = path.split('.')
        if len(parts) != 2:
            return None

        category, name = parts
        category_obj = getattr(self, category, None)
        if category_obj is None:
            return None

        return getattr(category_obj, name, None)

    def set_threshold_value(self, path: str, value: float) -> bool:
        """Set threshold value by path."""
        parts = path.split('.')
        if len(parts) != 2:
            return False

        category, name = parts
        category_obj = getattr(self, category, None)
        if category_obj is None:
            return False

        if not hasattr(category_obj, name):
            return False

        setattr(category_obj, name, value)
        return True

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'oi': {
                'spike_ratio': self.oi.spike_ratio,
                'spike_window_sec': self.oi.spike_window_sec,
                'collapse_ratio': self.oi.collapse_ratio,
                'collapse_window_sec': self.oi.collapse_window_sec,
                'elevation_zscore': self.oi.elevation_zscore,
                'elevation_lookback_sec': self.oi.elevation_lookback_sec,
                'velocity_threshold': self.oi.velocity_threshold,
                'acceleration_threshold': self.oi.acceleration_threshold,
            },
            'funding': {
                'skew_threshold': self.funding.skew_threshold,
                'extreme_skew': self.funding.extreme_skew,
                'velocity_threshold': self.funding.velocity_threshold,
                'divergence_zscore': self.funding.divergence_zscore,
                'baseline_lookback_hours': self.funding.baseline_lookback_hours,
            },
            'depth': {
                'asymmetry_ratio': self.depth.asymmetry_ratio,
                'significant_asymmetry': self.depth.significant_asymmetry,
                'thinning_pct': self.depth.thinning_pct,
                'critical_thinning_pct': self.depth.critical_thinning_pct,
                'absorption_ratio': self.depth.absorption_ratio,
            },
            'confidence': {
                'minimum_match_score': self.confidence.minimum_match_score,
                'high_confidence_score': self.confidence.high_confidence_score,
                'min_confirming_signals': self.confidence.min_confirming_signals,
                'require_regime_match': self.confidence.require_regime_match,
            },
            'timing': {
                'armed_timeout_sec': self.timing.armed_timeout_sec,
                'armed_min_duration_sec': self.timing.armed_min_duration_sec,
                'entry_window_sec': self.timing.entry_window_sec,
                'min_hold_sec': self.timing.min_hold_sec,
                'max_hold_sec': self.timing.max_hold_sec,
                'cooldown_sec': self.timing.cooldown_sec,
                'entry_grace_sec': self.timing.entry_grace_sec,
            },
            '_validated': list(self._validated),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ThresholdConfig':
        """Create from dictionary."""
        config = cls()

        if 'oi' in data:
            for key, value in data['oi'].items():
                if hasattr(config.oi, key):
                    setattr(config.oi, key, value)

        if 'funding' in data:
            for key, value in data['funding'].items():
                if hasattr(config.funding, key):
                    setattr(config.funding, key, value)

        if 'depth' in data:
            for key, value in data['depth'].items():
                if hasattr(config.depth, key):
                    setattr(config.depth, key, value)

        if 'confidence' in data:
            for key, value in data['confidence'].items():
                if hasattr(config.confidence, key):
                    setattr(config.confidence, key, value)

        if 'timing' in data:
            for key, value in data['timing'].items():
                if hasattr(config.timing, key):
                    setattr(config.timing, key, value)

        if '_validated' in data:
            config._validated = set(data['_validated'])

        return config

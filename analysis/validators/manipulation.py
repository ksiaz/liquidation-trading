"""
Manipulation Detection Validator.

Tests HLP25 Part 7 hypothesis:
"Manipulated cascades show OI pause/reversal mid-event."

Validation criteria:
- Organic cascades: OI drops monotonically
- Manipulated: OI drops, pauses/increases, drops again
- Multi-leg cascades (>2 distinct down-legs) suggest manipulation
"""

from typing import List, Any, Dict, Optional, Tuple

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


class ManipulationValidator:
    """Validates manipulation detection hypothesis from HLP25 Part 7.

    Tests whether OI patterns during cascades indicate manipulation.
    """

    def __init__(
        self,
        pause_threshold_pct: float = 0.5,  # 0.5% OI increase = pause
        max_organic_legs: int = 2,  # More legs suggests manipulation
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            pause_threshold_pct: OI change threshold to detect pause/reversal
            max_organic_legs: Maximum legs for organic cascade
            min_sample_size: Minimum cascades for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._pause_threshold = pause_threshold_pct
        self._max_organic_legs = max_organic_legs
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Manipulation Detection (HLP25 Part 7)"

    def validate(self, cascades: List[Any], db=None) -> ValidationResult:
        """Validate manipulation detection hypothesis.

        Analyzes OI patterns within cascades to detect manipulation signatures.
        Requires OI snapshot data to fully validate.

        Args:
            cascades: List of LabeledCascade objects
            db: Optional ResearchDatabase for OI data

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        if len(cascades) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(cascades),
                reason=f"Need {self._min_sample_size} cascades, have {len(cascades)}"
            )

        # Analyze wave structure as proxy for manipulation detection
        # Multi-wave cascades with pauses between may indicate manipulation
        manipulation_signatures = 0
        organic_signatures = 0
        inconclusive = 0

        multi_leg_cascades = []
        single_leg_cascades = []

        for cascade in cascades:
            wave_count = cascade.wave_count

            if wave_count > self._max_organic_legs:
                # Multiple distinct waves may indicate manipulation
                manipulation_signatures += 1
                multi_leg_cascades.append(cascade)
            elif wave_count <= self._max_organic_legs and wave_count > 0:
                organic_signatures += 1
                single_leg_cascades.append(cascade)
            else:
                inconclusive += 1

        total_classified = manipulation_signatures + organic_signatures

        if total_classified < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total_classified,
                reason=f"Only {total_classified} classifiable cascades"
            )

        # Analyze outcomes for multi-leg vs single-leg cascades
        multi_leg_outcomes = self._analyze_outcomes(multi_leg_cascades)
        single_leg_outcomes = self._analyze_outcomes(single_leg_cascades)

        details = {
            'multi_leg_cascades': manipulation_signatures,
            'single_leg_cascades': organic_signatures,
            'inconclusive': inconclusive,
            'max_organic_legs': self._max_organic_legs,
            'multi_leg_outcomes': multi_leg_outcomes,
            'single_leg_outcomes': single_leg_outcomes,
            'note': "Proxy validation using wave count - full validation requires OI timeseries"
        }

        # Hypothesis validated if multi-leg cascades show different outcome pattern
        # (e.g., more continuations = manipulation extending the cascade)
        multi_continuation_rate = (
            multi_leg_outcomes.get('CONTINUATION', 0) /
            max(sum(multi_leg_outcomes.values()), 1)
        )
        single_continuation_rate = (
            single_leg_outcomes.get('CONTINUATION', 0) /
            max(sum(single_leg_outcomes.values()), 1)
        )

        details['multi_leg_continuation_rate'] = round(multi_continuation_rate, 3)
        details['single_leg_continuation_rate'] = round(single_continuation_rate, 3)

        # If multi-leg cascades have higher continuation rate, suggests manipulation
        # extends the cascade artificially
        rate_difference = multi_continuation_rate - single_continuation_rate

        if rate_difference > 0.1:  # 10% higher continuation rate
            return ValidationResult.validated(
                name=self.name,
                total=total_classified,
                supporting=manipulation_signatures,
                threshold=float(self._max_organic_legs),
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total_classified,
                supporting=manipulation_signatures,
                details=details
            )

    def _analyze_outcomes(
        self,
        cascades: List[Any]
    ) -> Dict[str, int]:
        """Count outcomes for a set of cascades."""
        outcomes = {}
        for cascade in cascades:
            outcome = cascade.outcome or 'UNKNOWN'
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        return outcomes

    def detect_manipulation_pattern(
        self,
        oi_values: List[float],
        timestamps: List[int]
    ) -> Dict[str, Any]:
        """Detect manipulation pattern in OI timeseries.

        Pattern detection:
        - Count down-legs (distinct periods of OI decrease)
        - Detect mid-cascade OI increases (pause/accumulation)

        Args:
            oi_values: List of OI values during cascade
            timestamps: Corresponding timestamps

        Returns:
            Dict with pattern analysis
        """
        if len(oi_values) < 3:
            return {
                'leg_count': 0,
                'has_mid_pause': False,
                'pattern': 'INSUFFICIENT_DATA'
            }

        legs = self._count_down_legs(oi_values)
        has_pause = self._detect_mid_pause(oi_values)

        if legs > self._max_organic_legs or has_pause:
            pattern = 'MANIPULATION_SUSPECTED'
        elif legs <= self._max_organic_legs:
            pattern = 'ORGANIC'
        else:
            pattern = 'UNKNOWN'

        return {
            'leg_count': legs,
            'has_mid_pause': has_pause,
            'pattern': pattern,
            'oi_changes': self._calculate_oi_changes(oi_values)
        }

    def _count_down_legs(self, oi_values: List[float]) -> int:
        """Count distinct down-legs in OI series.

        A down-leg starts when OI begins decreasing after flat/increase.
        """
        if len(oi_values) < 2:
            return 0

        legs = 0
        in_down_leg = False

        for i in range(1, len(oi_values)):
            change = oi_values[i] - oi_values[i - 1]
            change_pct = (change / oi_values[i - 1]) * 100 if oi_values[i - 1] != 0 else 0

            if change_pct < -self._pause_threshold and not in_down_leg:
                # Start of new down-leg
                legs += 1
                in_down_leg = True
            elif change_pct >= self._pause_threshold:
                # End of down-leg (OI increased or flat)
                in_down_leg = False

        return legs

    def _detect_mid_pause(self, oi_values: List[float]) -> bool:
        """Detect OI pause or increase mid-cascade.

        Skips first and last readings, checks for OI increase in middle.
        """
        if len(oi_values) < 5:
            return False

        # Check middle portion (skip first 2 and last 2)
        for i in range(2, len(oi_values) - 2):
            change = oi_values[i + 1] - oi_values[i]
            change_pct = (change / oi_values[i]) * 100 if oi_values[i] != 0 else 0

            if change_pct > self._pause_threshold:
                # OI increased mid-cascade
                return True

        return False

    def _calculate_oi_changes(
        self,
        oi_values: List[float]
    ) -> List[float]:
        """Calculate percentage changes between OI readings."""
        if len(oi_values) < 2:
            return []

        changes = []
        for i in range(1, len(oi_values)):
            if oi_values[i - 1] != 0:
                change_pct = ((oi_values[i] - oi_values[i - 1]) / oi_values[i - 1]) * 100
                changes.append(round(change_pct, 3))
            else:
                changes.append(0.0)

        return changes

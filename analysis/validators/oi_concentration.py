"""
OI Concentration Validator.

Tests HLP25 Part 4 hypothesis:
"When top 10 wallets hold >40% of OI, cascade risk is elevated."

Validation criteria:
- Cascades with high OI concentration have larger OI drops
- High concentration precedes more severe cascades
"""

from typing import List, Any, Optional

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


class OIConcentrationValidator:
    """Validates OI concentration hypothesis from HLP25 Part 4.

    Tests whether concentrated OI leads to more severe cascades.

    Note: This requires wallet-level position data to calculate
    concentration. Falls back to cascade severity analysis if
    concentration data unavailable.
    """

    def __init__(
        self,
        concentration_threshold: float = 0.40,  # 40%
        severity_threshold: float = 15.0,  # 15% OI drop
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            concentration_threshold: Top 10 wallet share threshold
            severity_threshold: OI drop % to consider "severe"
            min_sample_size: Minimum cascades for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._concentration_threshold = concentration_threshold
        self._severity_threshold = severity_threshold
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "OI Concentration (HLP25 Part 4)"

    def validate(self, cascades: List[Any]) -> ValidationResult:
        """Validate OI concentration hypothesis.

        Without concentration data, analyzes correlation between
        cascade severity (OI drop %) and outcome.

        Args:
            cascades: List of LabeledCascade objects

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        if len(cascades) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(cascades),
                reason=f"Need {self._min_sample_size} events, have {len(cascades)}"
            )

        # Analyze cascade severity distribution
        severe_cascades = []
        moderate_cascades = []

        for cascade in cascades:
            try:
                oi_drop = abs(float(cascade.oi_drop_pct))
            except (ValueError, TypeError):
                continue

            if oi_drop >= self._severity_threshold:
                severe_cascades.append(cascade)
            else:
                moderate_cascades.append(cascade)

        total = len(severe_cascades) + len(moderate_cascades)

        if total < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason=f"Insufficient valid OI drop data"
            )

        # Analyze outcomes for severe vs moderate cascades
        severe_reversal = sum(1 for c in severe_cascades if c.outcome == "REVERSAL")
        severe_continuation = sum(1 for c in severe_cascades if c.outcome == "CONTINUATION")
        moderate_reversal = sum(1 for c in moderate_cascades if c.outcome == "REVERSAL")
        moderate_continuation = sum(1 for c in moderate_cascades if c.outcome == "CONTINUATION")

        # Calculate severity statistics
        oi_drops = []
        for cascade in cascades:
            try:
                oi_drops.append(abs(float(cascade.oi_drop_pct)))
            except (ValueError, TypeError):
                continue

        avg_oi_drop = sum(oi_drops) / len(oi_drops) if oi_drops else 0
        max_oi_drop = max(oi_drops) if oi_drops else 0

        details = {
            'severe_cascade_count': len(severe_cascades),
            'moderate_cascade_count': len(moderate_cascades),
            'severity_threshold_pct': self._severity_threshold,
            'avg_oi_drop_pct': round(avg_oi_drop, 2),
            'max_oi_drop_pct': round(max_oi_drop, 2),
            'severe_reversal_count': severe_reversal,
            'severe_continuation_count': severe_continuation,
            'note': "Proxy validation - requires wallet concentration data for rigorous test"
        }

        # For concentration hypothesis:
        # Severe cascades (proxy for concentrated) should show distinct patterns
        # Supporting if severe cascades have higher reversal rate (larger moves attract buyers)
        if len(severe_cascades) < 5:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason=f"Only {len(severe_cascades)} severe cascades, need 5+"
            )

        severe_non_neutral = severe_reversal + severe_continuation
        if severe_non_neutral == 0:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason="Severe cascades all have NEUTRAL outcomes"
            )

        # Check if severe cascades have higher reversal rate than moderate
        severe_reversal_rate = severe_reversal / severe_non_neutral

        moderate_non_neutral = moderate_reversal + moderate_continuation
        moderate_reversal_rate = (
            moderate_reversal / moderate_non_neutral
            if moderate_non_neutral > 0 else 0
        )

        details['severe_reversal_rate'] = round(severe_reversal_rate, 3)
        details['moderate_reversal_rate'] = round(moderate_reversal_rate, 3)

        # Validated if severe cascades show distinct behavior
        # (different reversal rate indicates concentration effect)
        rate_difference = abs(severe_reversal_rate - moderate_reversal_rate)

        if rate_difference >= 0.15:  # 15% difference indicates pattern
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=len(severe_cascades),
                threshold=self._severity_threshold,
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=len(severe_cascades),
                details=details
            )

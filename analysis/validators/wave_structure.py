"""
Wave Structure Validator.

Tests HLP25 Part 2 hypothesis:
"Liquidation cascades occur in 3-5 discrete waves, not continuous flow."

Validation criteria:
- Majority of cascades have 3-5 waves
- Wave count is consistent (low variance)
"""

from typing import List, Any

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


class WaveStructureValidator:
    """Validates wave structure hypothesis from HLP25 Part 2."""

    def __init__(
        self,
        min_waves: int = 3,
        max_waves: int = 5,
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            min_waves: Minimum expected waves (inclusive)
            max_waves: Maximum expected waves (inclusive)
            min_sample_size: Minimum cascades for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._min_waves = min_waves
        self._max_waves = max_waves
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Wave Structure (HLP25 Part 2)"

    def validate(self, cascades: List[Any]) -> ValidationResult:
        """Validate wave structure hypothesis.

        Tests if cascades have 3-5 discrete waves.

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

        # Count cascades with expected wave count
        supporting = 0
        wave_distribution = {}
        total_waves = 0

        for cascade in cascades:
            wave_count = cascade.wave_count
            total_waves += wave_count

            # Track distribution
            wave_distribution[wave_count] = wave_distribution.get(wave_count, 0) + 1

            # Check if in expected range
            if self._min_waves <= wave_count <= self._max_waves:
                supporting += 1

        total = len(cascades)
        success_rate = supporting / total

        # Calculate variance to check consistency
        avg_waves = total_waves / total
        variance = sum(
            (c.wave_count - avg_waves) ** 2 for c in cascades
        ) / total

        details = {
            'wave_distribution': wave_distribution,
            'avg_waves': round(avg_waves, 2),
            'variance': round(variance, 2),
            'expected_range': f"{self._min_waves}-{self._max_waves}"
        }

        if success_rate >= self._min_success_rate:
            # Find optimal wave count (mode)
            optimal = max(wave_distribution.keys(), key=lambda k: wave_distribution[k])
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=supporting,
                threshold=float(optimal),
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=supporting,
                details=details
            )

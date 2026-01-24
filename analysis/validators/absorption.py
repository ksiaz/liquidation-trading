"""
Absorption Validator.

Tests HLP25 Part 3 hypothesis:
"Absorption (bid depth increasing while price decreasing) predicts exhaustion."

Validation criteria:
- Absorption events detected during cascades
- Absorption followed by reversal outcome more often than continuation
"""

from typing import List, Any, Optional

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


class AbsorptionValidator:
    """Validates absorption detection hypothesis from HLP25 Part 3.

    Note: This validator requires orderbook depth data which may not
    be available in all HLP24 datasets. Falls back to outcome-based
    analysis if depth data unavailable.
    """

    def __init__(
        self,
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            min_sample_size: Minimum cascades for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Absorption Detection (HLP25 Part 3)"

    def validate(self, cascades: List[Any]) -> ValidationResult:
        """Validate absorption hypothesis.

        Since we may not have orderbook depth data, this validator
        uses outcome data as a proxy:
        - REVERSAL outcome suggests absorption occurred
        - CONTINUATION outcome suggests no absorption

        More rigorous validation requires orderbook depth snapshots.

        Args:
            cascades: List of LabeledCascade objects

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        # Filter cascades with known outcomes
        cascades_with_outcome = [c for c in cascades if c.outcome is not None]

        if len(cascades_with_outcome) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(cascades_with_outcome),
                reason=f"Need {self._min_sample_size} events with outcomes, have {len(cascades_with_outcome)}"
            )

        # Analyze outcomes
        reversal_count = 0
        continuation_count = 0
        neutral_count = 0

        for cascade in cascades_with_outcome:
            if cascade.outcome == "REVERSAL":
                reversal_count += 1
            elif cascade.outcome == "CONTINUATION":
                continuation_count += 1
            else:
                neutral_count += 1

        total = len(cascades_with_outcome)

        # For absorption hypothesis to hold:
        # Reversals should be more common than continuations
        # (indicating buyers absorbed the selling)
        non_neutral = reversal_count + continuation_count

        if non_neutral == 0:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason="All outcomes are NEUTRAL, cannot validate"
            )

        reversal_rate = reversal_count / non_neutral

        details = {
            'reversal_count': reversal_count,
            'continuation_count': continuation_count,
            'neutral_count': neutral_count,
            'reversal_rate': round(reversal_rate, 3),
            'note': "Proxy validation - requires orderbook depth for rigorous test"
        }

        # Hypothesis validated if reversals > continuations significantly
        if reversal_rate >= self._min_success_rate:
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=reversal_count,
                threshold=round(reversal_rate, 3),
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=reversal_count,
                details=details
            )

"""
Base Validator Protocol.

Defines the interface for HLP25 hypothesis validators.
All validators must implement the validate method.
"""

from dataclasses import dataclass
from typing import List, Optional, Protocol, Any
from abc import abstractmethod


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a hypothesis.

    Immutable record of validation outcome.
    """
    hypothesis_name: str
    total_events: int
    supporting_events: int
    success_rate: float  # supporting_events / total_events
    calibrated_threshold: Optional[float]  # Optimal threshold if discovered
    status: str  # VALIDATED, FAILED, INSUFFICIENT_DATA
    details: Optional[dict]  # Additional hypothesis-specific details

    @classmethod
    def validated(
        cls,
        name: str,
        total: int,
        supporting: int,
        threshold: Optional[float] = None,
        details: Optional[dict] = None
    ) -> 'ValidationResult':
        """Create a VALIDATED result."""
        return cls(
            hypothesis_name=name,
            total_events=total,
            supporting_events=supporting,
            success_rate=supporting / total if total > 0 else 0.0,
            calibrated_threshold=threshold,
            status="VALIDATED",
            details=details
        )

    @classmethod
    def failed(
        cls,
        name: str,
        total: int,
        supporting: int,
        details: Optional[dict] = None
    ) -> 'ValidationResult':
        """Create a FAILED result."""
        return cls(
            hypothesis_name=name,
            total_events=total,
            supporting_events=supporting,
            success_rate=supporting / total if total > 0 else 0.0,
            calibrated_threshold=None,
            status="FAILED",
            details=details
        )

    @classmethod
    def insufficient_data(
        cls,
        name: str,
        total: int,
        reason: str
    ) -> 'ValidationResult':
        """Create an INSUFFICIENT_DATA result."""
        return cls(
            hypothesis_name=name,
            total_events=total,
            supporting_events=0,
            success_rate=0.0,
            calibrated_threshold=None,
            status="INSUFFICIENT_DATA",
            details={'reason': reason}
        )


class HypothesisValidator(Protocol):
    """Protocol for hypothesis validators.

    Each validator tests a specific HLP25 hypothesis against cascade data.
    """

    @property
    def name(self) -> str:
        """Return the hypothesis name."""
        ...

    @abstractmethod
    def validate(self, cascades: List[Any]) -> ValidationResult:
        """Validate hypothesis against labeled cascades.

        Args:
            cascades: List of LabeledCascade objects

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        ...


# Validation thresholds
MIN_SAMPLE_SIZE = 30  # Minimum events for statistical significance
MIN_SUCCESS_RATE = 0.60  # 60% to be considered validated

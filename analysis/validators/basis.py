"""
Spot-Perp Basis Validator.

Tests HLP25 Part 8 hypothesis:
"Perp trading at significant discount to spot indicates liquidation pressure."

Validation criteria:
- Negative basis (perp < spot) precedes or coincides with cascades
- Extreme negative basis (>0.5% discount) correlates with larger cascades
"""

from typing import List, Any, Dict, Optional
from dataclasses import dataclass

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


@dataclass(frozen=True)
class BasisSnapshot:
    """Record of spot-perp basis at a point in time."""
    timestamp: int
    coin: str
    perp_price: float
    spot_price: float
    basis: float  # (perp - spot) / spot
    basis_category: str  # LIQUIDATION_PRESSURE, MILD_SELLING, NEUTRAL, MILD_BUYING, FOMO_PREMIUM


class BasisValidator:
    """Validates spot-perp basis hypothesis from HLP25 Part 8.

    Tests whether negative basis predicts or coincides with liquidation cascades.
    Requires spot price data to fully validate.
    """

    # Basis thresholds (from HLP25)
    LIQUIDATION_PRESSURE = -0.005  # >0.5% discount
    MILD_SELLING = -0.002  # >0.2% discount
    MILD_BUYING = 0.002  # >0.2% premium
    FOMO_PREMIUM = 0.005  # >0.5% premium

    def __init__(
        self,
        liquidation_threshold: float = -0.005,
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            liquidation_threshold: Basis below this indicates liquidation pressure
            min_sample_size: Minimum cascades for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._liq_threshold = liquidation_threshold
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Spot-Perp Basis (HLP25 Part 8)"

    def validate(
        self,
        cascades: List[Any],
        basis_data: Optional[List[Dict]] = None
    ) -> ValidationResult:
        """Validate spot-perp basis hypothesis.

        Requires basis data (perp and spot prices) to fully validate.
        Falls back to proxy validation using cascade severity if no basis data.

        Args:
            cascades: List of LabeledCascade objects
            basis_data: Optional list of basis snapshots with timestamp, coin,
                       perp_price, spot_price

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        if basis_data is None:
            return self._validate_proxy(cascades)
        else:
            return self._validate_with_basis(cascades, basis_data)

    def _validate_proxy(self, cascades: List[Any]) -> ValidationResult:
        """Proxy validation using cascade characteristics.

        Without spot price data, we analyze if larger OI drops
        (proxy for liquidation pressure) correlate with worse outcomes.
        """
        if len(cascades) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(cascades),
                reason=f"Need {self._min_sample_size} cascades, have {len(cascades)}"
            )

        # Analyze correlation between cascade severity and outcome
        severe_cascades = []
        mild_cascades = []

        for cascade in cascades:
            try:
                oi_drop = abs(float(cascade.oi_drop_pct))
            except (ValueError, TypeError):
                continue

            if oi_drop >= 15.0:  # Severe: >15% OI drop
                severe_cascades.append(cascade)
            else:
                mild_cascades.append(cascade)

        total = len(severe_cascades) + len(mild_cascades)

        if total < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason="Insufficient valid OI drop data"
            )

        # Count continuations (proxy for sustained liquidation pressure)
        severe_continuation = sum(
            1 for c in severe_cascades if c.outcome == "CONTINUATION"
        )
        mild_continuation = sum(
            1 for c in mild_cascades if c.outcome == "CONTINUATION"
        )

        severe_rate = (
            severe_continuation / len(severe_cascades)
            if severe_cascades else 0
        )
        mild_rate = (
            mild_continuation / len(mild_cascades)
            if mild_cascades else 0
        )

        details = {
            'severe_cascades': len(severe_cascades),
            'mild_cascades': len(mild_cascades),
            'severe_continuation_rate': round(severe_rate, 3),
            'mild_continuation_rate': round(mild_rate, 3),
            'note': "Proxy validation - requires spot price data for full test"
        }

        # Hypothesis: severe cascades (more liquidation pressure) should have
        # higher continuation rate (selling continues)
        if severe_rate > mild_rate + 0.1:  # 10% higher continuation
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=len(severe_cascades),
                threshold=self._liq_threshold,
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=len(severe_cascades),
                details=details
            )

    def _validate_with_basis(
        self,
        cascades: List[Any],
        basis_data: List[Dict]
    ) -> ValidationResult:
        """Validate using actual basis data.

        Checks if negative basis precedes cascades.
        """
        if len(basis_data) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(basis_data),
                reason=f"Need {self._min_sample_size} basis snapshots"
            )

        # Build basis lookup by (coin, timestamp rounded to minute)
        basis_lookup = {}
        for snap in basis_data:
            coin = snap.get('coin')
            ts = snap.get('timestamp', 0)
            perp = float(snap.get('perp_price', 0))
            spot = float(snap.get('spot_price', 0))

            if spot > 0:
                basis = (perp - spot) / spot
                key = (coin, ts // 60_000_000_000)  # Round to minute
                basis_lookup[key] = basis

        # Check basis before each cascade
        cascades_with_liq_pressure = 0
        cascades_with_neutral = 0

        for cascade in cascades:
            coin = cascade.coin
            ts = cascade.start_ts
            key = (coin, ts // 60_000_000_000)

            # Check basis in preceding 5 minutes
            found_liq_pressure = False
            for offset in range(5):
                check_key = (coin, (ts // 60_000_000_000) - offset)
                basis = basis_lookup.get(check_key)
                if basis is not None and basis < self._liq_threshold:
                    found_liq_pressure = True
                    break

            if found_liq_pressure:
                cascades_with_liq_pressure += 1
            else:
                cascades_with_neutral += 1

        total = cascades_with_liq_pressure + cascades_with_neutral

        if total < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=total,
                reason="Insufficient cascade-basis matches"
            )

        success_rate = cascades_with_liq_pressure / total

        details = {
            'cascades_with_liq_pressure': cascades_with_liq_pressure,
            'cascades_with_neutral': cascades_with_neutral,
            'success_rate': round(success_rate, 3),
            'threshold': self._liq_threshold
        }

        if success_rate >= self._min_success_rate:
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=cascades_with_liq_pressure,
                threshold=self._liq_threshold,
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=cascades_with_liq_pressure,
                details=details
            )

    def calculate_basis(
        self,
        perp_price: float,
        spot_price: float
    ) -> float:
        """Calculate basis from perp and spot prices.

        Args:
            perp_price: Perpetual contract price
            spot_price: Spot market price

        Returns:
            Basis as decimal (e.g., -0.005 for 0.5% discount)
        """
        if spot_price == 0:
            return 0.0
        return (perp_price - spot_price) / spot_price

    def categorize_basis(self, basis: float) -> str:
        """Categorize basis into market state.

        Args:
            basis: Basis value (decimal)

        Returns:
            Category string
        """
        if basis < self.LIQUIDATION_PRESSURE:
            return "LIQUIDATION_PRESSURE"
        elif basis < self.MILD_SELLING:
            return "MILD_SELLING"
        elif basis > self.FOMO_PREMIUM:
            return "FOMO_PREMIUM"
        elif basis > self.MILD_BUYING:
            return "MILD_BUYING"
        else:
            return "NEUTRAL"

    def create_snapshot(
        self,
        timestamp: int,
        coin: str,
        perp_price: float,
        spot_price: float
    ) -> BasisSnapshot:
        """Create a basis snapshot.

        Args:
            timestamp: Timestamp in nanoseconds
            coin: Coin symbol
            perp_price: Perpetual contract price
            spot_price: Spot market price

        Returns:
            BasisSnapshot with calculated basis and category
        """
        basis = self.calculate_basis(perp_price, spot_price)
        category = self.categorize_basis(basis)

        return BasisSnapshot(
            timestamp=timestamp,
            coin=coin,
            perp_price=perp_price,
            spot_price=spot_price,
            basis=basis,
            basis_category=category
        )

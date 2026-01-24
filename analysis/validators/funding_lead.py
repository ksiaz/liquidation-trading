"""
Cross-Exchange Funding Lead Validator.

Tests HLP25 Part 1 hypothesis:
"Binance funding leads Hyperliquid by 5-30 minutes."

Validation criteria:
- Binance funding changes predict HL funding direction
- Lead time is consistent and exploitable
- Divergence reliably closes within expected window
"""

from typing import List, Any, Dict, Optional, Tuple
from dataclasses import dataclass

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


@dataclass(frozen=True)
class FundingDivergence:
    """Record of funding divergence between exchanges."""
    timestamp: int
    coin: str
    binance_funding: float
    hl_funding: float
    divergence: float
    expected_direction: str  # UP or DOWN


class FundingLeadValidator:
    """Validates cross-exchange funding lead hypothesis from HLP25 Part 1.

    Tests whether Binance funding leads Hyperliquid funding.
    Requires Binance funding data collection to fully validate.
    """

    def __init__(
        self,
        divergence_threshold: float = 0.0005,  # 0.05% divergence
        min_lead_time_min: int = 5,
        max_lead_time_min: int = 30,
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            divergence_threshold: Minimum divergence to consider significant
            min_lead_time_min: Minimum expected lead time (minutes)
            max_lead_time_min: Maximum expected lead time (minutes)
            min_sample_size: Minimum divergence events for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._divergence_threshold = divergence_threshold
        self._min_lead_min = min_lead_time_min
        self._max_lead_min = max_lead_time_min
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Cross-Exchange Funding Lead (HLP25 Part 1)"

    def validate(
        self,
        cascades: List[Any],
        binance_funding: Optional[List[Dict]] = None,
        hl_funding: Optional[List[Dict]] = None
    ) -> ValidationResult:
        """Validate cross-exchange funding lead hypothesis.

        Requires both Binance and Hyperliquid funding rate data.
        Falls back to insufficient data if external data not provided.

        Args:
            cascades: List of LabeledCascade objects (for context)
            binance_funding: Optional list of Binance funding snapshots
            hl_funding: Optional list of Hyperliquid funding snapshots

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        if binance_funding is None or hl_funding is None:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=0,
                reason="Requires Binance funding data - not yet collected"
            )

        if len(binance_funding) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(binance_funding),
                reason=f"Need {self._min_sample_size} Binance funding snapshots"
            )

        # Find divergence events
        divergences = self._find_divergences(binance_funding, hl_funding)

        if len(divergences) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(divergences),
                reason=f"Only {len(divergences)} significant divergences found"
            )

        # Test if divergences predict HL funding direction
        correct_predictions = 0
        lead_times = []

        for div in divergences:
            result = self._check_prediction(div, hl_funding)
            if result['correct']:
                correct_predictions += 1
                if result['lead_time_min'] is not None:
                    lead_times.append(result['lead_time_min'])

        total = len(divergences)
        success_rate = correct_predictions / total

        avg_lead_time = sum(lead_times) / len(lead_times) if lead_times else 0

        details = {
            'total_divergences': total,
            'correct_predictions': correct_predictions,
            'success_rate': round(success_rate, 3),
            'avg_lead_time_min': round(avg_lead_time, 1),
            'divergence_threshold': self._divergence_threshold,
            'expected_lead_range_min': f"{self._min_lead_min}-{self._max_lead_min}"
        }

        if success_rate >= self._min_success_rate:
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=correct_predictions,
                threshold=round(avg_lead_time, 1),
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=correct_predictions,
                details=details
            )

    def _find_divergences(
        self,
        binance_funding: List[Dict],
        hl_funding: List[Dict]
    ) -> List[FundingDivergence]:
        """Find significant funding divergences between exchanges.

        Args:
            binance_funding: Binance funding snapshots with timestamp, coin, rate
            hl_funding: Hyperliquid funding snapshots

        Returns:
            List of significant divergence events
        """
        divergences = []

        # Build HL funding lookup by (coin, timestamp)
        hl_lookup = {}
        for snap in hl_funding:
            key = (snap.get('coin'), snap.get('timestamp', 0) // 60_000_000_000)  # Round to minute
            hl_lookup[key] = snap.get('funding_rate', 0)

        for b_snap in binance_funding:
            coin = b_snap.get('coin')
            ts = b_snap.get('timestamp', 0)
            b_rate = float(b_snap.get('funding_rate', 0))

            # Find matching HL funding
            key = (coin, ts // 60_000_000_000)
            hl_rate = float(hl_lookup.get(key, 0))

            divergence = b_rate - hl_rate

            if abs(divergence) >= self._divergence_threshold:
                divergences.append(FundingDivergence(
                    timestamp=ts,
                    coin=coin,
                    binance_funding=b_rate,
                    hl_funding=hl_rate,
                    divergence=divergence,
                    expected_direction='UP' if divergence > 0 else 'DOWN'
                ))

        return divergences

    def _check_prediction(
        self,
        divergence: FundingDivergence,
        hl_funding: List[Dict]
    ) -> Dict[str, Any]:
        """Check if divergence correctly predicted HL funding direction.

        Args:
            divergence: Divergence event to check
            hl_funding: Hyperliquid funding history

        Returns:
            Dict with correct (bool) and lead_time_min (if found)
        """
        # Find HL funding changes after divergence
        window_start = divergence.timestamp
        window_end = window_start + self._max_lead_min * 60 * 1_000_000_000

        for snap in hl_funding:
            ts = snap.get('timestamp', 0)
            if window_start < ts <= window_end:
                coin = snap.get('coin')
                if coin != divergence.coin:
                    continue

                new_rate = float(snap.get('funding_rate', 0))
                old_rate = divergence.hl_funding

                # Check direction
                if divergence.expected_direction == 'UP':
                    correct = new_rate > old_rate
                else:
                    correct = new_rate < old_rate

                if correct:
                    lead_time = (ts - divergence.timestamp) / 60_000_000_000
                    return {'correct': True, 'lead_time_min': lead_time}

        return {'correct': False, 'lead_time_min': None}

    def check_current_divergence(
        self,
        binance_rate: float,
        hl_rate: float,
        coin: str
    ) -> Optional[Dict[str, Any]]:
        """Check for current funding divergence.

        Utility method for live monitoring.

        Args:
            binance_rate: Current Binance funding rate
            hl_rate: Current Hyperliquid funding rate
            coin: Coin symbol

        Returns:
            Dict with divergence info if significant, None otherwise
        """
        divergence = binance_rate - hl_rate

        if abs(divergence) >= self._divergence_threshold:
            return {
                'coin': coin,
                'binance_rate': binance_rate,
                'hl_rate': hl_rate,
                'divergence': divergence,
                'expected_hl_direction': 'UP' if divergence > 0 else 'DOWN',
                'window_minutes': f"{self._min_lead_min}-{self._max_lead_min}"
            }

        return None

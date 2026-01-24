"""
Funding Settlement Validator.

Tests HLP25 Part 5 hypothesis:
"15-30 minutes before funding settlement, positions adjust creating directional pressure."

Validation criteria:
- Price movement before settlement correlates with funding direction
- Extreme funding (>0.05%) creates measurable pre-settlement bias
"""

from typing import List, Any, Dict, Optional
from datetime import datetime, timezone

from .base import HypothesisValidator, ValidationResult, MIN_SAMPLE_SIZE, MIN_SUCCESS_RATE


# Hyperliquid funding settlement times (UTC)
SETTLEMENT_HOURS = [0, 8, 16]  # 00:00, 08:00, 16:00 UTC


class FundingSettlementValidator:
    """Validates funding settlement timing hypothesis from HLP25 Part 5.

    Tests whether extreme funding creates predictable pre-settlement price movement.
    """

    def __init__(
        self,
        pre_settlement_window_min: int = 30,  # Minutes before settlement
        extreme_funding_threshold: float = 0.0005,  # 0.05%
        price_move_threshold: float = 0.001,  # 0.1% price move
        min_sample_size: int = MIN_SAMPLE_SIZE,
        min_success_rate: float = MIN_SUCCESS_RATE
    ):
        """Initialize validator.

        Args:
            pre_settlement_window_min: Window before settlement to analyze
            extreme_funding_threshold: Funding rate to consider "extreme"
            price_move_threshold: Minimum price move to count as directional
            min_sample_size: Minimum settlement events for valid test
            min_success_rate: Minimum rate to validate hypothesis
        """
        self._window_min = pre_settlement_window_min
        self._extreme_threshold = extreme_funding_threshold
        self._price_threshold = price_move_threshold
        self._min_sample_size = min_sample_size
        self._min_success_rate = min_success_rate

    @property
    def name(self) -> str:
        """Return hypothesis name."""
        return "Funding Settlement Timing (HLP25 Part 5)"

    def validate(self, cascades: List[Any], db=None) -> ValidationResult:
        """Validate funding settlement hypothesis.

        Note: This validator requires funding snapshot data, not just cascades.
        If db is provided, queries funding data directly.

        Without db, falls back to analyzing cascades that occurred near
        settlement times.

        Args:
            cascades: List of LabeledCascade objects
            db: Optional ResearchDatabase for funding data

        Returns:
            ValidationResult indicating if hypothesis holds
        """
        if db is not None:
            return self._validate_with_funding_data(db)
        else:
            return self._validate_from_cascades(cascades)

    def _validate_from_cascades(self, cascades: List[Any]) -> ValidationResult:
        """Validate using cascade timing relative to settlements.

        Proxy validation: Check if cascades cluster near settlement times.
        """
        if len(cascades) < self._min_sample_size:
            return ValidationResult.insufficient_data(
                name=self.name,
                total=len(cascades),
                reason=f"Need {self._min_sample_size} cascades, have {len(cascades)}"
            )

        near_settlement = 0
        far_from_settlement = 0
        window_ns = self._window_min * 60 * 1_000_000_000

        for cascade in cascades:
            ts_ns = cascade.start_ts
            minutes_to_settlement = self._minutes_to_nearest_settlement(ts_ns)

            if minutes_to_settlement <= self._window_min:
                near_settlement += 1
            else:
                far_from_settlement += 1

        total = near_settlement + far_from_settlement

        # Calculate expected rate if cascades were random (uniform distribution)
        # 30 min window out of 480 min (8 hours) = 6.25% per window, 3 windows = 18.75%
        expected_rate = (self._window_min / 480) * 3
        actual_rate = near_settlement / total if total > 0 else 0

        details = {
            'cascades_near_settlement': near_settlement,
            'cascades_far_from_settlement': far_from_settlement,
            'actual_rate': round(actual_rate, 3),
            'expected_random_rate': round(expected_rate, 3),
            'window_minutes': self._window_min,
            'note': "Proxy validation - tests if cascades cluster near settlements"
        }

        # Hypothesis validated if cascades cluster near settlements
        # more than random expectation
        if actual_rate > expected_rate * 1.5:  # 50% more than random
            return ValidationResult.validated(
                name=self.name,
                total=total,
                supporting=near_settlement,
                threshold=self._window_min,
                details=details
            )
        else:
            return ValidationResult.failed(
                name=self.name,
                total=total,
                supporting=near_settlement,
                details=details
            )

    def _validate_with_funding_data(self, db) -> ValidationResult:
        """Validate using actual funding rate data.

        Checks if extreme funding before settlement predicts price direction.
        """
        # Query funding snapshots
        # This would need funding data with timestamps and rates
        # For now, return insufficient data until funding collection is active

        return ValidationResult.insufficient_data(
            name=self.name,
            total=0,
            reason="Funding snapshot data required - use HLP24 collector"
        )

    def _minutes_to_nearest_settlement(self, ts_ns: int) -> int:
        """Calculate minutes to nearest funding settlement.

        Args:
            ts_ns: Timestamp in nanoseconds

        Returns:
            Minutes to nearest settlement (0-240 range)
        """
        ts_sec = ts_ns / 1_000_000_000
        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)

        current_minutes = dt.hour * 60 + dt.minute

        # Find distance to each settlement
        min_distance = float('inf')
        for hour in SETTLEMENT_HOURS:
            settlement_minutes = hour * 60

            # Distance forward
            forward = (settlement_minutes - current_minutes) % (24 * 60)
            # Distance backward
            backward = (current_minutes - settlement_minutes) % (24 * 60)

            distance = min(forward, backward)
            min_distance = min(min_distance, distance)

        return int(min_distance)

    def get_settlement_windows(
        self,
        start_ts: int,
        end_ts: int
    ) -> List[Dict[str, int]]:
        """Get all settlement windows in time range.

        Args:
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            List of dicts with window_start, settlement_ts, window_end
        """
        from datetime import timedelta

        windows = []
        window_ns = self._window_min * 60 * 1_000_000_000

        # Convert to datetime
        start_dt = datetime.fromtimestamp(start_ts / 1e9, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ts / 1e9, tz=timezone.utc)

        # Start from beginning of start day
        current = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        while current <= end_dt:
            for hour in SETTLEMENT_HOURS:
                settlement_dt = current.replace(hour=hour)
                settlement_ts = int(settlement_dt.timestamp() * 1e9)

                if start_ts <= settlement_ts <= end_ts:
                    windows.append({
                        'window_start': settlement_ts - window_ns,
                        'settlement_ts': settlement_ts,
                        'window_end': settlement_ts
                    })

            current = current + timedelta(days=1)

        return windows

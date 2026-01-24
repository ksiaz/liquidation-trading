"""
Cascade Event Labeler.

Mechanically labels cascade events from raw HLP24 data.
No interpretation - pure observable facts.

Cascade Definition:
- OI dropped >10% in <60 seconds
- At least 2 liquidation events detected in the window

Constitutional: Factual labeling only.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from decimal import Decimal


@dataclass(frozen=True)
class WaveLabel:
    """Labeled wave within a cascade.

    Immutable record of wave structure.
    """
    wave_num: int
    start_ts: int
    end_ts: int
    liquidation_count: int
    oi_drop_pct: Optional[str]  # Raw string, no conversion


@dataclass(frozen=True)
class LabeledCascade:
    """Labeled cascade event.

    Immutable record of mechanically-detected cascade.
    All numeric fields stored as strings to preserve precision.
    """
    cascade_id: int
    coin: str
    start_ts: int
    end_ts: int
    oi_drop_pct: str
    liquidation_count: int
    price_at_start: str
    price_at_end: str
    price_5min_after: Optional[str]
    wave_count: int
    waves: tuple  # Tuple of WaveLabel for immutability
    outcome: Optional[str]  # REVERSAL, CONTINUATION, NEUTRAL


class CascadeLabeler:
    """Labels cascade events from raw HLP24 data.

    Mechanical detection based on observable criteria:
    - OI change exceeds threshold
    - Liquidation count exceeds minimum
    - Events within time window

    No interpretation of market conditions.
    """

    # Detection thresholds (configurable)
    DEFAULT_OI_DROP_PCT = 10.0  # 10% OI drop
    DEFAULT_TIME_WINDOW_NS = 60_000_000_000  # 60 seconds in nanoseconds
    DEFAULT_MIN_LIQUIDATIONS = 2
    DEFAULT_WAVE_GAP_NS = 30_000_000_000  # 30 second gap between waves
    DEFAULT_OUTCOME_WINDOW_NS = 300_000_000_000  # 5 minutes for outcome

    def __init__(
        self,
        db,
        oi_drop_threshold: float = DEFAULT_OI_DROP_PCT,
        time_window_ns: int = DEFAULT_TIME_WINDOW_NS,
        min_liquidations: int = DEFAULT_MIN_LIQUIDATIONS,
        wave_gap_ns: int = DEFAULT_WAVE_GAP_NS,
        outcome_window_ns: int = DEFAULT_OUTCOME_WINDOW_NS
    ):
        """Initialize labeler with database connection.

        Args:
            db: ResearchDatabase instance
            oi_drop_threshold: Minimum OI drop percentage to qualify as cascade
            time_window_ns: Time window in nanoseconds for OI drop
            min_liquidations: Minimum liquidation count for cascade
            wave_gap_ns: Gap between liquidations to define new wave
            outcome_window_ns: Time after cascade to measure outcome
        """
        self._db = db
        self._oi_drop_threshold = oi_drop_threshold
        self._time_window_ns = time_window_ns
        self._min_liquidations = min_liquidations
        self._wave_gap_ns = wave_gap_ns
        self._outcome_window_ns = outcome_window_ns

    def label_all(
        self,
        start_ts: int,
        end_ts: int,
        coins: Optional[List[str]] = None
    ) -> List[LabeledCascade]:
        """Label all cascade events in time range.

        Args:
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            coins: Optional list of coins to analyze (None = all coins)

        Returns:
            List of labeled cascade events
        """
        # Get unique coins from liquidation data if not specified
        if coins is None:
            coins = self._get_coins_with_liquidations(start_ts, end_ts)

        all_cascades = []

        for coin in coins:
            cascades = self._label_coin_cascades(coin, start_ts, end_ts)
            all_cascades.extend(cascades)

        # Sort by start timestamp
        all_cascades.sort(key=lambda c: c.start_ts)

        return all_cascades

    def _get_coins_with_liquidations(self, start_ts: int, end_ts: int) -> List[str]:
        """Get list of coins with liquidation events in range."""
        cursor = self._db.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT coin FROM hl_liquidation_events_raw
            WHERE detected_ts >= ? AND detected_ts <= ?
        """, (start_ts, end_ts))

        return [row[0] for row in cursor.fetchall()]

    def _label_coin_cascades(
        self,
        coin: str,
        start_ts: int,
        end_ts: int
    ) -> List[LabeledCascade]:
        """Label cascade events for a single coin.

        Algorithm:
        1. Get all OI snapshots for the coin
        2. Find periods where OI dropped >threshold in <time_window
        3. For each drop, count liquidations in the window
        4. If meets criteria, label as cascade
        5. Detect wave structure within cascade
        6. Calculate outcome from price after cascade
        """
        # Get OI snapshots
        oi_snapshots = self._db.get_oi_history(coin, start_ts, end_ts)
        if len(oi_snapshots) < 2:
            return []

        cascades = []
        processed_timestamps = set()

        for i in range(len(oi_snapshots) - 1):
            snap1 = oi_snapshots[i]
            ts1 = snap1['snapshot_ts']

            # Skip if already part of a cascade
            if ts1 in processed_timestamps:
                continue

            oi1 = self._parse_oi(snap1['open_interest'])
            if oi1 is None or oi1 == 0:
                continue

            # Look forward for OI drops
            for j in range(i + 1, len(oi_snapshots)):
                snap2 = oi_snapshots[j]
                ts2 = snap2['snapshot_ts']

                # Check time window
                if ts2 - ts1 > self._time_window_ns:
                    break

                oi2 = self._parse_oi(snap2['open_interest'])
                if oi2 is None:
                    continue

                # Calculate OI drop percentage
                oi_drop_pct = ((oi1 - oi2) / oi1) * 100

                if oi_drop_pct >= self._oi_drop_threshold:
                    # Count liquidations in this window
                    liquidations = self._get_liquidations_in_range(coin, ts1, ts2)

                    if len(liquidations) >= self._min_liquidations:
                        # This is a cascade event
                        cascade = self._create_cascade_label(
                            coin, ts1, ts2, oi_drop_pct, liquidations
                        )
                        if cascade is not None:
                            cascades.append(cascade)
                            # Mark all timestamps in range as processed
                            for k in range(i, j + 1):
                                processed_timestamps.add(oi_snapshots[k]['snapshot_ts'])
                        break

        return cascades

    def _parse_oi(self, oi_str: str) -> Optional[float]:
        """Parse OI string to float for calculations."""
        if oi_str is None:
            return None
        try:
            return float(oi_str)
        except (ValueError, TypeError):
            return None

    def _get_liquidations_in_range(
        self,
        coin: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict[str, Any]]:
        """Get liquidation events in time range for coin."""
        return self._db.get_liquidation_events_raw(start_ts, end_ts, coin)

    def _create_cascade_label(
        self,
        coin: str,
        start_ts: int,
        end_ts: int,
        oi_drop_pct: float,
        liquidations: List[Dict[str, Any]]
    ) -> Optional[LabeledCascade]:
        """Create labeled cascade from detected event."""
        # Get price at start
        price_start = self._get_price_at_time(coin, start_ts)
        if price_start is None:
            return None

        # Get price at end
        price_end = self._get_price_at_time(coin, end_ts)
        if price_end is None:
            return None

        # Get price 5 minutes after for outcome
        outcome_ts = end_ts + self._outcome_window_ns
        price_5min = self._get_price_at_time(coin, outcome_ts)

        # Detect wave structure
        waves = self._detect_waves(liquidations)

        # Calculate outcome
        outcome = self._calculate_outcome(price_start, price_end, price_5min)

        # Store in database and get ID
        cascade_id = self._db.log_labeled_cascade(
            coin=coin,
            start_ts=start_ts,
            end_ts=end_ts,
            oi_drop_pct=str(oi_drop_pct),
            liquidation_count=len(liquidations),
            wave_count=len(waves),
            price_start=price_start,
            price_end=price_end,
            price_5min_after=price_5min,
            outcome=outcome
        )

        # Store waves
        wave_labels = []
        for i, wave in enumerate(waves):
            wave_num = i + 1
            wave_id = self._db.log_cascade_wave(
                cascade_id=cascade_id,
                wave_num=wave_num,
                start_ts=wave['start_ts'],
                end_ts=wave['end_ts'],
                liquidation_count=wave['count'],
                oi_drop_pct=None  # Per-wave OI not calculated yet
            )
            wave_labels.append(WaveLabel(
                wave_num=wave_num,
                start_ts=wave['start_ts'],
                end_ts=wave['end_ts'],
                liquidation_count=wave['count'],
                oi_drop_pct=None
            ))

        return LabeledCascade(
            cascade_id=cascade_id,
            coin=coin,
            start_ts=start_ts,
            end_ts=end_ts,
            oi_drop_pct=str(oi_drop_pct),
            liquidation_count=len(liquidations),
            price_at_start=price_start,
            price_at_end=price_end,
            price_5min_after=price_5min,
            wave_count=len(wave_labels),
            waves=tuple(wave_labels),
            outcome=outcome
        )

    def _get_price_at_time(self, coin: str, ts: int) -> Optional[str]:
        """Get mark price closest to timestamp.

        Searches a small window around the target timestamp.
        """
        window = 5_000_000_000  # 5 second window
        cursor = self._db.conn.cursor()

        # Get closest price before or at timestamp
        cursor.execute("""
            SELECT mark_px FROM hl_mark_prices_raw
            WHERE coin = ? AND snapshot_ts <= ?
            ORDER BY snapshot_ts DESC
            LIMIT 1
        """, (coin, ts + window))

        row = cursor.fetchone()
        if row:
            return row[0]

        # Try getting price after timestamp
        cursor.execute("""
            SELECT mark_px FROM hl_mark_prices_raw
            WHERE coin = ? AND snapshot_ts >= ?
            ORDER BY snapshot_ts ASC
            LIMIT 1
        """, (coin, ts))

        row = cursor.fetchone()
        return row[0] if row else None

    def _detect_waves(
        self,
        liquidations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect wave structure within liquidations.

        Groups liquidations separated by >wave_gap_ns into distinct waves.
        """
        if not liquidations:
            return []

        # Sort by timestamp
        sorted_liqs = sorted(liquidations, key=lambda x: x['detected_ts'])

        waves = []
        current_wave = {
            'start_ts': sorted_liqs[0]['detected_ts'],
            'end_ts': sorted_liqs[0]['detected_ts'],
            'count': 1
        }

        for liq in sorted_liqs[1:]:
            ts = liq['detected_ts']
            time_gap = ts - current_wave['end_ts']

            if time_gap > self._wave_gap_ns:
                # New wave
                waves.append(current_wave)
                current_wave = {
                    'start_ts': ts,
                    'end_ts': ts,
                    'count': 1
                }
            else:
                # Same wave
                current_wave['end_ts'] = ts
                current_wave['count'] += 1

        waves.append(current_wave)
        return waves

    def _calculate_outcome(
        self,
        price_start: str,
        price_end: str,
        price_5min: Optional[str]
    ) -> Optional[str]:
        """Calculate cascade outcome based on price movement.

        Outcome classification:
        - REVERSAL: Price moved back toward start price after cascade
        - CONTINUATION: Price continued in cascade direction
        - NEUTRAL: No significant movement

        Returns None if price_5min not available.
        """
        if price_5min is None:
            return None

        try:
            p_start = float(price_start)
            p_end = float(price_end)
            p_5min = float(price_5min)
        except (ValueError, TypeError):
            return None

        if p_start == 0:
            return None

        # Cascade direction
        cascade_direction = p_end - p_start

        # Post-cascade movement
        post_movement = p_5min - p_end

        # Threshold for significance (0.5% of start price)
        threshold = abs(p_start * 0.005)

        if abs(post_movement) < threshold:
            return "NEUTRAL"

        # Reversal: post-movement opposite to cascade direction
        if (cascade_direction > 0 and post_movement < -threshold) or \
           (cascade_direction < 0 and post_movement > threshold):
            return "REVERSAL"

        # Continuation: post-movement same direction as cascade
        if (cascade_direction > 0 and post_movement > threshold) or \
           (cascade_direction < 0 and post_movement < -threshold):
            return "CONTINUATION"

        return "NEUTRAL"

    def get_statistics(self, cascades: List[LabeledCascade]) -> Dict[str, Any]:
        """Calculate statistics about labeled cascades.

        Returns factual counts and distributions, no interpretation.
        """
        if not cascades:
            return {
                'total_cascades': 0,
                'by_coin': {},
                'by_outcome': {},
                'wave_distribution': {},
                'avg_liquidations': 0.0
            }

        by_coin = {}
        by_outcome = {}
        wave_counts = {}
        total_liquidations = 0

        for cascade in cascades:
            # Count by coin
            by_coin[cascade.coin] = by_coin.get(cascade.coin, 0) + 1

            # Count by outcome
            outcome = cascade.outcome or 'UNKNOWN'
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1

            # Wave distribution
            wc = cascade.wave_count
            wave_counts[wc] = wave_counts.get(wc, 0) + 1

            # Total liquidations
            total_liquidations += cascade.liquidation_count

        return {
            'total_cascades': len(cascades),
            'by_coin': by_coin,
            'by_outcome': by_outcome,
            'wave_distribution': wave_counts,
            'avg_liquidations': total_liquidations / len(cascades)
        }

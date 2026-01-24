"""
Wave Structure Detector.

Detects discrete waves within liquidation cascades.
Based on HLP25 Part 2 hypothesis about wave structure.

Constitutional: Mechanical detection, no interpretation.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass(frozen=True)
class DetectedWave:
    """A detected wave within a liquidation cascade.

    Immutable record of wave boundaries and counts.
    """
    wave_num: int
    start_ts: int
    end_ts: int
    liquidation_count: int
    total_value: Optional[float]  # Sum of liquidation values if available


@dataclass(frozen=True)
class WaveStructure:
    """Complete wave structure analysis for a cascade event.

    Immutable record of all detected waves and metrics.
    """
    total_waves: int
    waves: tuple  # Tuple of DetectedWave for immutability
    total_duration_ns: int
    avg_inter_wave_gap_ns: Optional[int]
    largest_wave_num: int  # Which wave had most liquidations


class WaveDetector:
    """Detects wave structure in liquidation events.

    Based on HLP25 hypothesis that cascades occur in 3-5 discrete waves.
    Waves are separated by gaps in liquidation activity.
    """

    DEFAULT_WAVE_GAP_NS = 30_000_000_000  # 30 seconds in nanoseconds
    DEFAULT_MIN_WAVE_SIZE = 1  # Minimum liquidations for a wave

    def __init__(
        self,
        wave_gap_ns: int = DEFAULT_WAVE_GAP_NS,
        min_wave_size: int = DEFAULT_MIN_WAVE_SIZE
    ):
        """Initialize wave detector.

        Args:
            wave_gap_ns: Gap between liquidations to define new wave
            min_wave_size: Minimum liquidations to count as a wave
        """
        self._wave_gap_ns = wave_gap_ns
        self._min_wave_size = min_wave_size

    def detect_waves(
        self,
        liquidations: List[Dict[str, Any]],
        value_field: str = 'last_known_position_value'
    ) -> WaveStructure:
        """Detect wave structure from liquidation events.

        Args:
            liquidations: List of liquidation event dicts with detected_ts
            value_field: Field name for liquidation value (optional)

        Returns:
            WaveStructure with all detected waves
        """
        if not liquidations:
            return WaveStructure(
                total_waves=0,
                waves=tuple(),
                total_duration_ns=0,
                avg_inter_wave_gap_ns=None,
                largest_wave_num=0
            )

        # Sort by timestamp
        sorted_liqs = sorted(liquidations, key=lambda x: x.get('detected_ts', 0))

        # Group into raw waves
        raw_waves = self._group_into_waves(sorted_liqs, value_field)

        # Filter by minimum size
        filtered_waves = [w for w in raw_waves if w['count'] >= self._min_wave_size]

        if not filtered_waves:
            return WaveStructure(
                total_waves=0,
                waves=tuple(),
                total_duration_ns=0,
                avg_inter_wave_gap_ns=None,
                largest_wave_num=0
            )

        # Create DetectedWave objects
        detected = []
        largest_count = 0
        largest_wave_num = 0

        for i, wave in enumerate(filtered_waves):
            wave_num = i + 1
            dw = DetectedWave(
                wave_num=wave_num,
                start_ts=wave['start_ts'],
                end_ts=wave['end_ts'],
                liquidation_count=wave['count'],
                total_value=wave.get('total_value')
            )
            detected.append(dw)

            if wave['count'] > largest_count:
                largest_count = wave['count']
                largest_wave_num = wave_num

        # Calculate inter-wave gaps
        gaps = self._calculate_inter_wave_gaps(filtered_waves)
        avg_gap = sum(gaps) // len(gaps) if gaps else None

        # Total duration
        total_duration = filtered_waves[-1]['end_ts'] - filtered_waves[0]['start_ts']

        return WaveStructure(
            total_waves=len(detected),
            waves=tuple(detected),
            total_duration_ns=total_duration,
            avg_inter_wave_gap_ns=avg_gap,
            largest_wave_num=largest_wave_num
        )

    def _group_into_waves(
        self,
        sorted_liqs: List[Dict[str, Any]],
        value_field: str
    ) -> List[Dict[str, Any]]:
        """Group sorted liquidations into waves by time gaps."""
        waves = []
        current_wave = {
            'start_ts': sorted_liqs[0].get('detected_ts', 0),
            'end_ts': sorted_liqs[0].get('detected_ts', 0),
            'count': 1,
            'total_value': self._get_value(sorted_liqs[0], value_field)
        }

        for liq in sorted_liqs[1:]:
            ts = liq.get('detected_ts', 0)
            time_gap = ts - current_wave['end_ts']

            if time_gap > self._wave_gap_ns:
                # Start new wave
                waves.append(current_wave)
                current_wave = {
                    'start_ts': ts,
                    'end_ts': ts,
                    'count': 1,
                    'total_value': self._get_value(liq, value_field)
                }
            else:
                # Continue current wave
                current_wave['end_ts'] = ts
                current_wave['count'] += 1
                value = self._get_value(liq, value_field)
                if value is not None:
                    if current_wave['total_value'] is None:
                        current_wave['total_value'] = value
                    else:
                        current_wave['total_value'] += value

        waves.append(current_wave)
        return waves

    def _get_value(self, liq: Dict[str, Any], field: str) -> Optional[float]:
        """Extract numeric value from liquidation dict."""
        val = liq.get(field)
        if val is None:
            return None
        try:
            return abs(float(val))
        except (ValueError, TypeError):
            return None

    def _calculate_inter_wave_gaps(
        self,
        waves: List[Dict[str, Any]]
    ) -> List[int]:
        """Calculate gaps between consecutive waves."""
        if len(waves) < 2:
            return []

        gaps = []
        for i in range(1, len(waves)):
            gap = waves[i]['start_ts'] - waves[i - 1]['end_ts']
            gaps.append(gap)

        return gaps

    def is_exhausted(
        self,
        wave_structure: WaveStructure,
        current_ts: int,
        exhaustion_gap_ns: Optional[int] = None
    ) -> bool:
        """Check if wave structure indicates exhaustion.

        Exhaustion defined as: time since last wave exceeds threshold.

        Args:
            wave_structure: Detected wave structure
            current_ts: Current timestamp in nanoseconds
            exhaustion_gap_ns: Gap threshold for exhaustion (default: 2x wave_gap)

        Returns:
            True if cascade appears exhausted
        """
        if wave_structure.total_waves == 0:
            return True

        if exhaustion_gap_ns is None:
            exhaustion_gap_ns = self._wave_gap_ns * 2

        last_wave = wave_structure.waves[-1]
        time_since_last = current_ts - last_wave.end_ts

        return time_since_last > exhaustion_gap_ns

    def get_wave_statistics(
        self,
        structures: List[WaveStructure]
    ) -> Dict[str, Any]:
        """Calculate statistics across multiple wave structures.

        Returns factual counts and distributions.
        """
        if not structures:
            return {
                'total_structures': 0,
                'wave_count_distribution': {},
                'avg_waves_per_cascade': 0.0,
                'largest_wave_distribution': {}
            }

        wave_counts = {}
        largest_positions = {}
        total_waves = 0

        for struct in structures:
            # Wave count distribution
            wc = struct.total_waves
            wave_counts[wc] = wave_counts.get(wc, 0) + 1
            total_waves += wc

            # Position of largest wave
            if struct.largest_wave_num > 0:
                pos = struct.largest_wave_num
                largest_positions[pos] = largest_positions.get(pos, 0) + 1

        return {
            'total_structures': len(structures),
            'wave_count_distribution': wave_counts,
            'avg_waves_per_cascade': total_waves / len(structures),
            'largest_wave_distribution': largest_positions
        }

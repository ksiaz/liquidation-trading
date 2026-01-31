"""
HLP24: Event Labeler.

Mechanical event labeling for historical data.

Labels events based on objective, measurable criteria:
- CASCADE: OI drops >15% within 60 seconds with skewed funding
- HUNT_FAILED: Price rejected at liquidation band after OI spike
- SQUEEZE: OI collapse with rapid price move in opposite direction

These labels provide ground truth for strategy validation.

Usage:
    labeler = EventLabeler()

    # Label cascade events
    events = labeler.label_cascades(snapshots)

    for event in events:
        print(f"{event.event_type}: {event.symbol} at {event.start_ts}")
        print(f"  OI drop: {event.metrics['oi_drop_pct']:.1%}")
        print(f"  Price move: {event.metrics['price_move_pct']:.1%}")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Tuple
import statistics


class EventLabel(Enum):
    """Event type labels."""
    CASCADE = "cascade"              # Liquidation cascade
    HUNT_FAILED = "hunt_failed"      # Failed liquidation hunt
    SQUEEZE = "squeeze"              # Short/long squeeze
    OI_SPIKE = "oi_spike"            # Sudden OI increase
    OI_COLLAPSE = "oi_collapse"      # Sudden OI decrease
    FUNDING_EXTREME = "funding_extreme"  # Extreme funding rate


@dataclass
class LabelConfig:
    """Configuration for event labeling."""

    # CASCADE detection
    cascade_oi_drop_pct: float = 0.15       # 15% OI drop
    cascade_window_sec: int = 60            # Within 60 seconds
    cascade_funding_skew: float = 0.01      # 1% funding threshold

    # HUNT_FAILED detection
    hunt_oi_spike_pct: float = 0.10         # 10% OI spike
    hunt_rejection_pct: float = 0.02        # 2% price rejection
    hunt_window_sec: int = 300              # 5 minute window

    # SQUEEZE detection
    squeeze_oi_drop_pct: float = 0.10       # 10% OI drop
    squeeze_price_move_pct: float = 0.05    # 5% price move
    squeeze_window_sec: int = 120           # 2 minute window

    # General
    min_oi_for_event: int = 1_000_000       # Minimum OI to consider


@dataclass
class LabeledEvent:
    """An event with ground truth label."""
    event_id: str
    event_type: EventLabel
    symbol: str
    start_ts: int                   # Microseconds
    end_ts: int                     # Microseconds
    metrics: Dict[str, float]       # Measurements at detection
    confidence: float = 1.0         # Confidence in label (always 1.0 for mechanical)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'symbol': self.symbol,
            'start_ts': self.start_ts,
            'end_ts': self.end_ts,
            'metrics': self.metrics,
            'confidence': self.confidence,
        }


@dataclass
class SnapshotData:
    """Minimal snapshot for labeling."""
    ts_us: int
    symbol: str
    open_interest: float
    funding_rate: float
    mark_price: float
    bid_depth: float = 0
    ask_depth: float = 0


class EventLabeler:
    """
    Mechanical event labeler.

    Labels events based on objective criteria applied to historical data.
    All labels are deterministic and reproducible.
    """

    def __init__(
        self,
        config: LabelConfig = None,
        logger: logging.Logger = None,
    ):
        self._config = config or LabelConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._event_counter = 0

    def _generate_event_id(self, event_type: EventLabel, symbol: str, ts: int) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        return f"{event_type.value}_{symbol}_{ts}_{self._event_counter}"

    def label_cascades(
        self,
        snapshots: List[SnapshotData],
    ) -> List[LabeledEvent]:
        """
        Label cascade events.

        Definition:
        - OI drops >15%
        - Within 60 seconds
        - Funding was skewed (>1%)

        Args:
            snapshots: List of market snapshots, sorted by timestamp

        Returns:
            List of labeled cascade events
        """
        if len(snapshots) < 2:
            return []

        events = []
        config = self._config
        window_us = config.cascade_window_sec * 1_000_000

        # Group by symbol
        by_symbol: Dict[str, List[SnapshotData]] = {}
        for s in snapshots:
            if s.symbol not in by_symbol:
                by_symbol[s.symbol] = []
            by_symbol[s.symbol].append(s)

        for symbol, symbol_snapshots in by_symbol.items():
            if len(symbol_snapshots) < 2:
                continue

            # Sort by timestamp
            symbol_snapshots.sort(key=lambda s: s.ts_us)

            i = 0
            while i < len(symbol_snapshots):
                start_snap = symbol_snapshots[i]

                # Skip if OI too low
                if start_snap.open_interest < config.min_oi_for_event:
                    i += 1
                    continue

                # Look for cascade within window
                max_oi = start_snap.open_interest
                min_oi = start_snap.open_interest
                end_idx = i

                j = i + 1
                while j < len(symbol_snapshots):
                    snap = symbol_snapshots[j]

                    # Check window
                    if snap.ts_us - start_snap.ts_us > window_us:
                        break

                    if snap.open_interest > max_oi:
                        max_oi = snap.open_interest
                    if snap.open_interest < min_oi:
                        min_oi = snap.open_interest
                        end_idx = j

                    j += 1

                # Check for cascade
                if max_oi > 0:
                    oi_drop_pct = (max_oi - min_oi) / max_oi
                    funding_skewed = abs(start_snap.funding_rate) >= config.cascade_funding_skew

                    if oi_drop_pct >= config.cascade_oi_drop_pct and funding_skewed:
                        # Calculate price move
                        price_start = start_snap.mark_price
                        price_end = symbol_snapshots[end_idx].mark_price
                        price_move_pct = (price_end - price_start) / price_start if price_start > 0 else 0

                        event = LabeledEvent(
                            event_id=self._generate_event_id(EventLabel.CASCADE, symbol, start_snap.ts_us),
                            event_type=EventLabel.CASCADE,
                            symbol=symbol,
                            start_ts=start_snap.ts_us,
                            end_ts=symbol_snapshots[end_idx].ts_us,
                            metrics={
                                'oi_drop_pct': oi_drop_pct,
                                'oi_start': max_oi,
                                'oi_end': min_oi,
                                'funding_rate': start_snap.funding_rate,
                                'price_move_pct': price_move_pct,
                                'duration_sec': (symbol_snapshots[end_idx].ts_us - start_snap.ts_us) / 1_000_000,
                            },
                        )
                        events.append(event)

                        # Skip past this event
                        i = end_idx + 1
                        continue

                i += 1

        self._logger.debug(f"Labeled {len(events)} cascade events")
        return events

    def label_hunt_failures(
        self,
        snapshots: List[SnapshotData],
    ) -> List[LabeledEvent]:
        """
        Label failed hunt events.

        Definition:
        - OI spikes >10%
        - Price approaches liquidation band
        - Price rejects (reverses >2%)

        Args:
            snapshots: List of market snapshots

        Returns:
            List of labeled hunt failure events
        """
        if len(snapshots) < 3:
            return []

        events = []
        config = self._config
        window_us = config.hunt_window_sec * 1_000_000

        # Group by symbol
        by_symbol: Dict[str, List[SnapshotData]] = {}
        for s in snapshots:
            if s.symbol not in by_symbol:
                by_symbol[s.symbol] = []
            by_symbol[s.symbol].append(s)

        for symbol, symbol_snapshots in by_symbol.items():
            if len(symbol_snapshots) < 3:
                continue

            symbol_snapshots.sort(key=lambda s: s.ts_us)

            for i in range(len(symbol_snapshots) - 2):
                start_snap = symbol_snapshots[i]

                if start_snap.open_interest < config.min_oi_for_event:
                    continue

                # Look for OI spike
                max_oi = start_snap.open_interest
                spike_idx = i
                extreme_price = start_snap.mark_price

                j = i + 1
                while j < len(symbol_snapshots):
                    snap = symbol_snapshots[j]

                    if snap.ts_us - start_snap.ts_us > window_us:
                        break

                    if snap.open_interest > max_oi:
                        max_oi = snap.open_interest
                        spike_idx = j

                    # Track extreme price
                    if start_snap.funding_rate > 0:  # Longs being hunted
                        if snap.mark_price < extreme_price:
                            extreme_price = snap.mark_price
                    else:  # Shorts being hunted
                        if snap.mark_price > extreme_price:
                            extreme_price = snap.mark_price

                    j += 1

                # Check for spike
                oi_spike_pct = (max_oi - start_snap.open_interest) / start_snap.open_interest \
                    if start_snap.open_interest > 0 else 0

                if oi_spike_pct < config.hunt_oi_spike_pct:
                    continue

                # Look for rejection after spike
                end_idx = min(spike_idx + 10, len(symbol_snapshots) - 1)
                end_snap = symbol_snapshots[end_idx]

                if start_snap.mark_price > 0:
                    rejection = abs(end_snap.mark_price - extreme_price) / start_snap.mark_price
                else:
                    rejection = 0

                if rejection >= config.hunt_rejection_pct:
                    event = LabeledEvent(
                        event_id=self._generate_event_id(EventLabel.HUNT_FAILED, symbol, start_snap.ts_us),
                        event_type=EventLabel.HUNT_FAILED,
                        symbol=symbol,
                        start_ts=start_snap.ts_us,
                        end_ts=end_snap.ts_us,
                        metrics={
                            'oi_spike_pct': oi_spike_pct,
                            'rejection_pct': rejection,
                            'funding_rate': start_snap.funding_rate,
                            'extreme_price': extreme_price,
                            'final_price': end_snap.mark_price,
                        },
                    )
                    events.append(event)

        self._logger.debug(f"Labeled {len(events)} hunt failure events")
        return events

    def label_squeezes(
        self,
        snapshots: List[SnapshotData],
    ) -> List[LabeledEvent]:
        """
        Label squeeze events.

        Definition:
        - OI drops >10%
        - Price moves >5% in opposite direction to position bias
        - Within 2 minutes

        Args:
            snapshots: List of market snapshots

        Returns:
            List of labeled squeeze events
        """
        if len(snapshots) < 2:
            return []

        events = []
        config = self._config
        window_us = config.squeeze_window_sec * 1_000_000

        # Group by symbol
        by_symbol: Dict[str, List[SnapshotData]] = {}
        for s in snapshots:
            if s.symbol not in by_symbol:
                by_symbol[s.symbol] = []
            by_symbol[s.symbol].append(s)

        for symbol, symbol_snapshots in by_symbol.items():
            if len(symbol_snapshots) < 2:
                continue

            symbol_snapshots.sort(key=lambda s: s.ts_us)

            i = 0
            while i < len(symbol_snapshots) - 1:
                start_snap = symbol_snapshots[i]

                if start_snap.open_interest < config.min_oi_for_event:
                    i += 1
                    continue

                # Look for OI drop with price move in window
                min_oi = start_snap.open_interest
                best_squeeze_idx = -1
                best_squeeze_score = 0

                j = i + 1
                while j < len(symbol_snapshots):
                    snap = symbol_snapshots[j]

                    if snap.ts_us - start_snap.ts_us > window_us:
                        break

                    oi_drop_pct = (start_snap.open_interest - snap.open_interest) / start_snap.open_interest \
                        if start_snap.open_interest > 0 else 0

                    price_move_pct = (snap.mark_price - start_snap.mark_price) / start_snap.mark_price \
                        if start_snap.mark_price > 0 else 0

                    # Check if price moved against position bias
                    # Positive funding = longs pay = long bias = price should fall
                    # If price rises, it's a short squeeze
                    is_squeeze = (start_snap.funding_rate > 0 and price_move_pct > 0) or \
                                 (start_snap.funding_rate < 0 and price_move_pct < 0)

                    if oi_drop_pct >= config.squeeze_oi_drop_pct and \
                       abs(price_move_pct) >= config.squeeze_price_move_pct and is_squeeze:
                        score = oi_drop_pct * abs(price_move_pct)
                        if score > best_squeeze_score:
                            best_squeeze_score = score
                            best_squeeze_idx = j
                            min_oi = snap.open_interest

                    j += 1

                if best_squeeze_idx > 0:
                    end_snap = symbol_snapshots[best_squeeze_idx]
                    oi_drop = (start_snap.open_interest - end_snap.open_interest) / start_snap.open_interest
                    price_move = (end_snap.mark_price - start_snap.mark_price) / start_snap.mark_price

                    squeeze_type = "short" if price_move > 0 else "long"

                    event = LabeledEvent(
                        event_id=self._generate_event_id(EventLabel.SQUEEZE, symbol, start_snap.ts_us),
                        event_type=EventLabel.SQUEEZE,
                        symbol=symbol,
                        start_ts=start_snap.ts_us,
                        end_ts=end_snap.ts_us,
                        metrics={
                            'oi_drop_pct': oi_drop,
                            'price_move_pct': price_move,
                            'squeeze_type': squeeze_type,
                            'funding_rate': start_snap.funding_rate,
                            'duration_sec': (end_snap.ts_us - start_snap.ts_us) / 1_000_000,
                        },
                    )
                    events.append(event)
                    i = best_squeeze_idx + 1
                    continue

                i += 1

        self._logger.debug(f"Labeled {len(events)} squeeze events")
        return events

    def label_all(
        self,
        snapshots: List[SnapshotData],
    ) -> Dict[EventLabel, List[LabeledEvent]]:
        """
        Apply all labeling rules.

        Args:
            snapshots: List of market snapshots

        Returns:
            Dict mapping event type to list of events
        """
        return {
            EventLabel.CASCADE: self.label_cascades(snapshots),
            EventLabel.HUNT_FAILED: self.label_hunt_failures(snapshots),
            EventLabel.SQUEEZE: self.label_squeezes(snapshots),
        }

    def get_stats(self, events: Dict[EventLabel, List[LabeledEvent]]) -> Dict[str, Any]:
        """Get statistics about labeled events."""
        total = sum(len(e) for e in events.values())
        by_type = {k.value: len(v) for k, v in events.items()}

        # Get unique symbols
        all_symbols = set()
        for event_list in events.values():
            for e in event_list:
                all_symbols.add(e.symbol)

        return {
            'total_events': total,
            'by_type': by_type,
            'symbols': sorted(all_symbols),
        }

"""
Capitulation Tracker — detects forced position unwinding.

Tracks per-symbol rolling windows of:
- close_ratio: fraction of fills that close/reduce positions
- cumulative_loss: sum of negative closedPnl (realized losses)
- flip_count: position direction reversals (Long>Short, Short>Long)
- unwind_rate: fills where position fully closes (startPosition → 0)

High capitulation = traders being forced out of positions.
When combined with a structural pivot, this provides high confidence
that the cascade is exhausting and reversal is imminent.

Not an M4 primitive (requires state). Parallel to OrganicFlowDetector.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CapitulationMetrics:
    """Capitulation signal for a single symbol."""
    symbol: str
    close_ratio: float       # 0.0-1.0, fraction of fills that are closes
    cumulative_loss: float   # Sum of negative PnL in window (always <= 0)
    flip_count: int          # Position direction reversals
    unwind_count: int        # Full position closures
    total_fills: int         # Total fills in window
    confidence: float        # 0.0-1.0 composite capitulation confidence


@dataclass
class _SymbolState:
    """Per-symbol rolling window state."""
    # (timestamp, is_close, pnl, is_flip, is_full_unwind)
    fills: deque = field(default_factory=lambda: deque(maxlen=500))


class CapitulationTracker:
    """
    Detects capitulation from HL fill metadata.

    Fed with every fill (organic + liquidation). Tracks position
    close/flip/loss patterns in a rolling window.
    """

    def __init__(self, window_sec: float = 60.0):
        self._window_sec = window_sec
        self._state: Dict[str, _SymbolState] = {}

    def on_fill(
        self,
        symbol: str,
        dir_type: str,
        closed_pnl: float,
        start_position: float,
        size: float,
        timestamp: float,
    ):
        """
        Process a fill event.

        Args:
            symbol: Asset symbol (e.g., "BTC")
            dir_type: Fill direction ("Open Long", "Close Short", "Long > Short", etc.)
            closed_pnl: Realized PnL for this fill (negative = loss)
            start_position: Position size before this fill
            size: Fill size
            timestamp: Unix timestamp in seconds
        """
        if symbol not in self._state:
            self._state[symbol] = _SymbolState()
        state = self._state[symbol]

        is_close = dir_type.startswith('Close') or '>' in dir_type
        is_flip = '>' in dir_type  # "Long > Short" or "Short > Long"
        is_full_unwind = (
            is_close and
            start_position != 0.0 and
            abs(size) >= abs(start_position) * 0.95  # Within 5% = full close
        )
        pnl = closed_pnl if is_close else 0.0

        state.fills.append((timestamp, is_close, pnl, is_flip, is_full_unwind))

    def get_metrics(self, symbol: str, timestamp: float = None) -> CapitulationMetrics:
        """
        Get capitulation metrics for a symbol.

        Args:
            symbol: Asset symbol
            timestamp: Current time (for window pruning)

        Returns:
            CapitulationMetrics with current readings
        """
        import time as _time
        if timestamp is None:
            timestamp = _time.time()

        state = self._state.get(symbol)
        if not state or not state.fills:
            return CapitulationMetrics(
                symbol=symbol, close_ratio=0.0, cumulative_loss=0.0,
                flip_count=0, unwind_count=0, total_fills=0, confidence=0.0,
            )

        cutoff = timestamp - self._window_sec
        # Snapshot and filter to window
        fills = [(ts, ic, pnl, ifl, ifu) for ts, ic, pnl, ifl, ifu in list(state.fills)
                 if ts >= cutoff]

        if not fills:
            return CapitulationMetrics(
                symbol=symbol, close_ratio=0.0, cumulative_loss=0.0,
                flip_count=0, unwind_count=0, total_fills=0, confidence=0.0,
            )

        total = len(fills)
        closes = sum(1 for _, ic, _, _, _ in fills if ic)
        close_ratio = closes / total if total > 0 else 0.0

        cum_loss = sum(pnl for _, _, pnl, _, _ in fills if pnl < 0)
        flip_count = sum(1 for _, _, _, ifl, _ in fills if ifl)
        unwind_count = sum(1 for _, _, _, _, ifu in fills if ifu)

        # Composite confidence: weighted sum of signals
        # Each component contributes 0-0.25 to total confidence (max 1.0)
        c_close = min(1.0, close_ratio / 0.8) * 0.35      # 80%+ closes → full weight
        c_loss = min(1.0, abs(cum_loss) / 10000) * 0.25    # $10k+ losses → full weight
        c_flip = min(1.0, flip_count / 5) * 0.20           # 5+ flips → full weight
        c_unwind = min(1.0, unwind_count / 3) * 0.20       # 3+ unwinds → full weight
        confidence = min(1.0, c_close + c_loss + c_flip + c_unwind)

        return CapitulationMetrics(
            symbol=symbol,
            close_ratio=close_ratio,
            cumulative_loss=cum_loss,
            flip_count=flip_count,
            unwind_count=unwind_count,
            total_fills=total,
            confidence=confidence,
        )

    def cleanup(self, current_time: float) -> int:
        """Remove stale data outside window."""
        cutoff = current_time - self._window_sec
        cleaned = 0
        for state in self._state.values():
            before = len(state.fills)
            while state.fills and state.fills[0][0] < cutoff:
                state.fills.popleft()
            cleaned += before - len(state.fills)
        return cleaned

"""
Multi-Timeframe VWAP Tracker — maintains running VWAP at 5m, 15m, 30m windows.

Lightweight: stores (timestamp, price*volume, volume) tuples in a deque,
computes VWAP on demand by summing within window. No PG dependency.

Thread-safe: append-only deque with list() snapshots for reads.
"""

import time
from collections import deque
from typing import Dict, Optional


class MTFVwapTracker:
    """Computes VWAP at multiple timeframes from raw aggTrade data."""

    _MAX_WINDOW = 1800  # 30m — longest window we support
    _MAX_EVENTS = 60_000  # per-symbol cap (~30min of BTC at ~33/sec avg)

    def __init__(self):
        # Per-symbol deque of (ts, price_x_volume, volume)
        self._data: Dict[str, deque] = {}

    def add_trade(self, symbol: str, price: float, volume: float, timestamp: float):
        """Add a trade. Called from fill handler (daemon thread). Thread-safe append."""
        if symbol not in self._data:
            self._data[symbol] = deque(maxlen=self._MAX_EVENTS)
        self._data[symbol].append((timestamp, price * volume, volume))

    def get_vwap(self, symbol: str, window_sec: float, timestamp: float = None) -> Optional[float]:
        """Compute VWAP over the last window_sec seconds. Thread-safe via list() snapshot."""
        buf = self._data.get(symbol)
        if not buf:
            return None
        if timestamp is None:
            timestamp = time.time()
        cutoff = timestamp - window_sec
        events = list(buf)  # thread-safe snapshot
        total_pv = 0.0
        total_v = 0.0
        for ts, pv, v in events:
            if ts >= cutoff:
                total_pv += pv
                total_v += v
        if total_v <= 0:
            return None
        return total_pv / total_v

    def get_multi_tf_vwap(self, symbol: str, price: float, atr: float,
                          timestamp: float = None) -> dict:
        """Get VWAP distance in ATR units at multiple timeframes.

        Returns dict with vwap_5m_atr, vwap_15m_atr, vwap_30m_atr.
        Positive = price above VWAP, negative = below.
        """
        if timestamp is None:
            timestamp = time.time()
        result = {}
        for name, sec in [('5m', 300), ('15m', 900), ('30m', 1800)]:
            vwap = self.get_vwap(symbol, sec, timestamp)
            if vwap and atr and atr > 0:
                result[f'vwap_{name}_atr'] = round((price - vwap) / atr, 3)
            else:
                result[f'vwap_{name}_atr'] = None
        return result

    def trim(self, timestamp: float = None):
        """Remove events older than _MAX_WINDOW. Call periodically."""
        if timestamp is None:
            timestamp = time.time()
        cutoff = timestamp - self._MAX_WINDOW
        for sym, buf in self._data.items():
            while buf and buf[0][0] < cutoff:
                buf.popleft()

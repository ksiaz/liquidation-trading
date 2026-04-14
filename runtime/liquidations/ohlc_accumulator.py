"""OHLC candle accumulator — builds 1-minute candles from raw trade fills."""

import time
from typing import Dict, Optional


class OHLCAccumulator:
    """Accumulates fills into 1-minute OHLC candles.

    Call on_fill() for every aggTrade. When the minute rolls over,
    the previous candle is flushed to PG via the buffered database.
    """

    def __init__(self, db):
        self._db = db
        self._candles: Dict[str, Dict] = {}  # symbol → current candle

    def on_fill(self, symbol: str, price: float, size: float, ts: float):
        minute_ts = int(ts // 60) * 60

        if symbol not in self._candles or self._candles[symbol]['ts'] != minute_ts:
            # Flush previous candle if exists
            if symbol in self._candles:
                self._flush_candle(self._candles[symbol])
            # Start new candle
            self._candles[symbol] = {
                'symbol': symbol, 'ts': minute_ts,
                'open': price, 'high': price, 'low': price, 'close': price,
                'volume': size, 'count': 1,
            }
        else:
            c = self._candles[symbol]
            c['high'] = max(c['high'], price)
            c['low'] = min(c['low'], price)
            c['close'] = price
            c['volume'] += size
            c['count'] += 1

    def _flush_candle(self, c: Dict):
        try:
            self._db.log_ohlc_candle(
                symbol=c['symbol'], timestamp=c['ts'],
                open_price=c['open'], high=c['high'],
                low=c['low'], close=c['close'],
                volume=c['volume'], trade_count=c['count'],
            )
        except Exception:
            pass  # BRD handles errors; don't crash the callback

    def flush_all(self):
        """Flush all open candles (e.g., on shutdown)."""
        for c in self._candles.values():
            self._flush_candle(c)
        self._candles.clear()

"""
M1 Ingestion Layer (Internal)

Responsible for:
1. Normalizing raw external payloads into canonical events.
2. Maintaining fixed-size raw buffers for inspection.
3. Managing Ingestion counters.
"""

from typing import Dict, List, Any, Deque, Optional
from collections import deque, defaultdict
import json

class M1IngestionEngine:
    """
    Pure data ingestion and normalization engine.
    No IO, no threads, no clock.
    """
    
    def __init__(self, trade_buffer_size: int = 500, liquidation_buffer_size: int = 200):
        # Raw Buffers (Per Symbol)
        self.raw_trades: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=trade_buffer_size))
        self.raw_liquidations: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=liquidation_buffer_size))
        
        # Counters
        self.counters = {
            'trades': 0,
            'liquidations': 0,
            'klines': 0,
            'oi': 0,
            'depth_updates': 0,
            'mark_price_updates': 0,
            'errors': 0
        }

    def normalize_trade(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
        """
        Normalize raw binance trade paylod.
        """
        try:
            # Binance AggTrade format
            price = float(raw_payload['p'])
            quantity = float(raw_payload['q'])
            timestamp = int(raw_payload['T']) / 1000.0
            is_buyer_maker = raw_payload['m']
            side = "SELL" if is_buyer_maker else "BUY" # Maker is buyer -> Taker sold -> SELL (?) 
            # Wait, standard Binance: m=True means maker was buyer. 
            # If maker was buyer, the taker was SELLER. So it's a SELL. Correct.
            
            # 1. Update Raw Buffer
            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'price': price,
                'quantity': quantity,
                'side': side,
                'base_qty': quantity,
                'quote_qty': quantity * price
            }
            self.raw_trades[symbol].append(event)
            self.counters['trades'] += 1
            
            return event
            
        except Exception as e:
            self.counters['errors'] += 1
            return None

    def normalize_liquidation(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
        """
        Normalize raw binance liquidation payload.
        """
        try:
            # Binance ForceOrder format
            order = raw_payload['o']
            price = float(order['p'])
            quantity = float(order['q'])
            timestamp = int(raw_payload['E']) / 1000.0
            side = order['S'] # BUY or SELL

            # 1. Update Raw Buffer
            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'price': price,
                'quantity': quantity,
                'side': side,
                'base_qty': quantity,
                'quote_qty': quantity * price
            }
            self.raw_liquidations[symbol].append(event)
            self.counters['liquidations'] += 1

            print(f"DEBUG M1: Liquidation normalized - {symbol} {side} @ ${price} vol={quantity}")

            return event

        except Exception as e:
            print(f"DEBUG M1: Liquidation normalization FAILED for {symbol}: {e}")
            print(f"  Payload: {raw_payload}")
            self.counters['errors'] += 1
            return None

    def record_kline(self, symbol: str):
        self.counters['klines'] += 1

    def record_oi(self, symbol: str):
        self.counters['oi'] += 1

    def normalize_depth_update(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
        """
        Normalize Binance @depth update.

        Binance @depth format:
        {
            "e": "depthUpdate",
            "E": 1234567890,  # Event time
            "s": "BTCUSDT",
            "U": 157,         # First update ID
            "u": 160,         # Final update ID
            "b": [            # Bids to be updated
                ["9000.00", "1.5"]  # [price, qty]
            ],
            "a": [            # Asks to be updated
                ["9001.00", "2.0"]
            ]
        }

        Returns:
            {
                'timestamp': float,
                'symbol': str,
                'bids': [(price, size), ...],
                'asks': [(price, size), ...]
            }
        """
        try:
            timestamp = int(raw_payload['E']) / 1000.0

            # Parse bids/asks
            bids = [(float(p), float(q)) for p, q in raw_payload.get('b', [])]
            asks = [(float(p), float(q)) for p, q in raw_payload.get('a', [])]

            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'bids': bids,
                'asks': asks
            }

            self.counters['depth_updates'] += 1
            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def normalize_mark_price(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
        """
        Normalize Binance @markPrice update.

        Binance @markPrice format:
        {
            "e": "markPriceUpdate",
            "E": 1234567890,  # Event time
            "s": "BTCUSDT",
            "p": "9000.00",   # Mark price
            "i": "8999.50",   # Index price (optional)
            "r": "0.0001"     # Funding rate (ignored - not a primitive)
        }

        Returns:
            {
                'timestamp': float,
                'symbol': str,
                'mark_price': float,
                'index_price': float (optional)
            }
        """
        try:
            timestamp = int(raw_payload['E']) / 1000.0
            mark_price = float(raw_payload['p'])

            # Index price is optional
            index_price = None
            if 'i' in raw_payload and raw_payload['i']:
                index_price = float(raw_payload['i'])

            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'mark_price': mark_price,
                'index_price': index_price
            }

            self.counters['mark_price_updates'] += 1
            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def get_buffers(self) -> Dict:
        """Return copy of raw buffers."""
        return {
            'trades': {s: list(d) for s, d in self.raw_trades.items()},
            'liquidations': {s: list(d) for s, d in self.raw_liquidations.items()}
        }

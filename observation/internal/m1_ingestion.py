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
    
    def __init__(self, trade_buffer_size: int = 500, liquidation_buffer_size: int = 200, depth_buffer_size: int = 100):
        # Raw Buffers (Per Symbol)
        self.raw_trades: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=trade_buffer_size))
        self.raw_liquidations: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=liquidation_buffer_size))
        self.raw_depth: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=depth_buffer_size))

        # Latest depth snapshot per symbol (for order book primitives)
        self.latest_depth: Dict[str, Optional[Dict]] = {}

        # Previous depth snapshot per symbol (for change detection)
        self.previous_depth: Dict[str, Optional[Dict]] = {}

        # Recent price tracking per symbol (for absorption detection)
        self.recent_prices: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=10))

        # Counters
        self.counters = {
            'trades': 0,
            'liquidations': 0,
            'klines': 0,
            'oi': 0,
            'depth': 0,
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
            self.recent_prices[symbol].append((timestamp, price))  # Track for absorption detection
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
            
            return event
            
        except Exception:
            self.counters['errors'] += 1
            return None

    def normalize_depth(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
        """
        Normalize raw binance depth payload.
        """
        try:
            # Binance Depth format
            bids = raw_payload.get('b', [])
            asks = raw_payload.get('a', [])
            timestamp = int(raw_payload.get('E', 0)) / 1000.0

            # Calculate total size at best levels (top 5 levels)
            bid_size = sum(float(level[1]) for level in bids[:5]) if bids else 0.0
            ask_size = sum(float(level[1]) for level in asks[:5]) if asks else 0.0

            # Extract best prices
            best_bid_price = float(bids[0][0]) if bids else None
            best_ask_price = float(asks[0][0]) if asks else None

            # Create normalized event
            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'bid_size': bid_size,
                'ask_size': ask_size,
                'best_bid_price': best_bid_price,
                'best_ask_price': best_ask_price,
                'bid_levels': len(bids),
                'ask_levels': len(asks)
            }
            self.raw_depth[symbol].append(event)

            # Save previous state before updating latest
            if symbol in self.latest_depth:
                self.previous_depth[symbol] = self.latest_depth[symbol]

            self.latest_depth[symbol] = event  # Store latest for primitive computation
            self.counters['depth'] += 1

            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def record_kline(self, symbol: str):
        self.counters['klines'] += 1

    def record_oi(self, symbol: str):
        self.counters['oi'] += 1

    def get_buffers(self) -> Dict:
        """Return copy of raw buffers."""
        return {
            'trades': {s: list(d) for s, d in self.raw_trades.items()},
            'liquidations': {s: list(d) for s, d in self.raw_liquidations.items()}
        }

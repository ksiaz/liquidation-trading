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

        # Hyperliquid buffers
        self.hl_positions: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=trade_buffer_size))
        self.hl_liquidations: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=liquidation_buffer_size))

        # Counters
        self.counters = {
            'trades': 0,
            'liquidations': 0,
            'klines': 0,
            'oi': 0,
            'depth': 0,
            'hl_positions': 0,
            'hl_liquidations': 0,
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

            # DEBUG: Log trade buffer size
            print(f"DEBUG M1: Added TRADE for {symbol}, buffer size now={len(self.raw_trades[symbol])}")

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
        Normalize raw binance bookTicker payload.

        bookTicker format:
        {
            "e": "bookTicker",
            "E": 1234567890123,  // Event time
            "s": "BTCUSDT",
            "b": "96573.28",     // Best bid price
            "B": "0.44492",      // Best bid quantity
            "a": "96573.29",     // Best ask price
            "A": "5.85264"       // Best ask quantity
        }
        """
        try:
            # Extract timestamp
            timestamp = int(raw_payload.get('E', 0)) / 1000.0

            # Extract best bid/ask from bookTicker format
            best_bid_price = float(raw_payload['b']) if 'b' in raw_payload else None
            bid_size = float(raw_payload['B']) if 'B' in raw_payload else 0.0
            best_ask_price = float(raw_payload['a']) if 'a' in raw_payload else None
            ask_size = float(raw_payload['A']) if 'A' in raw_payload else 0.0

            # Create normalized event
            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'bid_size': bid_size,
                'ask_size': ask_size,
                'best_bid_price': best_bid_price,
                'best_ask_price': best_ask_price,
                'bid_levels': 1,  # bookTicker only provides best level
                'ask_levels': 1
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

    # =========================================================================
    # Hyperliquid Normalization (Tier 1 - Confirmed Facts)
    # =========================================================================

    def normalize_hl_position(self, symbol: str, payload: Dict) -> Optional[Dict]:
        """
        Normalize Hyperliquid position event (Tier 1 - confirmed fact).

        This is factual data from the exchange - no transformation, just format.

        Args:
            symbol: Trading symbol (e.g., "BTC")
            payload: Position data with keys:
                - wallet_address: Wallet address
                - position_size: Signed size (positive=long, negative=short)
                - entry_price: Entry price
                - liquidation_price: Liquidation trigger price
                - leverage: Leverage multiplier
                - margin_used: Margin used (USD)
                - position_value: Position value (USD)
                - timestamp: Event timestamp

        Returns:
            Normalized event dict or None on error
        """
        try:
            position_size = float(payload.get('position_size', 0))
            side = 'LONG' if position_size > 0 else 'SHORT'

            event = {
                'timestamp': float(payload.get('timestamp', 0)),
                'symbol': symbol,
                'wallet_address': payload.get('wallet_address', ''),
                'position_size': position_size,
                'entry_price': float(payload.get('entry_price', 0)),
                'liquidation_price': float(payload.get('liquidation_price', 0)),
                'leverage': float(payload.get('leverage', 1)),
                'margin_used': float(payload.get('margin_used', 0)),
                'position_value': float(payload.get('position_value', 0)),
                'side': side,
                'event_type': 'HL_POSITION',
                'exchange': 'HYPERLIQUID'
            }
            self.hl_positions[symbol].append(event)
            self.counters['hl_positions'] += 1
            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def normalize_hl_liquidation(self, symbol: str, payload: Dict) -> Optional[Dict]:
        """
        Normalize Hyperliquid liquidation event (Tier 1 - confirmed fact).

        This is factual data from the exchange - liquidation confirmed.

        Args:
            symbol: Trading symbol (e.g., "BTC")
            payload: Liquidation data with keys:
                - wallet_address: Wallet address
                - liquidated_size: Size liquidated
                - price: Liquidation price
                - side: Position side that was liquidated
                - timestamp: Event timestamp
                - value: USD value liquidated

        Returns:
            Normalized event dict or None on error
        """
        try:
            event = {
                'timestamp': float(payload.get('timestamp', 0)),
                'symbol': symbol,
                'wallet_address': payload.get('wallet_address', ''),
                'liquidated_size': abs(float(payload.get('liquidated_size', 0))),
                'liquidation_price': float(payload.get('price', 0)),
                'side': payload.get('side', 'UNKNOWN'),
                'value': float(payload.get('value', 0)),
                'event_type': 'HL_LIQUIDATION',
                'exchange': 'HYPERLIQUID'
            }
            self.hl_liquidations[symbol].append(event)
            self.counters['hl_liquidations'] += 1
            return event

        except Exception:
            self.counters['errors'] += 1
            return None

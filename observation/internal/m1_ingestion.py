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
            'errors': 0,
            # P2: Side derivation validation counters
            'side_validated': 0,
            'side_mismatch': 0,
            'side_unvalidated': 0
        }

    def normalize_trade(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
        """
        Normalize raw binance trade payload.

        P2: Validates trade side derivation against order book delta.
        """
        try:
            # Binance AggTrade format
            price = float(raw_payload['p'])
            quantity = float(raw_payload['q'])
            timestamp = int(raw_payload['T']) / 1000.0
            is_buyer_maker = raw_payload['m']

            # Standard derivation: m=True means maker was buyer, taker sold -> SELL
            derived_side = "SELL" if is_buyer_maker else "BUY"

            # P2: Validate side against order book
            validated_side, validation_status = self._validate_trade_side(
                symbol, price, derived_side
            )

            # Use validated side if available, otherwise use derived
            side = validated_side if validated_side else derived_side

            # Update Raw Buffer
            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'price': price,
                'quantity': quantity,
                'side': side,
                'base_qty': quantity,
                'quote_qty': quantity * price,
                'side_validation': validation_status  # P2: Track validation result
            }
            self.raw_trades[symbol].append(event)
            self.recent_prices[symbol].append((timestamp, price))
            self.counters['trades'] += 1

            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def _validate_trade_side(
        self,
        symbol: str,
        trade_price: float,
        derived_side: str
    ) -> tuple:
        """
        P2: Validate trade side derivation against order book.

        Cross-references trade price with book delta:
        - Trade at/above best ask = BUY (taker buying from asks)
        - Trade at/below best bid = SELL (taker selling into bids)

        Args:
            symbol: Trading symbol
            trade_price: Trade execution price
            derived_side: Side derived from is_buyer_maker flag

        Returns:
            (validated_side, validation_status):
                - validated_side: Confirmed side or None if unvalidated
                - validation_status: "VALIDATED", "MISMATCH", "UNVALIDATED"
        """
        depth = self.latest_depth.get(symbol)

        if not depth:
            self.counters['side_unvalidated'] += 1
            return (None, "UNVALIDATED")

        best_bid = depth.get('best_bid_price')
        best_ask = depth.get('best_ask_price')

        if best_bid is None or best_ask is None:
            self.counters['side_unvalidated'] += 1
            return (None, "UNVALIDATED")

        # Determine side from book position
        if trade_price >= best_ask:
            book_side = "BUY"  # Trade at/above ask = taker buying
        elif trade_price <= best_bid:
            book_side = "SELL"  # Trade at/below bid = taker selling
        else:
            # Trade between spread - use derived side
            self.counters['side_validated'] += 1
            return (derived_side, "VALIDATED")

        # Compare with derived side
        if book_side == derived_side:
            self.counters['side_validated'] += 1
            return (derived_side, "VALIDATED")
        else:
            # Mismatch - trust the book delta over is_buyer_maker
            self.counters['side_mismatch'] += 1
            return (book_side, "MISMATCH")

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
        Normalize raw depth payload.

        Supports two formats:

        1. bookTicker format:
        {
            "e": "bookTicker",
            "E": 1234567890123,
            "b": "96573.28",     // Best bid price (string)
            "B": "0.44492",      // Best bid quantity (string)
            "a": "96573.29",     // Best ask price (string)
            "A": "5.85264"       // Best ask quantity (string)
        }

        2. Depth update format:
        {
            "E": 1234567890123,
            "b": [["96573.28", "0.44492"], ...],  // Bids array
            "a": [["96573.29", "5.85264"], ...]   // Asks array
        }
        """
        try:
            # Extract timestamp
            timestamp = int(raw_payload.get('E', 0)) / 1000.0

            # Detect format and extract accordingly
            bids = raw_payload.get('b')
            asks = raw_payload.get('a')

            if isinstance(bids, list):
                # Depth update format: arrays of [price, qty] pairs
                # Only use top 5 levels for aggregation
                MAX_LEVELS = 5

                if bids and len(bids) > 0:
                    best_bid_price = float(bids[0][0])
                    top_bids = bids[:MAX_LEVELS]
                    bid_size = sum(float(level[1]) for level in top_bids)
                    bid_levels = len(top_bids)
                else:
                    best_bid_price = None
                    bid_size = 0.0
                    bid_levels = 0

                if asks and len(asks) > 0:
                    best_ask_price = float(asks[0][0])
                    top_asks = asks[:MAX_LEVELS]
                    ask_size = sum(float(level[1]) for level in top_asks)
                    ask_levels = len(top_asks)
                else:
                    best_ask_price = None
                    ask_size = 0.0
                    ask_levels = 0
            else:
                # bookTicker format: single string values
                best_bid_price = float(bids) if bids else None
                bid_size = float(raw_payload.get('B', 0))
                best_ask_price = float(asks) if asks else None
                ask_size = float(raw_payload.get('A', 0))
                bid_levels = 1 if best_bid_price else 0
                ask_levels = 1 if best_ask_price else 0

            # Create normalized event
            event = {
                'timestamp': timestamp,
                'symbol': symbol,
                'bid_size': bid_size,
                'ask_size': ask_size,
                'best_bid_price': best_bid_price,
                'best_ask_price': best_ask_price,
                'bid_levels': bid_levels,
                'ask_levels': ask_levels
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

    def get_side_validation_stats(self) -> Dict:
        """
        P2: Get trade side validation statistics.

        Returns:
            Dict with validation metrics:
            - validated: Trades where side was confirmed by book delta
            - mismatch: Trades where book delta contradicted is_buyer_maker
            - unvalidated: Trades without book data for validation
            - mismatch_rate: Percentage of validated trades with mismatch
        """
        validated = self.counters['side_validated']
        mismatch = self.counters['side_mismatch']
        unvalidated = self.counters['side_unvalidated']
        total_checked = validated + mismatch

        return {
            'validated': validated,
            'mismatch': mismatch,
            'unvalidated': unvalidated,
            'total_checked': total_checked,
            'mismatch_rate': (mismatch / total_checked * 100) if total_checked > 0 else 0.0
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

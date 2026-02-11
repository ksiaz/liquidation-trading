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
        self.hl_prices: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=100))  # Price history per symbol
        self.hl_orders: Dict[str, Deque] = defaultdict(lambda: deque(maxlen=trade_buffer_size))  # Large orders (>$10k)

        # Latest Hyperliquid oracle prices (for proximity calculations)
        self.latest_hl_prices: Dict[str, Dict] = {}  # symbol -> {oracle_price, mark_price, timestamp}

        # Counters
        self.counters = {
            'trades': 0,
            'liquidations': 0,
            'klines': 0,
            'oi': 0,
            'depth': 0,
            'hl_positions': 0,
            'hl_liquidations': 0,
            'hl_prices': 0,
            'hl_orders': 0,
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

    def normalize_hl_order(self, symbol: str, payload: Dict) -> Optional[Dict]:
        """
        Normalize Hyperliquid order event (Tier 1 - confirmed fact).

        Only large orders (>$10k notional) are forwarded here.

        Args:
            symbol: Trading symbol (e.g., "BTC")
            payload: Order data with keys:
                - wallet_address: Wallet address
                - side: BUY or SELL
                - size: Order size
                - notional: USD value (size * price)
                - is_reduce_only: Whether order reduces position
                - timestamp: Event timestamp

        Returns:
            Normalized event dict or None on error
        """
        try:
            event = {
                'timestamp': float(payload.get('timestamp', 0)),
                'symbol': symbol,
                'wallet_address': payload.get('wallet_address', ''),
                'side': payload.get('side', 'UNKNOWN'),
                'size': float(payload.get('size', 0)),
                'notional': float(payload.get('notional', 0)),
                'is_reduce_only': bool(payload.get('is_reduce_only', False)),
                'event_type': 'HL_ORDER',
                'exchange': 'HYPERLIQUID'
            }
            self.hl_orders[symbol].append(event)
            self.counters['hl_orders'] += 1
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
                'liquidation_price': float(payload.get('liquidation_price', payload.get('price', 0))),
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

    def normalize_hl_price(self, symbol: str, payload: Dict) -> Optional[Dict]:
        """
        Normalize Hyperliquid price event from SetGlobalAction.

        Oracle prices are authoritative - they determine liquidation triggers.
        These come from the node's SetGlobalAction messages (~every 2.93s).

        Args:
            symbol: Trading symbol (e.g., "BTC")
            payload: Price data with keys:
                - oracle_price: Oracle price (authoritative)
                - mark_price: Mark price (may be None)
                - timestamp: Event timestamp

        Returns:
            Normalized event dict or None on error
        """
        try:
            oracle_price = payload.get('oracle_price')
            if oracle_price is None:
                return None

            event = {
                'timestamp': float(payload.get('timestamp', 0)),
                'symbol': symbol,
                'oracle_price': float(oracle_price),
                'mark_price': float(payload['mark_price']) if payload.get('mark_price') else None,
                'event_type': 'HL_PRICE',
                'exchange': 'HYPERLIQUID'
            }

            # Store in buffer
            self.hl_prices[symbol].append(event)

            # Update latest price (for proximity calculations)
            self.latest_hl_prices[symbol] = {
                'oracle_price': event['oracle_price'],
                'mark_price': event['mark_price'],
                'timestamp': event['timestamp']
            }

            self.counters['hl_prices'] += 1
            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def normalize_hl_fill(self, symbol: str, payload: Dict) -> Optional[Dict]:
        """
        Normalize Hyperliquid fill event for M2 node creation.

        Converts HL fill format to standard trade format compatible with
        _associate_trade_with_nodes(). Skips liquidation fills to avoid
        double-counting (liquidations create nodes via HL_LIQUIDATION).

        Args:
            symbol: Trading symbol (e.g., "BTC")
            payload: Fill data with keys:
                - side: "B" (buy) or "A" (sell)
                - price: Fill price
                - size: Fill size
                - value_usd: USD value
                - timestamp_ms: Timestamp in milliseconds
                - is_liquidation: True if this fill is a liquidation

        Returns:
            Normalized event dict or None if skipped/error
        """
        try:
            # Skip liquidation fills - they create nodes via HL_LIQUIDATION
            if payload.get('is_liquidation'):
                return None

            price = float(payload.get('price', 0))
            size = float(payload.get('size', 0))
            value_usd = float(payload.get('value_usd', 0))

            # Skip if no meaningful data
            if price <= 0 or size <= 0:
                return None

            # Calculate quote_qty (USD value) - use provided or compute
            quote_qty = value_usd if value_usd > 0 else price * size

            # Map side: "B" = BUY (taker lifted asks), "A" = SELL (taker hit bids)
            side = 'BUY' if payload.get('side') == 'B' else 'SELL'

            # Timestamp: convert ms to seconds, fallback to current time
            timestamp_ms = payload.get('timestamp_ms', 0)
            timestamp = timestamp_ms / 1000.0 if timestamp_ms > 0 else payload.get('timestamp', 0)

            # Normalize symbol: HL uses "BTC", M1 buffers keyed by "BTCUSDT"
            norm_symbol = f"{symbol}USDT" if not symbol.endswith("USDT") and not symbol.endswith("USD") else symbol

            event = {
                'timestamp': timestamp,
                'symbol': norm_symbol,
                'price': price,
                'quantity': size,
                'quote_qty': quote_qty,
                'base_qty': size,
                'side': side,
                'event_type': 'HL_FILL',
                'exchange': 'HYPERLIQUID',
            }

            # Populate raw_trades buffer (same as normalize_trade)
            # Enables trade-based primitives (velocity, compactness, zone_penetration)
            self.raw_trades[norm_symbol].append(event)
            self.recent_prices[norm_symbol].append((timestamp, price))

            self.counters['hl_fills'] = self.counters.get('hl_fills', 0) + 1
            return event

        except Exception:
            self.counters['errors'] += 1
            return None

    def get_latest_hl_price(self, symbol: str) -> Optional[float]:
        """
        Get latest Hyperliquid oracle price for a symbol.

        Used for real-time proximity calculations.
        """
        price_data = self.latest_hl_prices.get(symbol)
        return price_data['oracle_price'] if price_data else None

    def get_all_hl_prices(self) -> Dict[str, float]:
        """
        Get all latest Hyperliquid oracle prices.

        Returns dict of symbol -> oracle_price.
        """
        return {
            symbol: data['oracle_price']
            for symbol, data in list(self.latest_hl_prices.items())
        }

    def get_hl_price_at_offset(self, symbol: str, offset_sec: float, current_time: float) -> Optional[float]:
        """
        Get HL price from approximately offset_sec ago.

        Used by trend gate to calculate short-term returns.

        Args:
            symbol: Symbol to query (e.g., "BTC")
            offset_sec: Seconds in the past to look (e.g., 60 for 1 minute ago)
            current_time: Current timestamp for reference

        Returns:
            Price at offset time, or None if no data available
        """
        if symbol not in self.hl_prices:
            return None

        target_time = current_time - offset_sec
        price_history = self.hl_prices[symbol]

        if not price_history:
            return None

        # Find closest price to target time (binary search would be better but deque is small)
        best_price = None
        best_diff = float('inf')

        for event in list(price_history):
            diff = abs(event['timestamp'] - target_time)
            if diff < best_diff:
                best_diff = diff
                best_price = event['oracle_price']

        # Only return if we found something reasonably close (within 30s tolerance)
        if best_diff <= 30.0 and best_price is not None:
            return best_price

        return None

    def get_hl_price_returns(self, symbol: str, current_time: float) -> Dict[str, Optional[float]]:
        """
        Get price returns for trend gate calculations.

        Returns:
            Dict with ret_1m and ret_3m (as decimals, e.g., -0.001 = -0.1%)
        """
        current_price = self.get_latest_hl_price(symbol)
        if current_price is None:
            return {'ret_1m': None, 'ret_3m': None}

        price_1m = self.get_hl_price_at_offset(symbol, 60.0, current_time)
        price_3m = self.get_hl_price_at_offset(symbol, 180.0, current_time)

        ret_1m = None
        ret_3m = None

        if price_1m is not None and price_1m > 0:
            ret_1m = (current_price - price_1m) / price_1m

        if price_3m is not None and price_3m > 0:
            ret_3m = (current_price - price_3m) / price_3m

        return {'ret_1m': ret_1m, 'ret_3m': ret_3m}

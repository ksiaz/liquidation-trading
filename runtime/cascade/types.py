"""
Cascade Detection Types

Absorption detection based on:
"cumulative buying switching above 50% vs shorts"

Signal = buying_ratio > 0.5 where:
  buying_ratio = organic_buying / (organic_buying + liquidation_selling)

When organic buying exceeds liquidation selling, absorption is occurring.
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Tuple


class CascadeDirection(Enum):
    """Direction of the cascade."""
    DOWN = "DOWN"  # Long liquidations -> selling -> price dropping
    UP = "UP"      # Short liquidations -> buying -> price rising
    NONE = "NONE"


@dataclass
class AbsorptionSignal:
    """
    Absorption detection signal.

    Indicates when organic flow is opposing cascade direction,
    suggesting potential reversal.
    """
    symbol: str
    timestamp: float
    cascade_direction: CascadeDirection
    organic_net: float  # Positive = buying, negative = selling
    is_absorbing: bool
    confidence: float  # 0.0 to 1.0
    liqs_stopped: bool  # No liquidations in window
    # Additional fields for debugging
    buying_volume: float = 0.0
    liq_selling_volume: float = 0.0
    buying_ratio: float = 0.0
    entry_direction: str = ""  # Recommended entry direction if absorbing


@dataclass
class LiquidationEvent:
    """
    Normalized liquidation event.

    Used by cascade detection and strategy logic.
    """
    timestamp: float
    symbol: str
    wallet_address: str
    liquidated_size: float  # Always positive
    liquidation_price: float
    side: str  # 'long' or 'short' (lowercase)
    value: float  # USD value
    event_type: str = 'LIQUIDATION'
    exchange: str = 'UNKNOWN'

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'wallet_address': self.wallet_address,
            'liquidated_size': self.liquidated_size,
            'liquidation_price': self.liquidation_price,
            'side': self.side,
            'value': self.value,
            'event_type': self.event_type,
            'exchange': self.exchange,
        }


@dataclass
class _SymbolFlowState:
    """Track flow state for a single symbol."""
    # Rolling windows of (timestamp, value) tuples
    liquidations: deque = field(default_factory=deque)  # (ts, value, side)
    organic_buys: deque = field(default_factory=deque)   # (ts, value)
    organic_sells: deque = field(default_factory=deque)  # (ts, value)

    # Cumulative counters for warmup gate (not pruned)
    # These track total events since session start
    total_organic_fills: int = 0  # Total buy + sell fills
    total_liquidations: int = 0   # Total liquidation events

    # Cascade state
    cascade_active: bool = False
    cascade_direction: CascadeDirection = CascadeDirection.NONE
    cascade_start_ts: float = 0.0
    cascade_cluster_value: float = 0.0

    # Last liquidation timestamp (for quiet time detection)
    last_liq_ts: float = 0.0


class OrganicFlowDetector:
    """
    Absorption detection via organic flow analysis.

    Tracks cumulative buying vs liquidation selling.
    Signals absorption when: buying / (buying + liq_selling) > 0.5

    This means organic buying has exceeded forced liquidation selling,
    indicating the cascade is being absorbed and reversal is likely.
    """

    def __init__(
        self,
        window_sec: float = 30.0,
        symbols: list = None,
        min_organic_volume: float = 5000.0,
        min_quiet_time: float = 2.0,
        organic_ratio_threshold: float = 0.5  # The "50%" threshold
    ):
        """
        Initialize absorption flow detector.

        Args:
            window_sec: Rolling window for flow tracking (default 30s)
            symbols: List of symbols to track (optional)
            min_organic_volume: Minimum organic volume to consider ($USD)
            min_quiet_time: Seconds since last liquidation for "quiet" (default 2s)
            organic_ratio_threshold: Absorption threshold (default 0.5 = 50%)
        """
        self._window_sec = window_sec
        self._symbols = symbols or []
        self._min_organic_volume = min_organic_volume
        self._min_quiet_time = min_quiet_time
        self._absorption_threshold = organic_ratio_threshold

        # Per-symbol state
        self._state: Dict[str, _SymbolFlowState] = {}

    def _get_state(self, symbol: str) -> _SymbolFlowState:
        """Get or create state for symbol."""
        if symbol not in self._state:
            self._state[symbol] = _SymbolFlowState()
        return self._state[symbol]

    def _cleanup_window(self, q: deque, cutoff_ts: float) -> None:
        """Remove events older than cutoff from deque."""
        while q and q[0][0] < cutoff_ts:
            q.popleft()

    def add_liquidation(self, event: LiquidationEvent) -> None:
        """
        Record a liquidation event.

        For DOWN cascades (long liquidations), this is forced SELLING.
        For UP cascades (short liquidations), this is forced BUYING.
        """
        state = self._get_state(event.symbol)
        state.liquidations.append((event.timestamp, event.value, event.side.lower()))
        state.last_liq_ts = event.timestamp
        state.total_liquidations += 1  # Cumulative counter for warmup gate

    def add_organic_trade(
        self,
        symbol: str,
        timestamp: float,
        side: str,  # "BUY" or "SELL"
        value: float,
        wallet_address: str = ""
    ) -> None:
        """
        Record an organic (non-liquidation) trade.

        Args:
            symbol: Trading symbol (e.g., "SOLUSDT")
            timestamp: Trade timestamp
            side: "BUY" or "SELL" (taker side)
            value: USD value of trade
            wallet_address: Optional wallet (for future liquidator filtering)
        """
        state = self._get_state(symbol)
        side_upper = side.upper()

        if side_upper == "BUY":
            state.organic_buys.append((timestamp, value))
        elif side_upper == "SELL":
            state.organic_sells.append((timestamp, value))

        state.total_organic_fills += 1  # Cumulative counter for warmup gate

    def set_cascade_active(
        self,
        symbol: str,
        direction: CascadeDirection,
        cluster_value: float
    ) -> None:
        """
        Mark a cascade as active for a symbol.

        Called by CascadeStateMachine when transitioning to TRIGGERED state.
        """
        state = self._get_state(symbol)
        state.cascade_active = True
        state.cascade_direction = direction
        state.cascade_cluster_value = cluster_value
        # Don't reset cascade_start_ts here - let check_absorption use current ts

    def clear_cascade(self, symbol: str) -> None:
        """Clear cascade state for symbol."""
        state = self._get_state(symbol)
        state.cascade_active = False
        state.cascade_direction = CascadeDirection.NONE
        state.cascade_start_ts = 0.0
        state.cascade_cluster_value = 0.0

    def check_absorption(
        self,
        symbol: str,
        timestamp: float = None
    ) -> AbsorptionSignal:
        """
        Check if absorption is occurring.

        Absorption signal fires when:
        - Cascade is active
        - buying_ratio = buying / (buying + liq_selling) > threshold
        - This means organic buying exceeds liquidation selling

        For DOWN cascades (long liqs = selling):
          - We track long liquidation value as "liq_selling"
          - We track organic buys as "buying"
          - Absorption = buying > liq_selling

        For UP cascades (short liqs = buying from shorts closing):
          - We track short liquidation value as "liq_buying"
          - We track organic sells as "selling"
          - Absorption = selling > liq_buying
        """
        import time
        if timestamp is None:
            timestamp = time.time()

        state = self._get_state(symbol)
        cutoff_ts = timestamp - self._window_sec

        # Cleanup old events
        self._cleanup_window(state.liquidations, cutoff_ts)
        self._cleanup_window(state.organic_buys, cutoff_ts)
        self._cleanup_window(state.organic_sells, cutoff_ts)

        # Calculate volumes based on cascade direction
        direction = state.cascade_direction

        # Sum liquidations by side
        long_liq_value = sum(v for ts, v, side in state.liquidations if side == "long")
        short_liq_value = sum(v for ts, v, side in state.liquidations if side == "short")

        # Sum organic trades
        organic_buy_value = sum(v for ts, v in state.organic_buys)
        organic_sell_value = sum(v for ts, v in state.organic_sells)

        # Determine absorption based on cascade direction
        if direction == CascadeDirection.DOWN:
            # DOWN cascade: longs liquidated (forced selling), need organic buying
            liq_selling = long_liq_value
            buying = organic_buy_value
            entry_direction = "LONG"  # Reversal entry direction
        elif direction == CascadeDirection.UP:
            # UP cascade: shorts liquidated (forced buying), need organic selling
            liq_selling = short_liq_value  # Actually "liq_buying" but we use same formula
            buying = organic_sell_value    # Actually "selling" opposing the cascade
            entry_direction = "SHORT"  # Reversal entry direction
        else:
            # No cascade active - no absorption possible
            return AbsorptionSignal(
                symbol=symbol,
                timestamp=timestamp,
                cascade_direction=CascadeDirection.NONE,
                organic_net=organic_buy_value - organic_sell_value,
                is_absorbing=False,
                confidence=0.0,
                liqs_stopped=False,
                buying_volume=organic_buy_value,
                liq_selling_volume=0.0,
                buying_ratio=0.0,
                entry_direction=""
            )

        # Calculate buying ratio: buying / (buying + liq_selling)
        total_flow = buying + liq_selling
        if total_flow > 0:
            buying_ratio = buying / total_flow
        else:
            buying_ratio = 0.0

        # Check if liquidations have stopped (quiet time)
        time_since_last_liq = timestamp - state.last_liq_ts if state.last_liq_ts > 0 else float('inf')
        liqs_stopped = time_since_last_liq >= self._min_quiet_time

        # Absorption occurs when:
        # 1. buying_ratio > threshold (organic flow exceeds liquidation flow)
        # 2. Minimum organic volume reached
        # 3. (Optional) liquidations have quieted
        is_absorbing = (
            buying_ratio > self._absorption_threshold and
            buying >= self._min_organic_volume
        )

        # Confidence based on how much ratio exceeds threshold
        if buying_ratio > self._absorption_threshold:
            # Scale confidence: 0.5->0.0, 0.75->0.5, 1.0->1.0
            excess = buying_ratio - self._absorption_threshold
            max_excess = 1.0 - self._absorption_threshold
            confidence = min(1.0, excess / max_excess) if max_excess > 0 else 1.0
        else:
            confidence = 0.0

        # Boost confidence if liquidations have stopped
        if is_absorbing and liqs_stopped:
            confidence = min(1.0, confidence + 0.2)

        return AbsorptionSignal(
            symbol=symbol,
            timestamp=timestamp,
            cascade_direction=direction,
            organic_net=organic_buy_value - organic_sell_value,
            is_absorbing=is_absorbing,
            confidence=confidence,
            liqs_stopped=liqs_stopped,
            buying_volume=buying,
            liq_selling_volume=liq_selling,
            buying_ratio=buying_ratio,
            entry_direction=entry_direction if is_absorbing else ""
        )

    def is_absorbing(self, symbol: str) -> bool:
        """Quick check if absorption is occurring."""
        signal = self.check_absorption(symbol)
        return signal.is_absorbing

    def get_cascade_direction(self, symbol: str) -> CascadeDirection:
        """Get current cascade direction for symbol."""
        state = self._get_state(symbol)
        return state.cascade_direction

    def get_metrics(self, symbol: str = None) -> Optional[Dict]:
        """Get flow metrics for a symbol or all symbols."""
        if symbol:
            if symbol not in self._state:
                return None
            state = self._state[symbol]
            signal = self.check_absorption(symbol)
            return {
                'symbol': symbol,
                'cascade_active': state.cascade_active,
                'cascade_direction': state.cascade_direction.value,
                'buying_volume': signal.buying_volume,
                'liq_selling_volume': signal.liq_selling_volume,
                'buying_ratio': signal.buying_ratio,
                'is_absorbing': signal.is_absorbing,
                'confidence': signal.confidence,
                'liqs_stopped': signal.liqs_stopped,
            }
        return self.get_all_metrics()

    def get_all_metrics(self) -> Dict[str, Dict]:
        """Get metrics for all tracked symbols."""
        return {sym: self.get_metrics(sym) for sym in self._state}

    def get_warmup_status(self, symbol: str) -> Dict:
        """
        Get warmup status for a symbol.

        Used by warmup gate to check if enough data has been collected.
        Returns CUMULATIVE counts since session start, not rolling window counts.

        Returns:
            Dict with:
            - fill_count: Total organic fills since session start
            - liq_count: Total liquidation events since session start
            - is_tracking: Whether symbol has any data
        """
        if symbol not in self._state:
            return {
                'fill_count': 0,
                'liq_count': 0,
                'is_tracking': False,
            }

        state = self._state[symbol]
        return {
            'fill_count': state.total_organic_fills,  # Cumulative, not rolling
            'liq_count': state.total_liquidations,    # Cumulative, not rolling
            'is_tracking': True,
        }

    def cleanup(self, current_time: float) -> int:
        """Cleanup old data from all symbols."""
        cutoff = current_time - self._window_sec
        cleaned = 0
        for state in self._state.values():
            before = len(state.liquidations) + len(state.organic_buys) + len(state.organic_sells)
            self._cleanup_window(state.liquidations, cutoff)
            self._cleanup_window(state.organic_buys, cutoff)
            self._cleanup_window(state.organic_sells, cutoff)
            after = len(state.liquidations) + len(state.organic_buys) + len(state.organic_sells)
            cleaned += before - after
        return cleaned

    # Legacy method aliases for compatibility
    def on_liquidation(self, event: LiquidationEvent) -> None:
        """Alias for add_liquidation."""
        self.add_liquidation(event)

    def on_trade(
        self,
        symbol: str,
        timestamp: float,
        side: str,
        price: float,
        size: float,
        is_organic: bool = True
    ) -> None:
        """Legacy trade handler - converts to add_organic_trade."""
        if is_organic:
            value = price * size
            self.add_organic_trade(symbol, timestamp, side, value)

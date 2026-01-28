"""
Organic Flow Detector for Cascade Absorption

Research-backed absorption detection based on organic trade flow analysis.
Key insight: Absorption is STATE-based, not TIME-based.

Absorption conditions:
1. Liquidations have STOPPED (liqs_in_window == 0)
2. Organic flow OPPOSES cascade direction (organic_net direction)

For LONG liquidation cascade (price dropping):
- Absorption = liqs stopped AND organic_net > 0 (buyers stepping in)
- Trade signal = LONG (reversal upward)

For SHORT liquidation cascade (price rising):
- Absorption = liqs stopped AND organic_net < 0 (sellers stepping in)
- Trade signal = SHORT (reversal downward)

This replaces static orderbook depth analysis with dynamic flow detection.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import time

from .action_extractor import LiquidationEvent


class CascadeDirection(Enum):
    """Direction of the cascade."""
    DOWN = "DOWN"  # Long liquidations → selling → price dropping
    UP = "UP"      # Short liquidations → buying → price rising
    NONE = "NONE"


@dataclass
class OrganicFlowWindow:
    """Rolling window of organic trade flow."""
    symbol: str
    window_sec: float

    # Trade aggregates
    organic_buys: float = 0.0        # Buy volume from organic traders
    organic_sells: float = 0.0       # Sell volume from organic traders
    organic_buy_count: int = 0       # Number of organic buy trades
    organic_sell_count: int = 0      # Number of organic sell trades

    # Liquidation tracking
    long_liqs: float = 0.0           # Long liquidation volume (sells)
    short_liqs: float = 0.0          # Short liquidation volume (buys)
    liq_count: int = 0               # Number of liquidation events
    last_liq_time: float = 0.0       # Timestamp of last liquidation

    # Window bounds
    window_start: float = 0.0
    window_end: float = 0.0

    # Event buffer for rolling window
    events: List[Tuple[float, str, float, bool]] = field(default_factory=list)
    # (timestamp, side, value, is_liquidation)

    def add_trade(
        self,
        timestamp: float,
        side: str,  # "BUY" or "SELL"
        value: float,
        is_liquidation: bool = False
    ):
        """Add a trade to the window."""
        # Add to event buffer
        self.events.append((timestamp, side, value, is_liquidation))

        # Update aggregates
        if is_liquidation:
            self.liq_count += 1
            self.last_liq_time = timestamp
            if side == "SELL":  # Long liquidation
                self.long_liqs += value
            else:  # Short liquidation
                self.short_liqs += value
        else:
            if side == "BUY":
                self.organic_buys += value
                self.organic_buy_count += 1
            else:
                self.organic_sells += value
                self.organic_sell_count += 1

        # Update window bounds
        if self.window_start == 0:
            self.window_start = timestamp
        self.window_end = timestamp

        # Expire old events
        self._expire_events(timestamp)

    def _expire_events(self, current_time: float):
        """Remove events outside the rolling window."""
        cutoff = current_time - self.window_sec

        expired = []
        for event in self.events:
            ts, side, value, is_liq = event
            if ts < cutoff:
                expired.append(event)
                # Subtract from aggregates
                if is_liq:
                    self.liq_count -= 1
                    if side == "SELL":
                        self.long_liqs -= value
                    else:
                        self.short_liqs -= value
                else:
                    if side == "BUY":
                        self.organic_buys -= value
                        self.organic_buy_count -= 1
                    else:
                        self.organic_sells -= value
                        self.organic_sell_count -= 1

        for event in expired:
            self.events.remove(event)

        if self.events:
            self.window_start = self.events[0][0]

    @property
    def organic_net(self) -> float:
        """Net organic flow (positive = net buying, negative = net selling)."""
        return self.organic_buys - self.organic_sells

    @property
    def total_liqs(self) -> float:
        """Total liquidation volume in window."""
        return self.long_liqs + self.short_liqs

    @property
    def organic_volume(self) -> float:
        """Total organic volume in window."""
        return self.organic_buys + self.organic_sells


@dataclass
class AbsorptionSignal:
    """
    Absorption detection result.

    Absorption is detected when:
    1. Liquidations have stopped (liqs_in_window == 0)
    2. Organic flow opposes cascade direction
    """
    symbol: str
    timestamp: float

    # Cascade context
    cascade_direction: CascadeDirection

    # Absorption conditions
    liqs_stopped: bool                # No liquidations in window
    organic_opposes: bool             # Organic net opposes cascade
    absorption_detected: bool         # Both conditions met

    # Supporting data
    time_since_last_liq: float        # Seconds since last liquidation
    organic_net: float                # Net organic flow (buy - sell)
    organic_volume: float             # Total organic volume
    liq_volume_in_window: float       # Remaining liq volume in window

    # Entry signal
    entry_direction: Optional[str]    # "LONG" or "SHORT" if absorption detected

    # Confidence factors
    organic_ratio: float              # |organic_net| / organic_volume (0-1)
    liq_exhaustion_pct: float         # Pct of cluster liquidated (if known)


class OrganicFlowDetector:
    """
    Detects cascade absorption via organic flow analysis.

    Key research findings:
    - Organic traders buy 10:1 after liquidations, but price still drops
      if liquidations continue (liquidation pressure > organic flow)
    - Absorption = liquidations STOPPED + organic net OPPOSES cascade
    - This is STATE-based detection, not time-based

    Integration:
    - Feed ALL trades (liquidations + organic)
    - Call check_absorption() to detect entry opportunities
    - Replaces orderbook depth ratio analysis
    """

    # Known liquidator addresses (from research: 20 addresses, 12.8% of volume)
    LIQUIDATOR_ADDRESSES = {
        # These are addresses with >100 liquidation participations
        # TODO: Load from config or discover dynamically
    }

    def __init__(
        self,
        window_sec: float = 10.0,           # Rolling window
        min_organic_volume: float = 5000.0, # Minimum organic volume for signal
        min_quiet_time: float = 2.0,        # Min seconds since last liq
        organic_ratio_threshold: float = 0.3,  # Min |net|/total ratio
    ):
        self._window_sec = window_sec
        self._min_organic_volume = min_organic_volume
        self._min_quiet_time = min_quiet_time
        self._organic_ratio_threshold = organic_ratio_threshold

        # Flow windows per symbol
        self._windows: Dict[str, OrganicFlowWindow] = {}

        # Active cascade tracking
        self._cascade_directions: Dict[str, CascadeDirection] = {}
        self._cascade_start_value: Dict[str, float] = {}  # Total liq value at cascade start

        # Metrics
        self._signals_generated = 0
        self._absorptions_detected = 0

    def set_cascade_active(
        self,
        symbol: str,
        direction: CascadeDirection,
        cluster_value: float = 0.0
    ):
        """Mark a cascade as active for a symbol."""
        self._cascade_directions[symbol] = direction
        self._cascade_start_value[symbol] = cluster_value

    def clear_cascade(self, symbol: str):
        """Clear cascade state for a symbol."""
        self._cascade_directions.pop(symbol, None)
        self._cascade_start_value.pop(symbol, None)

    def add_liquidation(self, event: LiquidationEvent):
        """Record a liquidation event."""
        symbol = event.symbol

        # Get or create window
        if symbol not in self._windows:
            self._windows[symbol] = OrganicFlowWindow(
                symbol=symbol,
                window_sec=self._window_sec
            )

        window = self._windows[symbol]

        # Map liquidation side to trade side
        # Long liquidation = position closed by SELLING
        # Short liquidation = position closed by BUYING
        trade_side = "SELL" if event.side == "long" else "BUY"

        window.add_trade(
            timestamp=event.timestamp,
            side=trade_side,
            value=event.value,
            is_liquidation=True
        )

    def add_organic_trade(
        self,
        symbol: str,
        timestamp: float,
        side: str,  # "BUY" or "SELL"
        value: float,
        wallet_address: Optional[str] = None
    ):
        """Record an organic (non-liquidation) trade."""
        # Filter out liquidator addresses
        if wallet_address and wallet_address in self.LIQUIDATOR_ADDRESSES:
            return  # Skip liquidator trades

        # Get or create window
        if symbol not in self._windows:
            self._windows[symbol] = OrganicFlowWindow(
                symbol=symbol,
                window_sec=self._window_sec
            )

        window = self._windows[symbol]
        window.add_trade(
            timestamp=timestamp,
            side=side,
            value=value,
            is_liquidation=False
        )

    def check_absorption(
        self,
        symbol: str,
        current_time: Optional[float] = None
    ) -> AbsorptionSignal:
        """
        Check if cascade is being absorbed for a symbol.

        Returns AbsorptionSignal with detection result and entry direction.
        """
        if current_time is None:
            current_time = time.time()

        self._signals_generated += 1

        # Get cascade direction
        cascade_dir = self._cascade_directions.get(symbol, CascadeDirection.NONE)

        # Get flow window
        window = self._windows.get(symbol)

        # Default signal (no absorption)
        if window is None or cascade_dir == CascadeDirection.NONE:
            return AbsorptionSignal(
                symbol=symbol,
                timestamp=current_time,
                cascade_direction=cascade_dir,
                liqs_stopped=False,
                organic_opposes=False,
                absorption_detected=False,
                time_since_last_liq=0.0,
                organic_net=0.0,
                organic_volume=0.0,
                liq_volume_in_window=0.0,
                entry_direction=None,
                organic_ratio=0.0,
                liq_exhaustion_pct=0.0
            )

        # Calculate absorption conditions
        # "Liqs stopped" means: enough time has passed since last liquidation
        # (the old liqs may still be in the window, but no NEW ones are firing)
        time_since_last_liq = current_time - window.last_liq_time if window.last_liq_time > 0 else float('inf')
        liqs_stopped = time_since_last_liq >= self._min_quiet_time

        organic_net = window.organic_net
        organic_volume = window.organic_volume

        # Check if organic flow opposes cascade direction
        # DOWN cascade (long liqs, price dropping) → need organic_net > 0 (buying)
        # UP cascade (short liqs, price rising) → need organic_net < 0 (selling)
        organic_opposes = False
        entry_direction = None

        if cascade_dir == CascadeDirection.DOWN:
            organic_opposes = organic_net > 0
            if organic_opposes:
                entry_direction = "LONG"  # Reversal up
        elif cascade_dir == CascadeDirection.UP:
            organic_opposes = organic_net < 0
            if organic_opposes:
                entry_direction = "SHORT"  # Reversal down

        # Calculate organic ratio (conviction of opposing flow)
        organic_ratio = abs(organic_net) / organic_volume if organic_volume > 0 else 0.0

        # Calculate liquidation exhaustion
        liq_exhaustion_pct = 0.0
        start_value = self._cascade_start_value.get(symbol, 0)
        if start_value > 0:
            # How much of the original cluster has been liquidated?
            total_liquidated = window.long_liqs + window.short_liqs
            liq_exhaustion_pct = total_liquidated / start_value

        # Check all absorption conditions
        absorption_detected = (
            liqs_stopped and
            organic_opposes and
            organic_volume >= self._min_organic_volume and
            organic_ratio >= self._organic_ratio_threshold
        )

        if absorption_detected:
            self._absorptions_detected += 1

        return AbsorptionSignal(
            symbol=symbol,
            timestamp=current_time,
            cascade_direction=cascade_dir,
            liqs_stopped=liqs_stopped,
            organic_opposes=organic_opposes,
            absorption_detected=absorption_detected,
            time_since_last_liq=time_since_last_liq,
            organic_net=organic_net,
            organic_volume=organic_volume,
            liq_volume_in_window=window.total_liqs,
            entry_direction=entry_direction if absorption_detected else None,
            organic_ratio=organic_ratio,
            liq_exhaustion_pct=liq_exhaustion_pct
        )

    def get_flow_summary(self, symbol: str) -> Optional[Dict]:
        """Get current flow summary for a symbol."""
        window = self._windows.get(symbol)
        if window is None:
            return None

        return {
            "symbol": symbol,
            "organic_buys": window.organic_buys,
            "organic_sells": window.organic_sells,
            "organic_net": window.organic_net,
            "organic_volume": window.organic_volume,
            "long_liqs": window.long_liqs,
            "short_liqs": window.short_liqs,
            "total_liqs": window.total_liqs,
            "liq_count": window.liq_count,
            "last_liq_time": window.last_liq_time,
            "events_in_window": len(window.events),
        }

    def get_metrics(self) -> Dict:
        """Get detector metrics."""
        return {
            "symbols_tracked": len(self._windows),
            "active_cascades": len(self._cascade_directions),
            "signals_generated": self._signals_generated,
            "absorptions_detected": self._absorptions_detected,
            "detection_rate": (
                self._absorptions_detected / self._signals_generated
                if self._signals_generated > 0 else 0.0
            ),
        }

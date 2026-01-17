"""Manipulation Detector - Detect market manipulation patterns.

Detects:
1. Orderbook spoofing (large walls that disappear)
2. Wash trading patterns (self-matched liquidations)
3. Flash crash patterns (sudden price drops with instant recovery)
4. Liquidation hunting (price pushed to liquidation levels then reversed)

Provides:
- Real-time alerts when manipulation detected
- Circuit breaker triggers to halt cascade sniper
- Historical manipulation event log
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Deque
from enum import Enum


class ManipulationType(Enum):
    """Types of market manipulation detected."""
    SPOOFING = "SPOOFING"           # Large orders placed and quickly cancelled
    WASH_TRADING = "WASH_TRADING"   # Self-matched trades
    FLASH_CRASH = "FLASH_CRASH"     # Sudden drop with instant recovery
    LIQ_HUNTING = "LIQ_HUNTING"     # Price pushed to liquidation, then reversed
    DEPTH_MANIPULATION = "DEPTH_MANIPULATION"  # Artificial depth creation


@dataclass
class ManipulationAlert:
    """Alert when manipulation is detected."""
    type: ManipulationType
    symbol: str
    timestamp: float
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    details: str
    trigger_circuit_breaker: bool = False

    def __str__(self) -> str:
        cb = " [CIRCUIT BREAKER]" if self.trigger_circuit_breaker else ""
        return f"[{self.severity}] {self.type.value} on {self.symbol}: {self.details}{cb}"


@dataclass
class OrderbookSnapshot:
    """Snapshot of orderbook state for comparison."""
    symbol: str
    timestamp: float
    best_bid: float
    best_ask: float
    bid_depth_5: float  # Total depth in top 5 levels
    ask_depth_5: float
    bid_depth_10: float  # Total depth in top 10 levels
    ask_depth_10: float
    largest_bid_size: float
    largest_ask_size: float
    largest_bid_price: float
    largest_ask_price: float


class ManipulationDetector:
    """Detects market manipulation patterns in real-time.

    Maintains rolling windows of:
    - Orderbook snapshots for spoof detection
    - Price movements for flash crash detection
    - Liquidation events for hunting detection
    """

    # Spoofing thresholds
    SPOOF_SIZE_THRESHOLD = 100000  # $100k order considered large
    SPOOF_DISAPPEAR_TIME_SEC = 5.0  # Large order disappears within 5s
    SPOOF_SIZE_DROP_PCT = 80.0  # Size drops by 80%+

    # Flash crash thresholds
    FLASH_CRASH_DROP_PCT = 2.0  # 2% drop
    FLASH_CRASH_RECOVERY_PCT = 1.5  # Recovers 75% of drop
    FLASH_CRASH_WINDOW_SEC = 30.0  # Within 30 seconds

    # Liquidation hunting thresholds
    LIQ_HUNT_REVERSAL_PCT = 1.0  # 1% reversal after touching liq level
    LIQ_HUNT_TIME_SEC = 60.0  # Reversal within 60 seconds

    # Circuit breaker thresholds
    ALERTS_FOR_CIRCUIT_BREAKER = 3  # 3 alerts in window triggers breaker
    CIRCUIT_BREAKER_WINDOW_SEC = 300.0  # 5 minute window

    def __init__(self):
        # Rolling windows per symbol
        self._orderbook_history: Dict[str, Deque[OrderbookSnapshot]] = {}
        self._price_history: Dict[str, Deque[tuple]] = {}  # (timestamp, price)
        self._liq_events: Dict[str, Deque[tuple]] = {}  # (timestamp, price, side, value)

        # Alert tracking
        self._recent_alerts: Deque[ManipulationAlert] = deque(maxlen=100)
        self._circuit_breaker_active: Dict[str, float] = {}  # symbol -> expiry time

        # Statistics
        self._alerts_by_type: Dict[ManipulationType, int] = {t: 0 for t in ManipulationType}
        self._circuit_breakers_triggered = 0

    def update_orderbook(self, symbol: str, orderbook: Dict) -> Optional[ManipulationAlert]:
        """Update orderbook snapshot and check for spoofing.

        Returns ManipulationAlert if spoofing detected, None otherwise.
        """
        current_time = time.time()

        # Parse orderbook
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        if not bids or not asks:
            return None

        # Calculate snapshot
        best_bid = float(bids[0].get('px', 0)) if isinstance(bids[0], dict) else float(bids[0][0])
        best_ask = float(asks[0].get('px', 0)) if isinstance(asks[0], dict) else float(asks[0][0])
        mid_price = (best_bid + best_ask) / 2

        bid_depth_5 = sum(
            float(b.get('sz', 0)) * mid_price if isinstance(b, dict) else float(b[1]) * mid_price
            for b in bids[:5]
        )
        ask_depth_5 = sum(
            float(a.get('sz', 0)) * mid_price if isinstance(a, dict) else float(a[1]) * mid_price
            for a in asks[:5]
        )
        bid_depth_10 = sum(
            float(b.get('sz', 0)) * mid_price if isinstance(b, dict) else float(b[1]) * mid_price
            for b in bids[:10]
        )
        ask_depth_10 = sum(
            float(a.get('sz', 0)) * mid_price if isinstance(a, dict) else float(a[1]) * mid_price
            for a in asks[:10]
        )

        # Find largest orders
        largest_bid_size = 0
        largest_bid_price = 0
        for b in bids[:20]:
            size = float(b.get('sz', 0)) if isinstance(b, dict) else float(b[1])
            size_usd = size * mid_price
            if size_usd > largest_bid_size:
                largest_bid_size = size_usd
                largest_bid_price = float(b.get('px', 0)) if isinstance(b, dict) else float(b[0])

        largest_ask_size = 0
        largest_ask_price = 0
        for a in asks[:20]:
            size = float(a.get('sz', 0)) if isinstance(a, dict) else float(a[1])
            size_usd = size * mid_price
            if size_usd > largest_ask_size:
                largest_ask_size = size_usd
                largest_ask_price = float(a.get('px', 0)) if isinstance(a, dict) else float(a[0])

        snapshot = OrderbookSnapshot(
            symbol=symbol,
            timestamp=current_time,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_depth_5=bid_depth_5,
            ask_depth_5=ask_depth_5,
            bid_depth_10=bid_depth_10,
            ask_depth_10=ask_depth_10,
            largest_bid_size=largest_bid_size,
            largest_ask_size=largest_ask_size,
            largest_bid_price=largest_bid_price,
            largest_ask_price=largest_ask_price
        )

        # Initialize history if needed
        if symbol not in self._orderbook_history:
            self._orderbook_history[symbol] = deque(maxlen=60)  # 1 minute of snapshots

        # Check for spoofing against recent history
        alert = self._check_spoofing(symbol, snapshot)

        # Store snapshot
        self._orderbook_history[symbol].append(snapshot)

        return alert

    def _check_spoofing(self, symbol: str, current: OrderbookSnapshot) -> Optional[ManipulationAlert]:
        """Check if a large order disappeared (spoofing pattern)."""
        history = self._orderbook_history.get(symbol, deque())

        if len(history) < 2:
            return None

        # Look for large orders in recent history that disappeared
        for prev in list(history)[-10:]:  # Check last 10 snapshots
            time_diff = current.timestamp - prev.timestamp
            if time_diff < self.SPOOF_DISAPPEAR_TIME_SEC:
                # Check bid side spoofing
                if prev.largest_bid_size > self.SPOOF_SIZE_THRESHOLD:
                    # Did the large bid at that price disappear?
                    size_drop_pct = (prev.largest_bid_size - current.bid_depth_10) / prev.largest_bid_size * 100
                    if size_drop_pct > self.SPOOF_SIZE_DROP_PCT:
                        alert = ManipulationAlert(
                            type=ManipulationType.SPOOFING,
                            symbol=symbol,
                            timestamp=current.timestamp,
                            severity="HIGH",
                            details=f"Bid wall ${prev.largest_bid_size:,.0f} at {prev.largest_bid_price:.2f} disappeared in {time_diff:.1f}s",
                            trigger_circuit_breaker=False
                        )
                        self._record_alert(alert)
                        return alert

                # Check ask side spoofing
                if prev.largest_ask_size > self.SPOOF_SIZE_THRESHOLD:
                    size_drop_pct = (prev.largest_ask_size - current.ask_depth_10) / prev.largest_ask_size * 100
                    if size_drop_pct > self.SPOOF_SIZE_DROP_PCT:
                        alert = ManipulationAlert(
                            type=ManipulationType.SPOOFING,
                            symbol=symbol,
                            timestamp=current.timestamp,
                            severity="HIGH",
                            details=f"Ask wall ${prev.largest_ask_size:,.0f} at {prev.largest_ask_price:.2f} disappeared in {time_diff:.1f}s",
                            trigger_circuit_breaker=False
                        )
                        self._record_alert(alert)
                        return alert

        return None

    def update_price(self, symbol: str, price: float, timestamp: float) -> Optional[ManipulationAlert]:
        """Update price history and check for flash crash patterns."""
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=120)  # 2 minutes of prices

        self._price_history[symbol].append((timestamp, price))

        return self._check_flash_crash(symbol, price, timestamp)

    def _check_flash_crash(self, symbol: str, current_price: float, current_time: float) -> Optional[ManipulationAlert]:
        """Check for flash crash pattern: sudden drop followed by instant recovery."""
        history = list(self._price_history.get(symbol, []))

        if len(history) < 10:
            return None

        # Look for pattern in last 30 seconds
        recent_history = [(t, p) for t, p in history if current_time - t < self.FLASH_CRASH_WINDOW_SEC]

        if len(recent_history) < 5:
            return None

        # Find min and max in window
        prices = [p for _, p in recent_history]
        min_price = min(prices)
        max_price = max(prices)

        if max_price <= 0:
            return None

        # Calculate drop
        drop_pct = (max_price - min_price) / max_price * 100

        if drop_pct >= self.FLASH_CRASH_DROP_PCT:
            # Check if recovered
            recovery_pct = (current_price - min_price) / (max_price - min_price) * 100 if max_price > min_price else 0

            if recovery_pct >= self.FLASH_CRASH_RECOVERY_PCT * 100:
                # Find timing
                min_idx = prices.index(min_price)
                time_to_min = recent_history[min_idx][0] - recent_history[0][0]
                recovery_time = current_time - recent_history[min_idx][0]

                alert = ManipulationAlert(
                    type=ManipulationType.FLASH_CRASH,
                    symbol=symbol,
                    timestamp=current_time,
                    severity="CRITICAL",
                    details=f"Flash crash: {drop_pct:.1f}% drop in {time_to_min:.1f}s, {recovery_pct:.0f}% recovery in {recovery_time:.1f}s",
                    trigger_circuit_breaker=True
                )
                self._record_alert(alert)
                return alert

        return None

    def update_liquidation(
        self,
        symbol: str,
        liq_price: float,
        side: str,
        value: float,
        timestamp: float
    ) -> Optional[ManipulationAlert]:
        """Record liquidation event for hunting detection."""
        if symbol not in self._liq_events:
            self._liq_events[symbol] = deque(maxlen=50)

        self._liq_events[symbol].append((timestamp, liq_price, side, value))

        # Liquidation hunting is detected by price reversal, checked in update_price
        return None

    def check_liq_hunting(self, symbol: str, current_price: float, current_time: float) -> Optional[ManipulationAlert]:
        """Check if price reversed after hitting liquidation levels."""
        liq_events = list(self._liq_events.get(symbol, []))
        price_history = list(self._price_history.get(symbol, []))

        if not liq_events or len(price_history) < 5:
            return None

        # Check recent liquidations
        for liq_time, liq_price, side, value in liq_events:
            time_since_liq = current_time - liq_time

            if time_since_liq < self.LIQ_HUNT_TIME_SEC and time_since_liq > 5:
                # Did price touch liq level and reverse?
                prices_after_liq = [p for t, p in price_history if t > liq_time]

                if not prices_after_liq:
                    continue

                # For LONG liquidations, price dropped to liq level then bounced
                if side == "SELL":  # SELL = long position liquidated
                    min_after = min(prices_after_liq)
                    if min_after <= liq_price * 1.001:  # Price touched or went below liq
                        reversal = (current_price - min_after) / min_after * 100
                        if reversal >= self.LIQ_HUNT_REVERSAL_PCT:
                            alert = ManipulationAlert(
                                type=ManipulationType.LIQ_HUNTING,
                                symbol=symbol,
                                timestamp=current_time,
                                severity="HIGH",
                                details=f"Long liq hunt: price hit {liq_price:.2f}, reversed {reversal:.1f}% (${value:,.0f} liquidated)",
                                trigger_circuit_breaker=False
                            )
                            self._record_alert(alert)
                            return alert

                # For SHORT liquidations, price spiked to liq level then dropped
                elif side == "BUY":  # BUY = short position liquidated
                    max_after = max(prices_after_liq)
                    if max_after >= liq_price * 0.999:
                        reversal = (max_after - current_price) / max_after * 100
                        if reversal >= self.LIQ_HUNT_REVERSAL_PCT:
                            alert = ManipulationAlert(
                                type=ManipulationType.LIQ_HUNTING,
                                symbol=symbol,
                                timestamp=current_time,
                                severity="HIGH",
                                details=f"Short liq hunt: price hit {liq_price:.2f}, reversed {reversal:.1f}% (${value:,.0f} liquidated)",
                                trigger_circuit_breaker=False
                            )
                            self._record_alert(alert)
                            return alert

        return None

    def _record_alert(self, alert: ManipulationAlert):
        """Record alert and check for circuit breaker trigger."""
        self._recent_alerts.append(alert)
        self._alerts_by_type[alert.type] += 1

        # Check if circuit breaker should be triggered
        current_time = alert.timestamp
        window_start = current_time - self.CIRCUIT_BREAKER_WINDOW_SEC

        recent_count = sum(
            1 for a in self._recent_alerts
            if a.timestamp > window_start and a.symbol == alert.symbol
        )

        if recent_count >= self.ALERTS_FOR_CIRCUIT_BREAKER:
            self._circuit_breaker_active[alert.symbol] = current_time + self.CIRCUIT_BREAKER_WINDOW_SEC
            self._circuit_breakers_triggered += 1
            alert.trigger_circuit_breaker = True
            print(f"[CIRCUIT BREAKER] {alert.symbol}: {recent_count} manipulation alerts in {self.CIRCUIT_BREAKER_WINDOW_SEC/60:.0f} minutes")

    def is_circuit_breaker_active(self, symbol: str) -> bool:
        """Check if circuit breaker is active for a symbol."""
        if symbol not in self._circuit_breaker_active:
            return False

        if time.time() > self._circuit_breaker_active[symbol]:
            del self._circuit_breaker_active[symbol]
            return False

        return True

    def get_circuit_breaker_remaining(self, symbol: str) -> float:
        """Get remaining time on circuit breaker in seconds."""
        if not self.is_circuit_breaker_active(symbol):
            return 0.0
        return self._circuit_breaker_active[symbol] - time.time()

    def clear_circuit_breaker(self, symbol: str):
        """Manually clear circuit breaker for a symbol."""
        if symbol in self._circuit_breaker_active:
            del self._circuit_breaker_active[symbol]

    def get_stats(self) -> Dict:
        """Get manipulation detection statistics."""
        return {
            "total_alerts": sum(self._alerts_by_type.values()),
            "alerts_by_type": {t.value: c for t, c in self._alerts_by_type.items()},
            "circuit_breakers_triggered": self._circuit_breakers_triggered,
            "active_circuit_breakers": list(self._circuit_breaker_active.keys())
        }

    def get_recent_alerts(self, symbol: Optional[str] = None, limit: int = 10) -> List[ManipulationAlert]:
        """Get recent manipulation alerts."""
        alerts = list(self._recent_alerts)

        if symbol:
            alerts = [a for a in alerts if a.symbol == symbol]

        return alerts[-limit:]

"""Cross-Validator - Correlate Binance liquidations with Hyperliquid position changes.

Purpose:
- Verify data consistency between exchanges
- Detect when Hyperliquid positions disappear (liquidated)
- Correlate with Binance liquidation events
- Track cross-exchange latency

This is critical for:
1. Validating our liquidation data is accurate
2. Measuring cross-exchange correlation
3. Detecting missed liquidations or position changes
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Deque, Tuple


@dataclass
class PositionSnapshot:
    """Snapshot of a Hyperliquid position."""
    wallet: str
    coin: str
    size: float
    entry_price: float
    liquidation_price: float
    value: float
    side: str  # "LONG" or "SHORT"
    timestamp: float


@dataclass
class LiquidationEvent:
    """Binance liquidation event."""
    symbol: str
    side: str
    price: float
    quantity: float
    value: float
    timestamp: float


@dataclass
class CorrelationResult:
    """Result of cross-validating Binance and Hyperliquid data."""
    hl_wallet: str
    hl_coin: str
    hl_position_value: float
    hl_disappear_time: float

    binance_symbol: Optional[str]
    binance_value: Optional[float]
    binance_time: Optional[float]

    correlated: bool
    latency_ms: Optional[float]  # Time between events if correlated

    def __str__(self) -> str:
        if self.correlated:
            return (f"[CORRELATED] {self.hl_coin}: HL ${self.hl_position_value:,.0f} "
                    f"-> Binance ${self.binance_value:,.0f} ({self.latency_ms:.0f}ms)")
        else:
            return f"[UNCORRELATED] {self.hl_coin}: HL ${self.hl_position_value:,.0f} (no Binance match)"


@dataclass
class CrossValidationStats:
    """Statistics from cross-validation."""
    hl_positions_tracked: int = 0
    hl_positions_disappeared: int = 0
    binance_liquidations: int = 0
    correlations_found: int = 0
    average_latency_ms: float = 0.0
    correlation_rate: float = 0.0  # correlations / disappeared


class CrossValidator:
    """Correlate Binance liquidations with Hyperliquid position changes.

    Architecture:
    1. Track Hyperliquid positions per wallet
    2. Detect when positions disappear (liquidated or closed)
    3. Look for matching Binance liquidation within time window
    4. Log correlations for analysis

    This validates our data pipeline is working correctly.
    """

    # Correlation parameters
    CORRELATION_WINDOW_SEC = 10.0  # Look for Binance liq within 10s of HL disappearance
    VALUE_MATCH_TOLERANCE_PCT = 20.0  # Allow 20% value difference

    def __init__(self):
        # Track positions per wallet
        self._hl_positions: Dict[str, Dict[str, PositionSnapshot]] = {}  # wallet -> {coin -> snapshot}

        # Recent Binance liquidations
        self._binance_liqs: Deque[LiquidationEvent] = deque(maxlen=200)

        # Correlation results
        self._correlations: Deque[CorrelationResult] = deque(maxlen=100)

        # Statistics
        self._stats = CrossValidationStats()

    def on_hl_update(
        self,
        wallet: str,
        positions: Dict[str, PositionSnapshot]
    ) -> List[CorrelationResult]:
        """Update Hyperliquid positions and detect disappearances.

        Args:
            wallet: Wallet address
            positions: Current positions for this wallet {coin -> snapshot}

        Returns:
            List of correlation results for any disappeared positions
        """
        correlations = []
        current_time = time.time()

        # Get previous positions for this wallet
        prev_positions = self._hl_positions.get(wallet, {})

        # Detect disappeared positions
        for coin, prev_pos in prev_positions.items():
            if coin not in positions:
                # Position disappeared
                self._stats.hl_positions_disappeared += 1

                # Try to correlate with Binance liquidation
                result = self._check_binance_correlation(prev_pos, current_time)
                correlations.append(result)
                self._correlations.append(result)

                if result.correlated:
                    self._stats.correlations_found += 1
                    print(f"[CROSS] {result}")

        # Update stored positions
        self._hl_positions[wallet] = positions

        # Update tracked count
        total_positions = sum(len(p) for p in self._hl_positions.values())
        self._stats.hl_positions_tracked = total_positions

        # Update correlation rate
        if self._stats.hl_positions_disappeared > 0:
            self._stats.correlation_rate = (
                self._stats.correlations_found / self._stats.hl_positions_disappeared
            )

        return correlations

    def on_binance_liq(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        timestamp: float
    ):
        """Record Binance liquidation event.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            price: Liquidation price
            quantity: Quantity liquidated
            timestamp: Event timestamp
        """
        value = price * quantity

        event = LiquidationEvent(
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            value=value,
            timestamp=timestamp
        )

        self._binance_liqs.append(event)
        self._stats.binance_liquidations += 1

    def _check_binance_correlation(
        self,
        hl_position: PositionSnapshot,
        disappear_time: float
    ) -> CorrelationResult:
        """Check if a Binance liquidation matches the disappeared HL position."""
        # Convert coin to symbol (BTC -> BTCUSDT)
        expected_symbol = f"{hl_position.coin}USDT"

        # Expected Binance side based on HL position side
        # LONG liquidation = SELL (forced sell of long)
        # SHORT liquidation = BUY (forced buy to close short)
        expected_side = "SELL" if hl_position.side == "LONG" else "BUY"

        # Search for matching Binance liquidation within window
        best_match = None
        best_latency = float('inf')

        for liq in self._binance_liqs:
            # Check symbol match
            if liq.symbol != expected_symbol:
                continue

            # Check side match
            if liq.side != expected_side:
                continue

            # Check time window
            time_diff = abs(liq.timestamp - disappear_time)
            if time_diff > self.CORRELATION_WINDOW_SEC:
                continue

            # Check value match (within tolerance)
            value_diff_pct = abs(liq.value - hl_position.value) / hl_position.value * 100 if hl_position.value > 0 else 100
            if value_diff_pct > self.VALUE_MATCH_TOLERANCE_PCT:
                continue

            # Found a match - track the one with lowest latency
            latency_ms = time_diff * 1000
            if latency_ms < best_latency:
                best_match = liq
                best_latency = latency_ms

        # Build correlation result
        if best_match:
            # Update average latency
            prev_avg = self._stats.average_latency_ms
            prev_count = self._stats.correlations_found
            self._stats.average_latency_ms = (prev_avg * prev_count + best_latency) / (prev_count + 1)

            return CorrelationResult(
                hl_wallet=hl_position.wallet[:10],  # Truncate for privacy
                hl_coin=hl_position.coin,
                hl_position_value=hl_position.value,
                hl_disappear_time=disappear_time,
                binance_symbol=best_match.symbol,
                binance_value=best_match.value,
                binance_time=best_match.timestamp,
                correlated=True,
                latency_ms=best_latency
            )
        else:
            return CorrelationResult(
                hl_wallet=hl_position.wallet[:10],
                hl_coin=hl_position.coin,
                hl_position_value=hl_position.value,
                hl_disappear_time=disappear_time,
                binance_symbol=None,
                binance_value=None,
                binance_time=None,
                correlated=False,
                latency_ms=None
            )

    def get_stats(self) -> Dict:
        """Get cross-validation statistics."""
        return {
            "hl_positions_tracked": self._stats.hl_positions_tracked,
            "hl_positions_disappeared": self._stats.hl_positions_disappeared,
            "binance_liquidations": self._stats.binance_liquidations,
            "correlations_found": self._stats.correlations_found,
            "correlation_rate_pct": self._stats.correlation_rate * 100,
            "average_latency_ms": self._stats.average_latency_ms
        }

    def get_recent_correlations(self, limit: int = 10) -> List[CorrelationResult]:
        """Get recent correlation results."""
        return list(self._correlations)[-limit:]

    def create_position_snapshot(
        self,
        wallet: str,
        coin: str,
        size: float,
        entry_price: float,
        liquidation_price: float,
        value: float,
        side: str,
        timestamp: float
    ) -> PositionSnapshot:
        """Create a position snapshot from raw data."""
        return PositionSnapshot(
            wallet=wallet,
            coin=coin,
            size=size,
            entry_price=entry_price,
            liquidation_price=liquidation_price,
            value=value,
            side=side,
            timestamp=timestamp
        )

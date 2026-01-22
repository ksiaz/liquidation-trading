"""Data Validator - Input validation for cascade sniper system.

Validates:
1. Position data from Hyperliquid
2. Orderbook data from Hyperliquid
3. Liquidation events from Binance

Focuses on:
- Staleness detection
- Data consistency checks
- Range validation
- Cross-source consistency
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class DataSource(Enum):
    """Data source identifier."""
    HYPERLIQUID = "HYPERLIQUID"
    BINANCE = "BINANCE"


@dataclass
class ValidationResult:
    """Result of a validation check."""
    source: DataSource
    symbol: str
    timestamp: float
    is_valid: bool
    staleness_sec: float
    issues: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        issues_str = ", ".join(self.issues) if self.issues else "none"
        return f"[{status}] {self.source.value}/{self.symbol}: staleness={self.staleness_sec:.1f}s, issues=[{issues_str}]"


class DataValidator:
    """Validates input data for correctness and freshness.

    Performs mechanical validation only - does not interpret market meaning.
    """

    # Staleness thresholds
    MAX_POSITION_STALENESS_SEC = 30.0
    MAX_ORDERBOOK_STALENESS_SEC = 5.0
    MAX_LIQUIDATION_STALENESS_SEC = 10.0

    # Position validation ranges
    MIN_LEVERAGE = 1.0
    MAX_LEVERAGE = 100.0
    MAX_ENTRY_PRICE_DEVIATION_PCT = 50.0  # Entry price within 50% of current
    POSITION_VALUE_TOLERANCE_PCT = 5.0  # Computed value within 5% of reported

    # Orderbook validation
    MAX_SPREAD_PCT = 1.0  # Spread > 1% is suspicious
    MIN_DEPTH_LEVELS = 5  # Must have at least 5 levels each side

    # Liquidation validation
    MAX_LIQUIDATION_PRICE_DEVIATION_PCT = 5.0  # Liquidation price within 5% of market

    def __init__(self):
        self._validation_count = 0
        self._valid_count = 0
        self._stats_by_source: Dict[str, Dict[str, int]] = {
            "HYPERLIQUID": {"validated": 0, "valid": 0},
            "BINANCE": {"validated": 0, "valid": 0}
        }

    def validate_position(
        self,
        position: Any,
        current_time: float,
        market_price: Optional[float] = None
    ) -> ValidationResult:
        """Validate a Hyperliquid position.

        Checks:
        1. Staleness < 30s
        2. Leverage in range [1, 100]
        3. Liquidation price direction matches side
        4. Entry price within 50% of current (if market_price provided)
        5. Position value = size * price (within 5%)
        """
        issues = []
        symbol = getattr(position, 'coin', 'UNKNOWN')
        timestamp = getattr(position, 'timestamp', current_time)

        # Check staleness
        staleness = current_time - timestamp
        if staleness > self.MAX_POSITION_STALENESS_SEC:
            issues.append(f"stale: {staleness:.1f}s > {self.MAX_POSITION_STALENESS_SEC}s")

        # Check leverage
        leverage = getattr(position, 'leverage', 0)
        if leverage < self.MIN_LEVERAGE or leverage > self.MAX_LEVERAGE:
            issues.append(f"leverage out of range: {leverage}")

        # Check liquidation price direction
        side = getattr(position, 'side', None)
        liq_price = getattr(position, 'liquidation_price', None)
        entry_price = getattr(position, 'entry_price', None)

        if side and liq_price and entry_price:
            if side == "LONG" and liq_price >= entry_price:
                issues.append(f"long liq_price {liq_price} >= entry {entry_price}")
            elif side == "SHORT" and liq_price <= entry_price:
                issues.append(f"short liq_price {liq_price} <= entry {entry_price}")

        # Check entry price deviation from market
        if market_price and entry_price:
            deviation_pct = abs(entry_price - market_price) / market_price * 100
            if deviation_pct > self.MAX_ENTRY_PRICE_DEVIATION_PCT:
                issues.append(f"entry deviation: {deviation_pct:.1f}% > {self.MAX_ENTRY_PRICE_DEVIATION_PCT}%")

        # Check position value consistency
        size = getattr(position, 'size', None)
        reported_value = getattr(position, 'value', None)
        if size and entry_price and reported_value:
            computed_value = abs(size) * entry_price
            value_diff_pct = abs(computed_value - reported_value) / reported_value * 100 if reported_value > 0 else 100
            if value_diff_pct > self.POSITION_VALUE_TOLERANCE_PCT:
                issues.append(f"value mismatch: computed ${computed_value:,.0f} vs reported ${reported_value:,.0f}")

        is_valid = len(issues) == 0

        # Update stats
        self._validation_count += 1
        self._stats_by_source["HYPERLIQUID"]["validated"] += 1
        if is_valid:
            self._valid_count += 1
            self._stats_by_source["HYPERLIQUID"]["valid"] += 1

        return ValidationResult(
            source=DataSource.HYPERLIQUID,
            symbol=symbol,
            timestamp=timestamp,
            is_valid=is_valid,
            staleness_sec=staleness,
            issues=issues
        )

    def validate_orderbook(
        self,
        orderbook: Dict[str, Any],
        current_time: float
    ) -> ValidationResult:
        """Validate a Hyperliquid L2 orderbook.

        Checks:
        1. Staleness < 5s
        2. Bid < Ask (no crossed book)
        3. Spread < 1%
        4. Has depth on both sides (at least 5 levels)
        5. No zero-size levels
        """
        issues = []
        symbol = orderbook.get('coin', 'UNKNOWN')
        timestamp = orderbook.get('timestamp', current_time)

        # Check staleness
        staleness = current_time - timestamp
        if staleness > self.MAX_ORDERBOOK_STALENESS_SEC:
            issues.append(f"stale: {staleness:.1f}s > {self.MAX_ORDERBOOK_STALENESS_SEC}s")

        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        # Check depth
        if len(bids) < self.MIN_DEPTH_LEVELS:
            issues.append(f"insufficient bid depth: {len(bids)} < {self.MIN_DEPTH_LEVELS}")
        if len(asks) < self.MIN_DEPTH_LEVELS:
            issues.append(f"insufficient ask depth: {len(asks)} < {self.MIN_DEPTH_LEVELS}")

        # Check for crossed book
        if bids and asks:
            best_bid = float(bids[0].get('px', 0)) if isinstance(bids[0], dict) else float(bids[0][0])
            best_ask = float(asks[0].get('px', 0)) if isinstance(asks[0], dict) else float(asks[0][0])

            if best_bid >= best_ask:
                issues.append(f"crossed book: bid {best_bid} >= ask {best_ask}")
            else:
                # Check spread
                mid_price = (best_bid + best_ask) / 2
                spread_pct = (best_ask - best_bid) / mid_price * 100 if mid_price > 0 else 100
                if spread_pct > self.MAX_SPREAD_PCT:
                    issues.append(f"wide spread: {spread_pct:.2f}% > {self.MAX_SPREAD_PCT}%")

        # Check for zero-size levels (potential spoof remnants)
        for i, bid in enumerate(bids[:10]):
            size = float(bid.get('sz', 0)) if isinstance(bid, dict) else float(bid[1])
            if size <= 0:
                issues.append(f"zero bid at level {i}")
        for i, ask in enumerate(asks[:10]):
            size = float(ask.get('sz', 0)) if isinstance(ask, dict) else float(ask[1])
            if size <= 0:
                issues.append(f"zero ask at level {i}")

        is_valid = len(issues) == 0

        # Update stats
        self._validation_count += 1
        self._stats_by_source["HYPERLIQUID"]["validated"] += 1
        if is_valid:
            self._valid_count += 1
            self._stats_by_source["HYPERLIQUID"]["valid"] += 1

        return ValidationResult(
            source=DataSource.HYPERLIQUID,
            symbol=symbol,
            timestamp=timestamp,
            is_valid=is_valid,
            staleness_sec=staleness,
            issues=issues
        )

    def validate_liquidation(
        self,
        liquidation: Any,
        current_time: float,
        market_price: Optional[float] = None
    ) -> ValidationResult:
        """Validate a Binance liquidation event.

        Checks:
        1. Staleness < 10s
        2. Price within 5% of market (if market_price provided)
        3. Volume > 0
        4. Side is valid (BUY or SELL)
        """
        issues = []
        symbol = getattr(liquidation, 'symbol', 'UNKNOWN')
        timestamp = getattr(liquidation, 'timestamp', current_time)

        # Check staleness
        staleness = current_time - timestamp
        if staleness > self.MAX_LIQUIDATION_STALENESS_SEC:
            issues.append(f"stale: {staleness:.1f}s > {self.MAX_LIQUIDATION_STALENESS_SEC}s")

        # Check price deviation
        liq_price = getattr(liquidation, 'price', None)
        if market_price and liq_price:
            deviation_pct = abs(liq_price - market_price) / market_price * 100
            if deviation_pct > self.MAX_LIQUIDATION_PRICE_DEVIATION_PCT:
                issues.append(f"price deviation: {deviation_pct:.1f}% > {self.MAX_LIQUIDATION_PRICE_DEVIATION_PCT}%")

        # Check volume
        volume = getattr(liquidation, 'quantity', 0)
        if volume <= 0:
            issues.append(f"invalid volume: {volume}")

        # Check side
        side = getattr(liquidation, 'side', None)
        if side not in ['BUY', 'SELL']:
            issues.append(f"invalid side: {side}")

        is_valid = len(issues) == 0

        # Update stats
        self._validation_count += 1
        self._stats_by_source["BINANCE"]["validated"] += 1
        if is_valid:
            self._valid_count += 1
            self._stats_by_source["BINANCE"]["valid"] += 1

        return ValidationResult(
            source=DataSource.BINANCE,
            symbol=symbol,
            timestamp=timestamp,
            is_valid=is_valid,
            staleness_sec=staleness,
            issues=issues
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        valid_pct = (self._valid_count / self._validation_count * 100) if self._validation_count > 0 else 0
        return {
            "total_validated": self._validation_count,
            "total_valid": self._valid_count,
            "valid_pct": valid_pct,
            "by_source": self._stats_by_source
        }

    def reset_stats(self):
        """Reset validation statistics."""
        self._validation_count = 0
        self._valid_count = 0
        self._stats_by_source = {
            "HYPERLIQUID": {"validated": 0, "valid": 0},
            "BINANCE": {"validated": 0, "valid": 0}
        }

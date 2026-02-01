"""
HL-Native Decision Loop

PURPOSE: Answer one question only:
"Does Hyperliquid data alone ever produce a non-trivial, explainable trading signal?"

CONSTRAINTS:
- NO Binance data
- NO regime classification
- NO VWAP / ATR / orderflow
- NO paper trading or execution
- NO approximations

ALLOWED INPUTS (HL Node ONLY):
- Oracle price
- Mark price
- Liquidation events (side, size, wallet, timestamp)

METRIC: Liquidation Side Imbalance
- Tracks ratio of long vs short liquidations in rolling window
- Heavy imbalance indicates forced selling/buying pressure
"""

import time
import json
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional, Deque, Dict, List
from enum import Enum


class Decision(Enum):
    """Possible decisions from HL-native loop."""
    SKIP = "SKIP"                    # No signal
    LONG_PRESSURE = "LONG_PRESSURE"  # Heavy short liquidations → upward pressure
    SHORT_PRESSURE = "SHORT_PRESSURE"  # Heavy long liquidations → downward pressure


@dataclass
class LiquidationEvent:
    """Single liquidation event from HL node."""
    symbol: str
    side: str           # LONG or SHORT (position side that was liquidated)
    size_usd: float     # Notional value
    price: float        # Execution price
    timestamp: float    # Unix timestamp
    wallet: str = ""    # Liquidated wallet (optional)


@dataclass
class SideImbalanceMetric:
    """Computed metric for a symbol."""
    symbol: str
    window_seconds: float
    total_liquidations: int
    long_liquidations: int
    short_liquidations: int
    long_value_usd: float
    short_value_usd: float
    total_value_usd: float
    imbalance_ratio: float  # long_value / total_value (0.5 = balanced)
    timestamp: float

    @property
    def is_long_dominant(self) -> bool:
        """True if more long positions being liquidated."""
        return self.imbalance_ratio > 0.5

    @property
    def is_short_dominant(self) -> bool:
        """True if more short positions being liquidated."""
        return self.imbalance_ratio < 0.5


@dataclass
class DecisionRecord:
    """Record of a decision made by the loop."""
    timestamp: float
    symbol: str
    decision: str
    reason: str
    metric_value: float
    threshold_used: float
    total_value_usd: float
    long_value_usd: float
    short_value_usd: float
    event_count: int
    oracle_price: Optional[float] = None


class HLNativeDecisionLoop:
    """
    Minimal decision loop using ONLY HL node data.

    METRIC: Liquidation Side Imbalance
    - Rolling window of liquidation events
    - Compute ratio: long_liquidation_value / total_liquidation_value
    - 0.5 = balanced, >0.75 = heavy long liquidations, <0.25 = heavy short liquidations

    DECISION RULE:
    IF imbalance_ratio > 0.75 AND total_value > $100k → SHORT_PRESSURE
    IF imbalance_ratio < 0.25 AND total_value > $100k → LONG_PRESSURE
    ELSE → SKIP
    """

    # Decision thresholds (fixed, not tunable)
    IMBALANCE_THRESHOLD = 0.75      # 75% one-sided to trigger
    MIN_VALUE_THRESHOLD = 100_000   # $100k minimum to be meaningful
    WINDOW_SECONDS = 60.0           # 60-second rolling window

    def __init__(self, symbols: List[str] = None):
        """
        Initialize decision loop.

        Args:
            symbols: Symbols to track (HL format: BTC, ETH, etc.)
        """
        self._symbols = symbols or ['BTC', 'ETH', 'SOL']

        # Per-symbol liquidation buffers
        self._liquidations: Dict[str, Deque[LiquidationEvent]] = {
            s: deque(maxlen=1000) for s in self._symbols
        }

        # Per-symbol latest oracle prices (from HL_PRICE events)
        self._oracle_prices: Dict[str, float] = {}

        # Decision log
        self._decisions: List[DecisionRecord] = []
        self._max_decisions = 10000

        # Metrics
        self._events_processed = 0
        self._decisions_made = 0
        self._non_skip_decisions = 0

    def on_hl_price(self, symbol: str, oracle_price: float, timestamp: float):
        """
        Handle HL_PRICE event.

        Only stores oracle price for reference. Does NOT feed any calculator.
        """
        if symbol in self._symbols or symbol in [s + 'USDT' for s in self._symbols]:
            # Normalize to HL format
            clean_symbol = symbol.replace('USDT', '')
            self._oracle_prices[clean_symbol] = oracle_price

    def on_liquidation(self, event: LiquidationEvent) -> DecisionRecord:
        """
        Handle liquidation event from HL node.

        Args:
            event: Liquidation event with side, size, price, timestamp

        Returns:
            DecisionRecord with the decision made
        """
        # Normalize symbol
        symbol = event.symbol.replace('USDT', '')

        if symbol not in self._symbols:
            # Not tracking this symbol
            return self._make_decision(symbol, Decision.SKIP, "Symbol not tracked", 0.5, 0, event.timestamp)

        # Add to buffer
        self._liquidations[symbol].append(event)
        self._events_processed += 1

        # Compute metric
        metric = self._compute_metric(symbol, event.timestamp)

        # Evaluate decision rule
        return self._evaluate_decision(metric)

    def _compute_metric(self, symbol: str, current_time: float) -> SideImbalanceMetric:
        """
        Compute liquidation side imbalance metric.

        Uses rolling window of liquidation events.
        """
        buffer = self._liquidations.get(symbol, deque())

        # Filter to window
        cutoff = current_time - self.WINDOW_SECONDS
        recent = [e for e in buffer if e.timestamp >= cutoff]

        # Aggregate by side
        long_count = 0
        short_count = 0
        long_value = 0.0
        short_value = 0.0

        for event in recent:
            if event.side == 'LONG':
                long_count += 1
                long_value += event.size_usd
            elif event.side == 'SHORT':
                short_count += 1
                short_value += event.size_usd

        total_value = long_value + short_value
        total_count = long_count + short_count

        # Compute imbalance ratio (0.5 if no data)
        if total_value > 0:
            imbalance_ratio = long_value / total_value
        else:
            imbalance_ratio = 0.5

        return SideImbalanceMetric(
            symbol=symbol,
            window_seconds=self.WINDOW_SECONDS,
            total_liquidations=total_count,
            long_liquidations=long_count,
            short_liquidations=short_count,
            long_value_usd=long_value,
            short_value_usd=short_value,
            total_value_usd=total_value,
            imbalance_ratio=imbalance_ratio,
            timestamp=current_time,
        )

    def _evaluate_decision(self, metric: SideImbalanceMetric) -> DecisionRecord:
        """
        Evaluate decision rule against metric.

        DECISION RULE:
        - IF imbalance_ratio > 0.75 AND total_value > $100k → SHORT_PRESSURE
        - IF imbalance_ratio < 0.25 AND total_value > $100k → LONG_PRESSURE
        - ELSE → SKIP
        """
        symbol = metric.symbol
        timestamp = metric.timestamp
        oracle_price = self._oracle_prices.get(symbol)

        # Check minimum value threshold
        if metric.total_value_usd < self.MIN_VALUE_THRESHOLD:
            return self._make_decision(
                symbol=symbol,
                decision=Decision.SKIP,
                reason=f"Insufficient volume: ${metric.total_value_usd:,.0f} < ${self.MIN_VALUE_THRESHOLD:,.0f}",
                metric_value=metric.imbalance_ratio,
                total_value=metric.total_value_usd,
                timestamp=timestamp,
                metric=metric,
                oracle_price=oracle_price,
            )

        # Check for heavy long liquidations (SHORT_PRESSURE)
        if metric.imbalance_ratio > self.IMBALANCE_THRESHOLD:
            return self._make_decision(
                symbol=symbol,
                decision=Decision.SHORT_PRESSURE,
                reason=f"Heavy LONG liquidations: {metric.imbalance_ratio:.1%} > {self.IMBALANCE_THRESHOLD:.0%}",
                metric_value=metric.imbalance_ratio,
                total_value=metric.total_value_usd,
                timestamp=timestamp,
                metric=metric,
                oracle_price=oracle_price,
            )

        # Check for heavy short liquidations (LONG_PRESSURE)
        if metric.imbalance_ratio < (1 - self.IMBALANCE_THRESHOLD):
            return self._make_decision(
                symbol=symbol,
                decision=Decision.LONG_PRESSURE,
                reason=f"Heavy SHORT liquidations: {metric.imbalance_ratio:.1%} < {1 - self.IMBALANCE_THRESHOLD:.0%}",
                metric_value=metric.imbalance_ratio,
                total_value=metric.total_value_usd,
                timestamp=timestamp,
                metric=metric,
                oracle_price=oracle_price,
            )

        # No signal
        return self._make_decision(
            symbol=symbol,
            decision=Decision.SKIP,
            reason=f"Balanced: {metric.imbalance_ratio:.1%} in [{1-self.IMBALANCE_THRESHOLD:.0%}, {self.IMBALANCE_THRESHOLD:.0%}]",
            metric_value=metric.imbalance_ratio,
            total_value=metric.total_value_usd,
            timestamp=timestamp,
            metric=metric,
            oracle_price=oracle_price,
        )

    def _make_decision(
        self,
        symbol: str,
        decision: Decision,
        reason: str,
        metric_value: float,
        total_value: float,
        timestamp: float,
        metric: SideImbalanceMetric = None,
        oracle_price: float = None,
    ) -> DecisionRecord:
        """Create and log a decision record."""

        record = DecisionRecord(
            timestamp=timestamp,
            symbol=symbol,
            decision=decision.value,
            reason=reason,
            metric_value=metric_value,
            threshold_used=self.IMBALANCE_THRESHOLD,
            total_value_usd=total_value,
            long_value_usd=metric.long_value_usd if metric else 0,
            short_value_usd=metric.short_value_usd if metric else 0,
            event_count=metric.total_liquidations if metric else 0,
            oracle_price=oracle_price,
        )

        # Store decision
        self._decisions.append(record)
        if len(self._decisions) > self._max_decisions:
            self._decisions.pop(0)

        self._decisions_made += 1
        if decision != Decision.SKIP:
            self._non_skip_decisions += 1

        return record

    def get_decisions(self, limit: int = 100) -> List[DecisionRecord]:
        """Get recent decisions."""
        return list(self._decisions[-limit:])

    def get_non_skip_decisions(self, limit: int = 100) -> List[DecisionRecord]:
        """Get only non-SKIP decisions."""
        return [d for d in self._decisions if d.decision != Decision.SKIP.value][-limit:]

    def get_metrics(self) -> dict:
        """Get loop metrics."""
        return {
            'events_processed': self._events_processed,
            'decisions_made': self._decisions_made,
            'non_skip_decisions': self._non_skip_decisions,
            'skip_rate': 1 - (self._non_skip_decisions / max(1, self._decisions_made)),
            'symbols_tracked': len(self._symbols),
        }

    def export_decisions_json(self, filepath: str):
        """Export decisions to JSON file."""
        data = {
            'generated_at': time.time(),
            'metrics': self.get_metrics(),
            'config': {
                'imbalance_threshold': self.IMBALANCE_THRESHOLD,
                'min_value_threshold': self.MIN_VALUE_THRESHOLD,
                'window_seconds': self.WINDOW_SECONDS,
            },
            'decisions': [asdict(d) for d in self._decisions],
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)


# Singleton instance for integration
_decision_loop: Optional[HLNativeDecisionLoop] = None


def get_hl_native_loop(symbols: List[str] = None) -> HLNativeDecisionLoop:
    """Get or create the HL-native decision loop."""
    global _decision_loop
    if _decision_loop is None:
        _decision_loop = HLNativeDecisionLoop(symbols=symbols)
    return _decision_loop


def reset_hl_native_loop():
    """Reset the loop (for testing)."""
    global _decision_loop
    _decision_loop = None

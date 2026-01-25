"""
HLP18: Slippage Tracker.

Pre-trade slippage estimation and post-trade tracking.

Pre-trade:
- Analyze orderbook depth
- Estimate fill price for order size
- Check against acceptable thresholds

Post-trade:
- Measure actual slippage
- Track slippage costs
- Adjust future estimates
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple
from threading import RLock
from collections import defaultdict

from .types import (
    OrderSide,
    SlippageEstimate,
    OrderFill,
)


@dataclass
class SlippageConfig:
    """Configuration for slippage tracking."""
    # Slippage thresholds (percentage)
    default_max_slippage_pct: float = 0.5   # 50 bps normal
    aggressive_max_slippage_pct: float = 1.0 # 100 bps aggressive
    cascade_max_slippage_pct: float = 1.0   # 100 bps for cascade
    exit_max_slippage_pct: float = 2.0      # No limit on stops

    # Historical tracking
    history_window: int = 100  # Keep last 100 fills per symbol
    adjustment_factor: float = 1.2  # Adjust estimates by 20%


@dataclass
class SlippageRecord:
    """Record of actual slippage for a fill."""
    symbol: str
    side: OrderSide
    size: float
    expected_price: float
    fill_price: float
    slippage_pct: float
    slippage_bps: float
    slippage_cost: float  # In USD equivalent
    timestamp_ns: int


class SlippageTracker:
    """
    Tracks and estimates order slippage.

    Pre-trade:
    - estimate_slippage(): Analyze orderbook, predict fill price

    Post-trade:
    - record_fill(): Track actual slippage
    - get_statistics(): Historical slippage data
    """

    def __init__(
        self,
        config: SlippageConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or SlippageConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Orderbook cache (updated from external source)
        self._orderbooks: Dict[str, Dict] = {}

        # Slippage history per symbol
        self._history: Dict[str, List[SlippageRecord]] = defaultdict(list)

        # Aggregate statistics
        self._total_slippage_cost: float = 0.0
        self._total_fills: int = 0

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def update_orderbook(self, symbol: str, orderbook: Dict):
        """
        Update cached orderbook for a symbol.

        Expected format:
        {
            'bids': [{'price': float, 'size': float, 'cumulative': float}, ...],
            'asks': [{'price': float, 'size': float, 'cumulative': float}, ...],
            'mid_price': float,
            'timestamp': float
        }
        """
        with self._lock:
            self._orderbooks[symbol] = orderbook

    def estimate_slippage(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        max_slippage_pct: float = None
    ) -> SlippageEstimate:
        """
        Estimate slippage for a potential order.

        Analyzes orderbook depth to predict fill price.

        Args:
            symbol: Trading pair
            side: Buy or sell
            size: Order size
            max_slippage_pct: Maximum acceptable slippage

        Returns:
            SlippageEstimate with predicted fill price and acceptability
        """
        if max_slippage_pct is None:
            max_slippage_pct = self._config.default_max_slippage_pct

        with self._lock:
            orderbook = self._orderbooks.get(symbol)

            if not orderbook:
                # No orderbook data - use historical estimate
                return self._estimate_from_history(symbol, side, size, max_slippage_pct)

            mid_price = orderbook.get('mid_price', 0)
            if mid_price <= 0:
                return self._estimate_from_history(symbol, side, size, max_slippage_pct)

            # Analyze appropriate side of book
            if side == OrderSide.BUY:
                # Buying: taking from asks
                levels = orderbook.get('asks', [])
            else:
                # Selling: hitting bids
                levels = orderbook.get('bids', [])

            # Calculate fill price walking through book
            remaining = size
            total_cost = 0.0
            levels_consumed = 0

            for level in levels:
                level_price = level.get('price', 0)
                level_size = level.get('size', 0)

                if remaining <= 0:
                    break

                fill_at_level = min(remaining, level_size)
                total_cost += fill_at_level * level_price
                remaining -= fill_at_level
                levels_consumed += 1

            # Calculate average fill price
            filled_size = size - remaining
            if filled_size > 0:
                avg_fill_price = total_cost / filled_size
            else:
                # Not enough liquidity
                avg_fill_price = mid_price * (1 + max_slippage_pct / 100)

            # Calculate slippage
            if side == OrderSide.BUY:
                slippage_pct = (avg_fill_price - mid_price) / mid_price * 100
            else:
                slippage_pct = (mid_price - avg_fill_price) / mid_price * 100

            # Adjust based on historical accuracy
            slippage_pct = self._adjust_estimate(symbol, side, slippage_pct)

            # Check acceptability
            is_acceptable = slippage_pct <= max_slippage_pct
            reason = ""
            if not is_acceptable:
                reason = f"Estimated slippage {slippage_pct:.2f}% exceeds max {max_slippage_pct:.2f}%"
            elif remaining > 0:
                reason = f"Insufficient liquidity: only {filled_size:.4f} of {size:.4f} available"
                is_acceptable = filled_size >= size * 0.8  # Accept if >= 80% fillable

            # Calculate available liquidity
            if levels:
                available = levels[-1].get('cumulative', 0) if levels else 0
            else:
                available = 0

            return SlippageEstimate(
                symbol=symbol,
                side=side,
                size=size,
                mid_price=mid_price,
                estimated_fill_price=avg_fill_price,
                estimated_slippage_pct=slippage_pct,
                available_liquidity=available,
                depth_levels_consumed=levels_consumed,
                is_acceptable=is_acceptable,
                reason=reason
            )

    def _estimate_from_history(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        max_slippage_pct: float
    ) -> SlippageEstimate:
        """Estimate slippage from historical data."""
        history = self._history.get(symbol, [])

        if history:
            # Use average of recent fills for same side
            same_side = [r for r in history if r.side == side]
            if same_side:
                avg_slippage = sum(r.slippage_pct for r in same_side[-10:]) / min(len(same_side), 10)
                estimated_slippage = avg_slippage * self._config.adjustment_factor
            else:
                estimated_slippage = 0.1  # Default 10 bps
        else:
            estimated_slippage = 0.1  # Default 10 bps

        return SlippageEstimate(
            symbol=symbol,
            side=side,
            size=size,
            mid_price=0,
            estimated_fill_price=0,
            estimated_slippage_pct=estimated_slippage,
            available_liquidity=0,
            depth_levels_consumed=0,
            is_acceptable=estimated_slippage <= max_slippage_pct,
            reason="Estimated from historical data (no orderbook)"
        )

    def _adjust_estimate(self, symbol: str, side: OrderSide, estimate: float) -> float:
        """Adjust slippage estimate based on historical accuracy."""
        history = self._history.get(symbol, [])
        if not history:
            return estimate * self._config.adjustment_factor

        # Compare recent estimates to actuals
        same_side = [r for r in history[-20:] if r.side == side]
        if not same_side:
            return estimate * self._config.adjustment_factor

        # If actual is typically higher than estimated, increase estimate
        avg_actual = sum(r.slippage_pct for r in same_side) / len(same_side)

        # Simple adjustment: if actual > 0, scale estimate up slightly
        if avg_actual > 0:
            adjustment = 1 + (avg_actual / 100) * 0.5
            return estimate * adjustment

        return estimate

    def record_fill(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        expected_price: float,
        fill_price: float
    ) -> SlippageRecord:
        """
        Record actual slippage from a fill.

        Args:
            symbol: Trading pair
            side: Buy or sell
            size: Fill size
            expected_price: Expected/mid price at order time
            fill_price: Actual fill price

        Returns:
            SlippageRecord with calculated slippage metrics
        """
        # Calculate slippage
        if side == OrderSide.BUY:
            slippage_pct = (fill_price - expected_price) / expected_price * 100
        else:
            slippage_pct = (expected_price - fill_price) / expected_price * 100

        slippage_bps = slippage_pct * 100
        slippage_cost = abs(fill_price - expected_price) * size

        record = SlippageRecord(
            symbol=symbol,
            side=side,
            size=size,
            expected_price=expected_price,
            fill_price=fill_price,
            slippage_pct=slippage_pct,
            slippage_bps=slippage_bps,
            slippage_cost=slippage_cost,
            timestamp_ns=self._now_ns()
        )

        with self._lock:
            self._history[symbol].append(record)

            # Trim history
            if len(self._history[symbol]) > self._config.history_window:
                self._history[symbol] = self._history[symbol][-self._config.history_window:]

            # Update aggregates
            self._total_slippage_cost += slippage_cost
            self._total_fills += 1

        # Log significant slippage
        if abs(slippage_pct) > 0.5:
            self._logger.warning(
                f"HIGH SLIPPAGE: {symbol} {side.value} {size} - "
                f"expected={expected_price:.2f} filled={fill_price:.2f} "
                f"slippage={slippage_bps:.1f}bps"
            )
        else:
            self._logger.debug(
                f"Fill: {symbol} {side.value} slippage={slippage_bps:.1f}bps"
            )

        return record

    def record_from_order_fill(self, fill: OrderFill, expected_price: float) -> SlippageRecord:
        """Record slippage from an OrderFill object."""
        return self.record_fill(
            symbol=fill.symbol,
            side=fill.side,
            size=fill.size,
            expected_price=expected_price,
            fill_price=fill.price
        )

    def check_acceptable(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        is_cascade: bool = False,
        is_exit: bool = False
    ) -> Tuple[bool, SlippageEstimate]:
        """
        Check if order would have acceptable slippage.

        Args:
            symbol: Trading pair
            side: Buy or sell
            size: Order size
            is_cascade: True for cascade entry (higher tolerance)
            is_exit: True for exit/stop (highest tolerance)

        Returns:
            (is_acceptable, SlippageEstimate)
        """
        if is_exit:
            max_slippage = self._config.exit_max_slippage_pct
        elif is_cascade:
            max_slippage = self._config.cascade_max_slippage_pct
        else:
            max_slippage = self._config.default_max_slippage_pct

        estimate = self.estimate_slippage(symbol, side, size, max_slippage)
        return estimate.is_acceptable, estimate

    def get_statistics(self, symbol: str = None) -> Dict:
        """
        Get slippage statistics.

        Args:
            symbol: Optional symbol filter

        Returns:
            Dict with slippage statistics
        """
        with self._lock:
            if symbol:
                records = self._history.get(symbol, [])
            else:
                records = [r for recs in self._history.values() for r in recs]

            if not records:
                return {
                    'total_fills': 0,
                    'avg_slippage_bps': 0,
                    'max_slippage_bps': 0,
                    'total_slippage_cost': 0,
                    'positive_slippage_count': 0,  # Favorable
                    'negative_slippage_count': 0,  # Unfavorable
                }

            slippages = [r.slippage_bps for r in records]

            return {
                'total_fills': len(records),
                'avg_slippage_bps': sum(slippages) / len(slippages),
                'max_slippage_bps': max(slippages),
                'min_slippage_bps': min(slippages),
                'total_slippage_cost': sum(r.slippage_cost for r in records),
                'positive_slippage_count': sum(1 for s in slippages if s < 0),  # Favorable
                'negative_slippage_count': sum(1 for s in slippages if s > 0),  # Unfavorable
                'by_side': {
                    'buy': {
                        'count': sum(1 for r in records if r.side == OrderSide.BUY),
                        'avg_bps': (
                            sum(r.slippage_bps for r in records if r.side == OrderSide.BUY) /
                            max(1, sum(1 for r in records if r.side == OrderSide.BUY))
                        )
                    },
                    'sell': {
                        'count': sum(1 for r in records if r.side == OrderSide.SELL),
                        'avg_bps': (
                            sum(r.slippage_bps for r in records if r.side == OrderSide.SELL) /
                            max(1, sum(1 for r in records if r.side == OrderSide.SELL))
                        )
                    }
                }
            }

    def get_recent_slippage(self, symbol: str, count: int = 10) -> List[SlippageRecord]:
        """Get recent slippage records for a symbol."""
        with self._lock:
            return list(self._history.get(symbol, [])[-count:])

    def get_total_slippage_cost(self) -> float:
        """Get total slippage cost across all fills."""
        with self._lock:
            return self._total_slippage_cost

    def get_total_fill_count(self) -> int:
        """Get total number of fills tracked."""
        with self._lock:
            return self._total_fills

    def reset_statistics(self):
        """Reset all statistics."""
        with self._lock:
            self._history.clear()
            self._total_slippage_cost = 0.0
            self._total_fills = 0

"""Entry Quality Scoring - Data-driven entry validation for cascade sniper.

Based on analysis of 759 ghost trade entries and 4,685 liquidation events:

KEY INSIGHT - EXHAUSTION REVERSAL PATTERN:
Large liquidations mark exhaustion points in price moves:

1. Before SHORT liq (BUY): Price rose +0.16% (squeeze)
   → After SHORT liq: Price often reverses DOWN
   → BEST ENTRY: SHORT after large SHORT liquidation

2. Before LONG liq (SELL): Price fell -0.05% (dump)
   → After LONG liq: Price often reverses UP
   → BEST ENTRY: LONG after large LONG liquidation

SIZE MATTERS:
- 59% of liquidations are tiny (<$1k) - noise
- Only 10% are large (>$10k) - meaningful signal
- Very large (>$50k) are 2.3% but strongest signal

CASCADE BEHAVIOR:
- Large liquidations trigger 1.61x more liquidation value
- Average 5 follow-up events in 60 seconds
- Best cascades: $13k trigger → $245k follow-up (18.44x)

VALIDATED SCORING:
- High score entries: 58% WR, +0.123% avg PnL
- Zero score entries: 41% WR, -0.113% avg PnL
- Negative score: 10% WR, -0.107% avg PnL
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
from collections import deque
import time


class EntryQuality(Enum):
    """Entry quality classification."""
    HIGH = "HIGH"           # Score > 0.5, ~58%+ win rate
    NEUTRAL = "NEUTRAL"     # Score = 0, ~41% win rate
    AVOID = "AVOID"         # Score < 0, ~10% win rate


class LiquidationSide(Enum):
    """Side of liquidation event."""
    BUY = "BUY"    # Short position liquidated (forced buy to close)
    SELL = "SELL"  # Long position liquidated (forced sell to close)


@dataclass
class LiquidationContext:
    """Recent liquidation context for entry scoring."""
    symbol: str
    timestamp: float
    side: LiquidationSide
    value: float  # USD value


class EntryMode(Enum):
    """Entry mode based on liquidation context."""
    EXHAUSTION_REVERSAL = "EXHAUSTION_REVERSAL"  # Enter opposite direction after large liq
    MOMENTUM = "MOMENTUM"                          # Enter same direction as forced flow
    NEUTRAL = "NEUTRAL"                           # No clear signal


@dataclass
class EntryScore:
    """Entry quality score with breakdown."""
    symbol: str
    score: float
    quality: EntryQuality
    mode: EntryMode

    # Score components
    exhaustion_score: float  # Positive: large liq in opposite direction (reversal setup)
    momentum_score: float    # Positive: large liq in same direction (riding flow)
    size_multiplier: float   # Larger liquidations = stronger signal

    # Context
    buy_liqs_before: float   # USD of short liquidations before entry (shorts squeezed)
    sell_liqs_before: float  # USD of long liquidations before entry (longs dumped)
    largest_liq_value: float # Largest single liquidation in window
    total_liq_activity: float

    # Recommendations
    should_enter: bool
    suggested_side: str      # "LONG" or "SHORT" based on analysis
    reason: str


class EntryQualityScorer:
    """Score entry quality based on liquidation context.

    KEY INSIGHT - EXHAUSTION REVERSAL:
    Large liquidations mark exhaustion points. The best entry is:
    - LONG after large LONG liquidation (SELL) - exhausted dump, reversal UP
    - SHORT after large SHORT liquidation (BUY) - exhausted squeeze, reversal DOWN

    Size thresholds (data-driven):
    - Small (<$10k): Noise, ignore
    - Large ($10k-$50k): Meaningful signal
    - Very Large (>$50k): Strongest signal, 2.3% of events

    Architecture:
    1. Track recent liquidation events per symbol
    2. Focus on large liquidations only
    3. Score exhaustion reversal setup
    4. Suggest entry direction based on recent liquidation side
    """

    # Window parameters
    LOOKBACK_WINDOW_SEC = 120.0  # Look 2 min before entry

    # Size thresholds (data-driven)
    MIN_SIGNIFICANT_LIQ = 10_000.0    # Ignore liquidations below $10k
    LARGE_LIQ_THRESHOLD = 50_000.0    # Very strong signal above $50k

    # Scoring parameters
    EXHAUSTION_BASE_SCORE = 1.0       # Base score for exhaustion reversal
    SIZE_MULTIPLIER_FACTOR = 0.00001  # Per $100k of liquidation value

    # Score thresholds
    HIGH_QUALITY_THRESHOLD = 0.5
    AVOID_THRESHOLD = -0.3

    def __init__(self, max_history: int = 1000):
        # Recent liquidation events per symbol
        self._liquidations: dict[str, deque[LiquidationContext]] = {}
        self._max_history = max_history

    def record_liquidation(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        value: float,
        timestamp: Optional[float] = None
    ):
        """Record a liquidation event.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "BUY" (short liquidated) or "SELL" (long liquidated)
            value: USD value of liquidation
            timestamp: Event time (defaults to now)
        """
        if symbol not in self._liquidations:
            self._liquidations[symbol] = deque(maxlen=self._max_history)

        ctx = LiquidationContext(
            symbol=symbol,
            timestamp=timestamp or time.time(),
            side=LiquidationSide(side),
            value=value
        )
        self._liquidations[symbol].append(ctx)

    def score_entry(
        self,
        symbol: str,
        intended_side: Optional[str] = None,  # "LONG" or "SHORT", None for auto-suggest
        timestamp: Optional[float] = None
    ) -> EntryScore:
        """Score an entry opportunity based on liquidation context.

        EXHAUSTION REVERSAL PATTERN:
        - After large LONG liq (SELL): Price was falling, now exhausted → LONG
        - After large SHORT liq (BUY): Price was rising, now exhausted → SHORT

        Args:
            symbol: Trading symbol
            intended_side: Direction of intended entry (optional, will suggest if None)
            timestamp: Entry time (defaults to now)

        Returns:
            EntryScore with quality classification and suggested direction
        """
        current_time = timestamp or time.time()

        # Get liquidations in window
        liqs = self._liquidations.get(symbol, [])

        liqs_before = [
            l for l in liqs
            if 0 < current_time - l.timestamp < self.LOOKBACK_WINDOW_SEC
        ]

        # Filter to significant liquidations only
        significant_liqs = [l for l in liqs_before if l.value >= self.MIN_SIGNIFICANT_LIQ]
        large_liqs = [l for l in liqs_before if l.value >= self.LARGE_LIQ_THRESHOLD]

        # Calculate liquidation values by side
        buy_liqs = sum(l.value for l in significant_liqs if l.side == LiquidationSide.BUY)
        sell_liqs = sum(l.value for l in significant_liqs if l.side == LiquidationSide.SELL)
        total_activity = buy_liqs + sell_liqs

        # Find largest single liquidation
        largest_liq_value = max((l.value for l in liqs_before), default=0.0)

        # Determine suggested side based on exhaustion reversal
        # SELL liquidations (longs dumped) → exhausted dump → LONG entry
        # BUY liquidations (shorts squeezed) → exhausted squeeze → SHORT entry
        if sell_liqs > buy_liqs * 1.5:  # Strong long liquidations
            suggested_side = "LONG"  # Reversal up after dump
            mode = EntryMode.EXHAUSTION_REVERSAL
        elif buy_liqs > sell_liqs * 1.5:  # Strong short liquidations
            suggested_side = "SHORT"  # Reversal down after squeeze
            mode = EntryMode.EXHAUSTION_REVERSAL
        else:
            suggested_side = "LONG"  # Default
            mode = EntryMode.NEUTRAL

        # Use provided side or suggested
        entry_side = intended_side or suggested_side

        # Calculate exhaustion score (how well setup matches reversal pattern)
        if entry_side == "LONG":
            # LONG benefits from SELL liquidations (exhausted dump)
            exhaustion_score = sell_liqs * self.SIZE_MULTIPLIER_FACTOR
            # Penalized by BUY liquidations (riding into squeeze top)
            momentum_score = -buy_liqs * self.SIZE_MULTIPLIER_FACTOR * 0.5
        else:
            # SHORT benefits from BUY liquidations (exhausted squeeze)
            exhaustion_score = buy_liqs * self.SIZE_MULTIPLIER_FACTOR
            # Penalized by SELL liquidations (riding into dump bottom)
            momentum_score = -sell_liqs * self.SIZE_MULTIPLIER_FACTOR * 0.5

        # Size multiplier - larger liquidations = stronger signal
        size_multiplier = 1.0
        if large_liqs:
            size_multiplier = 1.5  # Boost for very large liquidations
        elif significant_liqs:
            size_multiplier = 1.2  # Moderate boost for significant

        # Calculate final score
        base_score = exhaustion_score + momentum_score
        score = base_score * size_multiplier

        # Cap score
        score = max(-3.0, min(3.0, score))

        # Classify quality
        if score > self.HIGH_QUALITY_THRESHOLD:
            quality = EntryQuality.HIGH
            should_enter = True
            if entry_side == "LONG":
                reason = f"Exhaustion reversal: ${sell_liqs:,.0f} longs liquidated, expect bounce"
            else:
                reason = f"Exhaustion reversal: ${buy_liqs:,.0f} shorts liquidated, expect pullback"
        elif score < self.AVOID_THRESHOLD:
            quality = EntryQuality.AVOID
            should_enter = False
            reason = f"Against exhaustion pattern: entering into ongoing pressure"
        else:
            quality = EntryQuality.NEUTRAL
            should_enter = total_activity > 0  # Enter if there's activity
            if total_activity > 0:
                reason = f"Mixed signal: ${total_activity:,.0f} total liquidations"
            else:
                reason = "No significant liquidation context"

        return EntryScore(
            symbol=symbol,
            score=score,
            quality=quality,
            mode=mode,
            exhaustion_score=exhaustion_score,
            momentum_score=momentum_score,
            size_multiplier=size_multiplier,
            buy_liqs_before=buy_liqs,
            sell_liqs_before=sell_liqs,
            largest_liq_value=largest_liq_value,
            total_liq_activity=total_activity,
            should_enter=should_enter,
            suggested_side=suggested_side,
            reason=reason
        )

    def get_entry_recommendation(
        self,
        symbol: str,
        intended_side: Optional[str] = None,
        min_quality: EntryQuality = EntryQuality.NEUTRAL,
        require_large_liq: bool = False
    ) -> Tuple[bool, EntryScore]:
        """Get entry recommendation with quality filter.

        Args:
            symbol: Trading symbol
            intended_side: "LONG" or "SHORT" (optional, will auto-suggest)
            min_quality: Minimum acceptable quality (default: NEUTRAL)
            require_large_liq: If True, only recommend entry if there's large liq activity

        Returns:
            (should_enter, score) tuple
        """
        score = self.score_entry(symbol, intended_side)

        # Apply quality filter
        quality_order = {
            EntryQuality.HIGH: 2,
            EntryQuality.NEUTRAL: 1,
            EntryQuality.AVOID: 0
        }

        meets_quality = quality_order[score.quality] >= quality_order[min_quality]

        # Check large liquidation requirement
        if require_large_liq and score.largest_liq_value < self.LARGE_LIQ_THRESHOLD:
            return (False, score)

        return (meets_quality and score.should_enter, score)

    def get_best_entry_opportunity(self, symbols: List[str]) -> Optional[EntryScore]:
        """Find the best entry opportunity across multiple symbols.

        Scans all symbols for exhaustion reversal setups and returns
        the highest scoring opportunity.

        Args:
            symbols: List of symbols to scan

        Returns:
            Best EntryScore if any HIGH quality setups found, else None
        """
        best_score = None
        best_entry = None

        for symbol in symbols:
            score = self.score_entry(symbol)
            if score.quality == EntryQuality.HIGH:
                if best_score is None or score.score > best_score:
                    best_score = score.score
                    best_entry = score

        return best_entry

    def get_stats(self) -> dict:
        """Get scoring statistics."""
        total_liqs = sum(len(q) for q in self._liquidations.values())
        symbols = list(self._liquidations.keys())

        return {
            "total_liquidations_tracked": total_liqs,
            "symbols_tracked": len(symbols),
            "symbols": symbols
        }

    def clear_old_data(self, max_age_sec: float = 300.0):
        """Clear liquidation data older than max_age."""
        current_time = time.time()
        cutoff = current_time - max_age_sec

        for symbol in self._liquidations:
            # Remove old entries
            while self._liquidations[symbol] and self._liquidations[symbol][0].timestamp < cutoff:
                self._liquidations[symbol].popleft()

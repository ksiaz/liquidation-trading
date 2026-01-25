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

# Import directional context for kill-switch (via observation layer)
from observation.types import (
    TrendRegimeContext,
    TrendDirection,
)


class EntryQuality(Enum):
    """Entry quality classification.

    SKIP: Trend kill-switch activated - entry blocked by trend context
    AVOID: Against exhaustion pattern - entry allowed but discouraged
    NEUTRAL: Mixed signal - entry allowed
    HIGH: Strong exhaustion reversal setup - entry recommended
    """
    SKIP = "SKIP"           # BLOCKED: Trend kill-switch (do not enter)
    AVOID = "AVOID"         # Score < 0, ~10% win rate
    NEUTRAL = "NEUTRAL"     # Score = 0, ~41% win rate
    HIGH = "HIGH"           # Score > 0.5, ~58%+ win rate


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

    # Trend context (for kill-switch)
    trend_direction: Optional[TrendDirection] = None
    trend_blocked: bool = False  # True if trend kill-switch activated
    trend_bonus: float = 0.0     # Bonus for trend-aligned entries

    # Recommendations
    should_enter: bool = False
    suggested_side: str = ""     # "LONG" or "SHORT" based on analysis
    reason: str = ""


class EntryQualityScorer:
    """Score entry quality based on liquidation context WITH TREND KILL-SWITCH.

    H8-A: Filter hit rate logging for observability.

    KEY INSIGHT - EXHAUSTION REVERSAL:
    Large liquidations mark exhaustion points. The best entry is:
    - LONG after large LONG liquidation (SELL) - exhausted dump, reversal UP
    - SHORT after large SHORT liquidation (BUY) - exhausted squeeze, reversal DOWN

    TREND KILL-SWITCH (hardening):
    Entries are BLOCKED when trend context is dangerous:
    - Fading strong directional moves (STRONG_DOWN with aligned delta)
    - Reversal entries against high-strength trends

    TREND BONUS (enhancement):
    Entries aligned with trend get a score bonus:
    - LONG in weak uptrend = aligned, bonus applied
    - SHORT in weak downtrend = aligned, bonus applied

    Size thresholds (data-driven):
    - Small (<$10k): Noise, ignore
    - Large ($10k-$50k): Meaningful signal
    - Very Large (>$50k): Strongest signal, 2.3% of events

    Architecture:
    1. Track recent liquidation events per symbol
    2. Focus on large liquidations only
    3. Check trend kill-switch FIRST (blocks entry before scoring)
    4. Score exhaustion reversal setup
    5. Apply trend bonus for aligned entries
    6. Suggest entry direction based on analysis
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

    # Trend kill-switch thresholds
    TREND_STRENGTH_BLOCK_THRESHOLD = 0.7   # Block entry if trend strength > 70%
    TREND_ALIGNED_BONUS = 0.3              # Bonus for trend-aligned entries

    def __init__(self, max_history: int = 1000):
        # Recent liquidation events per symbol
        self._liquidations: dict[str, deque[LiquidationContext]] = {}
        self._max_history = max_history

        # H8-A: Filter hit rate tracking for observability
        self._filter_stats = {
            'total_scored': 0,
            'trend_blocked': 0,
            'quality_high': 0,
            'quality_neutral': 0,
            'quality_avoid': 0,
            'quality_skip': 0
        }

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
        timestamp: Optional[float] = None,
        trend_context: Optional[TrendRegimeContext] = None
    ) -> EntryScore:
        """Score an entry opportunity based on liquidation context WITH TREND KILL-SWITCH.

        EXHAUSTION REVERSAL PATTERN:
        - After large LONG liq (SELL): Price was falling, now exhausted → LONG
        - After large SHORT liq (BUY): Price was rising, now exhausted → SHORT

        TREND KILL-SWITCH:
        Entry is BLOCKED (returns SKIP) when:
        - Strong downtrend with aligned delta (distribution, not exhaustion)
        - Fading strong directional moves

        TREND BONUS:
        Entries aligned with trend get a score bonus.

        Args:
            symbol: Trading symbol
            intended_side: Direction of intended entry (optional, will suggest if None)
            timestamp: Entry time (defaults to now)
            trend_context: Optional trend regime context for kill-switch

        Returns:
            EntryScore with quality classification and suggested direction
        """
        current_time = timestamp or time.time()

        # H8-A: Track filter calls
        self._filter_stats['total_scored'] += 1

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

        # =====================================================================
        # TREND KILL-SWITCH CHECK (before any scoring)
        # =====================================================================
        trend_direction = None
        trend_blocked = False
        trend_bonus = 0.0

        if trend_context is not None:
            trend_direction = trend_context.direction

            # KILL-SWITCH: Block entries that fade strong trends
            if self._is_entry_blocked_by_trend(entry_side, trend_context):
                trend_blocked = True
                # H8-A: Track trend blocks
                self._filter_stats['trend_blocked'] += 1
                self._filter_stats['quality_skip'] += 1

                return EntryScore(
                    symbol=symbol,
                    score=0.0,
                    quality=EntryQuality.SKIP,
                    mode=mode,
                    exhaustion_score=0.0,
                    momentum_score=0.0,
                    size_multiplier=0.0,
                    buy_liqs_before=buy_liqs,
                    sell_liqs_before=sell_liqs,
                    largest_liq_value=largest_liq_value,
                    total_liq_activity=total_activity,
                    trend_direction=trend_direction,
                    trend_blocked=True,
                    trend_bonus=0.0,
                    should_enter=False,
                    suggested_side=suggested_side,
                    reason=self._get_trend_block_reason(entry_side, trend_context)
                )

            # TREND BONUS: Apply bonus for trend-aligned entries
            trend_bonus = self._compute_trend_bonus(entry_side, trend_context)

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

        # Calculate final score (including trend bonus)
        base_score = exhaustion_score + momentum_score
        score = (base_score * size_multiplier) + trend_bonus

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
            if trend_bonus > 0:
                reason += f" (trend-aligned bonus: +{trend_bonus:.2f})"
            # H8-A: Track quality
            self._filter_stats['quality_high'] += 1
        elif score < self.AVOID_THRESHOLD:
            quality = EntryQuality.AVOID
            should_enter = False
            reason = f"Against exhaustion pattern: entering into ongoing pressure"
            # H8-A: Track quality
            self._filter_stats['quality_avoid'] += 1
        else:
            quality = EntryQuality.NEUTRAL
            should_enter = total_activity > 0  # Enter if there's activity
            if total_activity > 0:
                reason = f"Mixed signal: ${total_activity:,.0f} total liquidations"
            else:
                reason = "No significant liquidation context"
            # H8-A: Track quality
            self._filter_stats['quality_neutral'] += 1

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
            trend_direction=trend_direction,
            trend_blocked=trend_blocked,
            trend_bonus=trend_bonus,
            should_enter=should_enter,
            suggested_side=suggested_side,
            reason=reason
        )

    def _is_entry_blocked_by_trend(
        self,
        entry_side: str,
        trend: TrendRegimeContext
    ) -> bool:
        """
        Check if entry should be BLOCKED by trend context.

        BLOCKS entry when:
        1. LONG entry during STRONG_DOWN with aligned delta (distribution)
        2. SHORT entry during STRONG_UP with aligned delta (accumulation)
        3. High trend strength (>70%) with fading direction

        Absorption during strong trend = reload/pause, not reversal.
        """
        # Strong downtrend blocks LONG entries (fading the trend)
        if trend.direction == TrendDirection.STRONG_DOWN:
            if entry_side == "LONG":
                # Delta aligned = distribution continues, not exhaustion
                if trend.delta_direction_aligned:
                    return True
                # High trend strength = strong move, dangerous to fade
                if trend.trend_strength >= self.TREND_STRENGTH_BLOCK_THRESHOLD:
                    return True

        # Strong uptrend blocks SHORT entries (fading the trend)
        if trend.direction == TrendDirection.STRONG_UP:
            if entry_side == "SHORT":
                # Delta aligned = accumulation continues
                if trend.delta_direction_aligned:
                    return True
                # High trend strength = dangerous to fade
                if trend.trend_strength >= self.TREND_STRENGTH_BLOCK_THRESHOLD:
                    return True

        return False

    def _get_trend_block_reason(
        self,
        entry_side: str,
        trend: TrendRegimeContext
    ) -> str:
        """Get reason string for trend-blocked entry."""
        direction_str = trend.direction.name.replace("_", " ").lower()

        if entry_side == "LONG":
            if trend.delta_direction_aligned:
                return f"BLOCKED: LONG entry during {direction_str} with aligned selling (distribution phase)"
            else:
                return f"BLOCKED: LONG entry fading {direction_str} (trend strength {trend.trend_strength:.0%})"
        else:
            if trend.delta_direction_aligned:
                return f"BLOCKED: SHORT entry during {direction_str} with aligned buying (accumulation phase)"
            else:
                return f"BLOCKED: SHORT entry fading {direction_str} (trend strength {trend.trend_strength:.0%})"

    def _compute_trend_bonus(
        self,
        entry_side: str,
        trend: TrendRegimeContext
    ) -> float:
        """
        Compute trend bonus for trend-aligned entries.

        BONUS applied when:
        - LONG in weak/neutral uptrend
        - SHORT in weak/neutral downtrend
        - Entry aligns with overall direction
        """
        # No bonus in neutral trend
        if trend.direction == TrendDirection.NEUTRAL:
            return 0.0

        # LONG aligned with uptrend
        if entry_side == "LONG":
            if trend.direction in (TrendDirection.WEAK_UP, TrendDirection.STRONG_UP):
                return self.TREND_ALIGNED_BONUS * trend.trend_strength

        # SHORT aligned with downtrend
        if entry_side == "SHORT":
            if trend.direction in (TrendDirection.WEAK_DOWN, TrendDirection.STRONG_DOWN):
                return self.TREND_ALIGNED_BONUS * trend.trend_strength

        # Slight penalty for counter-trend entries (but not blocked)
        return -self.TREND_ALIGNED_BONUS * 0.3

    def get_entry_recommendation(
        self,
        symbol: str,
        intended_side: Optional[str] = None,
        min_quality: EntryQuality = EntryQuality.NEUTRAL,
        require_large_liq: bool = False,
        trend_context: Optional[TrendRegimeContext] = None
    ) -> Tuple[bool, EntryScore]:
        """Get entry recommendation with quality filter and trend kill-switch.

        Args:
            symbol: Trading symbol
            intended_side: "LONG" or "SHORT" (optional, will auto-suggest)
            min_quality: Minimum acceptable quality (default: NEUTRAL)
            require_large_liq: If True, only recommend entry if there's large liq activity
            trend_context: Optional trend regime context for kill-switch

        Returns:
            (should_enter, score) tuple
        """
        score = self.score_entry(symbol, intended_side, trend_context=trend_context)

        # SKIP quality = trend blocked, always reject
        if score.quality == EntryQuality.SKIP:
            return (False, score)

        # Apply quality filter
        quality_order = {
            EntryQuality.HIGH: 3,
            EntryQuality.NEUTRAL: 2,
            EntryQuality.AVOID: 1,
            EntryQuality.SKIP: 0
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

    def get_filter_stats(self) -> dict:
        """H8-A: Get filter hit rate statistics for observability."""
        stats = dict(self._filter_stats)
        total = stats['total_scored']
        if total > 0:
            stats['trend_block_rate'] = stats['trend_blocked'] / total
            stats['high_rate'] = stats['quality_high'] / total
            stats['neutral_rate'] = stats['quality_neutral'] / total
            stats['avoid_rate'] = stats['quality_avoid'] / total
            stats['skip_rate'] = stats['quality_skip'] / total
        else:
            stats['trend_block_rate'] = 0.0
            stats['high_rate'] = 0.0
            stats['neutral_rate'] = 0.0
            stats['avoid_rate'] = 0.0
            stats['skip_rate'] = 0.0
        return stats

    def reset_filter_stats(self):
        """H8-A: Reset filter statistics."""
        self._filter_stats = {
            'total_scored': 0,
            'trend_blocked': 0,
            'quality_high': 0,
            'quality_neutral': 0,
            'quality_avoid': 0,
            'quality_skip': 0
        }

    def clear_old_data(self, max_age_sec: float = 300.0):
        """Clear liquidation data older than max_age."""
        current_time = time.time()
        cutoff = current_time - max_age_sec

        for symbol in self._liquidations:
            # Remove old entries
            while self._liquidations[symbol] and self._liquidations[symbol][0].timestamp < cutoff:
                self._liquidations[symbol].popleft()

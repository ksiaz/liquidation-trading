"""Stop Hunt Detector - Detect and capitalize on stop/liquidation hunts.

Stop Hunt Pattern:
1. PRE-HUNT: Liquidity cluster visible (positions near liquidation)
2. HUNT: Price pushed through cluster, triggering stops/liquidations
3. ABSORPTION: Order book absorbs forced liquidations
4. REVERSAL: Price bounces back - ENTRY OPPORTUNITY

Detection Mechanisms:
- Cluster detection: Using Hyperliquid proximity data
- Hunt execution: Price breaks through cluster level
- Absorption confirmation: Book absorbs selling/buying pressure
- Reversal confirmation: Price recovers threshold percentage

Capitalization Strategy:
- Enter LONG after downward stop hunt completes (reversal up)
- Enter SHORT after upward stop hunt completes (reversal down)
- Stop loss below/above the hunt level
- Target previous price before hunt

Data Source Differentiation:
==========================
We CAN differentiate:
- LIQUIDATIONS: Binance forceOrder stream (100% certain - forced closures)
- LIQUIDATION LEVELS: Hyperliquid positions (where liquidations WILL occur)

We CANNOT directly see:
- Stop loss orders (hidden until triggered)
- Stop order prices (exchanges don't expose)

We INFER stop clusters through:
- Volume spikes at levels WITHOUT liquidations = likely stops
- Historical swing highs/lows = common stop placement
- Round number levels = psychological stop levels
- Order book walls = possible stop accumulation

LiquidityType enum distinguishes observed vs inferred clusters.

This is NOT market manipulation - it's detecting when manipulation occurs
and positioning to profit from the subsequent reversal.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Deque, Tuple
from enum import Enum


class StopHuntPhase(Enum):
    """Stop hunt lifecycle phases."""
    NONE = "NONE"                  # No hunt detected
    CLUSTER_DETECTED = "CLUSTER"   # Liquidity cluster visible
    HUNT_IN_PROGRESS = "HUNTING"   # Price moving toward cluster
    HUNT_TRIGGERED = "TRIGGERED"   # Stops/liquidations triggered
    ABSORBING = "ABSORBING"        # Book absorbing liquidations
    REVERSAL = "REVERSAL"          # Price reversing - ENTRY WINDOW
    COMPLETED = "COMPLETED"        # Hunt cycle complete


class HuntDirection(Enum):
    """Direction of the stop hunt."""
    DOWNWARD = "DOWNWARD"  # Hunt longs (price drops to hit long stops)
    UPWARD = "UPWARD"      # Hunt shorts (price rises to hit short stops)


class LiquidityType(Enum):
    """Type of liquidity cluster - distinguishes observed vs inferred.

    OBSERVED: We have direct evidence (Hyperliquid positions, Binance liquidations)
    INFERRED: We deduce from indirect signals (volume spikes, orderbook patterns)
    """
    LIQUIDATION_OBSERVED = "LIQUIDATION_OBSERVED"    # From HL positions (100% certain)
    LIQUIDATION_TRIGGERED = "LIQUIDATION_TRIGGERED"  # From Binance forceOrder (100% certain)
    STOP_INFERRED_VOLUME = "STOP_INFERRED_VOLUME"    # Volume spike without liquidation
    STOP_INFERRED_LEVEL = "STOP_INFERRED_LEVEL"      # Round number or technical level
    STOP_INFERRED_BOOK = "STOP_INFERRED_BOOK"        # Large orderbook wall


@dataclass
class LiquidityCluster:
    """A detected cluster of liquidations/stops."""
    symbol: str
    direction: HuntDirection      # Which side will be hunted
    cluster_price: float          # Price level of the cluster
    positions_count: int          # Number of positions at risk
    total_value: float            # Total value at risk ($USD)
    closest_liq_price: float      # Closest liquidation price
    distance_pct: float           # Distance from current price (%)
    timestamp: float
    liquidity_type: LiquidityType = LiquidityType.LIQUIDATION_OBSERVED  # Observed vs inferred
    confidence: float = 1.0       # 1.0 = observed, <1.0 = inferred based on signals


@dataclass
class StopHuntEvent:
    """A detected stop hunt event."""
    symbol: str
    phase: StopHuntPhase
    direction: HuntDirection

    # Cluster data
    cluster_price: float
    positions_triggered: int
    value_triggered: float

    # Price data
    price_before_hunt: float
    price_at_hunt: float
    price_current: float

    # Timing
    hunt_started: float
    hunt_triggered: float
    timestamp: float

    # Reversal metrics
    reversal_pct: float           # How much price has reversed
    entry_quality: str            # "EARLY", "OPTIMAL", "LATE", "MISSED"

    # Entry suggestion
    suggested_entry: Optional[str]  # "LONG" or "SHORT"
    stop_loss_price: float
    target_price: float


@dataclass
class StopHuntStats:
    """Statistics for stop hunt detection."""
    hunts_detected: int = 0
    hunts_by_direction: Dict[str, int] = field(default_factory=lambda: {"DOWNWARD": 0, "UPWARD": 0})
    successful_reversals: int = 0
    average_reversal_pct: float = 0.0
    average_hunt_duration_sec: float = 0.0
    # F6: Regime-blocked entries
    entries_blocked_by_regime: int = 0


@dataclass
class RegimeContext:
    """F6: Regime context for stop-hunt filtering.

    Stop-hunts may NOT reverse in strong trends - we must block entries.
    """
    # Trend strength (0.0 = no trend, 1.0 = very strong trend)
    trend_strength: float = 0.0

    # Trend direction: "BULLISH", "BEARISH", or None
    trend_direction: Optional[str] = None

    # Funding rate bias: positive = longs paying, negative = shorts paying
    funding_rate: float = 0.0

    # Whale activity: True if whales are adding in trend direction
    whale_continuation: bool = False

    # Timestamp of this context
    timestamp: float = 0.0


class StopHuntDetector:
    """Detect stop/liquidation hunts in real-time.

    Uses structural data only - no prediction, just pattern recognition.
    """

    # Detection thresholds
    MIN_CLUSTER_VALUE = 100_000.0      # $100k minimum cluster
    MIN_CLUSTER_POSITIONS = 2          # At least 2 positions
    MAX_CLUSTER_DISTANCE_PCT = 1.0     # Cluster within 1% of price

    # Hunt detection
    HUNT_TRIGGER_DISTANCE_PCT = 0.2    # Price within 0.2% of cluster = hunt started
    PRICE_BREAK_THRESHOLD_PCT = 0.1    # Price must break through cluster by 0.1%

    # Reversal detection
    MIN_REVERSAL_PCT = 0.3             # 0.3% reversal from hunt low/high
    OPTIMAL_REVERSAL_PCT = 0.5         # 0.5% is optimal entry
    MAX_REVERSAL_PCT = 1.0             # 1.0% = getting late

    # Timing
    MAX_HUNT_DURATION_SEC = 60.0       # Hunt should complete within 60s
    ENTRY_WINDOW_SEC = 30.0            # Entry window after reversal starts

    # F6: Regime thresholds for blocking stop-hunt entries
    STRONG_TREND_THRESHOLD = 0.7    # Block if trend_strength > 0.7
    FUNDING_ALIGNMENT_THRESHOLD = 0.0005  # 0.05% funding = significant

    def __init__(self):
        # Active hunts per symbol
        self._active_hunts: Dict[str, StopHuntEvent] = {}

        # Cluster tracking
        self._clusters: Dict[str, LiquidityCluster] = {}

        # Price history for reversal detection
        self._price_history: Dict[str, Deque[Tuple[float, float]]] = {}  # (timestamp, price)

        # Hunt history
        self._completed_hunts: Deque[StopHuntEvent] = deque(maxlen=100)

        # Statistics
        self._stats = StopHuntStats()

        # F6: Regime context per symbol
        self._regime_context: Dict[str, RegimeContext] = {}

    def update_cluster(
        self,
        symbol: str,
        current_price: float,
        long_positions_count: int,
        long_positions_value: float,
        long_closest_liq: Optional[float],
        short_positions_count: int,
        short_positions_value: float,
        short_closest_liq: Optional[float],
        timestamp: float
    ) -> Optional[LiquidityCluster]:
        """Update liquidity cluster detection from proximity data.

        Returns:
            LiquidityCluster if significant cluster detected, None otherwise
        """
        # Guard against division by zero
        if not current_price or current_price <= 0:
            return None

        # Check for LONG cluster (can be hunted downward)
        long_cluster = None
        if (long_positions_count >= self.MIN_CLUSTER_POSITIONS and
            long_positions_value >= self.MIN_CLUSTER_VALUE and
            long_closest_liq is not None):
            distance_pct = abs(current_price - long_closest_liq) / current_price * 100
            if distance_pct <= self.MAX_CLUSTER_DISTANCE_PCT:
                long_cluster = LiquidityCluster(
                    symbol=symbol,
                    direction=HuntDirection.DOWNWARD,
                    cluster_price=long_closest_liq,
                    positions_count=long_positions_count,
                    total_value=long_positions_value,
                    closest_liq_price=long_closest_liq,
                    distance_pct=distance_pct,
                    timestamp=timestamp
                )

        # Check for SHORT cluster (can be hunted upward)
        short_cluster = None
        if (short_positions_count >= self.MIN_CLUSTER_POSITIONS and
            short_positions_value >= self.MIN_CLUSTER_VALUE and
            short_closest_liq is not None):
            distance_pct = abs(short_closest_liq - current_price) / current_price * 100
            if distance_pct <= self.MAX_CLUSTER_DISTANCE_PCT:
                short_cluster = LiquidityCluster(
                    symbol=symbol,
                    direction=HuntDirection.UPWARD,
                    cluster_price=short_closest_liq,
                    positions_count=short_positions_count,
                    total_value=short_positions_value,
                    closest_liq_price=short_closest_liq,
                    distance_pct=distance_pct,
                    timestamp=timestamp
                )

        # Pick the more significant cluster (higher value)
        best_cluster = None
        if long_cluster and short_cluster:
            best_cluster = long_cluster if long_cluster.total_value > short_cluster.total_value else short_cluster
        elif long_cluster:
            best_cluster = long_cluster
        elif short_cluster:
            best_cluster = short_cluster

        if best_cluster:
            self._clusters[symbol] = best_cluster
        elif symbol in self._clusters:
            del self._clusters[symbol]

        return best_cluster

    def update_price(
        self,
        symbol: str,
        price: float,
        timestamp: float
    ) -> Optional[StopHuntEvent]:
        """Update price and check for stop hunt patterns.

        Returns:
            StopHuntEvent if hunt detected/updated, None otherwise
        """
        # Store price
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=300)  # 5 minutes at 1s intervals
        self._price_history[symbol].append((timestamp, price))

        # Check for active hunt
        if symbol in self._active_hunts:
            return self._update_active_hunt(symbol, price, timestamp)

        # Check if cluster exists and hunt is starting
        cluster = self._clusters.get(symbol)
        if cluster is None:
            return None

        return self._check_hunt_start(symbol, cluster, price, timestamp)

    def _check_hunt_start(
        self,
        symbol: str,
        cluster: LiquidityCluster,
        price: float,
        timestamp: float
    ) -> Optional[StopHuntEvent]:
        """Check if a stop hunt is starting."""
        # Get pre-hunt price (price from 30s ago or earliest available)
        history = list(self._price_history.get(symbol, []))
        price_before = price
        for ts, p in history:
            if timestamp - ts >= 30:
                price_before = p
                break

        # Calculate distance to cluster
        if cluster.direction == HuntDirection.DOWNWARD:
            # Hunting longs - price dropping toward cluster
            distance_to_cluster = (price - cluster.cluster_price) / price * 100
            is_approaching = distance_to_cluster <= self.HUNT_TRIGGER_DISTANCE_PCT and distance_to_cluster >= 0
            has_broken = price <= cluster.cluster_price * (1 - self.PRICE_BREAK_THRESHOLD_PCT / 100)
        else:
            # Hunting shorts - price rising toward cluster
            distance_to_cluster = (cluster.cluster_price - price) / price * 100
            is_approaching = distance_to_cluster <= self.HUNT_TRIGGER_DISTANCE_PCT and distance_to_cluster >= 0
            has_broken = price >= cluster.cluster_price * (1 + self.PRICE_BREAK_THRESHOLD_PCT / 100)

        if is_approaching or has_broken:
            # Hunt started
            phase = StopHuntPhase.HUNT_TRIGGERED if has_broken else StopHuntPhase.HUNT_IN_PROGRESS

            hunt = StopHuntEvent(
                symbol=symbol,
                phase=phase,
                direction=cluster.direction,
                cluster_price=cluster.cluster_price,
                positions_triggered=cluster.positions_count,
                value_triggered=cluster.total_value,
                price_before_hunt=price_before,
                price_at_hunt=price,
                price_current=price,
                hunt_started=timestamp,
                hunt_triggered=timestamp if has_broken else 0,
                timestamp=timestamp,
                reversal_pct=0,
                entry_quality="EARLY" if has_broken else "NONE",
                suggested_entry=None,
                stop_loss_price=cluster.cluster_price,
                target_price=price_before
            )

            self._active_hunts[symbol] = hunt
            self._stats.hunts_detected += 1
            self._stats.hunts_by_direction[cluster.direction.value] += 1

            print(f"[STOP HUNT] {symbol}: {cluster.direction.value} hunt STARTED")
            print(f"  Cluster: {cluster.positions_count} pos, ${cluster.total_value:,.0f} @ {cluster.cluster_price:.2f}")
            print(f"  Current: {price:.2f}, Distance: {distance_to_cluster:.2f}%")

            return hunt

        return None

    def _update_active_hunt(
        self,
        symbol: str,
        price: float,
        timestamp: float
    ) -> Optional[StopHuntEvent]:
        """Update an active stop hunt."""
        hunt = self._active_hunts[symbol]
        hunt_duration = timestamp - hunt.hunt_started

        # Check for timeout
        if hunt_duration > self.MAX_HUNT_DURATION_SEC:
            print(f"[STOP HUNT] {symbol}: Hunt TIMED OUT after {hunt_duration:.0f}s")
            self._complete_hunt(symbol, hunt)
            return None

        # Update current price
        old_phase = hunt.phase

        # Track hunt extreme price
        if hunt.direction == HuntDirection.DOWNWARD:
            # Track lowest price during hunt
            if price < hunt.price_at_hunt:
                hunt = StopHuntEvent(
                    **{**hunt.__dict__,
                       'price_at_hunt': price,
                       'hunt_triggered': timestamp if hunt.hunt_triggered == 0 else hunt.hunt_triggered,
                       'phase': StopHuntPhase.HUNT_TRIGGERED if hunt.phase == StopHuntPhase.HUNT_IN_PROGRESS else hunt.phase}
                )

            # Check for reversal (price bouncing back up)
            if hunt.price_at_hunt > 0:
                reversal_pct = (price - hunt.price_at_hunt) / hunt.price_at_hunt * 100

                if reversal_pct >= self.MIN_REVERSAL_PCT:
                    # Determine entry quality
                    if reversal_pct < self.OPTIMAL_REVERSAL_PCT:
                        entry_quality = "EARLY"
                    elif reversal_pct < self.MAX_REVERSAL_PCT:
                        entry_quality = "OPTIMAL"
                    else:
                        entry_quality = "LATE"

                    hunt = StopHuntEvent(
                        **{**hunt.__dict__,
                           'phase': StopHuntPhase.REVERSAL,
                           'reversal_pct': reversal_pct,
                           'entry_quality': entry_quality,
                           'suggested_entry': "LONG",  # After downward hunt, go LONG
                           'price_current': price,
                           'timestamp': timestamp}
                    )

        else:  # UPWARD hunt
            # Track highest price during hunt
            if price > hunt.price_at_hunt:
                hunt = StopHuntEvent(
                    **{**hunt.__dict__,
                       'price_at_hunt': price,
                       'hunt_triggered': timestamp if hunt.hunt_triggered == 0 else hunt.hunt_triggered,
                       'phase': StopHuntPhase.HUNT_TRIGGERED if hunt.phase == StopHuntPhase.HUNT_IN_PROGRESS else hunt.phase}
                )

            # Check for reversal (price dropping back down)
            if hunt.price_at_hunt > 0:
                reversal_pct = (hunt.price_at_hunt - price) / hunt.price_at_hunt * 100

                if reversal_pct >= self.MIN_REVERSAL_PCT:
                    if reversal_pct < self.OPTIMAL_REVERSAL_PCT:
                        entry_quality = "EARLY"
                    elif reversal_pct < self.MAX_REVERSAL_PCT:
                        entry_quality = "OPTIMAL"
                    else:
                        entry_quality = "LATE"

                    hunt = StopHuntEvent(
                        **{**hunt.__dict__,
                           'phase': StopHuntPhase.REVERSAL,
                           'reversal_pct': reversal_pct,
                           'entry_quality': entry_quality,
                           'suggested_entry': "SHORT",  # After upward hunt, go SHORT
                           'price_current': price,
                           'timestamp': timestamp}
                    )

        # Store updated hunt
        self._active_hunts[symbol] = hunt

        # Log phase transitions
        if hunt.phase != old_phase:
            print(f"[STOP HUNT] {symbol}: {old_phase.value} -> {hunt.phase.value}")
            if hunt.phase == StopHuntPhase.REVERSAL:
                print(f"  Reversal: {hunt.reversal_pct:.2f}%, Entry: {hunt.entry_quality}")
                print(f"  Suggested: {hunt.suggested_entry} @ {price:.2f}")
                print(f"  Stop loss: {hunt.stop_loss_price:.2f}, Target: {hunt.target_price:.2f}")

        # Check if hunt is complete (reversal exceeded target)
        if hunt.phase == StopHuntPhase.REVERSAL:
            if hunt.direction == HuntDirection.DOWNWARD and price >= hunt.price_before_hunt:
                print(f"[STOP HUNT] {symbol}: Hunt COMPLETED - price recovered to pre-hunt level")
                self._stats.successful_reversals += 1
                self._complete_hunt(symbol, hunt)
            elif hunt.direction == HuntDirection.UPWARD and price <= hunt.price_before_hunt:
                print(f"[STOP HUNT] {symbol}: Hunt COMPLETED - price recovered to pre-hunt level")
                self._stats.successful_reversals += 1
                self._complete_hunt(symbol, hunt)

        return hunt

    def _complete_hunt(self, symbol: str, hunt: StopHuntEvent):
        """Mark a hunt as completed."""
        hunt = StopHuntEvent(
            **{**hunt.__dict__, 'phase': StopHuntPhase.COMPLETED}
        )
        self._completed_hunts.append(hunt)

        if symbol in self._active_hunts:
            del self._active_hunts[symbol]
        if symbol in self._clusters:
            del self._clusters[symbol]

    def update_liquidation(
        self,
        symbol: str,
        side: str,
        value: float,
        price: float,
        timestamp: float
    ) -> Optional[StopHuntEvent]:
        """Update with liquidation event (confirms hunt triggered)."""
        if symbol not in self._active_hunts:
            return None

        hunt = self._active_hunts[symbol]

        # Liquidation confirms hunt
        if hunt.phase in (StopHuntPhase.HUNT_IN_PROGRESS, StopHuntPhase.CLUSTER_DETECTED):
            hunt = StopHuntEvent(
                **{**hunt.__dict__,
                   'phase': StopHuntPhase.HUNT_TRIGGERED,
                   'hunt_triggered': timestamp}
            )
            self._active_hunts[symbol] = hunt

            print(f"[STOP HUNT] {symbol}: Hunt CONFIRMED by liquidation ${value:,.0f}")

        return hunt

    def get_active_hunt(self, symbol: str) -> Optional[StopHuntEvent]:
        """Get active hunt for a symbol."""
        return self._active_hunts.get(symbol)

    def get_cluster(self, symbol: str) -> Optional[LiquidityCluster]:
        """Get current liquidity cluster for a symbol."""
        return self._clusters.get(symbol)

    def update_regime_context(
        self,
        symbol: str,
        trend_strength: float,
        trend_direction: Optional[str],
        funding_rate: float,
        whale_continuation: bool,
        timestamp: float
    ):
        """F6: Update regime context for a symbol.

        Called by observation layer to provide trend/funding data.

        Args:
            symbol: Trading symbol
            trend_strength: 0.0-1.0 trend strength
            trend_direction: "BULLISH", "BEARISH", or None
            funding_rate: Current funding rate
            whale_continuation: Whether whales are adding in trend direction
            timestamp: Current timestamp
        """
        self._regime_context[symbol] = RegimeContext(
            trend_strength=trend_strength,
            trend_direction=trend_direction,
            funding_rate=funding_rate,
            whale_continuation=whale_continuation,
            timestamp=timestamp
        )

    def _check_regime_block(self, symbol: str, entry_direction: str) -> Optional[str]:
        """F6: Check if regime should block this stop-hunt entry.

        Returns:
            Block reason string if entry should be blocked, None if OK
        """
        regime = self._regime_context.get(symbol)
        if regime is None:
            return None  # No regime data = allow entry

        # F6 Block #1: Strong trend against entry direction
        if regime.trend_strength > self.STRONG_TREND_THRESHOLD:
            # In strong uptrend, block SHORT entries (hunt reversals expecting drop)
            # In strong downtrend, block LONG entries (hunt reversals expecting bounce)
            if regime.trend_direction == "BULLISH" and entry_direction == "SHORT":
                return f"F6: Blocked SHORT in strong BULLISH trend (strength={regime.trend_strength:.2f})"
            if regime.trend_direction == "BEARISH" and entry_direction == "LONG":
                return f"F6: Blocked LONG in strong BEARISH trend (strength={regime.trend_strength:.2f})"

        # F6 Block #2: Funding alignment suggests trend continuation
        if abs(regime.funding_rate) > self.FUNDING_ALIGNMENT_THRESHOLD:
            # High positive funding = longs paying = market is long-heavy
            # Shorting against this is risky (stop-hunt shorts may fail)
            if regime.funding_rate > self.FUNDING_ALIGNMENT_THRESHOLD and entry_direction == "SHORT":
                # However, if trend is BEARISH despite high funding, short may work
                if regime.trend_direction != "BEARISH":
                    return f"F6: Blocked SHORT with high positive funding ({regime.funding_rate:.4f})"

            # High negative funding = shorts paying = market is short-heavy
            # Longing against this is risky
            if regime.funding_rate < -self.FUNDING_ALIGNMENT_THRESHOLD and entry_direction == "LONG":
                if regime.trend_direction != "BULLISH":
                    return f"F6: Blocked LONG with high negative funding ({regime.funding_rate:.4f})"

        # F6 Block #3: Whale continuation mode
        if regime.whale_continuation:
            # If whales are adding in trend direction, don't fade
            if regime.trend_direction == "BULLISH" and entry_direction == "SHORT":
                return "F6: Blocked SHORT - whale continuation in BULLISH trend"
            if regime.trend_direction == "BEARISH" and entry_direction == "LONG":
                return "F6: Blocked LONG - whale continuation in BEARISH trend"

        return None  # No block

    def get_entry_opportunity(self, symbol: str) -> Optional[Dict]:
        """Get entry opportunity if hunt is in reversal phase.

        F6: Returns None if regime blocks the entry.

        Returns dict with entry details or None.
        """
        hunt = self._active_hunts.get(symbol)
        if hunt is None or hunt.phase != StopHuntPhase.REVERSAL:
            return None

        # F6: Check regime filter
        block_reason = self._check_regime_block(symbol, hunt.suggested_entry)
        if block_reason:
            print(f"[STOP HUNT] {symbol}: Entry BLOCKED - {block_reason}")
            self._stats.entries_blocked_by_regime += 1
            return None

        return {
            "symbol": symbol,
            "direction": hunt.suggested_entry,
            "entry_price": hunt.price_current,
            "stop_loss": hunt.stop_loss_price,
            "target": hunt.target_price,
            "quality": hunt.entry_quality,
            "reversal_pct": hunt.reversal_pct,
            "hunt_value": hunt.value_triggered,
            "risk_reward": abs(hunt.target_price - hunt.price_current) / abs(hunt.price_current - hunt.stop_loss_price) if hunt.price_current != hunt.stop_loss_price else 0,
            "regime_clear": True  # F6: Indicates regime check passed
        }

    def get_stats(self) -> Dict:
        """Get stop hunt detection statistics."""
        return {
            "hunts_detected": self._stats.hunts_detected,
            "hunts_by_direction": self._stats.hunts_by_direction,
            "successful_reversals": self._stats.successful_reversals,
            "active_hunts": list(self._active_hunts.keys()),
            "clusters_detected": list(self._clusters.keys()),
            "entries_blocked_by_regime": self._stats.entries_blocked_by_regime  # F6
        }

    def get_recent_hunts(self, limit: int = 10) -> List[StopHuntEvent]:
        """Get recent completed hunts."""
        return list(self._completed_hunts)[-limit:]

    # ==========================================================================
    # Stop Cluster Inference Methods
    # ==========================================================================

    def infer_stop_cluster_from_volume(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: float,
        had_liquidation: bool = False
    ) -> Optional[LiquidityCluster]:
        """Infer stop cluster from volume spike at a level WITHOUT liquidation.

        When we see high volume at a level but NO liquidation event,
        it's likely stop losses triggering (not forced liquidations).

        Args:
            symbol: Trading symbol
            price: Price where volume spike occurred
            volume: Volume at this level ($USD)
            timestamp: Current timestamp
            had_liquidation: True if a liquidation occurred at this level

        Returns:
            LiquidityCluster if stops are inferred, None otherwise
        """
        # If there was a liquidation, this is not a stop cluster
        if had_liquidation:
            return None

        # Volume must be significant (proxy for stops)
        MIN_VOLUME_FOR_STOP_INFERENCE = 50_000.0  # $50k volume spike

        if volume < MIN_VOLUME_FOR_STOP_INFERENCE:
            return None

        # Determine direction based on recent price movement
        history = list(self._price_history.get(symbol, []))
        if len(history) < 5:
            return None

        recent_prices = [p for _, p in history[-10:]]
        avg_recent = sum(recent_prices) / len(recent_prices)

        # If price dropped to this level and bounced = long stops hit
        # If price rose to this level and dropped = short stops hit
        if price < avg_recent:
            direction = HuntDirection.DOWNWARD  # Longs were stopped out
        else:
            direction = HuntDirection.UPWARD  # Shorts were stopped out

        # Confidence based on volume magnitude
        confidence = min(1.0, volume / (MIN_VOLUME_FOR_STOP_INFERENCE * 4))

        return LiquidityCluster(
            symbol=symbol,
            direction=direction,
            cluster_price=price,
            positions_count=0,  # Unknown for inferred
            total_value=volume,  # Use volume as proxy
            closest_liq_price=price,
            distance_pct=0.0,
            timestamp=timestamp,
            liquidity_type=LiquidityType.STOP_INFERRED_VOLUME,
            confidence=confidence
        )

    def infer_stop_cluster_from_level(
        self,
        symbol: str,
        current_price: float,
        timestamp: float
    ) -> Optional[LiquidityCluster]:
        """Infer stop clusters at round number psychological levels.

        Traders commonly place stops at:
        - Round numbers ($100,000, $95,000, $90,000)
        - Percentage levels (5%, 10% below entry)
        - Technical levels (recent swing highs/lows)

        This method identifies the nearest round number level
        where stops are likely accumulated.

        Args:
            symbol: Trading symbol
            current_price: Current market price
            timestamp: Current timestamp

        Returns:
            LiquidityCluster at nearest likely stop level
        """
        # Find nearest round number levels
        if current_price >= 10000:
            # For BTC-like prices, round to nearest $1000
            round_unit = 1000
        elif current_price >= 1000:
            # For ETH-like prices, round to nearest $100
            round_unit = 100
        elif current_price >= 100:
            # For SOL-like prices, round to nearest $10
            round_unit = 10
        else:
            # For smaller coins, round to nearest $1
            round_unit = 1

        # Find levels above and below current price
        level_below = (current_price // round_unit) * round_unit
        level_above = level_below + round_unit

        # Calculate distances
        dist_below_pct = (current_price - level_below) / current_price * 100
        dist_above_pct = (level_above - current_price) / current_price * 100

        # If closer to lower level, expect long stops there
        # If closer to upper level, expect short stops there
        if dist_below_pct < dist_above_pct and dist_below_pct <= self.MAX_CLUSTER_DISTANCE_PCT:
            return LiquidityCluster(
                symbol=symbol,
                direction=HuntDirection.DOWNWARD,
                cluster_price=level_below,
                positions_count=0,  # Unknown
                total_value=0,  # Unknown
                closest_liq_price=level_below,
                distance_pct=dist_below_pct,
                timestamp=timestamp,
                liquidity_type=LiquidityType.STOP_INFERRED_LEVEL,
                confidence=0.5  # Medium confidence for level-based inference
            )
        elif dist_above_pct <= self.MAX_CLUSTER_DISTANCE_PCT:
            return LiquidityCluster(
                symbol=symbol,
                direction=HuntDirection.UPWARD,
                cluster_price=level_above,
                positions_count=0,
                total_value=0,
                closest_liq_price=level_above,
                distance_pct=dist_above_pct,
                timestamp=timestamp,
                liquidity_type=LiquidityType.STOP_INFERRED_LEVEL,
                confidence=0.5
            )

        return None

    def infer_stop_cluster_from_orderbook(
        self,
        symbol: str,
        current_price: float,
        orderbook: Dict,
        timestamp: float
    ) -> Optional[LiquidityCluster]:
        """Infer stop cluster from large orderbook walls.

        Large resting orders at specific levels may indicate:
        - Market makers defending price levels
        - Iceberg orders hiding larger positions
        - Stop hunting liquidity targets

        Args:
            symbol: Trading symbol
            current_price: Current market price
            orderbook: L2 orderbook data with bids/asks
            timestamp: Current timestamp

        Returns:
            LiquidityCluster if large wall detected, None otherwise
        """
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        if not bids or not asks:
            return None

        # Find largest wall in top 20 levels
        MIN_WALL_SIZE = 100_000.0  # $100k wall

        # Check bid walls (could be stop hunt targets below)
        largest_bid_wall = 0
        largest_bid_price = 0
        for bid in bids[:20]:
            price = float(bid.get('px', 0)) if isinstance(bid, dict) else float(bid[0])
            size = float(bid.get('sz', 0)) if isinstance(bid, dict) else float(bid[1])
            value = size * price
            if value > largest_bid_wall:
                largest_bid_wall = value
                largest_bid_price = price

        # Check ask walls (could be stop hunt targets above)
        largest_ask_wall = 0
        largest_ask_price = 0
        for ask in asks[:20]:
            price = float(ask.get('px', 0)) if isinstance(ask, dict) else float(ask[0])
            size = float(ask.get('sz', 0)) if isinstance(ask, dict) else float(ask[1])
            value = size * price
            if value > largest_ask_wall:
                largest_ask_wall = value
                largest_ask_price = price

        # Return cluster for larger wall if significant
        if largest_bid_wall >= MIN_WALL_SIZE and largest_bid_wall > largest_ask_wall:
            dist_pct = (current_price - largest_bid_price) / current_price * 100
            if dist_pct <= self.MAX_CLUSTER_DISTANCE_PCT * 2:  # Wider range for book inference
                return LiquidityCluster(
                    symbol=symbol,
                    direction=HuntDirection.DOWNWARD,
                    cluster_price=largest_bid_price,
                    positions_count=0,
                    total_value=largest_bid_wall,
                    closest_liq_price=largest_bid_price,
                    distance_pct=dist_pct,
                    timestamp=timestamp,
                    liquidity_type=LiquidityType.STOP_INFERRED_BOOK,
                    confidence=0.7  # Higher confidence for book-based inference
                )
        elif largest_ask_wall >= MIN_WALL_SIZE:
            dist_pct = (largest_ask_price - current_price) / current_price * 100
            if dist_pct <= self.MAX_CLUSTER_DISTANCE_PCT * 2:
                return LiquidityCluster(
                    symbol=symbol,
                    direction=HuntDirection.UPWARD,
                    cluster_price=largest_ask_price,
                    positions_count=0,
                    total_value=largest_ask_wall,
                    closest_liq_price=largest_ask_price,
                    distance_pct=dist_pct,
                    timestamp=timestamp,
                    liquidity_type=LiquidityType.STOP_INFERRED_BOOK,
                    confidence=0.7
                )

        return None

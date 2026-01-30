"""
M2.5: Candidate Zones

Tracks potential liquidation zones identified from proximity data.
Candidate zones accumulate price action evidence and get validated
when actual liquidations occur, providing context to M2 nodes.

Constitutional Compliance:
- Candidate zones are NOT M2 nodes
- M2 nodes still only created from actual liquidations
- Candidate zones track factual price action, not predictions
"""

import math
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# ==============================================================================
# Configuration
# ==============================================================================

@dataclass(frozen=True)
class CandidateZoneConfig:
    """Configuration for candidate zone creation and management."""

    # Zone creation thresholds
    min_positions_for_zone: int = 3           # Minimum positions to create zone
    min_value_for_zone: float = 50_000.0      # Minimum USD value to create zone

    # Price bucketing
    price_bucket_pct: float = 0.001           # 0.1% price granularity

    # Zone boundaries
    min_zone_width_pct: float = 0.002         # Minimum 0.2% zone width

    # Decay rates (per second)
    active_decay_rate: float = 0.001          # ~11.5 min half-life when active
    dormant_decay_rate: float = 0.0001        # ~115 min half-life when dormant

    # State transitions
    dormant_threshold_sec: float = 300.0      # 5 min without interaction → DORMANT
    expire_threshold_strength: float = 0.05   # Below this → EXPIRED

    # Validation tolerance
    validation_tolerance_pct: float = 0.5     # 50% of zone width for validation match


DEFAULT_CONFIG = CandidateZoneConfig()


# ==============================================================================
# Data Structures
# ==============================================================================

@dataclass
class CandidateZone:
    """
    A potential liquidation zone identified from proximity data.

    NOT an M2 node - this is a "zone of interest" that may become
    validated when actual liquidations occur.
    """

    # Identity
    zone_id: str
    symbol: str
    price_center: float
    price_low: float
    price_high: float

    # Proximity origin
    created_at: float
    initial_positions_at_risk: int
    initial_value_at_risk: float
    dominant_side: str  # 'long' or 'short'

    # Current proximity state
    current_positions_at_risk: int = 0
    current_value_at_risk: float = 0.0
    last_proximity_update: float = 0.0

    # Price action evidence
    price_visits: int = 0
    price_rejections: int = 0
    price_breakthroughs: int = 0
    time_in_zone_sec: float = 0.0
    max_penetration_depth: float = 0.0

    # Volume evidence
    total_volume_in_zone: float = 0.0
    buy_volume_in_zone: float = 0.0
    sell_volume_in_zone: float = 0.0

    # Absorption evidence
    absorption_events: int = 0

    # Lifecycle
    state: str = 'ACTIVE'  # ACTIVE, DORMANT, EXPIRED
    strength: float = 1.0
    last_interaction: float = 0.0

    # Internal tracking
    _currently_in_zone: bool = field(default=False, repr=False)
    _zone_entry_time: float = field(default=0.0, repr=False)

    @property
    def zone_width(self) -> float:
        return self.price_high - self.price_low

    @property
    def age_sec(self) -> float:
        return time.time() - self.created_at


@dataclass
class M2NodeContext:
    """
    Context from candidate zone to attach to validated M2 node.
    Provides pre-liquidation knowledge.
    """

    # Pre-liquidation positions
    pre_liq_positions_at_risk: int
    pre_liq_value_at_risk: float

    # Price action history
    price_visits_before_liq: int
    price_rejections_before_liq: int
    price_breakthroughs_before_liq: int
    time_in_zone_before_liq: float

    # Volume history
    volume_before_liq: float
    buy_volume_before_liq: float
    sell_volume_before_liq: float

    # Absorption history
    absorption_events_before_liq: int

    # Candidate zone metadata
    candidate_zone_age_sec: float
    candidate_zone_strength_at_validation: float


@dataclass
class CandidateZoneMetrics:
    """Metrics for monitoring candidate zone system."""

    zones_created: int = 0
    zones_validated: int = 0
    zones_expired: int = 0
    zones_active: int = 0
    zones_dormant: int = 0

    total_price_visits: int = 0
    total_rejections: int = 0
    total_breakthroughs: int = 0

    avg_time_to_validation_sec: float = 0.0
    validation_rate: float = 0.0


# ==============================================================================
# Proximity Cluster
# ==============================================================================

@dataclass
class ProximityCluster:
    """Aggregated proximity alerts at a price level."""

    symbol: str
    price_bucket: float
    positions: List[dict] = field(default_factory=list)

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def total_value(self) -> float:
        return sum(p.get('value', 0) for p in self.positions)

    @property
    def dominant_side(self) -> str:
        long_value = sum(p.get('value', 0) for p in self.positions if p.get('side') == 'long')
        short_value = sum(p.get('value', 0) for p in self.positions if p.get('side') == 'short')
        return 'long' if long_value >= short_value else 'short'


# ==============================================================================
# Candidate Zone Manager
# ==============================================================================

class CandidateZoneManager:
    """
    Manages candidate zones lifecycle.

    Responsibilities:
    - Create candidate zones from proximity clusters
    - Track price action at zones
    - Validate zones when liquidations occur
    - Decay and expire old zones
    """

    def __init__(self, config: CandidateZoneConfig = DEFAULT_CONFIG):
        self._config = config
        self._zones: Dict[str, Dict[str, CandidateZone]] = defaultdict(dict)  # symbol -> zone_id -> zone
        self._proximity_buffer: Dict[str, Dict[float, ProximityCluster]] = defaultdict(dict)  # symbol -> price_bucket -> cluster
        self._prev_prices: Dict[str, float] = {}
        self._metrics = CandidateZoneMetrics()
        self._validation_times: List[float] = []

        logger.info("[CANDIDATE_ZONES] Manager initialized")

    # --------------------------------------------------------------------------
    # Proximity Alert Processing
    # --------------------------------------------------------------------------

    def process_proximity_alert(self, alert) -> Optional[CandidateZone]:
        """
        Process a proximity alert from PositionStateManager.

        Args:
            alert: ProximityAlert with coin, liquidation_price, position_value, side, etc.

        Returns:
            CandidateZone if one was created or updated, None otherwise.
        """
        try:
            # Extract alert data
            symbol = f"{alert.coin}USDT" if not alert.coin.endswith('USDT') else alert.coin
            liq_price = alert.liquidation_price
            value = alert.position_value
            side = alert.side if hasattr(alert, 'side') else 'unknown'

            # Calculate price bucket
            price_bucket = self._calculate_price_bucket(liq_price)

            # Add to proximity buffer
            if price_bucket not in self._proximity_buffer[symbol]:
                self._proximity_buffer[symbol][price_bucket] = ProximityCluster(
                    symbol=symbol,
                    price_bucket=price_bucket
                )

            cluster = self._proximity_buffer[symbol][price_bucket]
            cluster.positions.append({
                'price': liq_price,
                'value': value,
                'side': side,
                'timestamp': time.time()
            })

            # Check if cluster warrants a zone
            if self._should_create_zone(cluster):
                return self._create_or_update_zone(cluster)

            return None

        except Exception as e:
            logger.error(f"[CANDIDATE_ZONES] Error processing proximity alert: {e}")
            return None

    def _calculate_price_bucket(self, price: float) -> float:
        """Calculate price bucket for clustering."""
        bucket_size = price * self._config.price_bucket_pct
        return round(price / bucket_size) * bucket_size

    def _should_create_zone(self, cluster: ProximityCluster) -> bool:
        """Determine if cluster warrants a candidate zone."""
        return (
            cluster.position_count >= self._config.min_positions_for_zone
            or cluster.total_value >= self._config.min_value_for_zone
        )

    def _create_or_update_zone(self, cluster: ProximityCluster) -> CandidateZone:
        """Create new zone or update existing one from cluster."""
        symbol = cluster.symbol

        # Calculate zone boundaries
        prices = [p['price'] for p in cluster.positions]
        price_center = sum(prices) / len(prices)

        # Zone width: range of positions or minimum width
        price_min = min(prices)
        price_max = max(prices)
        natural_width = price_max - price_min
        min_width = price_center * self._config.min_zone_width_pct

        half_width = max(natural_width / 2, min_width / 2)
        price_low = price_center - half_width
        price_high = price_center + half_width

        # Generate zone ID
        zone_id = f"{symbol}_candidate_{self._calculate_price_bucket(price_center):.0f}"

        # Check for existing zone
        if zone_id in self._zones[symbol]:
            zone = self._zones[symbol][zone_id]
            # Update existing zone
            zone.current_positions_at_risk = cluster.position_count
            zone.current_value_at_risk = cluster.total_value
            zone.last_proximity_update = time.time()
            zone.last_interaction = time.time()
            zone.strength = min(1.0, zone.strength + 0.1)  # Boost on update
            if zone.state == 'DORMANT':
                zone.state = 'ACTIVE'
            return zone

        # Create new zone
        now = time.time()
        zone = CandidateZone(
            zone_id=zone_id,
            symbol=symbol,
            price_center=price_center,
            price_low=price_low,
            price_high=price_high,
            created_at=now,
            initial_positions_at_risk=cluster.position_count,
            initial_value_at_risk=cluster.total_value,
            dominant_side=cluster.dominant_side,
            current_positions_at_risk=cluster.position_count,
            current_value_at_risk=cluster.total_value,
            last_proximity_update=now,
            last_interaction=now,
            strength=1.0,
            state='ACTIVE'
        )

        self._zones[symbol][zone_id] = zone
        self._metrics.zones_created += 1
        self._metrics.zones_active += 1

        logger.info(
            f"[CANDIDATE_ZONES] Created {zone_id}: "
            f"${zone.initial_value_at_risk:,.0f} at risk, "
            f"{zone.initial_positions_at_risk} positions, "
            f"price {zone.price_low:.2f}-{zone.price_high:.2f}"
        )

        return zone

    # --------------------------------------------------------------------------
    # Price Action Tracking
    # --------------------------------------------------------------------------

    def update_from_price(self, symbol: str, current_price: float, prev_price: Optional[float] = None) -> None:
        """
        Update candidate zones based on price movement.

        Args:
            symbol: Trading pair symbol
            current_price: Current price
            prev_price: Previous price (optional, uses internal tracking if not provided)
        """
        if prev_price is None:
            prev_price = self._prev_prices.get(symbol, current_price)

        self._prev_prices[symbol] = current_price

        if symbol not in self._zones:
            return

        now = time.time()

        for zone in list(self._zones[symbol].values()):
            if zone.state == 'EXPIRED':
                continue

            was_in_zone = zone.price_low <= prev_price <= zone.price_high
            is_in_zone = zone.price_low <= current_price <= zone.price_high

            # Track zone entry
            if not was_in_zone and is_in_zone:
                zone.price_visits += 1
                zone.last_interaction = now
                zone.strength = min(1.0, zone.strength + 0.05)
                zone._currently_in_zone = True
                zone._zone_entry_time = now
                self._metrics.total_price_visits += 1

                if zone.state == 'DORMANT':
                    zone.state = 'ACTIVE'
                    self._metrics.zones_dormant -= 1
                    self._metrics.zones_active += 1

            # Track zone exit
            elif was_in_zone and not is_in_zone:
                zone._currently_in_zone = False

                # Calculate time spent in zone
                if zone._zone_entry_time > 0:
                    zone.time_in_zone_sec += now - zone._zone_entry_time

                # Determine if rejection or breakthrough
                if self._is_rejection(zone, current_price, prev_price):
                    zone.price_rejections += 1
                    zone.strength = min(1.0, zone.strength + 0.1)
                    self._metrics.total_rejections += 1
                else:
                    zone.price_breakthroughs += 1
                    zone.strength = max(0.0, zone.strength - 0.1)
                    self._metrics.total_breakthroughs += 1

                zone.last_interaction = now

            # Track penetration depth while in zone
            elif is_in_zone:
                # Update time in zone
                if zone._currently_in_zone and zone._zone_entry_time > 0:
                    zone.time_in_zone_sec += now - zone._zone_entry_time
                    zone._zone_entry_time = now

                # Track max penetration
                if zone.dominant_side == 'long':
                    # Longs liquidate below - track how far price went down
                    penetration = zone.price_high - current_price
                else:
                    # Shorts liquidate above - track how far price went up
                    penetration = current_price - zone.price_low

                zone.max_penetration_depth = max(zone.max_penetration_depth, penetration)

    def _is_rejection(self, zone: CandidateZone, current_price: float, prev_price: float) -> bool:
        """Determine if price movement was a rejection from zone."""
        zone_center = zone.price_center

        # Rejection: price moved away from zone center after being in zone
        if zone.dominant_side == 'long':
            # For long liquidation zones (below price), rejection = price bounced up
            return current_price > zone.price_high and prev_price < current_price
        else:
            # For short liquidation zones (above price), rejection = price bounced down
            return current_price < zone.price_low and prev_price > current_price

    def update_volume(self, symbol: str, price: float, volume: float, is_buy: bool) -> None:
        """Update volume metrics for zones containing the trade price."""
        if symbol not in self._zones:
            return

        for zone in self._zones[symbol].values():
            if zone.state == 'EXPIRED':
                continue

            if zone.price_low <= price <= zone.price_high:
                zone.total_volume_in_zone += volume
                if is_buy:
                    zone.buy_volume_in_zone += volume
                else:
                    zone.sell_volume_in_zone += volume
                zone.last_interaction = time.time()

    def record_absorption(self, symbol: str, price: float) -> None:
        """Record an absorption event at price level."""
        if symbol not in self._zones:
            return

        for zone in self._zones[symbol].values():
            if zone.state == 'EXPIRED':
                continue

            if zone.price_low <= price <= zone.price_high:
                zone.absorption_events += 1
                zone.strength = min(1.0, zone.strength + 0.15)
                zone.last_interaction = time.time()

    # --------------------------------------------------------------------------
    # Validation (Candidate → M2 Context)
    # --------------------------------------------------------------------------

    def validate_zone(self, symbol: str, liquidation_price: float) -> Optional[M2NodeContext]:
        """
        Check if liquidation validates a candidate zone.

        Args:
            symbol: Trading pair symbol
            liquidation_price: Price where liquidation occurred

        Returns:
            M2NodeContext if a zone was validated, None otherwise.
        """
        if symbol not in self._zones:
            return None

        for zone in list(self._zones[symbol].values()):
            if zone.state == 'EXPIRED':
                continue

            # Check if liquidation is within zone (with tolerance)
            tolerance = zone.zone_width * self._config.validation_tolerance_pct
            if not (zone.price_low - tolerance <= liquidation_price <= zone.price_high + tolerance):
                continue

            # Zone validated!
            now = time.time()
            age = now - zone.created_at

            context = M2NodeContext(
                pre_liq_positions_at_risk=zone.initial_positions_at_risk,
                pre_liq_value_at_risk=zone.initial_value_at_risk,
                price_visits_before_liq=zone.price_visits,
                price_rejections_before_liq=zone.price_rejections,
                price_breakthroughs_before_liq=zone.price_breakthroughs,
                time_in_zone_before_liq=zone.time_in_zone_sec,
                volume_before_liq=zone.total_volume_in_zone,
                buy_volume_before_liq=zone.buy_volume_in_zone,
                sell_volume_before_liq=zone.sell_volume_in_zone,
                absorption_events_before_liq=zone.absorption_events,
                candidate_zone_age_sec=age,
                candidate_zone_strength_at_validation=zone.strength
            )

            # Mark zone as validated (remove it)
            self._metrics.zones_validated += 1
            self._validation_times.append(age)
            if zone.state == 'ACTIVE':
                self._metrics.zones_active -= 1
            else:
                self._metrics.zones_dormant -= 1

            del self._zones[symbol][zone.zone_id]

            logger.info(
                f"[CANDIDATE_ZONES] Validated {zone.zone_id}: "
                f"age={age:.0f}s, visits={zone.price_visits}, "
                f"rejections={zone.price_rejections}"
            )

            return context

        return None

    # --------------------------------------------------------------------------
    # Decay & Maintenance
    # --------------------------------------------------------------------------

    def decay_zones(self) -> int:
        """
        Apply time-based decay to all zones.

        Returns:
            Number of zones expired.
        """
        now = time.time()
        expired_count = 0

        for symbol in list(self._zones.keys()):
            for zone_id in list(self._zones[symbol].keys()):
                zone = self._zones[symbol][zone_id]

                if zone.state == 'EXPIRED':
                    continue

                time_since_interaction = now - zone.last_interaction

                # State transition: ACTIVE → DORMANT
                if zone.state == 'ACTIVE' and time_since_interaction > self._config.dormant_threshold_sec:
                    zone.state = 'DORMANT'
                    self._metrics.zones_active -= 1
                    self._metrics.zones_dormant += 1

                # Apply decay
                decay_rate = (
                    self._config.active_decay_rate
                    if zone.state == 'ACTIVE'
                    else self._config.dormant_decay_rate
                )
                zone.strength *= math.exp(-decay_rate * time_since_interaction)

                # Check for expiration
                if zone.strength < self._config.expire_threshold_strength:
                    zone.state = 'EXPIRED'
                    self._metrics.zones_expired += 1
                    if zone.state == 'ACTIVE':
                        self._metrics.zones_active -= 1
                    else:
                        self._metrics.zones_dormant -= 1

                    del self._zones[symbol][zone_id]
                    expired_count += 1

        return expired_count

    def prune_proximity_buffer(self, max_age_sec: float = 60.0) -> int:
        """Prune old entries from proximity buffer."""
        now = time.time()
        pruned = 0

        for symbol in list(self._proximity_buffer.keys()):
            for bucket in list(self._proximity_buffer[symbol].keys()):
                cluster = self._proximity_buffer[symbol][bucket]

                # Remove old positions
                original_count = len(cluster.positions)
                cluster.positions = [
                    p for p in cluster.positions
                    if now - p.get('timestamp', 0) <= max_age_sec
                ]
                pruned += original_count - len(cluster.positions)

                # Remove empty clusters
                if not cluster.positions:
                    del self._proximity_buffer[symbol][bucket]

        return pruned

    # --------------------------------------------------------------------------
    # Query Interface
    # --------------------------------------------------------------------------

    def get_zones(self, symbol: str, state: Optional[str] = None) -> List[CandidateZone]:
        """Get candidate zones for symbol."""
        if symbol not in self._zones:
            return []

        zones = list(self._zones[symbol].values())

        if state:
            zones = [z for z in zones if z.state == state]

        return sorted(zones, key=lambda z: z.strength, reverse=True)

    def get_zone_at_price(self, symbol: str, price: float) -> Optional[CandidateZone]:
        """Get candidate zone containing price."""
        if symbol not in self._zones:
            return None

        for zone in self._zones[symbol].values():
            if zone.state != 'EXPIRED' and zone.price_low <= price <= zone.price_high:
                return zone

        return None

    def get_strongest_zones(self, symbol: str, limit: int = 5) -> List[CandidateZone]:
        """Get top candidate zones by strength."""
        return self.get_zones(symbol)[:limit]

    def get_all_zones(self) -> Dict[str, List[CandidateZone]]:
        """Get all zones grouped by symbol."""
        return {
            symbol: self.get_zones(symbol)
            for symbol in self._zones.keys()
        }

    def get_metrics(self) -> CandidateZoneMetrics:
        """Get candidate zone metrics."""
        # Update computed metrics
        if self._validation_times:
            self._metrics.avg_time_to_validation_sec = sum(self._validation_times) / len(self._validation_times)

        total_resolved = self._metrics.zones_validated + self._metrics.zones_expired
        if total_resolved > 0:
            self._metrics.validation_rate = self._metrics.zones_validated / total_resolved

        return self._metrics

    def compute_zone_quality(self, zone: CandidateZone) -> float:
        """
        Compute quality score for candidate zone.

        Higher score = more likely to be significant when validated.
        """
        # Value score (cap at $500k)
        value_score = min(1.0, zone.current_value_at_risk / 500_000)

        # Rejection score (cap at 5)
        rejection_score = min(1.0, zone.price_rejections / 5)

        # Age score (cap at 1 hour)
        age_score = min(1.0, zone.age_sec / 3600)

        # Absorption score (cap at 3)
        absorption_score = min(1.0, zone.absorption_events / 3)

        # Weighted combination
        quality = (
            value_score * 0.3 +
            rejection_score * 0.3 +
            age_score * 0.2 +
            absorption_score * 0.2
        )

        return quality * zone.strength

    # --------------------------------------------------------------------------
    # Memory Estimation (for ResourceMonitor)
    # --------------------------------------------------------------------------

    def estimate_memory_bytes(self) -> int:
        """Estimate memory usage in bytes."""
        zone_count = sum(len(zones) for zones in self._zones.values())
        buffer_count = sum(
            sum(len(c.positions) for c in clusters.values())
            for clusters in self._proximity_buffer.values()
        )

        # Rough estimates
        bytes_per_zone = 500
        bytes_per_buffer_entry = 100

        return zone_count * bytes_per_zone + buffer_count * bytes_per_buffer_entry

    def get_item_count(self) -> int:
        """Get total item count for monitoring."""
        return sum(len(zones) for zones in self._zones.values())

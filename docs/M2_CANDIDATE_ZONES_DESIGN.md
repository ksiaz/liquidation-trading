# M2.5: Candidate Zones Design Document

## Overview

This document specifies the **Candidate Zone** layer (M2.5), which bridges proximity data and validated M2 nodes. Candidate zones track potential liquidation levels and accumulate market behavior evidence BEFORE liquidations occur.

## Problem Statement

The current architecture has a gap:

1. **Proximity data** identifies WHERE liquidations COULD happen (positions near liquidation price)
2. **M2 nodes** are created ONLY when liquidations ACTUALLY happen
3. **No mechanism** exists to track market behavior at potential liquidation levels before validation

This means:
- System is "blind" to potential zones until liquidation occurs
- No pre-liquidation context when M2 nodes are created
- Price action at unvalidated levels is lost

## Design Goals

1. **Pre-knowledge**: Know where liquidations could happen before they do
2. **Price action tracking**: Record how market behaves at potential zones
3. **Richer validation**: When liquidation occurs, M2 node inherits behavioral context
4. **Progressive learning**: Build knowledge over time from price action
5. **Constitutional compliance**: M2 nodes still only from actual liquidations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PROXIMITY ALERTS                                            │
│  (positions crossing CRITICAL/WATCHLIST thresholds)          │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  CANDIDATE ZONE AGGREGATOR                                   │
│  - Cluster nearby proximity alerts by price level            │
│  - Minimum cluster size to create candidate zone             │
│  - Track aggregate position value at risk                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  M2.5: CANDIDATE ZONES                                       │
│  - Price level where liquidations COULD occur                │
│  - NOT validated (no liquidation yet)                        │
│  - Accumulate price action evidence                          │
│  - Faster decay than M2 nodes                                │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ When actual liquidation occurs at/near zone
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  M2: VALIDATED NODES                                         │
│  - Created from actual liquidation event                     │
│  - Inherit candidate zone context (if existed)               │
│  - Full M2 lifecycle (ACTIVE → DORMANT → ARCHIVED)          │
└─────────────────────────────────────────────────────────────┘
```

---

## Candidate Zone Data Structure

```python
@dataclass
class CandidateZone:
    """
    A potential liquidation zone identified from proximity data.

    NOT an M2 node - this is a "zone of interest" that may become
    validated when actual liquidations occur.
    """

    # Identity
    zone_id: str                      # {symbol}_{price_bucket}
    symbol: str
    price_center: float               # Center of the zone
    price_low: float                  # Lower boundary
    price_high: float                 # Upper boundary

    # Proximity Origin (why this zone was created)
    created_at: float                 # Timestamp of creation
    initial_positions_at_risk: int    # Positions when zone created
    initial_value_at_risk: float      # USD value when zone created
    dominant_side: str                # 'long' or 'short' - which side would liquidate

    # Current Proximity State (updated on each proximity alert)
    current_positions_at_risk: int    # Current count
    current_value_at_risk: float      # Current USD value
    last_proximity_update: float      # Last proximity alert timestamp

    # Price Action Evidence (accumulated over time)
    price_visits: int                 # Times price entered this zone
    price_rejections: int             # Times price reversed from zone edge
    price_breakthroughs: int          # Times price broke through zone
    time_in_zone_sec: float           # Total time price spent in zone
    max_penetration_depth: float      # Deepest price went into zone

    # Volume Evidence
    total_volume_in_zone: float       # Total trade volume while in zone
    buy_volume_in_zone: float         # Buy-side volume
    sell_volume_in_zone: float        # Sell-side volume

    # Absorption Evidence
    absorption_events: int            # Times orderbook absorbed selling/buying pressure
    rejection_velocity: float         # Average speed of price rejection from zone

    # Lifecycle
    state: str                        # 'ACTIVE', 'DORMANT', 'EXPIRED'
    strength: float                   # 0.0 - 1.0, decays over time
    last_interaction: float           # Last price visit or proximity update
```

---

## Zone Creation Rules

### When to Create a Candidate Zone

A candidate zone is created when:

1. **Proximity cluster detected**:
   - Minimum 3 positions within 2% of same liquidation price level
   - OR minimum $50,000 aggregate value at risk at same level

2. **Price bucket calculation**:
   - Round liquidation prices to 0.1% granularity
   - Group positions into same bucket if within this range

3. **No existing zone**:
   - Check if candidate zone already exists at this level
   - If exists, UPDATE the zone instead of creating new

```python
def should_create_candidate_zone(proximity_cluster) -> bool:
    """Determine if proximity cluster warrants a candidate zone."""
    return (
        proximity_cluster.position_count >= MIN_POSITIONS_FOR_ZONE  # 3
        or proximity_cluster.total_value >= MIN_VALUE_FOR_ZONE      # $50,000
    )
```

### Zone Boundaries

```python
def calculate_zone_boundaries(liquidation_prices: List[float]) -> Tuple[float, float, float]:
    """Calculate zone boundaries from clustered liquidation prices."""
    price_center = statistics.median(liquidation_prices)
    price_std = statistics.stdev(liquidation_prices) if len(liquidation_prices) > 1 else price_center * 0.001

    # Zone width: 2 standard deviations or minimum 0.2% of price
    half_width = max(price_std, price_center * 0.001)

    return (
        price_center - half_width,  # price_low
        price_center,                # price_center
        price_center + half_width   # price_high
    )
```

---

## Price Action Tracking

### Events That Update Candidate Zones

| Event | Update Action |
|-------|---------------|
| Price enters zone | `price_visits += 1`, start tracking time_in_zone |
| Price exits zone (rejection) | `price_rejections += 1`, calculate rejection_velocity |
| Price breaks through zone | `price_breakthroughs += 1` |
| Trade occurs in zone | Update volume metrics |
| Orderbook absorption detected | `absorption_events += 1` |
| Proximity alert at zone | Update positions/value at risk |

### Visit Detection Logic

```python
def update_candidate_zone_from_price(zone: CandidateZone, current_price: float, prev_price: float):
    """Update zone based on price movement."""

    was_in_zone = zone.price_low <= prev_price <= zone.price_high
    is_in_zone = zone.price_low <= current_price <= zone.price_high

    if not was_in_zone and is_in_zone:
        # Price entered zone
        zone.price_visits += 1
        zone.last_interaction = time.time()
        zone.strength = min(1.0, zone.strength + 0.05)  # Boost strength

    elif was_in_zone and not is_in_zone:
        # Price exited zone
        if price_moved_away_from_center(zone, current_price, prev_price):
            # Rejection - price bounced off zone
            zone.price_rejections += 1
            zone.strength = min(1.0, zone.strength + 0.1)  # Stronger signal
        else:
            # Breakthrough - price broke through zone
            zone.price_breakthroughs += 1
            zone.strength = max(0.0, zone.strength - 0.1)  # Weaker zone
```

---

## Decay Model

Candidate zones decay faster than M2 nodes (they're unvalidated):

```python
# Decay rates (per second)
CANDIDATE_ZONE_DECAY_RATE = 0.001      # ~16 min half-life when active
CANDIDATE_ZONE_DORMANT_RATE = 0.0001   # ~160 min half-life when dormant

# State transitions
DORMANT_THRESHOLD_SEC = 300     # 5 min without interaction → DORMANT
EXPIRE_THRESHOLD_STRENGTH = 0.1 # Below this strength → EXPIRED

def decay_candidate_zone(zone: CandidateZone, current_time: float):
    """Apply time-based decay to candidate zone."""

    time_since_interaction = current_time - zone.last_interaction

    # Check for state transition
    if zone.state == 'ACTIVE' and time_since_interaction > DORMANT_THRESHOLD_SEC:
        zone.state = 'DORMANT'

    # Apply decay based on state
    decay_rate = (CANDIDATE_ZONE_DECAY_RATE if zone.state == 'ACTIVE'
                  else CANDIDATE_ZONE_DORMANT_RATE)

    zone.strength *= math.exp(-decay_rate * time_since_interaction)

    # Check for expiration
    if zone.strength < EXPIRE_THRESHOLD_STRENGTH:
        zone.state = 'EXPIRED'
```

---

## Validation: Candidate Zone → M2 Node

When a liquidation occurs, check if it falls within a candidate zone:

```python
def validate_candidate_zone(zone: CandidateZone, liquidation_event) -> Optional[M2NodeContext]:
    """
    Check if liquidation validates a candidate zone.
    Returns context to attach to new M2 node if validated.
    """

    liq_price = liquidation_event.price

    # Check if liquidation is within zone boundaries (with some tolerance)
    tolerance = (zone.price_high - zone.price_low) * 0.5
    if not (zone.price_low - tolerance <= liq_price <= zone.price_high + tolerance):
        return None  # Liquidation not at this zone

    # Zone validated! Prepare context for M2 node
    return M2NodeContext(
        # Pre-liquidation knowledge
        pre_liq_positions_at_risk=zone.initial_positions_at_risk,
        pre_liq_value_at_risk=zone.initial_value_at_risk,

        # Price action history
        price_visits_before_liq=zone.price_visits,
        price_rejections_before_liq=zone.price_rejections,
        price_breakthroughs_before_liq=zone.price_breakthroughs,
        time_in_zone_before_liq=zone.time_in_zone_sec,

        # Volume history
        volume_before_liq=zone.total_volume_in_zone,
        buy_volume_before_liq=zone.buy_volume_in_zone,
        sell_volume_before_liq=zone.sell_volume_in_zone,

        # Absorption history
        absorption_events_before_liq=zone.absorption_events,

        # Candidate zone metadata
        candidate_zone_age_sec=time.time() - zone.created_at,
        candidate_zone_strength_at_validation=zone.strength,
    )
```

### M2 Node Creation with Context

```python
def create_m2_node_from_liquidation(liquidation_event, candidate_context: Optional[M2NodeContext]):
    """Create M2 node, optionally enriched with candidate zone context."""

    node = M2Node(
        # Standard M2 fields from liquidation
        price_center=liquidation_event.price,
        liquidation_volume=liquidation_event.volume,
        liquidation_side=liquidation_event.side,
        # ... other standard fields
    )

    if candidate_context:
        # Attach pre-liquidation knowledge
        node.pre_liquidation_context = candidate_context

        # Boost initial strength based on pre-validation activity
        activity_bonus = min(0.3, candidate_context.price_visits_before_liq * 0.05)
        node.strength += activity_bonus

    return node
```

---

## Query Interface

### Active Candidate Zones

```python
def get_candidate_zones(symbol: str, state: str = 'ACTIVE') -> List[CandidateZone]:
    """Get candidate zones for symbol."""
    pass

def get_candidate_zone_at_price(symbol: str, price: float) -> Optional[CandidateZone]:
    """Get candidate zone containing price, if any."""
    pass

def get_strongest_candidate_zones(symbol: str, limit: int = 5) -> List[CandidateZone]:
    """Get top candidate zones by strength."""
    pass
```

### Zone Quality Metrics

```python
def compute_candidate_zone_quality(zone: CandidateZone) -> float:
    """
    Compute quality score for candidate zone.
    Higher score = more likely to be significant when validated.

    Factors:
    - Positions/value at risk (potential impact)
    - Price rejections (market respects level)
    - Time survived (persistence)
    - Absorption events (orderbook defense)
    """

    value_score = min(1.0, zone.current_value_at_risk / 500_000)  # Cap at $500k
    rejection_score = min(1.0, zone.price_rejections / 5)          # Cap at 5 rejections
    age_score = min(1.0, (time.time() - zone.created_at) / 3600)  # Cap at 1 hour
    absorption_score = min(1.0, zone.absorption_events / 3)        # Cap at 3 absorptions

    # Weighted combination
    return (
        value_score * 0.3 +
        rejection_score * 0.3 +
        age_score * 0.2 +
        absorption_score * 0.2
    ) * zone.strength  # Modulated by current strength
```

---

## Integration Points

### 1. Observation Bridge (proximity alerts → candidate zones)

```python
# In observation_bridge.py _handle_proximity_alert()

async def _handle_proximity_alert(self, alert) -> None:
    # ... existing logging ...

    # Forward to candidate zone manager
    if self._candidate_zone_manager:
        self._candidate_zone_manager.process_proximity_alert(alert)
```

### 2. Price Updates (track price action at zones)

```python
# In collector service price processing

def _process_price_update(self, symbol: str, price: float):
    # ... existing processing ...

    # Update candidate zones
    if self._candidate_zone_manager:
        self._candidate_zone_manager.update_from_price(symbol, price, self._prev_prices.get(symbol))
```

### 3. M2 Node Creation (inherit candidate context)

```python
# In governance.py _create_or_update_node_from_liquidation()

def _create_or_update_node_from_liquidation(self, event):
    # Check for candidate zone at this price
    candidate_context = None
    if self._candidate_zone_manager:
        candidate_zone = self._candidate_zone_manager.get_zone_at_price(
            event['symbol'], event['price']
        )
        if candidate_zone:
            candidate_context = self._candidate_zone_manager.validate_zone(
                candidate_zone, event
            )

    # Create M2 node with context
    self._m2_store.add_or_update_node(
        # ... existing params ...
        candidate_context=candidate_context
    )
```

### 4. Strategy Access (query candidate zones)

```python
# In external_policy strategies

def generate_geometry_proposal(*, candidate_zones: List[CandidateZone], ...):
    """
    Strategy can consider candidate zones in addition to validated M2 nodes.

    Use cases:
    - Avoid entering trades near high-value candidate zones (potential cascade)
    - Increase confidence when M2 zone has rich candidate history
    - Track zone quality over time
    """
    pass
```

---

## Constitutional Compliance

This design maintains M2 constitutional requirements:

| Requirement | How Satisfied |
|-------------|---------------|
| "Nodes created ONLY from liquidations" | ✅ M2 nodes still only from actual liquidations |
| "No predictive resurrection" | ✅ Candidate zones don't become M2 nodes without liquidation |
| "Factual observations only" | ✅ Candidate zones track factual price action, not predictions |
| "No semantic labels" | ✅ Zones are price levels, not "support/resistance" |

**Key distinction:**
- **Candidate zones** = "price levels where liquidations COULD occur" (observational)
- **M2 nodes** = "price levels where liquidations DID occur" (validated)

---

## Implementation Phases

### Phase 1: Core Infrastructure
- [ ] CandidateZone dataclass
- [ ] CandidateZoneManager class
- [ ] Basic create/update/query operations
- [ ] Decay logic

### Phase 2: Price Action Tracking
- [ ] Price visit detection
- [ ] Rejection/breakthrough classification
- [ ] Volume tracking in zones
- [ ] Time-in-zone accumulation

### Phase 3: M2 Integration
- [ ] Validation logic (candidate → M2 context)
- [ ] M2 node context attachment
- [ ] Query interface for strategies

### Phase 4: Strategy Integration
- [ ] Expose candidate zones to geometry strategy
- [ ] Expose candidate zones to cascade sniper
- [ ] Quality scoring for entry decisions

---

## Metrics & Monitoring

```python
@dataclass
class CandidateZoneMetrics:
    zones_created: int
    zones_validated: int          # Became M2 nodes
    zones_expired: int            # Decayed without validation
    avg_time_to_validation: float # How long before liquidation
    avg_price_visits_before_validation: int
    validation_rate: float        # validated / (validated + expired)
```

These metrics help tune thresholds and understand zone quality.

---

## Summary

The Candidate Zone layer (M2.5) bridges proximity data and validated M2 nodes by:

1. **Creating candidate zones** from proximity clusters (potential liquidation levels)
2. **Tracking price action** at these levels (visits, rejections, volume)
3. **Validating zones** when actual liquidations occur (inheriting context)
4. **Building knowledge** over time (more price action = richer understanding)

This enables the system to "know where liquidations could happen" and "remember what market did at each level" - fulfilling the original design vision while maintaining M2 constitutional compliance.

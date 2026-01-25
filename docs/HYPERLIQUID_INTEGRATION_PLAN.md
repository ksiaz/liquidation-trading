# IMPLEMENTATION PLAN: Hyperliquid Integration
## Cascade Detection + Wallet Transparency System

**User Direction**:
- ✅ Cascade detection capabilities (primary goal)
- ✅ Full wallet transparency acceptable (public blockchain)
- ✅ All 4 high-value primitives selected:
  1. liquidation_cascade_proximity
  2. leverage_concentration_ratio
  3. open_interest_directional_bias
  4. cross_venue_zone_divergence

**Status**: This is an implementation plan, not just exploration.

---

## PART 1: Constitutional & Ethical Framework

### Critical Constitutional Constraints

**You selected "full transparency" but we MUST maintain epistemic rules:**

| ✅ ALLOWED | ❌ FORBIDDEN |
|-----------|-------------|
| "50 positions totaling $10M within 2% of liquidation" | "Cascade will occur" |
| "Wallet 0xABC... has $5M position at 15x leverage" | "This is a whale" or "Smart money" |
| "15 wallets positioned long since 14:30" | "Follow these wallets" |
| "Net $50M long across 200 accounts" | "Market is bullish" |
| "Insurance fund declining at $1000/min" | "Exchange is at risk" |

**Wallet Tracking Guardrails** (even with full transparency):
1. ✅ Display wallet addresses (it's public blockchain)
2. ✅ Track individual position patterns
3. ❌ NO "whale score" or "smart money" labels
4. ❌ NO predictive language ("will liquidate", "is bullish")
5. ❌ NO manipulation advice ("front-run this cascade")

### Ethical Red Lines

**Acceptable:**
- Observing cascade proximity (factual position distance calculation)
- Tracking leverage distribution (statistical market structure)
- Open interest aggregation (sum of all positions)
- Cross-venue zone comparison (structural divergence measurement)

**Questionable (proceed with caution):**
- Multi-account clustering (de-anonymization risk)
- Liquidator identification (professional vs retail distinction)
- Wallet behavior fingerprinting (pattern recognition → identity inference)

**Prohibited:**
- Publishing "whale alert" lists
- Creating front-running tools
- Identifying entities behind wallets publicly
- Cascade triggering (using observation to cause cascades)

---

## PART 2: System Architecture Changes

### Current State Analysis

**From codebase exploration:**
- M1 is Binance-only but architecturally pluggable
- M2-M6 are venue-agnostic
- Database schema has unused `exchange` field (multi-venue anticipated)
- No position tracking (only liquidation events)
- No wallet address fields anywhere

### Required Changes (6 layers)

#### Layer 1: M1 Ingestion Extension

**File**: `observation/internal/m1_ingestion.py`

**Add Hyperliquid Event Types:**
```python
# New event types beyond current TRADE, LIQUIDATION
- POSITION_OPEN    # New position created
- POSITION_CLOSE   # Position closed voluntarily
- POSITION_UPDATE  # Leverage/size changed
- POSITION_LIQUIDATED  # Already have this, but add wallet info
```

**Add Hyperliquid Normalizers:**
```python
def normalize_hyperliquid_position_open(self, symbol: str, raw_payload: Dict) -> Optional[Dict]:
    """
    Normalize Hyperliquid position open event.

    Input: {
        "user": "0x1234...",
        "coin": "BTC",
        "size": "0.5",      # Signed (negative = short)
        "leverage": "10",
        "entryPx": "43250.0",
        "liquidationPx": "41000.0",
        "margin": "2162.5",
        "time": 1673456789000
    }

    Output: Canonical structure with wallet field
    """
    return {
        'timestamp': int(raw_payload['time']) / 1000.0,
        'symbol': symbol,
        'price': float(raw_payload['entryPx']),
        'quantity': abs(float(raw_payload['size'])),
        'side': 'BUY' if float(raw_payload['size']) > 0 else 'SELL',
        'wallet_address': raw_payload['user'],  # NEW FIELD
        'leverage': float(raw_payload['leverage']),  # NEW FIELD
        'liquidation_price': float(raw_payload['liquidationPx']),  # NEW FIELD
        'margin': float(raw_payload['margin']),  # NEW FIELD
        'event_type': 'POSITION_OPEN',
        'exchange': 'HYPERLIQUID'  # NEW FIELD
    }
```

**Add to M1 Buffers:**
```python
# In M1IngestionEngine.__init__
self._position_events = defaultdict(lambda: deque(maxlen=500))  # NEW
```

**Effort**: ~300 lines

---

#### Layer 2: M2 Memory Extension

**File**: `observation/internal/m2_memory.py`

**Add Position Zone Node Type:**

Current M2 tracks "liquidation zones" (price levels where liquidations cluster).

NEW: Track "position concentration zones" (price levels where open positions cluster).

```python
@dataclass
class PositionZoneNode:
    """M2 node tracking position concentration (not just liquidation history)."""
    id: str
    price_center: float
    price_band: float
    total_position_size: float  # NEW: Aggregate position size at this zone
    long_position_size: float   # NEW: Long positions
    short_position_size: float  # NEW: Short positions
    avg_leverage: float         # NEW: Average leverage in zone
    wallet_count: int           # NEW: Number of unique wallets
    liquidation_proximity: float  # NEW: Distance to nearest liquidation price

    # Existing fields
    first_seen_ts: float
    last_interaction_ts: float
    strength: float
    confidence: float
```

**Add Position Tracking Methods:**
```python
class M2MemoryStore:
    # NEW METHOD
    def track_position_open(self, event: Dict):
        """Track new position opening at price level."""
        # Find or create position zone node near event price
        # Increment total_position_size, wallet_count
        # Update avg_leverage
        # Compute liquidation_proximity

    # NEW METHOD
    def track_position_close(self, event: Dict):
        """Track position closing."""
        # Decrement zone's total_position_size
        # Update wallet_count if wallet has no more positions in zone

    # NEW METHOD
    def get_positions_near_liquidation(self, price: float, threshold_pct: float = 0.05):
        """Query positions within threshold_pct of their liquidation price."""
        # For cascade proximity primitive
```

**Effort**: ~400 lines

---

#### Layer 3: M3 Temporal Extension

**File**: `observation/internal/m3_temporal.py`

**Add Position Event Processing:**
```python
class M3TemporalEngine:
    def process_position_event(self, event: Dict):
        """
        Process position lifecycle events in temporal order.

        Tracks:
        - Position open timestamp
        - Position holding duration
        - Leverage changes over time
        - Distance to liquidation price over time
        """
        # Add to temporal window
        # Track position lifecycle per wallet
        # Compute holding duration on close

    def get_recent_position_events(self, symbol: str, max_count: int = 100):
        """Query recent position events for primitive computation."""
        # Similar to get_recent_prices
```

**Effort**: ~200 lines

---

#### Layer 4: M4 New Primitives

**File**: `memory/m4_cascade_proximity.py` (NEW FILE)

**Primitive 1: Liquidation Cascade Proximity**

```python
@dataclass(frozen=True)
class LiquidationCascadeProximity:
    """
    Structural fact: N positions within X% of liquidation.

    This is NOT a prediction. It's a mechanical distance calculation.
    """
    price_level: float              # Zone center price
    positions_at_risk_count: int    # Count of positions within threshold
    aggregate_position_size: float  # Total size of at-risk positions
    aggregate_margin: float         # Total margin backing at-risk positions
    avg_distance_to_liquidation_pct: float  # Average % from current liquidation
    closest_liquidation_price: float
    furthest_liquidation_price: float
    time_window: float              # Observation window duration (seconds)

    # Constitutional framing
    observation_only: bool = True   # Flag to prevent semantic drift

def compute_liquidation_cascade_proximity(
    position_zones: List[PositionZoneNode],
    current_price: float,
    threshold_pct: float = 0.05  # Within 5% of liquidation
) -> Optional[LiquidationCascadeProximity]:
    """
    Compute cascade proximity by measuring distance to liquidation.

    Algorithm:
    1. For each position zone, calculate distance to nearest liquidation price
    2. Filter positions within threshold_pct
    3. Aggregate sizes, margins, counts
    4. Return structural fact (NOT prediction)

    Constitutional constraint: This observes structural fact, does not predict cascade.
    """
    at_risk_positions = []

    for zone in position_zones:
        distance_pct = abs(current_price - zone.liquidation_proximity) / current_price
        if distance_pct < threshold_pct:
            at_risk_positions.append(zone)

    if not at_risk_positions:
        return None  # No cascade proximity detected

    return LiquidationCascadeProximity(
        price_level=current_price,
        positions_at_risk_count=len(at_risk_positions),
        aggregate_position_size=sum(z.total_position_size for z in at_risk_positions),
        aggregate_margin=sum(z.total_position_size * z.price_center / z.avg_leverage
                            for z in at_risk_positions),
        avg_distance_to_liquidation_pct=sum(
            abs(current_price - z.liquidation_proximity) / current_price
            for z in at_risk_positions
        ) / len(at_risk_positions),
        closest_liquidation_price=min(z.liquidation_proximity for z in at_risk_positions),
        furthest_liquidation_price=max(z.liquidation_proximity for z in at_risk_positions),
        time_window=60.0  # Observation over last 60 seconds
    )
```

**Effort**: ~150 lines

---

**File**: `memory/m4_leverage_concentration.py` (NEW FILE)

**Primitive 2: Leverage Concentration Ratio**

```python
@dataclass(frozen=True)
class LeverageConcentrationRatio:
    """
    Statistical distribution of leverage across all positions.

    Constitutional framing: Pure statistics, no "over-leveraged" interpretation.
    """
    median_leverage: float
    leverage_25th_percentile: float
    leverage_75th_percentile: float
    leverage_90th_percentile: float
    high_leverage_count: int        # Positions > 10x
    medium_leverage_count: int      # Positions 5x-10x
    low_leverage_count: int         # Positions < 5x
    weighted_avg_leverage: float    # Position-size weighted
    total_positions_observed: int

def compute_leverage_concentration_ratio(
    position_zones: List[PositionZoneNode]
) -> Optional[LeverageConcentrationRatio]:
    """
    Compute leverage distribution statistics.

    Algorithm:
    1. Extract leverage from all position zones
    2. Weight by position size
    3. Compute percentiles
    4. Categorize by leverage bands
    """
    if not position_zones:
        return None

    leverages = [(zone.avg_leverage, zone.total_position_size) for zone in position_zones]
    # Compute statistics...
    return LeverageConcentrationRatio(...)
```

**Effort**: ~100 lines

---

**File**: `memory/m4_open_interest_bias.py` (NEW FILE)

**Primitive 3: Open Interest Directional Bias**

```python
@dataclass(frozen=True)
class OpenInterestDirectionalBias:
    """
    Net direction of all open positions.

    Constitutional framing: Factual aggregation, NOT "bullish/bearish" prediction.
    """
    net_long_position_size: float
    net_short_position_size: float
    position_imbalance_ratio: float   # long / short (or short / long if inverted)
    long_participant_count: int
    short_participant_count: int
    long_avg_leverage: float
    short_avg_leverage: float
    total_open_interest: float        # long + short

def compute_open_interest_directional_bias(
    position_zones: List[PositionZoneNode]
) -> Optional[OpenInterestDirectionalBias]:
    """
    Aggregate all positions to compute net direction.

    Algorithm:
    1. Sum all long positions
    2. Sum all short positions
    3. Compute net (long - short)
    4. Compute ratio (avoiding division by zero)
    """
    long_total = sum(zone.long_position_size for zone in position_zones)
    short_total = sum(zone.short_position_size for zone in position_zones)
    # ...
    return OpenInterestDirectionalBias(...)
```

**Effort**: ~100 lines

---

**File**: `memory/m4_cross_venue_divergence.py` (NEW FILE)

**Primitive 4: Cross-Venue Zone Divergence**

```python
@dataclass(frozen=True)
class CrossVenueZoneDivergence:
    """
    Structural comparison of liquidation zones across venues.

    Constitutional framing: Factual divergence measurement, no arbitrage advice.
    """
    symbol: str
    venue_a: str  # "BINANCE"
    venue_b: str  # "HYPERLIQUID"
    venue_a_zone_count: int
    venue_b_zone_count: int
    venue_a_avg_zone_price: float
    venue_b_avg_zone_price: float
    price_divergence_abs: float       # Absolute price difference
    price_divergence_pct: float       # Percentage difference
    liquidation_density_ratio: float  # venue_b / venue_a
    correlation: float                # Zone price correlation

def compute_cross_venue_zone_divergence(
    venue_a_zones: List[M2Node],  # Binance zones
    venue_b_zones: List[M2Node],  # Hyperliquid zones
    symbol: str
) -> Optional[CrossVenueZoneDivergence]:
    """
    Compare liquidation zones across venues.

    Algorithm:
    1. Compute zone statistics per venue
    2. Calculate price divergence
    3. Compute density ratio
    4. Calculate price correlation
    """
    # ...
    return CrossVenueZoneDivergence(...)
```

**Effort**: ~150 lines

---

#### Layer 5: M5 Governance Extension

**File**: `observation/governance.py`

**Modify `_compute_primitives_for_symbol()` to include new primitives:**

```python
def _compute_primitives_for_symbol(self, symbol: str) -> M4PrimitiveBundle:
    # ... existing primitives ...

    # NEW: Query position zones (not just liquidation nodes)
    position_zones = self._m2_store.get_position_zones(symbol=symbol)

    # NEW: Compute cascade proximity
    cascade_proximity = None
    if len(position_zones) > 0:
        recent_price = self._m3.get_most_recent_price(symbol)
        if recent_price:
            cascade_proximity = compute_liquidation_cascade_proximity(
                position_zones=position_zones,
                current_price=recent_price,
                threshold_pct=0.05
            )

    # NEW: Compute leverage concentration
    leverage_concentration = None
    if len(position_zones) > 0:
        leverage_concentration = compute_leverage_concentration_ratio(
            position_zones=position_zones
        )

    # NEW: Compute open interest bias
    open_interest_bias = None
    if len(position_zones) > 0:
        open_interest_bias = compute_open_interest_directional_bias(
            position_zones=position_zones
        )

    # NEW: Compute cross-venue divergence (if we have both venues)
    cross_venue_divergence = None
    binance_zones = self._m2_store.get_active_nodes(symbol=symbol, venue="BINANCE")
    hyperliquid_zones = self._m2_store.get_active_nodes(symbol=symbol, venue="HYPERLIQUID")
    if len(binance_zones) > 0 and len(hyperliquid_zones) > 0:
        cross_venue_divergence = compute_cross_venue_zone_divergence(
            venue_a_zones=binance_zones,
            venue_b_zones=hyperliquid_zones,
            symbol=symbol
        )

    # Add to bundle
    return M4PrimitiveBundle(
        # ... existing fields ...
        liquidation_cascade_proximity=cascade_proximity,  # NEW
        leverage_concentration_ratio=leverage_concentration,  # NEW
        open_interest_directional_bias=open_interest_bias,  # NEW
        cross_venue_zone_divergence=cross_venue_divergence  # NEW
    )
```

**Effort**: ~100 lines

---

#### Layer 6: Database Schema Extension

**File**: `data_pipeline/schema/003_hyperliquid_schema.sql` (NEW FILE)

```sql
-- Add exchange field to existing tables
ALTER TABLE liquidation_events ADD COLUMN exchange TEXT DEFAULT 'BINANCE';
ALTER TABLE m2_nodes ADD COLUMN exchange TEXT DEFAULT 'BINANCE';

-- New table: Position events
CREATE TABLE position_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    symbol TEXT NOT NULL,
    wallet_address TEXT NOT NULL,  -- Wallet tracking
    event_type TEXT NOT NULL,       -- OPEN, CLOSE, UPDATE, LIQUIDATED
    price REAL NOT NULL,
    quantity REAL NOT NULL,
    side TEXT NOT NULL,             -- BUY/SELL (long/short)
    leverage REAL,
    liquidation_price REAL,
    margin REAL,
    exchange TEXT NOT NULL,

    INDEX idx_position_events_timestamp (timestamp),
    INDEX idx_position_events_symbol (symbol),
    INDEX idx_position_events_wallet (wallet_address)
);

-- New table: Position zones (M2 position tracking)
CREATE TABLE position_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    zone_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price_center REAL NOT NULL,
    price_band REAL NOT NULL,
    total_position_size REAL,
    long_position_size REAL,
    short_position_size REAL,
    avg_leverage REAL,
    wallet_count INTEGER,
    liquidation_proximity REAL,
    exchange TEXT NOT NULL,

    FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
);

-- New table: New primitive values
CREATE TABLE cascade_proximity_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    symbol TEXT NOT NULL,
    price_level REAL,
    positions_at_risk_count INTEGER,
    aggregate_position_size REAL,
    aggregate_margin REAL,
    avg_distance_to_liquidation_pct REAL,

    FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
);

CREATE TABLE leverage_concentration_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    symbol TEXT NOT NULL,
    median_leverage REAL,
    leverage_90th_percentile REAL,
    high_leverage_count INTEGER,
    weighted_avg_leverage REAL,

    FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
);

CREATE TABLE open_interest_bias_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    symbol TEXT NOT NULL,
    net_long_position_size REAL,
    net_short_position_size REAL,
    position_imbalance_ratio REAL,
    long_participant_count INTEGER,
    short_participant_count INTEGER,

    FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
);

CREATE TABLE cross_venue_divergence_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    symbol TEXT NOT NULL,
    venue_a TEXT,
    venue_b TEXT,
    price_divergence_pct REAL,
    liquidation_density_ratio REAL,

    FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
);
```

**Effort**: ~200 lines (schema + migration logic)

---

#### Layer 7: Collector Service Extension

**File**: `runtime/collector/service.py`

**Add Hyperliquid WebSocket Stream:**

```python
class CollectorService:
    async def start(self):
        # Existing Binance stream
        asyncio.create_task(self._run_binance_stream())

        # NEW: Hyperliquid stream
        asyncio.create_task(self._run_hyperliquid_stream())

    async def _run_hyperliquid_stream(self):
        """Connect to Hyperliquid WebSocket and ingest position events."""
        url = "wss://api.hyperliquid.xyz/ws"

        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "allMids",  # All market data
                "coins": ["BTC", "ETH", "SOL", ...]
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url) as ws:
                await ws.send_json(subscription)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)

                        # Route to appropriate handler
                        if data['channel'] == 'liquidation':
                            self._handle_hyperliquid_liquidation(data)
                        elif data['channel'] == 'user':
                            self._handle_hyperliquid_position(data)
                        # ... other channels

    def _handle_hyperliquid_position(self, data: Dict):
        """Process Hyperliquid position event and ingest to M1."""
        # Determine event type (open, close, update)
        event_type = self._infer_position_event_type(data)

        # Normalize via M1
        normalized = self._obs._m1.normalize_hyperliquid_position(
            symbol=data['coin'],
            raw_payload=data,
            event_type=event_type
        )

        # Ingest to observation system
        self._obs.ingest_observation(
            timestamp=normalized['timestamp'],
            symbol=normalized['symbol'],
            event_type=event_type,
            payload=normalized
        )
```

**Effort**: ~300 lines

---

## PART 3: Implementation Roadmap

### Phase 1: M1 Integration (Week 1-2)
**Goal**: Ingest Hyperliquid liquidation events alongside Binance.

**Tasks**:
1. Add Hyperliquid normalizers to M1 (`normalize_hyperliquid_liquidation`, etc.)
2. Extend CollectorService with `_run_hyperliquid_stream()`
3. Add `exchange` field to database schema
4. Test dual-stream ingestion (Binance + Hyperliquid)
5. Verify M2 nodes populate from both venues

**Deliverable**: System ingests liquidations from both venues, M2 nodes tagged with venue.

**Validation**:
```python
# Query database
SELECT exchange, COUNT(*) FROM liquidation_events GROUP BY exchange;
# Should show BINANCE + HYPERLIQUID counts

# Check M2 nodes
SELECT exchange, COUNT(DISTINCT node_id) FROM m2_nodes GROUP BY exchange;
```

---

### Phase 2: Position Tracking (Week 3-4)
**Goal**: Track position lifecycle (open, close, update).

**Tasks**:
1. Add POSITION_OPEN/CLOSE/UPDATE event types to M1
2. Extend M2 with PositionZoneNode class
3. Implement `track_position_open/close()` in M2MemoryStore
4. Add `position_events` table to database
5. Subscribe to Hyperliquid user position stream

**Deliverable**: System tracks open positions, not just liquidations.

**Validation**:
```python
# Query position events
SELECT event_type, COUNT(*) FROM position_events GROUP BY event_type;
# Should show OPEN, CLOSE, UPDATE, LIQUIDATED

# Check position zones
SELECT symbol, SUM(total_position_size), COUNT(*) as zones
FROM position_zones
GROUP BY symbol;
```

---

### Phase 3: Cascade Proximity Primitive (Week 5-6)
**Goal**: Implement liquidation_cascade_proximity primitive.

**Tasks**:
1. Create `memory/m4_cascade_proximity.py`
2. Implement `compute_liquidation_cascade_proximity()`
3. Add to M5 governance primitive computation
4. Add to M4PrimitiveBundle dataclass
5. Create `cascade_proximity_values` database table
6. Log primitive values to database

**Deliverable**: Cascade proximity observable in database and available to policies.

**Validation**:
```python
# Query cascade proximity detections
SELECT symbol, positions_at_risk_count, aggregate_position_size, avg_distance_to_liquidation_pct
FROM cascade_proximity_values
WHERE positions_at_risk_count > 10
ORDER BY aggregate_position_size DESC;
```

---

### Phase 4: Leverage & Open Interest Primitives (Week 7)
**Goal**: Implement remaining 2 primitives.

**Tasks**:
1. Create `memory/m4_leverage_concentration.py`
2. Create `memory/m4_open_interest_bias.py`
3. Add to M5 governance
4. Add database tables
5. Test with live data

**Deliverable**: All 4 new primitives operational.

---

### Phase 5: Cross-Venue Divergence (Week 8)
**Goal**: Compare Binance vs Hyperliquid zones.

**Tasks**:
1. Create `memory/m4_cross_venue_divergence.py`
2. Modify M2 to track venue in node queries
3. Compute divergence in M5
4. Add database table

**Deliverable**: Cross-venue analysis available.

---

### Phase 6: Policy Integration (Week 9-10)
**Goal**: Create EP-3 policy using new primitives.

**Tasks**:
1. Create `external_policy/ep3_cascade_detection.py`
2. Define cascade detection rules using new primitives
3. Test mandate generation
4. Validate with frozen policy contracts

**Deliverable**: New policy generates mandates based on cascade proximity.

---

### Phase 7: UI & Observability (Week 11-12)
**Goal**: Visualize cascade detection in native app.

**Tasks**:
1. Add cascade proximity panel to UI
2. Display wallet addresses (with ethical framing)
3. Show leverage distribution charts
4. Cross-venue comparison visualization

**Deliverable**: Full observability of cascade detection system.

---

## PART 4: Critical Files to Modify

### Core System (Must Touch)
1. `observation/internal/m1_ingestion.py` - Add Hyperliquid normalizers (~300 lines)
2. `observation/internal/m2_memory.py` - Add position tracking (~400 lines)
3. `observation/internal/m3_temporal.py` - Add position event processing (~200 lines)
4. `observation/governance.py` - Add new primitive computation (~100 lines)
5. `observation/types.py` - Extend M4PrimitiveBundle dataclass (~50 lines)
6. `runtime/collector/service.py` - Add Hyperliquid stream (~300 lines)

### New Files (Create)
7. `memory/m4_cascade_proximity.py` (~150 lines)
8. `memory/m4_leverage_concentration.py` (~100 lines)
9. `memory/m4_open_interest_bias.py` (~100 lines)
10. `memory/m4_cross_venue_divergence.py` (~150 lines)
11. `data_pipeline/schema/003_hyperliquid_schema.sql` (~200 lines)

### Optional (If Creating New Policy)
12. `external_policy/ep3_cascade_detection.py` (~200 lines)

**Total Estimated Code**: ~2,250 lines across 12 files

---

## PART 5: Verification Strategy

### Unit Tests
1. **M1 Normalization**: Test Hyperliquid payload parsing
2. **M2 Position Tracking**: Test position zone creation/update
3. **M4 Primitives**: Test cascade proximity calculation
4. **Cross-Venue**: Test zone divergence computation

### Integration Tests
1. **Dual Stream**: Verify Binance + Hyperliquid ingestion simultaneously
2. **Position Lifecycle**: Open → Update → Close sequence
3. **Cascade Detection**: Simulate 50 positions near liquidation, verify primitive
4. **Database**: Verify all new tables populate correctly

### Live Validation
1. **30-Minute Test**: Run live, verify cascade detections logged
2. **Cross-Venue Check**: Confirm both venues populate M2 nodes
3. **Primitive Coverage**: Check all 4 new primitives compute successfully
4. **Database Inspection**: Query primitive values, verify non-null counts

### End-to-End Validation
```bash
# Run system for 30 minutes
python runtime/native_app/main.py

# Query cascade detections
python -c "
import sqlite3
conn = sqlite3.connect('logs/execution.db')
c = conn.cursor()

# Check cascade proximity
c.execute('SELECT COUNT(*) FROM cascade_proximity_values WHERE positions_at_risk_count > 0')
print(f'Cascade detections: {c.fetchone()[0]}')

# Check leverage concentration
c.execute('SELECT AVG(median_leverage), AVG(leverage_90th_percentile) FROM leverage_concentration_values')
row = c.fetchone()
print(f'Avg median leverage: {row[0]:.2f}, Avg 90th percentile: {row[1]:.2f}')

# Check open interest
c.execute('SELECT AVG(position_imbalance_ratio) FROM open_interest_bias_values')
print(f'Avg position imbalance: {c.fetchone()[0]:.2f}')

# Check cross-venue divergence
c.execute('SELECT COUNT(*) FROM cross_venue_divergence_values WHERE ABS(price_divergence_pct) > 0.5')
print(f'Significant venue divergences (>0.5%): {c.fetchone()[0]}')

conn.close()
"
```

---

## PART 6: Constitutional Safeguards (Implementation)

### Code-Level Enforcement

**In M4 Primitive Dataclasses:**
```python
@dataclass(frozen=True)
class LiquidationCascadeProximity:
    # ... fields ...

    # Constitutional flag (prevents semantic drift)
    observation_only: bool = True

    def to_display_dict(self) -> Dict:
        """
        Export for UI display with constitutional framing.

        Forbidden phrases: "will cascade", "high risk", "dangerous"
        Allowed phrases: "N positions", "X% from liquidation", "aggregate size $Y"
        """
        return {
            'description': f'{self.positions_at_risk_count} positions within '
                          f'{self.avg_distance_to_liquidation_pct:.1%} of liquidation',
            'aggregate_size_usd': f'${self.aggregate_position_size:,.0f}',
            'closest_price': f'${self.closest_liquidation_price:,.2f}',
            'observation_window': f'{self.time_window:.0f}s',
            # NO "risk level", NO "will cascade", NO "high danger"
        }
```

**In Policy Code:**
```python
def generate_cascade_proposal(
    cascade_proximity: LiquidationCascadeProximity,
    context: StrategyContext,
    permission: PermissionOutput
) -> Optional[StrategyProposal]:
    """
    Generate proposal based on cascade proximity observation.

    Constitutional constraint: NO PREDICTION.
    This observes structural fact, does not predict cascade occurrence.
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None

    # Rule 2: Required primitive missing -> no proposal
    if cascade_proximity is None:
        return None

    # Rule 3: Check structural existence conditions
    # ALLOWED: "Are N positions within X% of liquidation?"
    # FORBIDDEN: "Will cascade occur?"
    if not (cascade_proximity.positions_at_risk_count > 20):  # Factual threshold
        return None

    if not (cascade_proximity.aggregate_position_size > 1_000_000):  # $1M threshold
        return None

    # All conditions met - emit proposal
    # Justification uses ONLY factual observations
    return StrategyProposal(
        action_type="CASCADE_PROXIMITY_OBSERVED",  # NOT "CASCADE_PREDICTED"
        confidence=0.0,  # No confidence - pure observation
        reason_code=f"B4.1|{cascade_proximity.positions_at_risk_count}_POSITIONS",
        justification=(
            f"{cascade_proximity.positions_at_risk_count} positions "
            f"aggregating ${cascade_proximity.aggregate_position_size:,.0f} "
            f"within {cascade_proximity.avg_distance_to_liquidation_pct:.1%} "
            f"of liquidation at ${cascade_proximity.closest_liquidation_price:,.2f}. "
            f"Observation only, no prediction."
        ),
        mandate_id=permission.mandate_id,
        action_id=permission.action_id,
        context=context
    )
```

---

## PART 7: Risk Assessment

### Technical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Hyperliquid API changes** | HIGH | Version pinning, API monitoring |
| **WebSocket disconnections** | MEDIUM | Reconnect logic, buffering |
| **Position tracking errors** | HIGH | Extensive unit tests, validation |
| **Database growth** | MEDIUM | Rotation policy, compression |
| **M2 memory overflow** | MEDIUM | Position zone cleanup, TTL |

### Constitutional Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Semantic drift ("cascade prediction")** | HIGH | Code review, prohibited phrase list |
| **"Whale" language leakage** | MEDIUM | Enforce "large account" terminology |
| **Confidence claims** | MEDIUM | Dataclass flags, UI review |
| **Cascade self-fulfilling prophecy** | HIGH | No public feed, no "will happen" language |

### Ethical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Wallet de-anonymization** | HIGH | Hash addresses, no public lists |
| **Front-running enablement** | VERY HIGH | Private use only, no public API |
| **Cascade triggering** | VERY HIGH | Observation-only, no automated actions |
| **Privacy violation** | MEDIUM | Aggregate stats preferred over individuals |

---

## PART 8: Go/No-Go Decision Criteria

### Prerequisites (Must Have Before Starting)

✅ **Technical:**
1. M1-M5 system proven stable (current system working)
2. Database handles current load
3. WebSocket infra handles dual streams
4. M2 memory can scale to position tracking

✅ **Constitutional:**
1. Clear prohibited phrase list
2. Code review process for semantic drift
3. UI/UX guidelines for factual presentation
4. Policy templates enforce observation-only

✅ **Ethical:**
1. Privacy policy drafted (wallet data usage)
2. Front-running safeguards designed
3. Public disclosure limits defined
4. Cascade triggering prevention plan

### Success Criteria (How We Know It Works)

**Week 4 Checkpoint:**
- [ ] Hyperliquid stream ingesting successfully
- [ ] Position events logged to database
- [ ] M2 position zones forming correctly
- [ ] No constitutional violations detected in logs

**Week 8 Checkpoint:**
- [ ] All 4 primitives computing successfully
- [ ] Cascade proximity detects >0 events per hour
- [ ] Cross-venue divergence shows venue differences
- [ ] Database queries performant (<500ms)

**Week 12 Final:**
- [ ] EP-3 policy generates mandates based on cascade proximity
- [ ] UI displays cascade data with constitutional framing
- [ ] No "whale" or "prediction" language in system
- [ ] 30-day live test with no crashes

---

## FINAL RECOMMENDATION

**Proceed**: YES, with strong constitutional/ethical oversight.

**Priority Order**:
1. Phase 1-2: Basic integration + position tracking (LOW RISK, HIGH VALUE)
2. Phase 3: Cascade proximity primitive (MEDIUM RISK, VERY HIGH VALUE)
3. Phase 4: Leverage + open interest (LOW RISK, HIGH VALUE)
4. Phase 5: Cross-venue divergence (LOW RISK, MEDIUM VALUE)
5. Phase 6-7: Policy + UI (requires constitutional review)

**Key Success Factors**:
- Maintain observation-only discipline
- No semantic drift into prediction
- Hash wallet addresses
- Private use only (no public API)

**Estimated Timeline**: 12 weeks full-time (or 24 weeks part-time)

**Estimated Complexity**: HIGH (2,250+ lines, 6 layers, new data source)

---

## Questions Before Implementation

1. **Hyperliquid API Access**: Do you have API keys? Rate limits?
2. **Position Tracking Scope**: Track all wallets or just large ones (>$100k)?
3. **Database Retention**: How long to keep position events? (Disk space)
4. **UI Requirements**: Should cascade proximity be visible in native app?
5. **Policy Activation**: Should EP-3 cascade policy execute immediately or observe-only first?

Let me know if you want to proceed with implementation or need clarification on any phase.

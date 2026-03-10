# Gravity Zone Observer — Design Spec

## Purpose

Passive data collection module that observes price behavior at L2 gravity zones. Produces a dataset to validate the "gravity traverse" thesis: price bounces between strong liquidity zones, and zone absorption predicts successful traversals.

No trading. Pure observation. Runs alongside existing cascade sniper without interference.

## Thesis Under Test

1. Price arriving at a strong gravity zone tends to reverse toward the next strong zone
2. Stronger zones produce more reliable bounces
3. Absorption (zone liquidity consumed but replenishing) confirms the bounce
4. Thin paths between zones (low gravity in between) predict faster traversals
5. Zone breach (liquidity depleted, price passes through) is the failure mode

## Architecture

### New file: `runtime/liquidations/gravity_observer.py`

Single class `GravityObserver`. Instantiated in `service.py` alongside `LiquidityMap`.

### Dependencies (read-only)
- `LiquidityMap` — zone data, current sizes
- `_orderflow_calculators` — fill count and imbalance at zone arrival/exit
- Price feed — current price per coin (from regime loop)
- PG pool — for persistence

### No interaction with
- Trading logic, mandates, positions, trailing stops
- Cascade sniper, arbitration, ghost tracker

### Call site
- Regime loop in `service.py`, once per coin per cycle (~200ms)
- Same location where `_update_trailing_stops` and `_check_gravity_tp_targets` are called
- Signature: `observer.on_price_update(coin, price, timestamp, liquidity_map, orderflow_calc)`

## Zone Arrival Detection

Per-coin state machine with 3 states:

```
IDLE → DWELLING → TRACKING_OUTCOME
  ↑                      |
  └──────────────────────┘ (finalized after 120s or next zone arrival)
```

**IDLE → DWELLING**: Price enters a zone band (10bp) with gravity >= `MIN_OBS_GRAVITY` (5000) that it wasn't in last cycle.

**DWELLING → TRACKING_OUTCOME**: Price exits the zone band.

**TRACKING_OUTCOME → IDLE**: 120s elapsed since zone exit, OR price arrives at another qualifying zone (which also triggers a new DWELLING).

**TRACKING_OUTCOME → DWELLING**: Price arrives at destination zone — finalize current event as "traversal complete", start new arrival event.

## Event Data Model

### At arrival (immutable after creation)
| Field | Type | Source |
|---|---|---|
| event_id | UUID | generated |
| coin | str | input |
| timestamp | float | input |
| zone_center | float | LiquidityMap zone |
| zone_low | float | LiquidityMap zone |
| zone_high | float | LiquidityMap zone |
| zone_side | str | "bid" or "ask" |
| zone_gravity | float | gravity score at arrival |
| zone_persistence | float | 0-1 at arrival |
| zone_size_usd_initial | float | current_size_usd at first contact |
| arrival_price | float | price when entering zone |
| approach_direction | str | "from_above" or "from_below" |
| orderflow_imbalance | float | 60s OF imbalance at arrival |
| orderflow_fills | int | fill count at arrival |
| dest_zones_above | JSON | top 3 ask zones: [{center, gravity, distance_bps}] |
| dest_zones_below | JSON | top 3 bid zones: [{center, gravity, distance_bps}] |
| path_gravity_above | float | total gravity between zone and nearest dest above |
| path_gravity_below | float | total gravity between zone and nearest dest below |
| cascade_active | bool | whether cascade sniper has position on this coin |

### During dwell (updated in memory, persisted at finalization)
| Field | Type | Description |
|---|---|---|
| dwell_duration_s | float | time spent inside zone band |
| zone_size_samples | float[] | current_size_usd sampled every 5s during dwell |
| size_ratio | float | final_size / initial_size (>1 = absorption/refill) |
| min_size_ratio | float | minimum during dwell (how much was consumed) |
| of_imbalance_exit | float | orderflow imbalance when leaving zone |
| of_fills_exit | int | fill count when leaving zone |

### Outcome (updated during tracking, finalized at end)
| Field | Type | Description |
|---|---|---|
| exit_price | float | price when leaving zone band |
| exit_direction | str | "upward" or "downward" |
| reversal | bool | exit_direction opposite to approach_direction |
| mfe_30s | float | max favorable excursion 30s after zone exit (bps) |
| mfe_60s | float | max favorable excursion 60s after zone exit (bps) |
| mfe_120s | float | max favorable excursion 120s after zone exit (bps) |
| mae_30s | float | max adverse excursion 30s after zone exit (bps) |
| mae_60s | float | max adverse excursion 60s after zone exit (bps) |
| mae_120s | float | max adverse excursion 120s after zone exit (bps) |
| destination_reached | str or null | zone center of destination reached (if any) |
| destination_gravity | float or null | gravity of destination zone reached |
| destination_time_s | float or null | seconds to reach destination |
| breached | bool | price went through zone and continued (zone failed) |

## PG Table: `gravity_zone_events`

One row per arrival event. Created via `ensure_schema()` pattern (idempotent).

Arrival fields written on INSERT. Dwell and outcome fields UPDATEd at finalization.

JSON columns (`dest_zones_above`, `dest_zones_below`, `zone_size_samples`) stored as TEXT (JSON-serialized). Simple, no need for PG JSON operators in research queries.

Retention: keep all data. Estimated volume ~50-200 events/day across 20 coins. Negligible storage.

Index on `(coin, timestamp)` for time-range queries.

## In-Memory State

```python
@dataclass
class _ZoneArrival:
    event_id: str
    coin: str
    state: str  # "DWELLING", "TRACKING"
    zone: LiquidityZone  # snapshot at arrival
    arrival_ts: float
    arrival_price: float
    approach_direction: str
    zone_exit_ts: float = 0.0
    exit_price: float = 0.0
    exit_direction: str = ""
    size_samples: list = field(default_factory=list)
    last_sample_ts: float = 0.0
    highest_since_exit: float = 0.0
    lowest_since_exit: float = 0.0
    # ... orderflow snapshots, destination info
```

Per-coin dict: `_active: Dict[str, Optional[_ZoneArrival]]`

Ring buffer for recent events (inspection): `_recent: deque(maxlen=500)`

## Key Decisions

**Min gravity for observation:** 5000 USD (same as LiquidityMap floor). Log everything; filter in analysis.

**Zone overlap:** Price can be inside multiple zones simultaneously (10bp bands can be adjacent). Use the **strongest** (highest gravity) zone as the active arrival.

**Re-entry:** If price leaves a zone and re-enters the same zone within 10s, treat as continuation of the same dwell (not a new event). Prevents flicker at zone edges.

**Sampling during dwell:** Every 5s (aligned with LiquidityMap sample interval). Max 24 samples for 120s dwell. Store in Python list, serialize to JSON at persistence.

**MFE/MAE baseline:** Measured from exit_price (when price leaves the zone), not arrival_price. This measures "how far did price go after the bounce" — the tradeable move.

**"Reversal" definition:** Exit direction opposite to approach direction. Approach from above + exit upward = reversal (bounce). Approach from above + exit downward = breach (failure).

## Integration Points

### service.py changes
1. Import and instantiate `GravityObserver` (next to `LiquidityMap`)
2. In regime loop per-coin section, call `observer.on_price_update(...)`
3. Pass `liquidity_map` reference and orderflow calculator
4. No other changes to service.py

### pg_schema.py changes
1. Add `gravity_zone_events` table to `ensure_schema()`

### No changes to
- LiquidityMap (read-only consumer)
- Cascade sniper, trailing stops, ghost tracker
- Any external_policy files
- Arbitration layer

## Analysis Queries (post-collection)

After 3-5 days, run analysis scripts to answer:

1. **Reversal rate by gravity**: GROUP BY gravity buckets, measure reversal %
2. **Absorption predicts bounce**: WHERE size_ratio > 1 vs < 1, compare reversal rate and MFE
3. **Dwell time signal**: does longer dwell = higher reversal confidence?
4. **Path thickness**: does low path_gravity between zones predict faster traversal?
5. **Destination accuracy**: when reversal occurs, does price actually reach the predicted destination?
6. **Gravity threshold**: at what gravity level does reversal rate exceed 55%? 60%?
7. **Cascade overlap**: do arrivals during cascade positions have different stats?

## Expected Output

A dataset of ~500-2000 zone arrival events over 5 days, each annotated with:
- Zone characteristics (gravity, persistence, size evolution)
- Confirmation signals (dwell, absorption, orderflow)
- Outcomes (reversal, MFE/MAE, destination reached)

This dataset determines whether the gravity traverse strategy is viable and which confirmation method (dwell time, absorption, orderflow, or combination) produces the best signal.

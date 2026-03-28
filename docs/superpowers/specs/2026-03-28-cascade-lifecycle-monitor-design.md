# Cascade Lifecycle Monitor — Design Spec

## Purpose

Passively record the FULL lifecycle of every liquidation cascade at ~200ms resolution with shadow entry PnL tracking. Provides the data needed to find the optimal entry point in the cascade z-curve — replacing static gate-based filtering (which failed) with evidence-based entry timing.

## Problem Statement

Over the past week, we tried 10+ combinations of entry gates (decel phase, ratio, OF, z-cap, isolation, fuel gate). Every combination either blocked too many winners or let through too many losers. The fundamental issue: we're guessing at static thresholds without understanding the dynamic cascade lifecycle.

Research finding: `liq_z [1,4]` = 71% WR, but this is a static band. We don't know:
- How fast z rises and falls (the curve shape)
- Whether the peak-to-entry delay matters
- Whether L2 absorption at specific z levels predicts reversal
- What the optimal entry point looks like in the z trajectory

## Architecture

### CascadeLifecycleMonitor

One new class called once per coin per regime cycle (~200ms). Maintains per-coin cascade state and writes snapshots to PG.

**State machine per coin:**
- **QUIET** — `liq_z < 1.0`. No recording.
- **ACTIVE** — `liq_z >= 1.0`. Recording every cycle. Tracks peak_z, start_ts, start_price.
- **FADING** — z dropped below 50% of peak_z. Still recording.
- **DONE** — `liq_z < 0.5` after being ACTIVE, OR 120s since z last exceeded 1.0. Stop recording. Backfill shadow PnL. Flush to PG.

Transitions: QUIET → ACTIVE (z crosses 1.0 upward), ACTIVE → FADING (z < peak * 0.5), ACTIVE/FADING → DONE (z < 0.5 or timeout), DONE → QUIET (immediate).

### Data Flow

```
Regime loop (per coin, ~200ms)
  → rolling_volume_tracker.get_current_z()
  → CascadeLifecycleMonitor.update(symbol, liq_z, price, regime_metrics, ...)
    → If ACTIVE/FADING: append snapshot to in-memory buffer
    → If → DONE: backfill shadow PnL from price_history, batch insert to PG
```

### PG Table: `cascade_lifecycle`

```sql
CREATE TABLE IF NOT EXISTS cascade_lifecycle (
    id              BIGSERIAL PRIMARY KEY,
    cascade_id      TEXT NOT NULL,          -- UUID, same for all snapshots in one cascade
    symbol          TEXT NOT NULL,
    ts              DOUBLE PRECISION NOT NULL,
    phase           TEXT NOT NULL,           -- ACTIVE / FADING / DONE

    -- Z-curve
    liq_z           DOUBLE PRECISION,       -- current z-score
    peak_z          DOUBLE PRECISION,       -- highest z seen in this cascade
    time_since_peak DOUBLE PRECISION,       -- seconds since peak z
    z_velocity      DOUBLE PRECISION,       -- rate of z change (per second)

    -- Price context
    price           DOUBLE PRECISION,
    price_at_start  DOUBLE PRECISION,       -- price when cascade began (z crossed 1.0)
    move_from_start DOUBLE PRECISION,       -- bps from cascade start price
    vwap_distance   DOUBLE PRECISION,
    atr_5m          DOUBLE PRECISION,
    atr_30m         DOUBLE PRECISION,

    -- Flow context
    orderflow       DOUBLE PRECISION,       -- OF imbalance at snapshot
    burst_volume    DOUBLE PRECISION,       -- liq $ in burst window
    liq_side        TEXT,                    -- dominant side: LONG or SHORT

    -- L2 / gravity context
    wall_consec_rev SMALLINT,               -- consecutive zone reversals at nearest wall
    wall_is_ob      BOOLEAN,                -- order block detected
    wall_gravity    DOUBLE PRECISION,       -- total gravity of nearest wall
    bid_depth_ratio DOUBLE PRECISION,       -- bid_total / ask_total in top 20 levels

    -- Multi-coin context
    n_coins_active  SMALLINT,               -- how many other coins have liq_z >= 1.0 right now

    -- Shadow entry PnL (backfilled when cascade ends)
    fade_direction  TEXT,                    -- which direction would the fade be (LONG/SHORT)
    shadow_mfe_1m   DOUBLE PRECISION,
    shadow_mfe_2m   DOUBLE PRECISION,
    shadow_mfe_5m   DOUBLE PRECISION,
    shadow_mae_1m   DOUBLE PRECISION,
    shadow_mae_2m   DOUBLE PRECISION,
    shadow_mae_5m   DOUBLE PRECISION,

    -- Trade linkage
    trade_id        TEXT                     -- ghost_trades trade_id if entry happened during this cascade, NULL otherwise
);

CREATE INDEX IF NOT EXISTS idx_cascade_lifecycle_cascade_id ON cascade_lifecycle(cascade_id);
CREATE INDEX IF NOT EXISTS idx_cascade_lifecycle_symbol_ts ON cascade_lifecycle(symbol, ts);
```

### Shadow PnL Backfill

When cascade transitions to DONE:
1. Get the full price history from `_price_history` deque (15min, 4500 entries)
2. For each snapshot in the cascade buffer:
   - Determine fade_direction from price movement (price falling → fade LONG, rising → fade SHORT)
   - Find prices at +1m, +2m, +5m after snapshot timestamp
   - Compute MFE (max favorable) and MAE (max adverse) for each window
   - If a ghost trade entered during this cascade (match by symbol + timestamp overlap), set trade_id
3. Batch INSERT all snapshots to PG

### Concurrent Cascade Tracking

The monitor maintains a dict of `{symbol: phase}` for all coins. At each snapshot, `n_coins_active` = count of coins currently in ACTIVE or FADING phase (excluding the current coin). This captures the multi-coin cascade signal without needing the isolation gate.

### Bid/Ask Depth Ratio

From the liquidity map (already computing L2 zones from depth20 data):
- Sum bid-side gravity within 50bp of current price
- Sum ask-side gravity within 50bp
- `bid_depth_ratio = bid_sum / ask_sum`
- Ratio > 1.5 = strong bid support (good for LONG fades). Ratio < 0.67 = strong ask pressure (good for SHORT fades).

### Trade Linkage

When a ghost trade opens during an active cascade (same symbol, entry timestamp within cascade start/end window), the cascade_id is stored in the ghost trade's entry_context, and the trade_id is stored in the cascade snapshot closest to the entry timestamp.

## Integration Points

**service.py regime loop** — After `check_for_signal()` call (~line 1595), add:
```python
self._cascade_monitor.update(
    symbol=symbol, liq_z=liq_z, price=current_price,
    regime_metrics=regime_metrics,
    wall_status=self._gravity_observer.get_wall_status(hl_symbol),
    liquidity_map=self._liquidity_map,
    price_history=self._price_history.get(symbol),
    rolling_tracker=self._rolling_volume_tracker,
)
```

**pg_schema.py** — Add table creation in `ensure_schema()`.

**Ghost trade entry** — When opening a position, check if `_cascade_monitor` has an active cascade for that symbol and store cascade_id in entry_context.

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `runtime/liquidations/cascade_monitor.py` | Create | CascadeLifecycleMonitor class |
| `runtime/logging/pg_schema.py` | Modify | Add cascade_lifecycle table |
| `runtime/collector/service.py` | Modify | Wire monitor into regime loop |
| `scripts/analyze_cascades.py` | Create | Analysis script for cascade lifecycle data |

## Analysis Script

`scripts/analyze_cascades.py` queries the cascade_lifecycle table to answer:
1. **Z-curve shape**: Average z trajectory for cascades that produced good bounces vs bad
2. **Optimal entry point**: At what (z_level, time_since_peak) is shadow MFE maximized and MAE minimized?
3. **Context correlation**: Does wall presence, bid_depth_ratio, or n_coins_active at specific z levels predict better shadow PnL?
4. **Trade comparison**: For cascades where we DID trade, compare our actual entry point to the optimal shadow entry point

## Expected Output

After 3-5 days of collection (~50-100 cascades per day across 20 coins):
- Enough data to characterize the z-curve shape taxonomy (fast spike vs slow build, symmetric vs asymmetric decay)
- Statistical relationship between entry timing (z level + time since peak) and shadow PnL
- Evidence for which context factors (walls, depth, multi-coin) actually matter at each stage
- A data-driven entry rule: "enter when z has declined to X from peak, Y seconds after peak, with context Z"

## What This Does NOT Do

- Does not change any entry logic (purely passive)
- Does not modify any existing gates or filters
- Does not affect trading performance
- Does not require any parameter tuning

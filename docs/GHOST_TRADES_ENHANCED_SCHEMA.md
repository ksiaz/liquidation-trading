# Enhanced Ghost Trades Schema for Analysis

## Current Schema Issues

The current `ghost_trades` table captures basic trade data but lacks context needed for:
1. Understanding WHY a trade was taken (primitive state)
2. Evaluating QUALITY of execution (MFE/MAE)
3. Analyzing holding period BEHAVIOR
4. Correlating trades with system STATE
5. Tracking PARTIAL position management

## Recommended Enhanced Schema

### Core Trade Table (Enhanced)

```sql
CREATE TABLE ghost_trades_v2 (
    -- Identity
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT NOT NULL,
    parent_trade_id TEXT,  -- Link partial closes to original entry

    -- Basic Trade Info
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,              -- BUY/SELL
    position_side TEXT NOT NULL,     -- LONG/SHORT
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    timestamp REAL NOT NULL,

    -- Trade Type
    is_entry BOOLEAN NOT NULL,
    is_partial_close BOOLEAN DEFAULT 0,
    exit_reason TEXT,  -- FULL_EXIT, PARTIAL_REDUCE, STOP, MANDATE_EXIT

    -- Financial Results
    pnl REAL,
    pnl_pct REAL,  -- PNL as % of entry value
    fees_estimated REAL,  -- Estimated trading fees
    account_balance_after REAL NOT NULL,
    account_equity_after REAL,  -- Including unrealized from other positions

    -- System Context Links
    entry_cycle_id INTEGER,  -- Cycle when position opened
    exit_cycle_id INTEGER,   -- Cycle when position closed
    triggered_by_mandate_id INTEGER,
    winning_policy_name TEXT,

    -- Market Context at Trade Time
    spread_bps REAL,
    orderbook_depth_5 TEXT,  -- JSON of top 5 levels
    mark_price REAL,

    -- Active Primitives (JSON array of active primitive names)
    active_primitives TEXT,

    -- Position Management
    position_fraction REAL,  -- What % of max position size
    concurrent_positions INTEGER,  -- Other open positions count
    total_exposure_pct REAL,  -- % of account in all positions

    -- Trade Quality Metrics (filled during position lifecycle)
    max_favorable_excursion REAL,  -- Best unrealized gain
    max_adverse_excursion REAL,    -- Worst unrealized loss
    mfe_timestamp REAL,
    mae_timestamp REAL,
    holding_duration_sec REAL,

    -- Metadata
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ghost_trades_symbol ON ghost_trades_v2(symbol);
CREATE INDEX idx_ghost_trades_entry_cycle ON ghost_trades_v2(entry_cycle_id);
CREATE INDEX idx_ghost_trades_parent ON ghost_trades_v2(parent_trade_id);
```

### Trade Rejections Table (NEW)

```sql
CREATE TABLE ghost_trade_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,

    symbol TEXT NOT NULL,
    attempted_action TEXT NOT NULL,  -- ENTRY/EXIT/REDUCE
    attempted_side TEXT,  -- LONG/SHORT

    rejection_reason TEXT NOT NULL,
    -- e.g., "Position already exists", "Insufficient balance",
    --      "Exchange validation failed", "Spread too wide"

    mandate_id INTEGER,
    policy_name TEXT,

    -- Context at rejection
    account_balance REAL,
    account_equity REAL,
    open_positions_count INTEGER,

    -- Market state
    current_price REAL,
    spread_bps REAL,

    -- Primitives that triggered the attempt
    triggering_primitives TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Position Lifecycle Table (NEW)

```sql
CREATE TABLE ghost_position_lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,  -- Same as entry trade_id
    symbol TEXT NOT NULL,

    -- Entry
    entry_trade_id TEXT NOT NULL,
    entry_cycle_id INTEGER NOT NULL,
    entry_timestamp REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_quantity REAL NOT NULL,
    entry_side TEXT NOT NULL,

    -- Current State (updated each cycle while open)
    current_quantity REAL,
    current_unrealized_pnl REAL,
    current_mfe REAL,
    current_mae REAL,

    -- Exit
    exit_trade_id TEXT,
    exit_cycle_id INTEGER,
    exit_timestamp REAL,
    exit_price REAL,
    exit_reason TEXT,

    -- Results
    realized_pnl REAL,
    total_holding_time_sec REAL,

    -- Status
    status TEXT NOT NULL,  -- OPEN, CLOSED, PARTIAL

    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Analysis Queries This Enables

### 1. Trade Performance by Primitive State
```sql
-- Which primitive combinations led to best trades?
SELECT
    active_primitives,
    COUNT(*) as trade_count,
    AVG(pnl) as avg_pnl,
    AVG(pnl_pct) as avg_pnl_pct,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
FROM ghost_trades_v2
WHERE is_entry = 0  -- Exits only
GROUP BY active_primitives
HAVING trade_count >= 5
ORDER BY avg_pnl_pct DESC;
```

### 2. Trade Quality Analysis
```sql
-- Average MFE/MAE by holding duration
SELECT
    CAST(holding_duration_sec / 60 AS INTEGER) as duration_minutes,
    AVG(max_favorable_excursion) as avg_mfe,
    AVG(max_adverse_excursion) as avg_mae,
    AVG(pnl) as avg_pnl,
    COUNT(*) as count
FROM ghost_trades_v2
WHERE is_entry = 0
GROUP BY duration_minutes
ORDER BY duration_minutes;
```

### 3. Policy Performance
```sql
-- Win rate by policy
SELECT
    winning_policy_name,
    COUNT(*) as trades,
    AVG(pnl) as avg_pnl,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    AVG(holding_duration_sec / 3600) as avg_holding_hours
FROM ghost_trades_v2
WHERE is_entry = 0 AND winning_policy_name IS NOT NULL
GROUP BY winning_policy_name
ORDER BY avg_pnl DESC;
```

### 4. Entry Timing Analysis
```sql
-- Correlation between entry spread and trade outcome
SELECT
    CAST(spread_bps * 10 AS INTEGER) / 10.0 as spread_bucket,
    COUNT(*) as trades,
    AVG(pnl_pct) as avg_pnl_pct,
    AVG(holding_duration_sec) as avg_hold_sec
FROM ghost_trades_v2
WHERE is_entry = 1
GROUP BY spread_bucket
ORDER BY spread_bucket;
```

### 5. Rejection Pattern Analysis
```sql
-- Why are trades getting rejected?
SELECT
    rejection_reason,
    COUNT(*) as count,
    AVG(spread_bps) as avg_spread,
    COUNT(DISTINCT symbol) as symbols_affected
FROM ghost_trade_rejections
GROUP BY rejection_reason
ORDER BY count DESC;
```

## Migration Path

1. Keep existing `ghost_trades` table
2. Create `ghost_trades_v2` with enhanced schema
3. Add `ghost_trade_rejections` table
4. Add `ghost_position_lifecycle` table
5. Update ghost tracker to log to both tables during transition
6. After validation, migrate old data if needed

## Implementation Priority

**HIGH (Do Now):**
- entry_cycle_id / exit_cycle_id
- winning_policy_name
- active_primitives snapshot
- holding_duration_sec

**MEDIUM (Do Soon):**
- MFE/MAE tracking
- Rejection logging
- Position lifecycle table

**LOW (Nice to Have):**
- Orderbook depth snapshots
- Correlation with other symbols
- Fee tracking

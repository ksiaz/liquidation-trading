# Observatory Data Catalog

**Document Type:** Data Dictionary
**Phase:** F1 — Observatory Data Foundation
**Status:** ACTIVE
**Date:** 2026-02-01

---

## Purpose

This catalog documents all data sources available to the Observatory system for read-only observation. The Observatory provides visibility into system state without influencing execution.

**Constitutional Constraint:** All access is READ-ONLY. No modifications permitted.

---

## 1. Primary Database: execution.db

**Location:** `logs/execution.db`
**Access:** Read-only via `?mode=ro` URI parameter

### Core Execution Tables

#### execution_cycles
Records each execution cycle of the paper trading system.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key (auto-increment) |
| timestamp | REAL | Unix timestamp of cycle |
| observation_status | TEXT | Status of observation layer |
| m2_active_nodes | INTEGER | Count of active M2 zones |

#### mandates
Records policy mandates emitted during execution.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| cycle_id | INTEGER | FK to execution_cycles |
| policy_evaluation_id | INTEGER | FK to policy_evaluations |
| symbol | TEXT | Trading symbol (e.g., BTC, ETH) |
| mandate_type | TEXT | ENTRY, EXIT, or BLOCK |
| direction | TEXT | LONG or SHORT |
| source | TEXT | Policy that emitted mandate |
| confidence | REAL | Confidence score [0,1] |
| timestamp | REAL | Emission timestamp |

#### arbitration_rounds
Records mandate arbitration results.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| cycle_id | INTEGER | FK to execution_cycles |
| symbol | TEXT | Trading symbol |
| mandate_count | INTEGER | Input mandate count |
| winning_mandate_id | INTEGER | FK to winning mandate |
| action_taken | TEXT | Resulting action |
| theorem_applied | TEXT | Which theorem resolved |
| timestamp | REAL | Arbitration timestamp |

#### m2_nodes
Records M2 supply/demand zone state.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| cycle_id | INTEGER | FK to execution_cycles |
| node_id | TEXT | Unique zone identifier |
| symbol | TEXT | Trading symbol |
| zone_type | TEXT | demand or supply |
| price_low | REAL | Zone lower bound |
| price_high | REAL | Zone upper bound |
| strength | REAL | Zone strength [0,1] |
| created_at | REAL | Creation timestamp |
| invalidated_at | REAL | Invalidation timestamp (NULL if active) |

#### policy_evaluations
Records policy evaluation results.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| cycle_id | INTEGER | FK to execution_cycles |
| policy_name | TEXT | Policy identifier |
| symbol | TEXT | Trading symbol |
| result | TEXT | Evaluation outcome |
| confidence | REAL | Confidence score |
| timestamp | REAL | Evaluation timestamp |

### Liquidation Tables

#### liquidation_events
Records detected liquidation events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | REAL | Event timestamp |
| symbol | TEXT | Trading symbol |
| side | TEXT | LONG or SHORT |
| size | REAL | Liquidation size (USD) |
| price | REAL | Liquidation price |
| source | TEXT | Data source |

#### hl_liquidation_events_raw
Raw liquidation events from HL node.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| detected_ts | INTEGER | Detection timestamp |
| wallet_address | TEXT | Liquidated wallet |
| coin | TEXT | Coin symbol |
| last_known_szi | TEXT | Last known size |
| liquidation_price | TEXT | Estimated liq price |

#### hl_cascade_events
Cascade liquidation events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | REAL | Event timestamp |
| coin | TEXT | Coin symbol |
| event_type | TEXT | Event classification |
| current_price | REAL | Price at event |
| positions_at_risk | INTEGER | Count at risk |
| value_at_risk | REAL | USD at risk |

### Position Tables

#### hl_positions
HL position state snapshots.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | REAL | Snapshot timestamp |
| wallet_address | TEXT | Wallet identifier |
| coin | TEXT | Coin symbol |
| side | TEXT | LONG or SHORT |
| size | REAL | Position size |
| entry_price | REAL | Entry price |
| liquidation_price | REAL | Liquidation price |
| unrealized_pnl | REAL | Unrealized P&L |

#### hl_liquidation_proximity
Position proximity to liquidation.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | REAL | Calculation timestamp |
| coin | TEXT | Coin symbol |
| current_price | REAL | Current price |
| threshold_pct | REAL | Threshold percentage |
| total_positions_at_risk | INTEGER | Positions within threshold |
| total_value_at_risk | REAL | USD value at risk |

### Market Data Tables

#### ohlc_candles
Price candle data.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| symbol | TEXT | Trading symbol |
| timestamp | REAL | Candle timestamp |
| open | REAL | Open price |
| high | REAL | High price |
| low | REAL | Low price |
| close | REAL | Close price |
| volume | REAL | Volume |

#### mark_prices
Mark price snapshots.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | REAL | Snapshot timestamp |
| symbol | TEXT | Trading symbol |
| mark_price | REAL | Mark price |
| index_price | REAL | Index price |
| funding_rate | REAL | Current funding rate |

### System State Tables

#### hl_catastrophe_events
System catastrophe events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| ts_ns | INTEGER | Nanosecond timestamp |
| event_type | TEXT | Event classification |
| details | TEXT | Event details (JSON) |
| previous_state | TEXT | State before event |
| new_state | TEXT | State after event |

#### hl_gating_decisions
Execution gating decisions.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| ts_ns | INTEGER | Nanosecond timestamp |
| decision | TEXT | ALLOW or BLOCK |
| execution_state | TEXT | Current state |
| reason | TEXT | Decision reason |

---

## 2. Secondary Databases

### paper_trades.db

**Location:** `paper_trades.db`

#### paper_trades
Paper trade records.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| entry_time | TEXT | Entry timestamp |
| exit_time | TEXT | Exit timestamp |
| symbol | TEXT | Trading symbol |
| direction | TEXT | LONG or SHORT |
| entry_price | REAL | Entry price |
| exit_price | REAL | Exit price |
| size | REAL | Position size |
| pnl | REAL | Realized P&L |
| exit_reason | TEXT | Exit trigger |

### node_fills.db

**Location:** `logs/node_fills.db`

#### fills
Raw fill events from HL node.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | INTEGER | Fill timestamp |
| coin | TEXT | Coin symbol |
| side | TEXT | buy or sell |
| px | TEXT | Fill price |
| sz | TEXT | Fill size |
| start_position | TEXT | Position before |
| closed_pnl | TEXT | Closed P&L |
| hash | TEXT | Transaction hash |

---

## 3. In-Memory APIs

### StabilityObserver

**Module:** `runtime.stability_observer`
**Instance:** `stability_observer` (global singleton)

| Method | Returns | Description |
|--------|---------|-------------|
| `get_stability_status()` | dict | Overall stability status |
| `get_symbol_status(symbol)` | dict | Per-symbol stability |
| `summary()` | dict | Complete statistics |
| `get_recent_issues(n)` | list | Recent stability issues |

**Response Schema (get_stability_status):**
```python
{
    "status": "STABLE" | "WARNING" | "CRITICAL",
    "total_mandates": int,
    "total_actions": int,
    "issues_total": int,
    "symbols_monitored": int
}
```

### DiagnosticsCollector

**Module:** `runtime.diagnostics`
**Instance:** Accessed via CollectorService

| Method | Returns | Description |
|--------|---------|-------------|
| `get_counters()` | dict | Skip reason counters |
| `explain_inactivity(symbol)` | list | Recent skip reasons |

### ResourceMonitor

**Module:** `runtime.monitoring`
**Instance:** Created in paper trading script

| Method | Returns | Description |
|--------|---------|-------------|
| `get_report()` | ResourceReport | Current resource state |
| `get_trend()` | dict | Memory growth trend |

**Response Schema (get_report):**
```python
{
    "memory": {
        "rss_mb": float,
        "percent": float,
        "available_mb": float
    },
    "status": "NORMAL" | "WARNING" | "CRITICAL",
    "components": [...]
}
```

### CleanupCoordinator

**Module:** `runtime.monitoring`
**Instance:** Created in paper trading script

| Method | Returns | Description |
|--------|---------|-------------|
| `get_metrics()` | dict | Cleanup statistics |

**Response Schema:**
```python
{
    "cycles_completed": int,
    "total_items_pruned": int,
    "last_cycle_duration_ms": float
}
```

---

## 4. Access Patterns

### Read-Only Enforcement

All database connections MUST use read-only mode:

```python
conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
```

### Recommended Queries

**Recent mandates:**
```sql
SELECT * FROM mandates
ORDER BY timestamp DESC
LIMIT 100
```

**Active zones:**
```sql
SELECT * FROM m2_nodes
WHERE invalidated_at IS NULL
ORDER BY created_at DESC
```

**Liquidation events in last hour:**
```sql
SELECT * FROM liquidation_events
WHERE timestamp > strftime('%s', 'now') - 3600
ORDER BY timestamp DESC
```

**Stability status (in-memory):**
```python
from runtime.stability_observer import stability_observer
status = stability_observer.get_stability_status()
```

---

## 5. Constitutional Constraints

| Constraint | Enforcement |
|------------|-------------|
| No writes to execution.db | `?mode=ro` connection |
| No POST/PUT/DELETE endpoints | FastAPI GET-only |
| No feedback to execution | Process isolation |
| No performance metrics | Counts only, no scoring |
| Frozen layers untouched | No imports from frozen modules |

---

*End of Observatory Data Catalog*

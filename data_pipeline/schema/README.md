# Database Schema Documentation

Version 1 - Initial Schema for Market Data Pipeline

## Overview

Append-only storage for raw market data events from exchange feeds.

**Principle:** Data correctness > completeness > performance

---

## Tables

### orderbook_events

Stores L2 orderbook snapshots (top 20 levels).

| Column | Type | Description |
|--------|------|-------------|
| event_id | UUID | Primary key |
| timestamp | DOUBLE PRECISION | Exchange timestamp (seconds) |
| receive_time | DOUBLE PRECISION | Local receive timestamp |
| symbol | VARCHAR(20) | Trading pair (e.g., "BTCUSDT") |
| bids | TEXT | JSON array of [price, qty] |
| asks | TEXT | JSON array of [price, qty] |
| schema_version | INTEGER | Schema version (v1) |
| created_at | TIMESTAMPTZ | Insertion timestamp |

**Indexes:**
- `idx_orderbook_timestamp` on `(timestamp)`
- `idx_orderbook_symbol_timestamp` on `(symbol, timestamp)`

---

### trade_events

Stores aggressive trade executions.

| Column | Type | Description |
|--------|------|-------------|
| event_id | UUID | Primary key |
| timestamp | DOUBLE PRECISION | Exchange timestamp |
| receive_time | DOUBLE PRECISION | Local receive timestamp |
| symbol | VARCHAR(20) | Trading pair |
| price | DOUBLE PRECISION | Trade price |
| quantity | DOUBLE PRECISION | Trade quantity |
| is_buyer_maker | BOOLEAN | True if buyer was maker |
| schema_version | INTEGER | Schema version (v1) |
| created_at | TIMESTAMPTZ | Insertion timestamp |

**Indexes:**
- `idx_trade_timestamp` on `(timestamp)`
- `idx_trade_symbol_timestamp` on `(symbol, timestamp)`

---

### liquidation_events

Stores forced liquidation events.

| Column | Type | Description |
|--------|------|-------------|
| event_id | UUID | Primary key |
| timestamp | DOUBLE PRECISION | Exchange timestamp |
| receive_time | DOUBLE PRECISION | Local receive timestamp |
| symbol | VARCHAR(20) | Trading pair |
| side | VARCHAR(10) | "BUY" or "SELL" |
| price | DOUBLE PRECISION | Liquidation price |
| quantity | DOUBLE PRECISION | Liquidation quantity |
| schema_version | INTEGER | Schema version (v1) |
| created_at | TIMESTAMPTZ | Insertion timestamp |

**Indexes:**
- `idx_liquidation_timestamp` on `(timestamp)`
- `idx_liquidation_symbol_timestamp` on `(symbol, timestamp)`

---

### candle_events

Stores 1m OHLCV candles.

| Column | Type | Description |
|--------|------|-------------|
| event_id | UUID | Primary key |
| timestamp | DOUBLE PRECISION | Candle open time |
| receive_time | DOUBLE PRECISION | Local receive timestamp |
| symbol | VARCHAR(20) | Trading pair |
| open | DOUBLE PRECISION | Open price |
| high | DOUBLE PRECISION | High price |
| low | DOUBLE PRECISION | Low price |
| close | DOUBLE PRECISION | Close price |
| volume | DOUBLE PRECISION | Trade volume |
| is_closed | BOOLEAN | True if candle finalized |
| schema_version | INTEGER | Schema version (v1) |
| created_at | TIMESTAMPTZ | Insertion timestamp |

**Indexes:**
- `idx_candle_timestamp` on `(timestamp)`
- `idx_candle_symbol_timestamp` on `(symbol, timestamp)`

---

## Design Constraints

### Append-Only
- **INSERT only** - No UPDATE or DELETE operations
- Immutable historical record
- Audit trail preserved

### No Dependencies
- No foreign key constraints
- Self-contained tables
- Independent event streams

### No Computed Columns
- No mid_price calculation
- No trade_value aggregation
- Pure raw data storage

### Schema Versioning
- Current version: 1
- Future migrations add columns (never drop/rename)
- Allows backward-compatible evolution

---

## Usage

### Initial Setup
```bash
psql -U postgres -d trading -f schema/001_initial_schema.sql
```

### Verify Schema
```sql
SELECT tablename FROM pg_tables WHERE schemaname = 'public';
```

### Sample Query (Time Range)
```sql
SELECT * FROM trade_events
WHERE symbol = 'BTCUSDT'
  AND timestamp >= 1609459200.0
  AND timestamp < 1609545600.0
ORDER BY timestamp;
```

---

## Migration Strategy

**Version 1 (Current):**
- Initial schema

**Future Versions:**
- Add optional columns only
- Never drop existing columns
- Never change data types
- Maintain append-only invariant

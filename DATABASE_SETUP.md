# PostgreSQL Database Setup

This guide covers PostgreSQL setup for the liquidation trading system.

## Current Setup (Windows)

You're already using PostgreSQL on Windows. Your database is configured in `.env`:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=liquidation_trading
DB_USER=postgres
DB_PASSWORD=your_password
```

### Verify Your Setup

```bash
# Test database connection
python database.py
```

You should see:
```
✓ Connected to database
✓ Tables created
✅ Database setup complete!
```

---

## Adding Orderbook Storage Tables

To enable full 20-level orderbook storage:

### Option 1: Using pgAdmin (Recommended)

1. Open **pgAdmin 4**
2. Connect to your PostgreSQL server
3. Navigate to: **Databases → liquidation_trading**
4. Right-click → **Query Tool**
5. Open file: `database_orderbook_schema.sql`
6. Click **Execute** (F5)

### Option 2: Using Python

```bash
python -c "from database import DatabaseManager; db = DatabaseManager(); db.cursor.execute(open('database_orderbook_schema.sql').read()); db.conn.commit(); print('✅ Orderbook tables created!')"
```

### Option 3: Using psql (if in PATH)

```bash
psql -U postgres -d liquidation_trading -f database_orderbook_schema.sql
```

---

## Your Configuration

Your `.env` file should already be configured with:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=liquidation_trading
DB_USER=postgres
DB_PASSWORD=your_password_here
```

### Test Your Connection

```bash
python database.py
```

Expected output:
```
✓ Connected to database
✓ Tables created
✓ Test event inserted
✓ Database stats: 1 events

✅ Database setup complete!
```

---

## Database Schema

The system creates multiple tables for different data types:

### Core Liquidation Tables

#### 1. `liquidations` (Main Data)
- `id`: Auto-incrementing primary key
- `timestamp`: When liquidation occurred
- `trade_time`: Trade execution time
- `symbol`: Trading pair (BTCUSDT, ETHUSDT, SOLUSDT)
- `side`: SELL (longs) or BUY (shorts)
- `quantity`: Amount liquidated
- `price`: Liquidation price
- `avg_price`: Average execution price
- `value_usd`: Total USD value
- `status`: Order status
- `exchange`: Source exchange (BINANCE, DYDX, HYPERLIQUID)
- `created_at`: When record was inserted

**Indexes**: timestamp, symbol, side, value_usd, (symbol, timestamp)

**Storage**: ~10-50 MB/month depending on market activity

#### 2. `liquidation_stats` (Daily Aggregates)
- Daily statistics per symbol and side
- Total events, value, averages, min/max
- Used for dashboard summary metrics

**Storage**: <1 MB/month

#### 3. `monitor_sessions` (Session Tracking)
- Tracks each monitoring session
- Total events, uptime, metadata

**Storage**: <1 MB/month

### Orderbook Storage Tables (Optional)

> **Note**: These tables are created when you run `database_orderbook_schema.sql`

#### 4. `orderbook_snapshots` (Full 20-Level Data)
- `id`: Auto-incrementing primary key
- `symbol`: Trading pair
- `timestamp`: Snapshot time
- `best_bid`, `best_ask`: Top of book
- `best_bid_qty`, `best_ask_qty`: Sizes
- `spread_bps`: Spread in basis points
- `mid_price`: Mid-market price
- **`bids`**: JSONB array of 20 bid levels `[[price, qty], ...]`
- **`asks`**: JSONB array of 20 ask levels `[[price, qty], ...]`
- `update_id`: Binance update ID
- `event_time`: Exchange timestamp

**Indexes**: (symbol, timestamp), timestamp, recent data (7 days)

**Storage**: ~5.4 GB/month for 3 symbols at 1-second intervals

**Purpose**: Advanced market microstructure analysis, orderbook reconstruction, optimal execution research

#### 5. `orderbook_metrics` (Pre-calculated Analytics)
- `bid_depth_5levels`, `ask_depth_5levels`: USD depth in top 5 levels
- `bid_depth_10levels`, `ask_depth_10levels`: USD depth in top 10 levels
- `bid_depth_20levels`, `ask_depth_20levels`: USD depth in all 20 levels
- `imbalance_5levels`, `imbalance_10levels`, `imbalance_20levels`: Order flow imbalance
- `avg_bid_size_5levels`, `avg_ask_size_5levels`: Average order sizes
- `large_bid_wall`, `large_ask_wall`: Wall detection flags
- `wall_price`, `wall_size`: Detected wall details
- `mlofi_value`, `mlofi_momentum`: Multi-Level OFI metrics

**Storage**: ~200-300 MB/month for 3 symbols

**Purpose**: Fast queries for depth analysis, imbalance tracking, wall detection

### Legacy Tables (Old Format)

#### 6. `orderbook_depth` (Deprecated)
- Old liquidity analysis format
- Replaced by `orderbook_metrics`

#### 7. `orderbook_walls` (Deprecated)
- Old wall detection format
- Replaced by wall detection in `orderbook_metrics`

---

## Storage Summary

| Component | Storage/Month | Required |
|-----------|---------------|----------|
| Liquidations | 10-50 MB | ✅ Yes |
| Stats & Sessions | <2 MB | ✅ Yes |
| **Orderbook Snapshots** | **5.4 GB** | ❌ Optional |
| **Orderbook Metrics** | **300 MB** | ❌ Optional |
| **Total (Full System)** | **~6 GB** | - |

> **Recommendation**: Start with core liquidation tables only. Add orderbook storage after 1-2 weeks if you need advanced market microstructure analysis.

## Querying the Database

### Using psql (Command Line)

```bash
# Connect to database
psql -h localhost -U postgres -d liquidation_trading

# View recent liquidations
SELECT * FROM liquidations ORDER BY timestamp DESC LIMIT 10;

# Get statistics by symbol
SELECT symbol, COUNT(*), SUM(value_usd) 
FROM liquidations 
GROUP BY symbol;

# Find large liquidations
SELECT * FROM liquidations 
WHERE value_usd > 100000 
ORDER BY value_usd DESC;
```

### Using pgAdmin (GUI)

1. Open pgAdmin
2. Connect to your server
3. Navigate to: Servers > PostgreSQL > Databases > liquidation_trading
4. Right-click > Query Tool
5. Run SQL queries

### Using Python

```python
from database import DatabaseManager

db = DatabaseManager()

# Get statistics
stats = db.get_stats(symbol='BTCUSDT')
print(f"Total events: {stats['total_events']}")
print(f"Total value: ${stats['total_value']:,.2f}")

# Get recent liquidations
recent = db.get_recent_liquidations(limit=10)
for event in recent:
    print(f"{event['timestamp']} - {event['symbol']} ${event['value_usd']:,.2f}")

db.close()
```

## Backup and Maintenance

### Backup Database (Using pgAdmin)

1. Open **pgAdmin 4**
2. Right-click on `liquidation_trading` database
3. Select **Backup...**
4. Choose location and filename
5. Click **Backup**

### Monitor Database Size (Using pgAdmin)

1. Right-click on `liquidation_trading` database
2. Select **Properties** → **Statistics**
3. View size information

Or using Python:

```python
from database import DatabaseManager

db = DatabaseManager()
db.cursor.execute("SELECT pg_size_pretty(pg_database_size('liquidation_trading'));")
print(f"Database size: {db.cursor.fetchone()[0]}")
db.close()
```

---

## Troubleshooting

### "Connection refused" Error

**Check if PostgreSQL is running:**
1. Open **Services** (Windows + R, type `services.msc`)
2. Find **postgresql-x64-XX** service
3. Ensure it's **Running**
4. If not, right-click → **Start**

### "Authentication failed" Error

**Check your `.env` file:**
- Verify `DB_PASSWORD` matches your PostgreSQL password
- Verify `DB_USER` is `postgres` (or your actual username)

### "Database does not exist" Error

**Create the database:**
1. Open **pgAdmin 4**
2. Right-click **Databases**
3. Select **Create** → **Database...**
4. Name: `liquidation_trading`
5. Click **Save**

---

## Next Steps

Once database is set up:

1. ✅ Verify connection: `python database.py`
2. ✅ Run monitor: `python monitor.py` (starts collecting liquidation data)
3. ✅ Run dashboard: `python dashboard_server.py` (includes orderbook storage)
4. ⏳ Let it collect data for 24-48 hours
5. 📊 Start analyzing patterns and building strategies

The system will automatically create all necessary tables and start saving data!


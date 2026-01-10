# PostgreSQL Setup for Historical Data Ingestion

Quick setup guide for P8b ingestion.

## Option 1: Docker (Recommended)

```bash
# Pull PostgreSQL image
docker pull postgres:15

# Run PostgreSQL container
docker run -d \
  --name trading-db \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=trading \
  -p 5432:5432 \
  postgres:15

# Verify running
docker ps | grep trading-db
```

## Option 2: Local Install

Download from: https://www.postgresql.org/download/

After installation:
```bash
# Create database
createdb trading

# Or via psql
psql -U postgres
CREATE DATABASE trading;
```

## Apply Schema (P3)

```bash
cd d:/liquidation-trading

# Apply schema
psql -U postgres -d trading -f data_pipeline/schema/001_initial_schema.sql
```

## Update Connection String

Edit `scripts/ingest_historical_data.py`:

```python
# Line 173 - Update with your credentials
conn_string = "postgresql://postgres:password@localhost:5432/trading"
```

## Run Ingestion

```bash
python scripts/ingest_historical_data.py
```

Expected output:
```
Connected to PostgreSQL
Ingesting aggTrades from BTCUSDT-aggTrades-2024-12-01.csv...
  Progress: 10000 trades ingested
  ...
  Completed: XXXXX trades ingested
Ingesting klines from BTCUSDT-1m-2024-12-01.csv...
  Completed: 1440 candles ingested
...
=== Ingestion Summary ===
Trades ingested: XXXXX
Candles ingested: 2880
Liquidations ingested: 0
Total events: XXXXX
```

## Verify Data

```sql
-- Check counts
SELECT COUNT(*) FROM trade_events;
SELECT COUNT(*) FROM candle_events;
SELECT COUNT(*) FROM liquidation_events;

-- Check time range
SELECT MIN(timestamp), MAX(timestamp) FROM trade_events;
```

## Run Integrity Validation (P5)

```python
from data_pipeline.validation import DataIntegrityValidator

validator = DataIntegrityValidator("postgresql://postgres:password@localhost:5432/trading")
validator.connect()

report = validator.run_full_validation("BTCUSDT")
print(f"Total issues: {report['total_issues']}")

validator.close()
```

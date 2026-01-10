-- Initial Schema for Market Data Pipeline
-- Version: 1
-- Created: 2026-01-03
--
-- CRITICAL RULES:
-- - Append-only tables (INSERT only)
-- - No UPDATE or DELETE operations
-- - No foreign key constraints
-- - No computed columns
-- - No aggregation at database level
--
-- PRINCIPLE: Data correctness > completeness > performance

-- ==============================================
-- TABLE: orderbook_events
-- ==============================================
-- Stores L2 orderbook snapshots

CREATE TABLE IF NOT EXISTS orderbook_events (
    event_id UUID PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,
    receive_time DOUBLE PRECISION NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    bids TEXT NOT NULL,  -- JSON array: [[price, qty], ...]
    asks TEXT NOT NULL,  -- JSON array: [[price, qty], ...]
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for time-range queries
CREATE INDEX IF NOT EXISTS idx_orderbook_timestamp 
ON orderbook_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_timestamp 
ON orderbook_events(symbol, timestamp);

-- ==============================================
-- TABLE: trade_events
-- ==============================================
-- Stores aggressive trade executions

CREATE TABLE IF NOT EXISTS trade_events (
    event_id UUID PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,
    receive_time DOUBLE PRECISION NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    is_buyer_maker BOOLEAN NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for time-range queries
CREATE INDEX IF NOT EXISTS idx_trade_timestamp 
ON trade_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_trade_symbol_timestamp 
ON trade_events(symbol, timestamp);

-- ==============================================
-- TABLE: liquidation_events
-- ==============================================
-- Stores forced liquidation events

CREATE TABLE IF NOT EXISTS liquidation_events (
    event_id UUID PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,
    receive_time DOUBLE PRECISION NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- "BUY" or "SELL"
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for time-range queries
CREATE INDEX IF NOT EXISTS idx_liquidation_timestamp 
ON liquidation_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_liquidation_symbol_timestamp 
ON liquidation_events(symbol, timestamp);

-- ==============================================
-- TABLE: candle_events
-- ==============================================
-- Stores 1m OHLCV candles

CREATE TABLE IF NOT EXISTS candle_events (
    event_id UUID PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,  -- Candle open time
    receive_time DOUBLE PRECISION NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    is_closed BOOLEAN NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for time-range queries
CREATE INDEX IF NOT EXISTS idx_candle_timestamp 
ON candle_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_candle_symbol_timestamp 
ON candle_events(symbol, timestamp);

-- ==============================================
-- SCHEMA VERIFICATION QUERIES
-- ==============================================

-- Verify all tables exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'orderbook_events') THEN
        RAISE EXCEPTION 'Table orderbook_events not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'trade_events') THEN
        RAISE EXCEPTION 'Table trade_events not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'liquidation_events') THEN
        RAISE EXCEPTION 'Table liquidation_events not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'candle_events') THEN
        RAISE EXCEPTION 'Table candle_events not created';
    END IF;
    RAISE NOTICE 'All tables created successfully';
END $$;

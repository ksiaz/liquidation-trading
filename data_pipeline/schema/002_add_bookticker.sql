-- Add bookTicker events table
-- Created: 2026-01-03 for C5 compliance

CREATE TABLE IF NOT EXISTS bookticker_events (
    event_id UUID PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,
    receive_time DOUBLE PRECISION NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    best_bid_price DOUBLE PRECISION NOT NULL,
    best_bid_qty DOUBLE PRECISION NOT NULL,
    best_ask_price DOUBLE PRECISION NOT NULL,
    best_ask_qty DOUBLE PRECISION NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for time-range queries
CREATE INDEX IF NOT EXISTS idx_bookticker_timestamp 
ON bookticker_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_bookticker_symbol_timestamp 
ON bookticker_events(symbol, timestamp);

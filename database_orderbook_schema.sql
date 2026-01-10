-- Orderbook Storage Schema
-- Stores 20-level orderbook snapshots at 1-second intervals
-- Expected storage: ~5.4 GB/month for 3 symbols

-- Main orderbook snapshots table
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    event_time BIGINT,  -- Exchange timestamp in milliseconds
    
    -- Best bid/ask (for quick queries)
    best_bid DECIMAL(20, 8) NOT NULL,
    best_ask DECIMAL(20, 8) NOT NULL,
    best_bid_qty DECIMAL(20, 8) NOT NULL,
    best_ask_qty DECIMAL(20, 8) NOT NULL,
    
    -- Full orderbook data (JSONB for flexibility)
    bids JSONB NOT NULL,  -- Array of [price, quantity] pairs (20 levels)
    asks JSONB NOT NULL,  -- Array of [price, quantity] pairs (20 levels)
    
    -- Pre-calculated metrics (for performance)
    spread_bps DECIMAL(10, 4),
    mid_price DECIMAL(20, 8),
    
    -- Metadata
    update_id BIGINT,  -- Binance update ID for tracking
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_ob_symbol_time ON orderbook_snapshots(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ob_timestamp ON orderbook_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ob_symbol_created ON orderbook_snapshots(symbol, created_at DESC);

-- Partial index for recent data (most queries are on recent data)
CREATE INDEX IF NOT EXISTS idx_ob_recent ON orderbook_snapshots(symbol, timestamp DESC) 
WHERE timestamp > NOW() - INTERVAL '7 days';

-- Optional: Partition by month for better performance and easier archival
-- Uncomment if you want time-based partitioning
/*
CREATE TABLE orderbook_snapshots_2025_01 PARTITION OF orderbook_snapshots
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE orderbook_snapshots_2025_02 PARTITION OF orderbook_snapshots
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
*/

-- Derived metrics table (optional - for pre-calculated analytics)
CREATE TABLE IF NOT EXISTS orderbook_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    
    -- Depth metrics
    bid_depth_5levels DECIMAL(20, 2),   -- Total USD in top 5 bids
    ask_depth_5levels DECIMAL(20, 2),   -- Total USD in top 5 asks
    bid_depth_10levels DECIMAL(20, 2),
    ask_depth_10levels DECIMAL(20, 2),
    bid_depth_20levels DECIMAL(20, 2),
    ask_depth_20levels DECIMAL(20, 2),
    
    -- Imbalance metrics
    imbalance_5levels DECIMAL(10, 6),   -- (bid_vol - ask_vol) / total
    imbalance_10levels DECIMAL(10, 6),
    imbalance_20levels DECIMAL(10, 6),
    
    -- Multi-Level OFI
    mlofi_value DECIMAL(20, 2),
    mlofi_momentum DECIMAL(20, 2),
    
    -- Liquidity metrics
    avg_bid_size_5levels DECIMAL(20, 8),
    avg_ask_size_5levels DECIMAL(20, 8),
    
    -- Wall detection
    large_bid_wall BOOLEAN DEFAULT FALSE,
    large_ask_wall BOOLEAN DEFAULT FALSE,
    wall_price DECIMAL(20, 8),
    wall_size DECIMAL(20, 2),
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_symbol_time ON orderbook_metrics(symbol, timestamp DESC);

-- View for easy querying of latest orderbook
CREATE OR REPLACE VIEW latest_orderbook AS
SELECT DISTINCT ON (symbol)
    symbol,
    timestamp,
    best_bid,
    best_ask,
    spread_bps,
    mid_price,
    bids,
    asks
FROM orderbook_snapshots
ORDER BY symbol, timestamp DESC;

-- View for orderbook with metrics
CREATE OR REPLACE VIEW orderbook_with_metrics AS
SELECT 
    o.symbol,
    o.timestamp,
    o.best_bid,
    o.best_ask,
    o.spread_bps,
    o.bids,
    o.asks,
    m.imbalance_5levels,
    m.bid_depth_5levels,
    m.ask_depth_5levels,
    m.mlofi_value,
    m.large_bid_wall,
    m.large_ask_wall
FROM orderbook_snapshots o
LEFT JOIN orderbook_metrics m ON o.symbol = m.symbol 
    AND o.timestamp = m.timestamp;

-- Function to clean old data (keep last 30 days)
CREATE OR REPLACE FUNCTION cleanup_old_orderbook_data()
RETURNS void AS $$
BEGIN
    DELETE FROM orderbook_snapshots 
    WHERE timestamp < NOW() - INTERVAL '30 days';
    
    DELETE FROM orderbook_metrics 
    WHERE timestamp < NOW() - INTERVAL '30 days';
    
    RAISE NOTICE 'Cleaned up orderbook data older than 30 days';
END;
$$ LANGUAGE plpgsql;

-- Optional: Create scheduled job to run cleanup weekly
-- Requires pg_cron extension
/*
SELECT cron.schedule('cleanup-orderbook', '0 2 * * 0', 'SELECT cleanup_old_orderbook_data()');
*/

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT ON orderbook_snapshots TO your_app_user;
-- GRANT SELECT, INSERT ON orderbook_metrics TO your_app_user;
-- GRANT SELECT ON latest_orderbook TO your_app_user;
-- GRANT SELECT ON orderbook_with_metrics TO your_app_user;

-- Useful queries for monitoring storage

-- Check table sizes
/*
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename LIKE 'orderbook%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
*/

-- Count snapshots per symbol
/*
SELECT 
    symbol,
    COUNT(*) as snapshot_count,
    MIN(timestamp) as oldest,
    MAX(timestamp) as newest,
    MAX(timestamp) - MIN(timestamp) as time_range
FROM orderbook_snapshots
GROUP BY symbol;
*/

-- Check storage growth rate
/*
SELECT 
    DATE(timestamp) as date,
    symbol,
    COUNT(*) as snapshots_per_day,
    pg_size_pretty(
        COUNT(*) * 700  -- Approximate bytes per snapshot
    ) as estimated_daily_size
FROM orderbook_snapshots
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY DATE(timestamp), symbol
ORDER BY date DESC, symbol;
*/

-- Create only the orderbook_metrics table (snapshots already exists)

CREATE TABLE IF NOT EXISTS orderbook_metrics (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES orderbook_snapshots(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    
    -- Spread metrics
    spread_bps DECIMAL(10, 4),
    spread_pct DECIMAL(10, 6),
    mid_price DECIMAL(20, 8),
    
    -- Depth metrics (cumulative volume at price levels)
    depth_1_bps DECIMAL(20, 8),
    depth_5_bps DECIMAL(20, 8),
    depth_10_bps DECIMAL(20, 8),
    depth_25_bps DECIMAL(20, 8),
    depth_50_bps DECIMAL(20, 8),
    depth_100_bps DECIMAL(20, 8),
    
    -- Volume imbalance
    imbalance DECIMAL(10, 6),
    
    -- Weighted mid price
    weighted_mid DECIMAL(20, 8),
    
    -- Volume metrics
    total_bid_volume DECIMAL(20, 8),
    total_ask_volume DECIMAL(20, 8),
    bid_volume_10 DECIMAL(20, 8),
    ask_volume_10 DECIMAL(20, 8),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_orderbook_metrics_symbol_timestamp 
    ON orderbook_metrics(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_orderbook_metrics_snapshot_id 
    ON orderbook_metrics(snapshot_id);

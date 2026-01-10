-- Signal Persistence Database Schema
-- Stores all trading signals for recovery after crashes/restarts

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,  -- LONG or SHORT
    type TEXT NOT NULL,       -- FUNDING_FADE, VOLUME_FLOW, etc.
    
    -- Prices
    entry REAL NOT NULL,
    target REAL NOT NULL,
    stop REAL NOT NULL,
    current_price REAL,
    
    -- Signal metadata
    confidence REAL NOT NULL,
    reason TEXT,
    regime TEXT,
    nearby_zones INTEGER,
    risk_reward REAL,
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN, CLOSED
    outcome TEXT,                          -- WIN, LOSS, null if open
    
    -- P&L tracking
    unrealized_pnl_pct REAL DEFAULT 0,
    realized_pnl_pct REAL,
    distance_to_target_pct REAL,
    distance_to_stop_pct REAL,
    
    -- Timing
    timestamp REAL NOT NULL,
    entry_time REAL,
    exit_time REAL,
    duration_seconds REAL,
    
    -- Exit details
    exit_price REAL,
    close_reason TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_symbol (symbol),
    INDEX idx_status (status),
    INDEX idx_timestamp (timestamp),
    INDEX idx_outcome (outcome)
);

-- Performance stats table (aggregated metrics)
CREATE TABLE IF NOT EXISTS signal_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Overall stats
    total_signals INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    open_positions INTEGER DEFAULT 0,
    
    -- Performance metrics
    win_rate REAL DEFAULT 0,
    avg_rr_realized REAL DEFAULT 0,
    total_pnl_pct REAL DEFAULT 0,
    avg_pnl_per_trade REAL DEFAULT 0,
    
    -- By strategy type
    strategy_type TEXT,
    
    -- Timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(strategy_type)
);

-- Trigger to update timestamp on signal updates
CREATE TRIGGER IF NOT EXISTS update_signal_timestamp 
AFTER UPDATE ON signals
BEGIN
    UPDATE signals SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

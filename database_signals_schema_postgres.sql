-- PostgreSQL Schema for Trading Signals
-- Integrates with existing liquidation database

-- Signals table
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    type TEXT NOT NULL,
    entry DECIMAL(20, 8) NOT NULL,
    target DECIMAL(20, 8) NOT NULL,
    stop DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    regime TEXT,
    nearby_zones INTEGER,
    risk_reward DECIMAL(10, 4),
    status TEXT NOT NULL DEFAULT 'OPEN',
    outcome TEXT,
    unrealized_pnl_pct DECIMAL(10, 4) DEFAULT 0,
    realized_pnl_pct DECIMAL(10, 4),
    distance_to_target_pct DECIMAL(10, 4),
    distance_to_stop_pct DECIMAL(10, 4),
    timestamp DECIMAL(20, 6) NOT NULL,
    entry_time DECIMAL(20, 6),
    exit_time DECIMAL(20, 6),
    duration_seconds DECIMAL(20, 2),
    exit_price DECIMAL(20, 8),
    close_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(type);
CREATE INDEX IF NOT EXISTS idx_signals_outcome ON signals(outcome);

-- Signal performance summary view
CREATE OR REPLACE VIEW signal_performance AS
SELECT 
    type,
    COUNT(*) as total_signals,
    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_signals,
    ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN realized_pnl_pct ELSE NULL END), 4) as avg_pnl_pct,
    ROUND(
        CAST(SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) AS DECIMAL) / 
        NULLIF(SUM(CASE WHEN outcome IN ('WIN', 'LOSS') THEN 1 ELSE 0 END), 0) * 100, 
        2
    ) as win_rate_pct
FROM signals
GROUP BY type;

-- Update trigger for updated_at
CREATE OR REPLACE FUNCTION update_signals_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER signals_updated_at_trigger
    BEFORE UPDATE ON signals
    FOR EACH ROW
    EXECUTE FUNCTION update_signals_updated_at();

-- Clean up old signals and add position management fields

-- 1. Delete old signals (keep only last 7 days)
DELETE FROM trading_signals 
WHERE timestamp < NOW() - INTERVAL '7 days';

-- 2. Add position management fields
ALTER TABLE trading_signals 
ADD COLUMN IF NOT EXISTS target1_price DECIMAL(20, 8),
ADD COLUMN IF NOT EXISTS target1_hit BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS target1_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS sl_breakeven BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS sl_breakeven_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS exit_price DECIMAL(20, 8),
ADD COLUMN IF NOT EXISTS exit_time TIMESTAMP,
ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(50),
ADD COLUMN IF NOT EXISTS pnl_t1 DECIMAL(10, 4),
ADD COLUMN IF NOT EXISTS pnl_t2 DECIMAL(10, 4),
ADD COLUMN IF NOT EXISTS pnl_total DECIMAL(10, 4),
ADD COLUMN IF NOT EXISTS position_status VARCHAR(20) DEFAULT 'ACTIVE';

-- 3. Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_signals_status ON trading_signals(position_status);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading_signals(symbol, timestamp DESC);

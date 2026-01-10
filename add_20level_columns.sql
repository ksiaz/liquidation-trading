-- Add 20-level metrics to orderbook_snapshots table
ALTER TABLE orderbook_snapshots 
ADD COLUMN bid_volume_20 DECIMAL(20, 8),
ADD COLUMN ask_volume_20 DECIMAL(20, 8),
ADD COLUMN bid_value_20 DECIMAL(20, 2),
ADD COLUMN ask_value_20 DECIMAL(20, 2),
ADD COLUMN imbalance_20 DECIMAL(10, 6);

-- Update existing rows to have NULL for new columns (they'll be populated going forward)
COMMENT ON COLUMN orderbook_snapshots.bid_volume_20 IS 'Total bid volume across top 20 levels';
COMMENT ON COLUMN orderbook_snapshots.ask_volume_20 IS 'Total ask volume across top 20 levels';
COMMENT ON COLUMN orderbook_snapshots.bid_value_20 IS 'Total bid value in USD across top 20 levels';
COMMENT ON COLUMN orderbook_snapshots.ask_value_20 IS 'Total ask value in USD across top 20 levels';
COMMENT ON COLUMN orderbook_snapshots.imbalance_20 IS 'Orderbook imbalance across top 20 levels (-1 to +1)';

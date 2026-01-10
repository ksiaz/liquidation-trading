"""
Configuration settings for liquidation trading analysis
"""

# Trading pairs to monitor
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Liquidation thresholds (in USDT)
MIN_LIQUIDATION_SIZE = {
    'BTCUSDT': 50000,   # $50k minimum
    'ETHUSDT': 30000,   # $30k minimum
    'SOLUSDT': 20000,   # $20k minimum
}

# Time windows for aggregation (seconds)
AGGREGATION_WINDOW = 60  # 1 minute window to group liquidations

# Trading parameters
POSITION_SIZE_PCT = 0.01  # 1% of capital per trade
STOP_LOSS_PCT = 0.005     # 0.5% stop loss
TAKE_PROFIT_PCT = 0.01    # 1% take profit

# Data collection
DATA_DIR = 'D:\\liquidation-trading\\data'
LOG_FILE = 'data/liquidations.log'
CSV_FILE = 'data/liquidations.csv'

# Data persistence settings
BUFFER_SIZE = 100          # Events before flush
FLUSH_INTERVAL = 10        # Seconds between auto-flush
COMPRESSION_DAYS = 7       # Compress files older than N days

# WebSocket settings
RECONNECT_DELAY = 5        # Initial reconnect delay (seconds)
MAX_RECONNECT_DELAY = 60   # Maximum reconnect delay (seconds)
PING_INTERVAL = 60         # Ping interval (seconds)
PING_TIMEOUT = 10          # Ping timeout (seconds)

# Binance WebSocket endpoints
LIQUIDATION_STREAM_URL = 'wss://fstream.binance.com/ws/!forceOrder@arr'

# Dashboard settings
DASHBOARD_ZONES_TO_SHOW = 10  # Number of liquidation zones to display per side
DASHBOARD_MIN_VALUE_USD = 10000  # Minimum liquidation value to display ($10k)

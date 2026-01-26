"""
Node Adapter Configuration

All configurable parameters for the Hyperliquid node adapter.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class NodeAdapterConfig:
    """Configuration for HyperliquidNodeAdapter."""

    # ========== Node Paths ==========
    # Base path to Hyperliquid node data (native Ubuntu)
    node_data_path: str = "~/hl/data"

    # Path to state files
    node_state_path: str = "~/hl/hyperliquid_data"

    # ========== Streaming Configuration ==========
    # Maximum blocks to buffer before backpressure
    block_buffer_size: int = 100

    # Minimum interval between price emissions (ms)
    # Prevents flooding on rapid SetGlobalAction bursts
    price_emit_interval_ms: int = 0  # 0 = emit all

    # ========== TCP Server Configuration ==========
    # TCP server host (0.0.0.0 for all interfaces, 127.0.0.1 for localhost only)
    tcp_host: str = "127.0.0.1"

    # TCP server port
    tcp_port: int = 8090

    # Maximum concurrent TCP clients
    max_clients: int = 5

    # ========== Position State Configuration ==========
    # Refresh tiers for position state management

    # CRITICAL tier: positions < this % from liquidation
    critical_threshold_pct: float = 0.5

    # WATCHLIST tier: positions < this % from liquidation
    watchlist_threshold_pct: float = 2.0

    # MONITORED tier: positions < this % from liquidation
    monitored_threshold_pct: float = 5.0

    # Refresh intervals (seconds)
    watchlist_refresh_interval: float = 5.0
    monitored_refresh_interval: float = 30.0
    discovery_scan_interval: float = 60.0

    # Minimum position value to track (USD)
    min_position_value_usd: float = 1000.0

    # ========== Performance Configuration ==========
    # Number of JSON parse workers (0 = single-threaded)
    json_parse_workers: int = 0

    # Enable backpressure handling
    enable_backpressure: bool = True

    # Backpressure timeout (seconds) before dropping events
    backpressure_timeout: float = 1.0

    # ========== Extraction Configuration ==========
    # Extract order actions for position change detection
    extract_orders: bool = True

    # Extract cancel actions (useful for order flow analysis)
    extract_cancels: bool = False

    # Coins to focus on (empty = all coins)
    # Use for filtering to reduce processing
    focus_coins: List[str] = field(default_factory=list)

    # ========== Logging Configuration ==========
    # Log every N blocks processed (0 = no logging)
    log_block_interval: int = 1000

    # Log metrics every N seconds (0 = no logging)
    log_metrics_interval: float = 60.0

    # ========== Sync Configuration ==========
    # Maximum acceptable sync lag (seconds) before warning
    max_sync_lag_warning: float = 5.0

    # Maximum acceptable sync lag (seconds) before error
    max_sync_lag_error: float = 30.0


@dataclass
class WindowsConnectorConfig:
    """Configuration for Windows-side TCP connector."""

    # TCP connection settings
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 8090

    # Reconnection settings
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 30.0
    reconnect_backoff: float = 2.0

    # Buffer settings
    read_buffer_size: int = 65536  # 64KB

    # Timeout settings
    connect_timeout: float = 5.0
    read_timeout: float = 60.0  # Long timeout - we expect continuous data

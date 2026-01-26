"""
Node Adapter Metrics

Dataclasses for tracking adapter performance and health.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class StreamerMetrics:
    """Metrics for ReplicaCmdStreamer."""

    # Block processing
    blocks_read: int = 0
    bytes_read: int = 0

    # File management
    files_rotated: int = 0
    current_file: str = ""

    # Timing
    start_time: float = field(default_factory=time.time)
    last_block_time: float = 0.0

    # Errors
    read_errors: int = 0
    parse_errors: int = 0

    @property
    def blocks_per_second(self) -> float:
        elapsed = time.time() - self.start_time
        return self.blocks_read / elapsed if elapsed > 0 else 0.0

    @property
    def bytes_per_second(self) -> float:
        elapsed = time.time() - self.start_time
        return self.bytes_read / elapsed if elapsed > 0 else 0.0


@dataclass
class ExtractorMetrics:
    """Metrics for BlockActionExtractor."""

    # Action counts
    set_global_actions: int = 0
    force_orders: int = 0
    orders_extracted: int = 0
    cancels_extracted: int = 0

    # Event counts (normalized output)
    price_events: int = 0
    liquidation_events: int = 0
    order_activity_events: int = 0

    # Errors
    extraction_errors: int = 0

    # Timing
    total_extraction_time_ms: float = 0.0
    extractions_count: int = 0

    @property
    def avg_extraction_time_ms(self) -> float:
        return self.total_extraction_time_ms / self.extractions_count if self.extractions_count > 0 else 0.0


@dataclass
class PositionStateMetrics:
    """Metrics for PositionStateManager."""

    # Cache state
    positions_cached: int = 0
    wallets_tracked: int = 0

    # Tier distribution
    critical_positions: int = 0
    watchlist_positions: int = 0
    monitored_positions: int = 0

    # Refresh activity
    targeted_refreshes: int = 0
    watchlist_refreshes: int = 0
    discovery_scans: int = 0

    # Timing
    last_discovery_scan_time: float = 0.0
    last_discovery_scan_duration_ms: float = 0.0

    # Proximity alerts
    proximity_alerts_emitted: int = 0
    tier_promotions: int = 0
    tier_demotions: int = 0


@dataclass
class TCPServerMetrics:
    """Metrics for TCP server."""

    # Connections
    total_connections: int = 0
    active_connections: int = 0
    connection_errors: int = 0

    # Events sent
    events_sent: int = 0
    bytes_sent: int = 0

    # Backpressure
    backpressure_events: int = 0
    dropped_events: int = 0


@dataclass
class SyncMetrics:
    """Metrics for node sync status."""

    # Current state
    block_height: int = 0
    consensus_time: str = ""
    wall_clock_time: str = ""
    lag_seconds: float = 0.0
    is_synced: bool = False

    # History
    max_lag_observed: float = 0.0
    sync_checks: int = 0
    sync_failures: int = 0


@dataclass
class AdapterMetrics:
    """
    Aggregate metrics for the entire adapter.

    Combines all component metrics for monitoring.
    """

    # Component metrics
    streamer: StreamerMetrics = field(default_factory=StreamerMetrics)
    extractor: ExtractorMetrics = field(default_factory=ExtractorMetrics)
    position_state: PositionStateMetrics = field(default_factory=PositionStateMetrics)
    tcp_server: TCPServerMetrics = field(default_factory=TCPServerMetrics)
    sync: SyncMetrics = field(default_factory=SyncMetrics)

    # Overall state
    start_time: float = field(default_factory=time.time)
    is_running: bool = False

    # Latency tracking (block timestamp to event emit)
    latency_samples: List[float] = field(default_factory=list)
    max_latency_samples: int = 1000

    def record_latency(self, block_time: float, emit_time: float) -> None:
        """Record block-to-emit latency."""
        latency_ms = (emit_time - block_time) * 1000
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > self.max_latency_samples:
            self.latency_samples = self.latency_samples[-self.max_latency_samples:]

    @property
    def latency_avg_ms(self) -> float:
        return sum(self.latency_samples) / len(self.latency_samples) if self.latency_samples else 0.0

    @property
    def latency_p99_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        sorted_samples = sorted(self.latency_samples)
        idx = int(len(sorted_samples) * 0.99)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "uptime_seconds": self.uptime_seconds,
            "is_running": self.is_running,
            "latency_avg_ms": round(self.latency_avg_ms, 2),
            "latency_p99_ms": round(self.latency_p99_ms, 2),
            "streamer": {
                "blocks_read": self.streamer.blocks_read,
                "blocks_per_second": round(self.streamer.blocks_per_second, 2),
                "bytes_per_second": round(self.streamer.bytes_per_second, 0),
                "files_rotated": self.streamer.files_rotated,
                "errors": self.streamer.read_errors + self.streamer.parse_errors,
            },
            "extractor": {
                "set_global_actions": self.extractor.set_global_actions,
                "force_orders": self.extractor.force_orders,
                "price_events": self.extractor.price_events,
                "liquidation_events": self.extractor.liquidation_events,
                "avg_extraction_time_ms": round(self.extractor.avg_extraction_time_ms, 3),
            },
            "position_state": {
                "positions_cached": self.position_state.positions_cached,
                "wallets_tracked": self.position_state.wallets_tracked,
                "critical": self.position_state.critical_positions,
                "watchlist": self.position_state.watchlist_positions,
                "monitored": self.position_state.monitored_positions,
            },
            "tcp_server": {
                "active_connections": self.tcp_server.active_connections,
                "events_sent": self.tcp_server.events_sent,
                "backpressure_events": self.tcp_server.backpressure_events,
                "dropped_events": self.tcp_server.dropped_events,
            },
            "sync": {
                "block_height": self.sync.block_height,
                "lag_seconds": round(self.sync.lag_seconds, 2),
                "is_synced": self.sync.is_synced,
            },
        }

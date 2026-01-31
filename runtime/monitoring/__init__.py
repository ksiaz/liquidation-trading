"""
Runtime Monitoring Package

Provides resource monitoring, health tracking, alerting, and memory cleanup.

HLP19 Components:
- HealthDashboard: Real-time system health monitoring
- LatencyProfiler: Order pipeline latency tracking
- ResourceMonitor: Memory and CPU monitoring
- CleanupCoordinator: Memory cleanup coordination
"""

from .resource_monitor import (
    ResourceMonitor,
    ResourceReport,
    MemorySnapshot,
    ComponentMetrics,
    HealthStatus as ResourceHealthStatus,
    ComponentSizer,
    get_monitor,
    reset_monitor,
    get_memory_snapshot,
)

from .memory_cleanup import (
    CleanupCoordinator,
    CleanupReport,
    PruneResult,
    get_coordinator,
    reset_coordinator,
)

from .health_dashboard import (
    HealthDashboard,
    HealthLevel,
    HealthThresholds,
    HealthStatus,
    ComponentHealth,
)

from .latency_profiler import (
    LatencyProfiler,
    LatencyStage,
    LatencyTimer,
    LatencyRecord,
    StageStats,
    LatencySummary,
    LATENCY_TARGETS_US,
    get_profiler,
    reset_profiler,
)

__all__ = [
    # Resource Monitor
    'ResourceMonitor',
    'ResourceReport',
    'MemorySnapshot',
    'ComponentMetrics',
    'ResourceHealthStatus',
    'ComponentSizer',
    'get_monitor',
    'reset_monitor',
    'get_memory_snapshot',
    # Cleanup Coordinator
    'CleanupCoordinator',
    'CleanupReport',
    'PruneResult',
    'get_coordinator',
    'reset_coordinator',
    # Health Dashboard (HLP19)
    'HealthDashboard',
    'HealthLevel',
    'HealthThresholds',
    'HealthStatus',
    'ComponentHealth',
    # Latency Profiler (HLP19)
    'LatencyProfiler',
    'LatencyStage',
    'LatencyTimer',
    'LatencyRecord',
    'StageStats',
    'LatencySummary',
    'LATENCY_TARGETS_US',
    'get_profiler',
    'reset_profiler',
]

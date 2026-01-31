"""
HLP16: Failure Handling Package.

Provides comprehensive failure detection, handling, and recovery mechanisms:
- Network failure handling (WebSocket reconnection)
- Data quality validation (stale data, corruption)
- Recovery validation (post-failure state consistency)

Integration with:
- DegradationManager: Automatic level transitions on failures
- CircuitBreaker: Trading halt triggers
- HealthMonitor: Component liveness tracking
"""

from .network_handler import (
    NetworkConfig,
    NetworkHandler,
    ConnectionState,
    ReconnectionEvent,
)
from .data_quality import (
    DataQualityConfig,
    DataQualityValidator,
    ValidationResult,
    ValidationStatus,
)
from .recovery import (
    RecoveryConfig,
    RecoveryValidator,
    RecoveryResult,
    RecoveryCheck,
)

__all__ = [
    # Network handling
    'NetworkConfig',
    'NetworkHandler',
    'ConnectionState',
    'ReconnectionEvent',
    # Data quality
    'DataQualityConfig',
    'DataQualityValidator',
    'ValidationResult',
    'ValidationStatus',
    # Recovery
    'RecoveryConfig',
    'RecoveryValidator',
    'RecoveryResult',
    'RecoveryCheck',
]

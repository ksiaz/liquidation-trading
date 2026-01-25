"""
Meta-Monitoring Module.

Infrastructure for detecting when design assumptions break down.
Protects against bias by making implicit beliefs explicit and testable.

Components:
- AssumptionRegistry: Track and validate design assumptions
- ModelHealthTracker: Detect distribution drift in calibrated parameters
- SystemRegimeDetector: Detect when the system's edge is decaying

Philosophy:
- Every design decision rests on assumptions about reality
- Make assumptions explicit so they can be tested
- When assumptions fail, know which components to distrust
- Design for graceful degradation when wrong
"""

from .types import (
    Assumption,
    AssumptionStatus,
    CalibratedParameter,
    DistributionSnapshot,
    ModelHealthStatus,
    SystemRegime,
    EdgeMetrics,
    SystemHealthReport,
)

from .assumption_registry import (
    AssumptionRegistry,
    RegistryConfig,
    create_standard_assumptions,
)

from .model_health import (
    ModelHealthTracker,
    ModelHealthConfig,
)

from .system_regime import (
    SystemRegimeDetector,
    RegimeConfig,
)

__all__ = [
    # Types
    'Assumption',
    'AssumptionStatus',
    'CalibratedParameter',
    'DistributionSnapshot',
    'ModelHealthStatus',
    'SystemRegime',
    'EdgeMetrics',
    'SystemHealthReport',
    # Components
    'AssumptionRegistry',
    'RegistryConfig',
    'create_standard_assumptions',
    'ModelHealthTracker',
    'ModelHealthConfig',
    'SystemRegimeDetector',
    'RegimeConfig',
]

"""
HLP16 & HLP17: Risk Management Module.

Components for failure handling and capital management:

HLP16 - Failure Modes & Recovery:
- Circuit Breakers: Automatic safety mechanisms
- Health Monitor: Component health tracking
- Data Validator: Data quality validation
- Degradation Manager: Graceful degradation modes

HLP17 - Capital Management:
- Position Sizer: Position sizing calculator
- Risk Limits: Hard caps on exposure
- Drawdown Tracker: Drawdown monitoring and limits
- Capital Manager: Integrated risk coordinator
"""

# HLP16: Failure Modes
from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerConfig,
    CircuitBreakerEvent,
    RapidLossBreaker,
    AbnormalPriceBreaker,
    StrategyMalfunctionBreaker,
    ResourceExhaustionBreaker,
)

from .health_monitor import (
    HealthMonitor,
    HealthConfig,
    ComponentHealth,
    ComponentStatus,
    HealthAlert,
    AlertSeverity,
    Heartbeat,
)

from .data_validator import (
    DataValidator,
    ValidationConfig,
    ValidationResult,
    DataQuality,
    ValidationIssue,
    DataRecord,
)

from .degradation import (
    DegradationManager,
    DegradationLevel,
    DegradationTrigger,
    DegradationConfig,
    DegradationEvent,
    DegradationState,
)

# HLP17: Capital Management
from .position_sizer import (
    PositionSizer,
    SizingConfig,
    SizingResult,
    SizingMethod,
    Regime,
)

from .risk_limits import (
    RiskLimitsChecker,
    RiskLimitsConfig,
    Position,
    LimitCheckResult,
    LimitViolation,
)

from .drawdown_tracker import (
    DrawdownTracker,
    DrawdownConfig,
    DrawdownState,
    DrawdownEvent,
)

from .capital_manager import (
    CapitalManager,
    CapitalManagerConfig,
    TradeRequest,
    TradeApproval,
    TradeDecision,
)

__all__ = [
    # HLP16: Circuit Breakers
    'CircuitBreaker',
    'CircuitBreakerState',
    'CircuitBreakerConfig',
    'CircuitBreakerEvent',
    'RapidLossBreaker',
    'AbnormalPriceBreaker',
    'StrategyMalfunctionBreaker',
    'ResourceExhaustionBreaker',
    # HLP16: Health Monitor
    'HealthMonitor',
    'HealthConfig',
    'ComponentHealth',
    'ComponentStatus',
    'HealthAlert',
    'AlertSeverity',
    'Heartbeat',
    # HLP16: Data Validator
    'DataValidator',
    'ValidationConfig',
    'ValidationResult',
    'DataQuality',
    'ValidationIssue',
    'DataRecord',
    # HLP16: Degradation
    'DegradationManager',
    'DegradationLevel',
    'DegradationTrigger',
    'DegradationConfig',
    'DegradationEvent',
    'DegradationState',
    # HLP17: Position Sizer
    'PositionSizer',
    'SizingConfig',
    'SizingResult',
    'SizingMethod',
    'Regime',
    # HLP17: Risk Limits
    'RiskLimitsChecker',
    'RiskLimitsConfig',
    'Position',
    'LimitCheckResult',
    'LimitViolation',
    # HLP17: Drawdown
    'DrawdownTracker',
    'DrawdownConfig',
    'DrawdownState',
    'DrawdownEvent',
    # HLP17: Capital Manager
    'CapitalManager',
    'CapitalManagerConfig',
    'TradeRequest',
    'TradeApproval',
    'TradeDecision',
]

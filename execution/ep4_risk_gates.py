"""
EP-4 Risk Gates - Execution Policy Layer v1.0

Binary risk validation. Pass or fail only.
Zero optimization. Zero adaptation.

Authority: EP-4 Execution Policy Specification v1.0
"""

from dataclasses import dataclass
from typing import Optional
import math


# ==============================================================================
# Risk Configuration
# ==============================================================================

@dataclass(frozen=True)
class RiskConfig:
    """
    Risk configuration.
    All values are hard limits, not targets.
    """
    max_position_size: float
    max_notional: float
    max_leverage: float
    max_actions_per_minute: int
    cooldown_seconds: float


# ==============================================================================
# Risk Gate Results
# ==============================================================================

class RiskGateViolation(Exception):
    """Raised when a risk gate fails."""
    pass


# ==============================================================================
# Risk Gates (Binary, No Optimization)
# ==============================================================================

def validate_position_size_gate(
    *,
    quantity: float,
    max_position_size: float
) -> None:
    """
    Gate: Position size must not exceed maximum.
    
    Args:
        quantity: Requested position size
        max_position_size: Maximum allowed position size
    
    Raises:
        RiskGateViolation: If gate fails
    """
    if not math.isfinite(quantity):
        raise RiskGateViolation(f"quantity must be finite, got {quantity}")
    
    if not math.isfinite(max_position_size):
        raise RiskGateViolation(f"max_position_size must be finite, got {max_position_size}")
    
    if quantity > max_position_size:
        raise RiskGateViolation(
            f"Position size {quantity} exceeds max {max_position_size}"
        )


def validate_notional_gate(
    *,
    quantity: float,
    price: float,
    max_notional: float
) -> None:
    """
    Gate: Notional value must not exceed maximum.
    
    Args:
        quantity: Position size
        price: Price (current or limit)
        max_notional: Maximum allowed notional value
    
    Raises:
        RiskGateViolation: If gate fails
    """
    if not math.isfinite(quantity):
        raise RiskGateViolation(f"quantity must be finite, got {quantity}")
    
    if not math.isfinite(price):
        raise RiskGateViolation(f"price must be finite, got {price}")
    
    if not math.isfinite(max_notional):
        raise RiskGateViolation(f"max_notional must be finite, got {max_notional}")
    
    if price <= 0:
        raise RiskGateViolation(f"price must be > 0, got {price}")
    
    notional = quantity * price
    
    if notional > max_notional:
        raise RiskGateViolation(
            f"Notional value {notional} exceeds max {max_notional}"
        )


def validate_leverage_gate(
    *,
    position_value: float,
    account_balance: float,
    max_leverage: float
) -> None:
    """
    Gate: Leverage must not exceed maximum.
    
    Args:
        position_value: Total position value
        account_balance: Account balance
        max_leverage: Maximum allowed leverage
    
    Raises:
        RiskGateViolation: If gate fails
    """
    if not math.isfinite(position_value):
        raise RiskGateViolation(f"position_value must be finite, got {position_value}")
    
    if not math.isfinite(account_balance):
        raise RiskGateViolation(f"account_balance must be finite, got {account_balance}")
    
    if not math.isfinite(max_leverage):
        raise RiskGateViolation(f"max_leverage must be finite, got {max_leverage}")
    
    if account_balance <= 0:
        raise RiskGateViolation(f"account_balance must be > 0, got {account_balance}")
    
    leverage = position_value / account_balance
    
    if leverage > max_leverage:
        raise RiskGateViolation(
            f"Leverage {leverage:.2f}x exceeds max {max_leverage}x"
        )


def validate_action_frequency_gate(
    *,
    actions_in_window: int,
    max_actions_per_minute: int
) -> None:
    """
    Gate: Action frequency must not exceed maximum.
    
    Args:
        actions_in_window: Number of actions in current window
        max_actions_per_minute: Maximum allowed actions per minute
    
    Raises:
        RiskGateViolation: If gate fails
    """
    if actions_in_window >= max_actions_per_minute:
        raise RiskGateViolation(
            f"Action frequency {actions_in_window} >= max {max_actions_per_minute}"
        )


def validate_cooldown_gate(
    *,
    time_since_last_action: float,
    cooldown_seconds: float
) -> None:
    """
    Gate: Cooldown period must be satisfied.
    
    Args:
        time_since_last_action: Seconds since last action
        cooldown_seconds: Required cooldown period
    
    Raises:
        RiskGateViolation: If gate fails
    """
    if not math.isfinite(time_since_last_action):
        raise RiskGateViolation(
            f"time_since_last_action must be finite, got {time_since_last_action}"
        )
    
    if not math.isfinite(cooldown_seconds):
        raise RiskGateViolation(
            f"cooldown_seconds must be finite, got {cooldown_seconds}"
        )
    
    if time_since_last_action < cooldown_seconds:
        raise RiskGateViolation(
            f"Cooldown not satisfied: {time_since_last_action:.2f}s < {cooldown_seconds}s"
        )


# ==============================================================================
# Composite Risk Validation
# ==============================================================================

@dataclass(frozen=True)
class RiskContext:
    """
    Context for risk validation.
    All values must be provided by caller.
    """
    current_price: float
    account_balance: float
    current_position_size: float
    actions_in_last_minute: int
    time_since_last_action: float


def validate_all_risk_gates(
    *,
    quantity: float,
    risk_config: RiskConfig,
    risk_context: RiskContext
) -> None:
    """
    Validate all applicable risk gates.
    
    Args:
        quantity: Requested position size or delta
        risk_config: Risk configuration
        risk_context: Current risk context
    
    Raises:
        RiskGateViolation: If any gate fails
    """
    # Gate 1: Position size
    validate_position_size_gate(
        quantity=abs(quantity),
        max_position_size=risk_config.max_position_size
    )
    
    # Gate 2: Notional
    validate_notional_gate(
        quantity=abs(quantity),
        price=risk_context.current_price,
        max_notional=risk_config.max_notional
    )
    
    # Gate 3: Leverage
    new_position_value = (risk_context.current_position_size + quantity) * risk_context.current_price
    validate_leverage_gate(
        position_value=abs(new_position_value),
        account_balance=risk_context.account_balance,
        max_leverage=risk_config.max_leverage
    )
    
    # Gate 4: Action frequency
    validate_action_frequency_gate(
        actions_in_window=risk_context.actions_in_last_minute,
        max_actions_per_minute=risk_config.max_actions_per_minute
    )
    
    # Gate 5: Cooldown
    validate_cooldown_gate(
        time_since_last_action=risk_context.time_since_last_action,
        cooldown_seconds=risk_config.cooldown_seconds
    )

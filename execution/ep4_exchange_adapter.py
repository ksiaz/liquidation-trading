"""
EP-4 Exchange Adapter - Execution Policy Layer v1.0

Mocked exchange interface for testing.
Zero real exchange interaction in v1.0.

Authority: EP-4 Execution Policy Specification v1.0
"""

from dataclasses import dataclass
from typing import Optional, Literal
from enum import Enum


# ==============================================================================
# Exchange Configuration
# ==============================================================================

@dataclass(frozen=True)
class ExchangeConstraints:
    """
    Exchange-specific mechanical constraints.
    Cannot imply: strategy, optimization, interpretation.
    """
    min_order_size: float
    max_order_size: float
    step_size: float  # Quantity increment
    tick_size: float  # Price increment
    max_leverage: float
    margin_mode: Literal["CROSS", "ISOLATED"]


# ==============================================================================
# Exchange Response Types
# ==============================================================================

class ExchangeResponseCode(Enum):
    """Exchange response codes."""
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ExchangeResponse:
    """
    Opaque exchange response.
    No interpretation allowed.
    """
    response_code: ExchangeResponseCode
    order_id: Optional[str]
    message: str
    timestamp: float


# ==============================================================================
# Mocked Exchange Adapter
# ==============================================================================

class MockedExchangeAdapter:
    """
    Mocked exchange adapter for testing.
    
    In production, would connect to real exchange API.
    For v1.0, deterministic mock responses only.
    """
    
    def __init__(self, *, exchange_constraints: ExchangeConstraints):
        """
        Initialize mocked exchange adapter.
        
        Args:
            exchange_constraints: Exchange constraints
        """
        self._constraints = exchange_constraints
        self._call_count = 0
    
    def execute_order(
        self,
        *,
        action_id: str,
        order_params: dict,
        timestamp: float
    ) -> ExchangeResponse:
        """
        Execute order on exchange (mocked).
        
        In production: actual exchange API call.
        In v1.0: deterministic mock response.
        
        Args:
            action_id: Action identifier
            order_params: Opaque order parameters
            timestamp: Execution timestamp
        
        Returns:
            ExchangeResponse (mocked)
        """
        self._call_count += 1
        
        # Mock: Always acknowledge for testing
        # Real implementation would make actual API call
        return ExchangeResponse(
            response_code=ExchangeResponseCode.ACKNOWLEDGED,
            order_id=f"MOCK_ORDER_{action_id}_{self._call_count}",
            message="Order acknowledged (mocked)",
            timestamp=timestamp
        )
    
    def cancel_orders(
        self,
        *,
        action_id: str,
        symbol: Optional[str],
        timestamp: float
    ) -> ExchangeResponse:
        """
        Cancel orders on exchange (mocked).
        
        Args:
            action_id: Action identifier
            symbol: Symbol to cancel (None = all)
            timestamp: Execution timestamp
        
        Returns:
            ExchangeResponse (mocked)
        """
        self._call_count += 1
        
        return ExchangeResponse(
            response_code=ExchangeResponseCode.ACKNOWLEDGED,
            order_id=None,
            message=f"Orders cancelled for {symbol or 'all symbols'} (mocked)",
            timestamp=timestamp
        )
    
    def get_constraints(self) -> ExchangeConstraints:
        """Get exchange constraints."""
        return self._constraints
    
    def get_call_count(self) -> int:
        """Get number of exchange calls made (for testing)."""
        return self._call_count


# ==============================================================================
# Exchange Constraint Validation
# ==============================================================================

class ExchangeConstraintViolation(Exception):
    """Raised when exchange constraints are violated."""
    pass


def validate_exchange_constraints(
    *,
    quantity: float,
    price: Optional[float],
    constraints: ExchangeConstraints
) -> None:
    """
    Validate action against exchange constraints.
    
    No rounding. No fixing. Pass or fail only.
    
    Args:
        quantity: Order quantity
        price: Order price (None for market orders)
        constraints: Exchange constraints
    
    Raises:
        ExchangeConstraintViolation: If constraints violated
    """
    # Validate quantity bounds
    if quantity < constraints.min_order_size:
        raise ExchangeConstraintViolation(
            f"Quantity {quantity} < min {constraints.min_order_size}"
        )
    
    if quantity > constraints.max_order_size:
        raise ExchangeConstraintViolation(
            f"Quantity {quantity} > max {constraints.max_order_size}"
        )
    
    # Validate step size
    if constraints.step_size > 0:
        # Use division + is_integer() for better precision
        steps = quantity / constraints.step_size
        if not (abs(steps - round(steps)) < 1e-8):
            raise ExchangeConstraintViolation(
                f"Quantity {quantity} not multiple of step size {constraints.step_size}"
            )
    
    # Validate tick size (if limit order)
    if price is not None and constraints.tick_size > 0:
        # Use division + is_integer() for better precision
        ticks = price / constraints.tick_size
        if not (abs(ticks - round(ticks)) < 1e-8):
            raise ExchangeConstraintViolation(
                f"Price {price} not multiple of tick size {constraints.tick_size}"
            )

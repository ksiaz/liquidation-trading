"""
EP-4 Action Schemas - Execution Policy Layer v1.0

Defines action types and validation logic.
Zero market inference. Mechanical constraints only.

Authority: EP-4 Execution Policy Specification v1.0
"""

from dataclasses import dataclass
from typing import Optional, Literal
from enum import Enum


# ==============================================================================
# Enums
# ==============================================================================

class Side(Enum):
    """Position side. No semantic interpretation."""
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(Enum):
    """Order type. Mechanical only."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(Enum):
    """Time in force. Exchange-specific."""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel


# ==============================================================================
# Action Schemas (v1.0 - Exact as specified)
# ==============================================================================

@dataclass(frozen=True)
class OpenPositionAction:
    """
    ACTION_OPEN_POSITION
    
    Open a new position or increase existing position.
    Cannot imply: intent, quality, expectation.
    """
    action_id: str
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType
    limit_price: Optional[float]
    reduce_only: Literal[False] = False
    time_in_force: TimeInForce = TimeInForce.GTC


@dataclass(frozen=True)
class ClosePositionAction:
    """
    ACTION_CLOSE_POSITION
    
    Close position (full or partial).
    Cannot imply: exit strategy, stop loss.
    """
    action_id: str
    symbol: str
    quantity: Optional[float]  # None = full close
    order_type: Literal[OrderType.MARKET] = OrderType.MARKET
    reduce_only: Literal[True] = True


@dataclass(frozen=True)
class AdjustPositionAction:
    """
    ACTION_ADJUST_POSITION
    
    Adjust position size by delta.
    Cannot imply: scaling strategy, pyramid logic.
    """
    action_id: str
    symbol: str
    delta_quantity: float  # Positive = increase, negative = decrease


@dataclass(frozen=True)
class CancelOrdersAction:
    """
    ACTION_CANCEL_OPEN_ORDERS
    
    Cancel open orders.
    Cannot imply: reset, cleanup strategy.
    """
    action_id: str
    symbol: Optional[str]  # None = all symbols


@dataclass(frozen=True)
class NoOpAction:
    """
    ACTION_NOOP
    
    Explicit do-nothing instruction.
    Always succeeds.
    """
    action_id: str


# Union type for all actions
from typing import Union
Action = Union[OpenPositionAction, ClosePositionAction, AdjustPositionAction, CancelOrdersAction, NoOpAction]


# ==============================================================================
# Schema Validation (Deterministic)
# ==============================================================================

class SchemaValidationError(Exception):
    """Raised when action schema is invalid."""
    pass


def validate_open_position_schema(action: OpenPositionAction) -> None:
    """
    Validate OpenPositionAction schema.
    
    Raises SchemaValidationError if invalid.
    """
    if not action.action_id:
        raise SchemaValidationError("action_id cannot be empty")
    
    if not action.symbol:
        raise SchemaValidationError("symbol cannot be empty")
    
    if action.quantity <= 0:
        raise SchemaValidationError(f"quantity must be > 0, got {action.quantity}")
    
    if action.order_type == OrderType.LIMIT and action.limit_price is None:
        raise SchemaValidationError("limit_price required for LIMIT orders")
    
    if action.order_type == OrderType.MARKET and action.limit_price is not None:
        raise SchemaValidationError("limit_price forbidden for MARKET orders")
    
    if action.reduce_only is not False:
        raise SchemaValidationError("reduce_only must be False for open position")


def validate_close_position_schema(action: ClosePositionAction) -> None:
    """
    Validate ClosePositionAction schema.
    
    Raises SchemaValidationError if invalid.
    """
    if not action.action_id:
        raise SchemaValidationError("action_id cannot be empty")
    
    if not action.symbol:
        raise SchemaValidationError("symbol cannot be empty")
    
    if action.quantity is not None and action.quantity <= 0:
        raise SchemaValidationError(f"quantity must be > 0 or None, got {action.quantity}")
    
    if action.order_type != OrderType.MARKET:
        raise SchemaValidationError("order_type must be MARKET for close position")
    
    if action.reduce_only is not True:
        raise SchemaValidationError("reduce_only must be True for close position")


def validate_adjust_position_schema(action: AdjustPositionAction) -> None:
    """
    Validate AdjustPositionAction schema.
    
    Raises SchemaValidationError if invalid.
    """
    if not action.action_id:
        raise SchemaValidationError("action_id cannot be empty")
    
    if not action.symbol:
        raise SchemaValidationError("symbol cannot be empty")
    
    if action.delta_quantity == 0:
        raise SchemaValidationError("delta_quantity cannot be zero")


def validate_cancel_orders_schema(action: CancelOrdersAction) -> None:
    """
    Validate CancelOrdersAction schema.
    
    Raises SchemaValidationError if invalid.
    """
    if not action.action_id:
        raise SchemaValidationError("action_id cannot be empty")
    
    # symbol can be None (cancel all) or non-empty string
    if action.symbol is not None and not action.symbol:
        raise SchemaValidationError("symbol must be None or non-empty string")


def validate_noop_schema(action: NoOpAction) -> None:
    """
    Validate NoOpAction schema.
    
    Raises SchemaValidationError if invalid.
    """
    if not action.action_id:
        raise SchemaValidationError("action_id cannot be empty")


def validate_action_schema(action: Action) -> None:
    """
    Validate any action schema.
    
    Dispatches to specific validator based on type.
    
    Raises:
        SchemaValidationError: If schema is invalid
    """
    if isinstance(action, OpenPositionAction):
        validate_open_position_schema(action)
    elif isinstance(action, ClosePositionAction):
        validate_close_position_schema(action)
    elif isinstance(action, AdjustPositionAction):
        validate_adjust_position_schema(action)
    elif isinstance(action, CancelOrdersAction):
        validate_cancel_orders_schema(action)
    elif isinstance(action, NoOpAction):
        validate_noop_schema(action)
    else:
        raise SchemaValidationError(f"Unknown action type: {type(action)}")

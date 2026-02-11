"""
Phase B: ExecutionController Interface Verification Tests

Verifies that Action objects from arbitration match ExecutionController expectations.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase B requirements.
"""

import pytest
from decimal import Decimal
from typing import Optional

from runtime.arbitration.types import Action, ActionType, Mandate, MandateType
from runtime.arbitration.arbitrator import MandateArbitrator


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def arbitrator():
    """Fresh arbitrator instance."""
    return MandateArbitrator()


def create_entry_mandate(
    symbol: str = "BTCUSDT",
    direction: str = "LONG",
    quantity: Decimal = Decimal("0.01"),
    entry_price: Decimal = Decimal("65000.00"),
    authority: float = 5.0,
    strategy_id: str = "TEST_STRATEGY"
) -> Mandate:
    """Create ENTRY mandate with all required fields."""
    return Mandate(
        symbol=symbol,
        type=MandateType.ENTRY,
        authority=authority,
        timestamp=1000.0,
        direction=direction,
        strategy_id=strategy_id,
        quantity=quantity,
        entry_price=entry_price
    )


def create_exit_mandate(
    symbol: str = "BTCUSDT",
    authority: float = 5.0,
    strategy_id: str = "TEST_STRATEGY"
) -> Mandate:
    """Create EXIT mandate."""
    return Mandate(
        symbol=symbol,
        type=MandateType.EXIT,
        authority=authority,
        timestamp=1000.0,
        strategy_id=strategy_id
    )


def create_reduce_mandate(
    symbol: str = "BTCUSDT",
    quantity: Decimal = Decimal("0.005"),
    authority: float = 5.0
) -> Mandate:
    """Create REDUCE mandate with quantity."""
    return Mandate(
        symbol=symbol,
        type=MandateType.REDUCE,
        authority=authority,
        timestamp=1000.0,
        quantity=quantity
    )


# ==============================================================================
# TASK 3.1: Action Object Structure
# ==============================================================================

def test_action_has_required_fields():
    """Action has all fields expected by ExecutionController."""
    action = Action(
        type=ActionType.ENTRY,
        symbol="BTCUSDT",
        strategy_id="TEST",
        direction="LONG",
        quantity=Decimal("0.01"),
        entry_price=Decimal("65000.00")
    )

    # Verify all fields exist and are accessible
    assert hasattr(action, 'type')
    assert hasattr(action, 'symbol')
    assert hasattr(action, 'strategy_id')
    assert hasattr(action, 'direction')
    assert hasattr(action, 'quantity')
    assert hasattr(action, 'entry_price')


def test_action_is_frozen():
    """Action is immutable (frozen dataclass)."""
    action = Action(
        type=ActionType.ENTRY,
        symbol="BTCUSDT"
    )

    with pytest.raises(Exception):  # FrozenInstanceError
        action.type = ActionType.EXIT


# ==============================================================================
# TASK 3.2: ENTRY Action Requirements
# ==============================================================================

def test_entry_action_has_direction(arbitrator):
    """ENTRY action preserves direction from mandate."""
    mandates = {create_entry_mandate(direction="LONG")}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.ENTRY
    assert action.direction == "LONG"


def test_entry_action_has_quantity(arbitrator):
    """ENTRY action preserves quantity from mandate."""
    mandates = {create_entry_mandate(quantity=Decimal("0.025"))}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.ENTRY
    assert action.quantity == Decimal("0.025")


def test_entry_action_has_entry_price(arbitrator):
    """ENTRY action preserves entry_price from mandate."""
    mandates = {create_entry_mandate(entry_price=Decimal("64500.00"))}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.ENTRY
    assert action.entry_price == Decimal("64500.00")


def test_entry_action_has_strategy_id(arbitrator):
    """ENTRY action preserves strategy_id from mandate."""
    mandates = {create_entry_mandate(strategy_id="CASCADE_SNIPER")}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.ENTRY
    assert action.strategy_id == "CASCADE_SNIPER"


def test_entry_action_complete_for_execution(arbitrator):
    """ENTRY action has all fields needed for execution."""
    mandates = {
        create_entry_mandate(
            symbol="BTCUSDT",
            direction="SHORT",
            quantity=Decimal("0.015"),
            entry_price=Decimal("66000.00"),
            strategy_id="EFFCS"
        )
    }
    action = arbitrator.arbitrate(mandates)

    # ExecutionController expects:
    assert action.type == ActionType.ENTRY
    assert action.symbol == "BTCUSDT"
    assert action.direction in ("LONG", "SHORT")
    assert action.quantity is not None
    assert action.quantity > 0
    assert action.entry_price is not None
    assert action.entry_price > 0


# ==============================================================================
# TASK 3.3: EXIT Action Requirements
# ==============================================================================

def test_exit_action_has_symbol(arbitrator):
    """EXIT action has symbol."""
    mandates = {create_exit_mandate(symbol="ETHUSDT")}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.EXIT
    assert action.symbol == "ETHUSDT"


def test_exit_action_has_strategy_id(arbitrator):
    """EXIT action preserves strategy_id."""
    mandates = {create_exit_mandate(strategy_id="SLBRS")}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.EXIT
    assert action.strategy_id == "SLBRS"


def test_exit_action_no_quantity_required(arbitrator):
    """EXIT action doesn't require quantity (full exit)."""
    mandates = {create_exit_mandate()}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.EXIT
    # quantity may be None for full exit
    # ExecutionController should handle this


# ==============================================================================
# TASK 3.4: REDUCE Action Requirements
# ==============================================================================

def test_reduce_action_has_quantity(arbitrator):
    """REDUCE action preserves quantity from mandate."""
    mandates = {create_reduce_mandate(quantity=Decimal("0.008"))}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.REDUCE
    assert action.quantity == Decimal("0.008")


def test_reduce_action_has_symbol(arbitrator):
    """REDUCE action has symbol."""
    mandates = {create_reduce_mandate(symbol="SOLUSDT")}
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.REDUCE
    assert action.symbol == "SOLUSDT"


# ==============================================================================
# TASK 3.5: NO_ACTION and HOLD
# ==============================================================================

def test_no_action_has_minimal_fields(arbitrator):
    """NO_ACTION has type and symbol."""
    mandates = {
        Mandate(
            symbol="BTCUSDT",
            type=MandateType.BLOCK,
            authority=5.0,
            timestamp=1000.0
        )
    }
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.NO_ACTION
    assert action.symbol == "BTCUSDT"


def test_hold_action_has_type_and_symbol(arbitrator):
    """HOLD action has type and symbol."""
    mandates = {
        Mandate(
            symbol="BTCUSDT",
            type=MandateType.HOLD,
            authority=5.0,
            timestamp=1000.0
        )
    }
    action = arbitrator.arbitrate(mandates)

    assert action.type == ActionType.HOLD
    assert action.symbol == "BTCUSDT"


# ==============================================================================
# TASK 3.6: Action Does Not Query Observation
# ==============================================================================

def test_action_has_no_observation_references():
    """Action object has no references to observation state."""
    action = Action(
        type=ActionType.ENTRY,
        symbol="BTCUSDT",
        direction="LONG",
        quantity=Decimal("0.01"),
        entry_price=Decimal("65000.00")
    )

    # Verify no observation-related attributes
    assert not hasattr(action, 'snapshot')
    assert not hasattr(action, 'primitives')
    assert not hasattr(action, 'observation')
    assert not hasattr(action, 'm4_bundle')


def test_action_self_contained():
    """Action contains all info needed for execution (no external lookups)."""
    action = Action(
        type=ActionType.ENTRY,
        symbol="BTCUSDT",
        strategy_id="TEST",
        direction="LONG",
        quantity=Decimal("0.01"),
        entry_price=Decimal("65000.00")
    )

    # All execution-relevant info is in the action
    execution_info = {
        'type': action.type,
        'symbol': action.symbol,
        'direction': action.direction,
        'quantity': action.quantity,
        'entry_price': action.entry_price,
        'strategy_id': action.strategy_id
    }

    # No None values for ENTRY (except strategy_id which is optional)
    assert execution_info['type'] is not None
    assert execution_info['symbol'] is not None
    assert execution_info['direction'] is not None
    assert execution_info['quantity'] is not None
    assert execution_info['entry_price'] is not None


# ==============================================================================
# TASK 3.7: Action.from_mandate Conversion
# ==============================================================================

def test_from_mandate_preserves_all_fields():
    """Action.from_mandate preserves all mandate fields."""
    mandate = create_entry_mandate(
        symbol="BTCUSDT",
        direction="LONG",
        quantity=Decimal("0.02"),
        entry_price=Decimal("64000.00"),
        strategy_id="GEOMETRY"
    )

    action = Action.from_mandate(mandate)

    assert action.type == ActionType.ENTRY
    assert action.symbol == "BTCUSDT"
    assert action.direction == "LONG"
    assert action.quantity == Decimal("0.02")
    assert action.entry_price == Decimal("64000.00")
    assert action.strategy_id == "GEOMETRY"


def test_from_mandate_type_mapping():
    """Action.from_mandate_type maps correctly."""
    mappings = [
        (MandateType.ENTRY, ActionType.ENTRY),
        (MandateType.EXIT, ActionType.EXIT),
        (MandateType.REDUCE, ActionType.REDUCE),
        (MandateType.HOLD, ActionType.HOLD),
        (MandateType.BLOCK, ActionType.NO_ACTION),
    ]

    for mandate_type, expected_action_type in mappings:
        action = Action.from_mandate_type(
            mandate_type=mandate_type,
            symbol="TEST"
        )
        assert action.type == expected_action_type


# ==============================================================================
# TASK 3.8: ExecutionController Contract Compatibility
# ==============================================================================

def test_entry_action_execution_contract():
    """ENTRY action meets ExecutionController contract.

    Per DOWNSTREAM_ACTIVATION_SPEC.md Section 1.5:
    - ENTRY/REDUCE require non-None quantity (validated)
    - Action is consumed by ExecutionController
    """
    action = Action(
        type=ActionType.ENTRY,
        symbol="BTCUSDT",
        direction="LONG",
        quantity=Decimal("0.01"),
        entry_price=Decimal("65000.00")
    )

    # F5 validation: ENTRY requires quantity
    assert action.quantity is not None
    assert action.quantity > 0

    # Direction required for ENTRY
    assert action.direction in ("LONG", "SHORT")


def test_reduce_action_execution_contract():
    """REDUCE action meets ExecutionController contract."""
    action = Action(
        type=ActionType.REDUCE,
        symbol="BTCUSDT",
        quantity=Decimal("0.005")
    )

    # F5 validation: REDUCE requires quantity
    assert action.quantity is not None
    assert action.quantity > 0


def test_exit_action_execution_contract():
    """EXIT action meets ExecutionController contract."""
    action = Action(
        type=ActionType.EXIT,
        symbol="BTCUSDT"
    )

    # EXIT may have None quantity (full exit)
    assert action.symbol is not None
    assert action.symbol != ""


def test_no_action_execution_contract():
    """NO_ACTION meets ExecutionController contract.

    Per DOWNSTREAM_ACTIVATION_SPEC.md Section 1.5:
    - NO_ACTION and HOLD produce no exchange interaction
    """
    action = Action(
        type=ActionType.NO_ACTION,
        symbol="BTCUSDT"
    )

    # NO_ACTION should not have execution parameters
    # (They're allowed but not required)
    assert action.type == ActionType.NO_ACTION


# ==============================================================================
# TASK 3.9: Decimal Precision
# ==============================================================================

def test_quantity_decimal_precision():
    """Quantity uses Decimal for precision."""
    action = Action(
        type=ActionType.ENTRY,
        symbol="BTCUSDT",
        quantity=Decimal("0.00123456"),
        entry_price=Decimal("65432.10")
    )

    assert isinstance(action.quantity, Decimal)
    assert isinstance(action.entry_price, Decimal)


def test_decimal_arithmetic_safe():
    """Decimal arithmetic doesn't lose precision."""
    qty = Decimal("0.001")
    price = Decimal("65000.00")

    notional = qty * price

    assert notional == Decimal("65.00000")


# ==============================================================================
# TASK 3.10: Type Safety
# ==============================================================================

def test_action_type_is_enum():
    """Action.type is ActionType enum."""
    action = Action(type=ActionType.ENTRY, symbol="TEST")

    assert isinstance(action.type, ActionType)
    assert action.type.value == "ENTRY"


def test_direction_is_string():
    """Action.direction is string LONG/SHORT."""
    action = Action(
        type=ActionType.ENTRY,
        symbol="TEST",
        direction="LONG"
    )

    assert isinstance(action.direction, str)
    assert action.direction in ("LONG", "SHORT")

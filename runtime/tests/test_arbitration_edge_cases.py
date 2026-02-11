"""
Phase B: MandateArbitrator Edge-Case Verification Tests

Verifies all 13 theorems from MANDATE_ARBITRATION_PROOFS.md hold under edge conditions.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase B requirements.
"""

import pytest
from decimal import Decimal
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.arbitration.types import Mandate, MandateType, Action, ActionType


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def arbitrator():
    """Fresh arbitrator instance."""
    return MandateArbitrator()


def create_mandate(
    symbol: str = "BTCUSDT",
    mandate_type: MandateType = MandateType.ENTRY,
    authority: float = 5.0,
    timestamp: float = 1000.0,
    direction: str = None,
    strategy_id: str = None,
    quantity: Decimal = None,
    entry_price: Decimal = None
) -> Mandate:
    """Factory for creating test mandates."""
    return Mandate(
        symbol=symbol,
        type=mandate_type,
        authority=authority,
        timestamp=timestamp,
        direction=direction,
        strategy_id=strategy_id,
        quantity=quantity,
        entry_price=entry_price
    )


# ==============================================================================
# TASK 1.1: Empty Mandate Set → NO_ACTION
# ==============================================================================

def test_empty_mandate_set_returns_no_action(arbitrator):
    """Empty mandate set → NO_ACTION (Theorem 6.1: Completeness)."""
    result = arbitrator.arbitrate(set())

    assert result.type == ActionType.NO_ACTION
    assert result.symbol == ""


def test_empty_list_arbitrate_all_returns_empty_dict(arbitrator):
    """Empty list → empty actions dict."""
    result = arbitrator.arbitrate_all([])

    assert result == {}


# ==============================================================================
# TASK 1.2: BLOCK-only → NO_ACTION
# ==============================================================================

def test_block_only_returns_no_action(arbitrator):
    """Single BLOCK mandate → NO_ACTION (BLOCK is not actionable)."""
    mandates = {
        create_mandate(mandate_type=MandateType.BLOCK, authority=10.0)
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.NO_ACTION
    assert result.symbol == "BTCUSDT"


def test_multiple_blocks_return_no_action(arbitrator):
    """Multiple BLOCK mandates → NO_ACTION."""
    mandates = {
        create_mandate(mandate_type=MandateType.BLOCK, authority=10.0, strategy_id="S1"),
        create_mandate(mandate_type=MandateType.BLOCK, authority=5.0, strategy_id="S2"),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.NO_ACTION


# ==============================================================================
# TASK 1.3: EXIT Supremacy (Theorem 2.2)
# ==============================================================================

def test_exit_suppresses_entry(arbitrator):
    """EXIT + ENTRY → EXIT wins (Theorem 2.2)."""
    mandates = {
        create_mandate(mandate_type=MandateType.EXIT, authority=1.0),
        create_mandate(mandate_type=MandateType.ENTRY, authority=100.0),  # Higher authority
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.EXIT


def test_exit_suppresses_reduce(arbitrator):
    """EXIT + REDUCE → EXIT wins."""
    mandates = {
        create_mandate(mandate_type=MandateType.EXIT, authority=1.0),
        create_mandate(mandate_type=MandateType.REDUCE, authority=100.0),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.EXIT


def test_exit_suppresses_hold(arbitrator):
    """EXIT + HOLD → EXIT wins."""
    mandates = {
        create_mandate(mandate_type=MandateType.EXIT, authority=1.0),
        create_mandate(mandate_type=MandateType.HOLD, authority=100.0),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.EXIT


def test_exit_suppresses_block(arbitrator):
    """EXIT + BLOCK → EXIT wins."""
    mandates = {
        create_mandate(mandate_type=MandateType.EXIT, authority=1.0),
        create_mandate(mandate_type=MandateType.BLOCK, authority=100.0),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.EXIT


def test_exit_suppresses_all_types(arbitrator):
    """EXIT + all other types → EXIT wins."""
    mandates = {
        create_mandate(mandate_type=MandateType.EXIT, authority=1.0),
        create_mandate(mandate_type=MandateType.BLOCK, authority=10.0),
        create_mandate(mandate_type=MandateType.REDUCE, authority=10.0),
        create_mandate(mandate_type=MandateType.ENTRY, authority=10.0),
        create_mandate(mandate_type=MandateType.HOLD, authority=10.0),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.EXIT


def test_multiple_exits_still_returns_exit(arbitrator):
    """Multiple EXIT mandates → EXIT (first one's strategy_id)."""
    mandates = {
        create_mandate(mandate_type=MandateType.EXIT, authority=5.0, strategy_id="S1"),
        create_mandate(mandate_type=MandateType.EXIT, authority=10.0, strategy_id="S2"),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.EXIT


# ==============================================================================
# TASK 1.4: BLOCK Prevents ENTRY (Theorem 2.3)
# ==============================================================================

def test_block_prevents_entry(arbitrator):
    """BLOCK + ENTRY → ENTRY filtered out (Theorem 2.3)."""
    mandates = {
        create_mandate(mandate_type=MandateType.BLOCK, authority=1.0),
        create_mandate(mandate_type=MandateType.ENTRY, authority=100.0),
    }

    result = arbitrator.arbitrate(mandates)

    # BLOCK filters ENTRY, only BLOCK remains → NO_ACTION
    assert result.type == ActionType.NO_ACTION


def test_block_prevents_entry_but_not_reduce(arbitrator):
    """BLOCK + ENTRY + REDUCE → REDUCE wins (ENTRY filtered)."""
    mandates = {
        create_mandate(mandate_type=MandateType.BLOCK, authority=1.0),
        create_mandate(mandate_type=MandateType.ENTRY, authority=100.0),
        create_mandate(mandate_type=MandateType.REDUCE, authority=5.0),
    }

    result = arbitrator.arbitrate(mandates)

    # ENTRY filtered, REDUCE remains
    assert result.type == ActionType.REDUCE


def test_block_prevents_entry_but_not_hold(arbitrator):
    """BLOCK + ENTRY + HOLD → HOLD wins (ENTRY filtered)."""
    mandates = {
        create_mandate(mandate_type=MandateType.BLOCK, authority=1.0),
        create_mandate(mandate_type=MandateType.ENTRY, authority=100.0),
        create_mandate(mandate_type=MandateType.HOLD, authority=5.0),
    }

    result = arbitrator.arbitrate(mandates)

    # ENTRY filtered, HOLD remains
    assert result.type == ActionType.HOLD


# ==============================================================================
# TASK 1.5: Authority Ranking (Theorem 3.2)
# ==============================================================================

def test_higher_authority_wins_same_type(arbitrator):
    """Same type, different authorities → highest wins."""
    mandates = {
        create_mandate(mandate_type=MandateType.ENTRY, authority=5.0, strategy_id="LOW"),
        create_mandate(mandate_type=MandateType.ENTRY, authority=10.0, strategy_id="HIGH"),
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.ENTRY
    assert result.strategy_id == "HIGH"


def test_authority_deterministic_with_equal_values(arbitrator):
    """Equal authorities → deterministic result (implementation-defined)."""
    mandates = {
        create_mandate(mandate_type=MandateType.ENTRY, authority=5.0, strategy_id="A"),
        create_mandate(mandate_type=MandateType.ENTRY, authority=5.0, strategy_id="B"),
    }

    # Call multiple times - must be deterministic
    result1 = arbitrator.arbitrate(mandates)
    result2 = arbitrator.arbitrate(mandates)
    result3 = arbitrator.arbitrate(mandates)

    assert result1.type == result2.type == result3.type
    assert result1.strategy_id == result2.strategy_id == result3.strategy_id


def test_type_hierarchy_overrides_authority(arbitrator):
    """Higher type priority wins over higher authority (Theorem 2.2)."""
    mandates = {
        create_mandate(mandate_type=MandateType.REDUCE, authority=1.0),  # Priority 3
        create_mandate(mandate_type=MandateType.ENTRY, authority=100.0),  # Priority 2
    }

    result = arbitrator.arbitrate(mandates)

    # REDUCE has higher priority than ENTRY
    assert result.type == ActionType.REDUCE


# ==============================================================================
# TASK 1.6: Symbol-Local Independence (Theorem 5.1)
# ==============================================================================

def test_symbol_local_independence(arbitrator):
    """Different symbols arbitrated independently."""
    btc_mandates = [
        create_mandate(symbol="BTCUSDT", mandate_type=MandateType.ENTRY, authority=5.0),
    ]
    eth_mandates = [
        create_mandate(symbol="ETHUSDT", mandate_type=MandateType.EXIT, authority=5.0),
    ]

    all_mandates = btc_mandates + eth_mandates
    result = arbitrator.arbitrate_all(all_mandates)

    assert "BTCUSDT" in result
    assert "ETHUSDT" in result
    assert result["BTCUSDT"].type == ActionType.ENTRY
    assert result["ETHUSDT"].type == ActionType.EXIT


def test_cross_symbol_mandate_rejected(arbitrator):
    """Mandates from multiple symbols in single arbitrate() → error."""
    mandates = {
        create_mandate(symbol="BTCUSDT", mandate_type=MandateType.ENTRY),
        create_mandate(symbol="ETHUSDT", mandate_type=MandateType.ENTRY),
    }

    with pytest.raises(ValueError, match="single symbol"):
        arbitrator.arbitrate(mandates)


def test_symbol_isolation_no_interference(arbitrator):
    """EXIT on symbol A doesn't affect ENTRY on symbol B."""
    all_mandates = [
        create_mandate(symbol="BTCUSDT", mandate_type=MandateType.EXIT),
        create_mandate(symbol="ETHUSDT", mandate_type=MandateType.ENTRY),
        create_mandate(symbol="SOLUSDT", mandate_type=MandateType.HOLD),
    ]

    result = arbitrator.arbitrate_all(all_mandates)

    assert result["BTCUSDT"].type == ActionType.EXIT
    assert result["ETHUSDT"].type == ActionType.ENTRY
    assert result["SOLUSDT"].type == ActionType.HOLD


# ==============================================================================
# TASK 1.7: Determinism (Theorem 3.1)
# ==============================================================================

def test_determinism_same_input_same_output(arbitrator):
    """Same mandates → same action (Theorem 3.1)."""
    mandates = {
        create_mandate(mandate_type=MandateType.ENTRY, authority=5.0, strategy_id="S1"),
        create_mandate(mandate_type=MandateType.REDUCE, authority=3.0, strategy_id="S2"),
    }

    results = [arbitrator.arbitrate(mandates) for _ in range(10)]

    # All results must be identical
    first = results[0]
    for result in results[1:]:
        assert result.type == first.type
        assert result.symbol == first.symbol
        assert result.strategy_id == first.strategy_id


def test_determinism_complex_scenario(arbitrator):
    """Complex mandate set → deterministic resolution."""
    mandates = {
        create_mandate(mandate_type=MandateType.BLOCK, authority=8.0),
        create_mandate(mandate_type=MandateType.ENTRY, authority=10.0, direction="LONG"),
        create_mandate(mandate_type=MandateType.REDUCE, authority=6.0),
        create_mandate(mandate_type=MandateType.HOLD, authority=4.0),
    }

    results = [arbitrator.arbitrate(mandates) for _ in range(10)]

    # BLOCK filters ENTRY, REDUCE is highest remaining actionable
    for result in results:
        assert result.type == ActionType.REDUCE


# ==============================================================================
# TASK 1.8: Action Field Preservation
# ==============================================================================

def test_entry_preserves_direction(arbitrator):
    """ENTRY mandate direction preserved in action."""
    mandates = {
        create_mandate(
            mandate_type=MandateType.ENTRY,
            direction="LONG",
            quantity=Decimal("0.01"),
            entry_price=Decimal("65000.00")
        )
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.ENTRY
    assert result.direction == "LONG"
    assert result.quantity == Decimal("0.01")
    assert result.entry_price == Decimal("65000.00")


def test_reduce_preserves_quantity(arbitrator):
    """REDUCE mandate quantity preserved in action."""
    mandates = {
        create_mandate(
            mandate_type=MandateType.REDUCE,
            quantity=Decimal("0.005")
        )
    }

    result = arbitrator.arbitrate(mandates)

    assert result.type == ActionType.REDUCE
    assert result.quantity == Decimal("0.005")


def test_strategy_id_preserved(arbitrator):
    """Winning mandate's strategy_id preserved in action."""
    mandates = {
        create_mandate(
            mandate_type=MandateType.ENTRY,
            authority=10.0,
            strategy_id="CASCADE_SNIPER"
        )
    }

    result = arbitrator.arbitrate(mandates)

    assert result.strategy_id == "CASCADE_SNIPER"


# ==============================================================================
# TASK 1.9: Completeness (Theorem 8.1)
# ==============================================================================

def test_always_returns_action(arbitrator):
    """Arbitration always completes with an Action (Theorem 8.1)."""
    test_cases = [
        set(),  # Empty
        {create_mandate(mandate_type=MandateType.HOLD)},
        {create_mandate(mandate_type=MandateType.BLOCK)},
        {create_mandate(mandate_type=MandateType.ENTRY)},
        {create_mandate(mandate_type=MandateType.EXIT)},
        {create_mandate(mandate_type=MandateType.REDUCE)},
    ]

    for mandates in test_cases:
        result = arbitrator.arbitrate(mandates)
        assert isinstance(result, Action)
        assert result.type in ActionType


# ==============================================================================
# TASK 1.10: Single Action Per Symbol (Theorem 4.1)
# ==============================================================================

def test_single_action_per_symbol(arbitrator):
    """Each symbol gets exactly one action."""
    all_mandates = [
        create_mandate(symbol="BTCUSDT", mandate_type=MandateType.ENTRY),
        create_mandate(symbol="BTCUSDT", mandate_type=MandateType.REDUCE),
        create_mandate(symbol="ETHUSDT", mandate_type=MandateType.EXIT),
        create_mandate(symbol="ETHUSDT", mandate_type=MandateType.HOLD),
    ]

    result = arbitrator.arbitrate_all(all_mandates)

    # Exactly one action per symbol
    assert len(result) == 2
    assert isinstance(result["BTCUSDT"], Action)
    assert isinstance(result["ETHUSDT"], Action)

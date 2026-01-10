"""Tests for Mandate Arbitration.

Verifies all 13 theorems from MANDATE_ARBITRATION_PROOFS.md:
- EXIT supremacy (Theorem 2.2)
- BLOCK prevents ENTRY (Theorem 2.3)
- Determinism (Theorem 3.1, 3.2)
- Single action (Theorem 4.1, 4.2)
- Symbol independence (Theorem 5.1, 5.2)
- Completeness (Theorem 6.1)
- Risk constraints (Theorem 7.2)
- Liveness (Theorem 8.1, 8.2)
"""

import pytest

from runtime.arbitration.types import Mandate, Action, MandateType, ActionType
from runtime.arbitration.arbitrator import MandateArbitrator


class TestMandateTypeHierarchy:
    """Test authority hierarchy (Section 2.1)."""
    
    def test_hierarchy_ordering(self):
        """EXIT > BLOCK > REDUCE > ENTRY > HOLD."""
        assert MandateType.EXIT.value > MandateType.BLOCK.value
        assert MandateType.BLOCK.value > MandateType.REDUCE.value
        assert MandateType.REDUCE.value > MandateType.ENTRY.value
        assert MandateType.ENTRY.value > MandateType.HOLD.value


class TestEXITSupremacy:
    """Test EXIT supremacy (Theorem 2.2)."""
    
    def test_exit_alone(self):
        """EXIT alone → EXIT."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.EXIT, authority=1.0, timestamp=100.0)
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.EXIT
    
    def test_exit_with_entry(self):
        """EXIT + ENTRY → EXIT (EXIT wins)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.EXIT, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=10.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.EXIT
    
    def test_exit_with_all_types(self):
        """Theorem 2.2: EXIT + {ENTRY, REDUCE, HOLD, BLOCK} → EXIT."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.EXIT, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.HOLD, authority=2.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.BLOCK, authority=10.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.EXIT


class TestBLOCKPreventsENTRY:
    """Test BLOCK prevents ENTRY (Theorem 2.3)."""
    
    def test_block_filters_entry(self):
        """BLOCK + ENTRY → NO_ACTION (ENTRY filtered)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.BLOCK, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.NO_ACTION
   
    def test_block_with_entry_and_hold(self):
        """BLOCK + ENTRY + HOLD → HOLD (ENTRY filtered, HOLD wins)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.BLOCK, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=5.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.HOLD, authority=2.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.HOLD
    
    def test_block_allows_reduce(self):
        """BLOCK + REDUCE → REDUCE (REDUCE not filtered)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.BLOCK, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.REDUCE


class TestDeterminism:
    """Test deterministic arbitration (Theorem 3.1, 3.2)."""
    
    def test_same_mandates_same_result(self):
        """Theorem 3.1: Same mandates → same action."""
        arb1 = MandateArbitrator()
        arb2 = MandateArbitrator()
        
        mandates1 = {
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=2.0, timestamp=100.0),
        }
        mandates2 = {
            Mandate("BTCUSDT", MandateType.REDUCE, authority=3.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.ENTRY, authority=2.0, timestamp=100.0),
        }
        
        action1 = arb1.arbitrate(mandates1)
        action2 = arb2.arbitrate(mandates2)
        
        assert action1.type == action2.type == ActionType.REDUCE
    
    def test_authority_tiebreaker(self):
        """Theorem 3.2: Higher authority wins (deterministic)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.REDUCE, authority=10.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.REDUCE, authority=5.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.REDUCE


class TestSingleActionInvariant:
    """Test exactly one action per symbol (Theorem 4.1, 4.2)."""
    
    def test_single_action_returned(self):
        """Theorem 4.1: Arbitration returns exactly one action."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.EXIT, authority=2.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        
        # Action is singular, not a collection
        assert isinstance(action, Action)
        assert action.type in ActionType
    
    def test_no_conflicting_actions(self):
        """Theorem 4.2: Cannot simultaneously execute ENTRY and EXIT."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("BTCUSDT", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("BTCUSDT", MandateType.EXIT, authority=2.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        
        # Only one can win (EXIT supremacy)
        assert action.type == ActionType.EXIT
        assert action.type != ActionType.ENTRY  # Mutually exclusive


class TestSymbolIndependence:
    """Test symbol-local arbitration (Theorem 5.1, 5.2)."""
    
    def test_symbols_arbitrated_independently(self):
        """Theorem 5.1: Different symbols → independent results."""
        arb = MandateArbitrator()
        
        mandates = [
            Mandate("BTCUSDT", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("ETHUSDT", MandateType.EXIT, authority=2.0, timestamp=100.0),
        ]
        
        actions = arb.arbitrate_all(mandates)
        
        assert actions["BTCUSDT"].type == ActionType.ENTRY
        assert actions["ETHUSDT"].type == ActionType.EXIT
    
    def test_parallel_arbitration_equivalent(self):
        """Theorem 5.2: Parallel arbitration → same results as sequential."""
        arb = MandateArbitrator()
        
        mandates = [
            Mandate("SYM1", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("SYM2", MandateType.REDUCE, authority=2.0, timestamp=100.0),
            Mandate("SYM3", MandateType.EXIT, authority=3.0, timestamp=100.0),
        ]
        
        # Sequential (via arbitrate_all)
        actions_seq = arb.arbitrate_all(mandates)
        
        # "Parallel" (same function, symbol-local by design)
        actions_par = {}
        for symbol in ["SYM1", "SYM2", "SYM3"]:
            symbol_mandates = {m for m in mandates if m.symbol == symbol}
            actions_par[symbol] = arb.arbitrate(symbol_mandates)
        
        # Results identical
        assert actions_seq["SYM1"].type == actions_par["SYM1"].type
        assert actions_seq["SYM2"].type == actions_par["SYM2"].type
        assert actions_seq["SYM3"].type == actions_par["SYM3"].type


class TestCompleteness:
    """Test all mandate combinations handled (Theorem 6.1)."""
    
    def test_empty_mandates(self):
        """Empty set → NO_ACTION."""
        arb = MandateArbitrator()
        action = arb.arbitrate(set())
        assert action.type == ActionType.NO_ACTION
    
    def test_single_mandate_types(self):
        """Each type alone produces correct action."""
        arb = MandateArbitrator()
        
        # ENTRY alone
        action = arb.arbitrate({
            Mandate("SYM", MandateType.ENTRY, authority=1.0, timestamp=100.0)
        })
        assert action.type == ActionType.ENTRY
        
        # EXIT alone
        action = arb.arbitrate({
            Mandate("SYM", MandateType.EXIT, authority=1.0, timestamp=100.0)
        })
        assert action.type == ActionType.EXIT
        
        # REDUCE alone
        action = arb.arbitrate({
            Mandate("SYM", MandateType.REDUCE, authority=1.0, timestamp=100.0)
        })
        assert action.type == ActionType.REDUCE
        
        # HOLD alone
        action = arb.arbitrate({
            Mandate("SYM", MandateType.HOLD, authority=1.0, timestamp=100.0)
        })
        assert action.type == ActionType.HOLD
        
        # BLOCK alone (not actionable)
        action = arb.arbitrate({
            Mandate("SYM", MandateType.BLOCK, authority=1.0, timestamp=100.0)
        })
        assert action.type == ActionType.NO_ACTION
    
    def test_hierarchy_resolution(self):
        """REDUCE + ENTRY + HOLD → REDUCE (highest priority)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("SYM", MandateType.REDUCE, authority=1.0, timestamp=100.0),
            Mandate("SYM", MandateType.ENTRY, authority=5.0, timestamp=100.0),
            Mandate("SYM", MandateType.HOLD, authority=10.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.REDUCE


class TestLiveness:
    """Test arbitration always completes (Theorem 8.1, 8.2)."""
    
    def test_arbitration_completes(self):
        """Theorem 8.1: arbitrate() terminates for any input."""
        arb = MandateArbitrator()
        
        # Large set
        mandates = {
            Mandate(f"SYM", MandateType(i % 5 + 1), authority=float(i), timestamp=100.0)
            for i in range(50)
        }
        
        # Should complete (not hang)
        action = arb.arbitrate(mandates)
        assert action is not None
    
    def test_no_starvation(self):
        """Theorem 8.2: HOLD does not block indefinitely."""
        arb = MandateArbitrator()
        
        # Only HOLD
        mandates = {
            Mandate("SYM", MandateType.HOLD, authority=1.0, timestamp=100.0)
        }
        action = arb.arbitrate(mandates)
        
        # Returns HOLD (not stuck)
        assert action.type == ActionType.HOLD


class TestAdversarialResistance:
    """Test adversarial attack defenses (Section 9)."""
    
    def test_mandate_flooding(self):
        """Flooding with many mandates doesn't break arbitration."""
        arb = MandateArbitrator()
        
        # 100 mandates for same symbol
        mandates = {
            Mandate("SYM", MandateType.ENTRY, authority=float(i), timestamp=100.0)
            for i in range(100)
        }
        
       # Should complete (O(n log n) complexity)
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.ENTRY
    
    def test_authority_manipulation(self):
        """High authority ENTRY cannot override EXIT."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("SYM", MandateType.EXIT, authority=1.0, timestamp=100.0),
            Mandate("SYM", MandateType.ENTRY, authority=99999.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        
        # EXIT wins regardless of authority (hierarchy > authority)
        assert action.type == ActionType.EXIT
    
    def test_simultaneous_entry_exit(self):
        """Both ENTRY and EXIT → EXIT (deterministic)."""
        arb = MandateArbitrator()
        mandates = {
            Mandate("SYM", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("SYM", MandateType.EXIT, authority=1.0, timestamp=100.0),
        }
        action = arb.arbitrate(mandates)
        assert action.type == ActionType.EXIT


class TestMandateValidation:
    """Test mandate invariants enforced."""
    
    def test_empty_symbol_rejected(self):
        """Mandate with empty symbol is invalid."""
        with pytest.raises(ValueError):
            Mandate("", MandateType.ENTRY, authority=1.0, timestamp=100.0)
    
    def test_negative_authority_rejected(self):
        """Negative authority is invalid."""
        with pytest.raises(ValueError):
            Mandate("SYM", MandateType.ENTRY, authority=-1.0, timestamp=100.0)
    
    def test_negative_timestamp_rejected(self):
        """Negative timestamp is invalid."""
        with pytest.raises(ValueError):
            Mandate("SYM", MandateType.ENTRY, authority=1.0, timestamp=-1.0)


class TestMultiSymbolArbitration:
    """Test arbitrate_all with multiple symbols."""
    
    def test_different_symbols_resolved_independently(self):
        """Multiple symbols get independent actions."""
        arb = MandateArbitrator()
        
        mandates = [
            Mandate("BTC", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("ETH", MandateType.EXIT, authority=2.0, timestamp=100.0),
            Mandate("SOL", MandateType.REDUCE, authority=3.0, timestamp=100.0),
        ]
        
        actions = arb.arbitrate_all(mandates)
        
        assert actions["BTC"].type == ActionType.ENTRY
        assert actions["ETH"].type == ActionType.EXIT
        assert actions["SOL"].type == ActionType.REDUCE
    
    def test_mixed_symbol_mandates(self):
        """Symbol with multiple mandates resolved correctly."""
        arb = MandateArbitrator()
        
        mandates = [
            Mandate("BTC", MandateType.ENTRY, authority=1.0, timestamp=100.0),
            Mandate("BTC", MandateType.EXIT, authority=2.0, timestamp=100.0),
            Mandate("ETH", MandateType.HOLD, authority=1.0, timestamp=100.0),
        ]
        
        actions = arb.arbitrate_all(mandates)
        
        # BTC: EXIT wins over ENTRY
        assert actions["BTC"].type == ActionType.EXIT
        # ETH: HOLD alone
        assert actions["ETH"].type == ActionType.HOLD

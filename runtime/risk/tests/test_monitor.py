"""Tests for Risk Monitor.

Tests mandate emission per RISK_EXPOSURE_MATHEMATICS.md Section 11.
"""

import pytest
from decimal import Decimal

from runtime.risk.monitor import RiskMonitor
from runtime.risk.types import RiskConfig, AccountState
from runtime.arbitration.types import MandateType
from runtime.position.types import Position, PositionState, Direction


class TestRiskMonitorMandates:
    """Test risk monitor mandate emission."""
    
    def test_leverage_violation_emits_block(self):
        """I-L1 violated → emit BLOCK."""
        monitor = RiskMonitor(RiskConfig(L_max=5.0, L_target=4.0))
        
        # Position with 6x leverage (violates 5x limit)
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("1.2"),
                entry_price=Decimal("50000")
            )
        }
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("4000"),
            timestamp=100.0
        )
        
        mark_prices = {"BTCUSDT": Decimal("50000")}
        
        mandates = monitor.check_and_emit(account, positions, mark_prices)
        
        # Should emit BLOCK
        block_mandates = [m for m in mandates if m.type == MandateType.BLOCK]
        assert len(block_mandates) > 0, "Should emit BLOCK when leverage violated"
    
    def test_critical_liquidation_emits_exit(self):
        """D_liq < D_critical → emit EXIT."""
        config = RiskConfig(D_critical=0.05, D_min_safe=0.08)
        monitor = RiskMonitor(config)
        
        # Position near liquidation (mark price dropped significantly)
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("1"),
                entry_price=Decimal("50000")
            )
        }
        
        account = AccountState(
            equity=Decimal("5000"),  # Lower equity -> higher leverage (9.2x) -> P_liq closer
            margin_available=Decimal("1000"),
            timestamp=100.0
        )
        
        # Mark price near liquidation
        mark_prices = {"BTCUSDT": Decimal("46000")}  # ~8% drop
        
        mandates = monitor.check_and_emit(account, positions, mark_prices)
        
        # Should emit EXIT for critical distance
        exit_mandates = [m for m in mandates if m.type == MandateType.EXIT and m.symbol == "BTCUSDT"]
        assert len(exit_mandates) > 0, "Should emit EXIT when D_liq < D_critical"
    
    def test_min_safe_violation_emits_reduce(self):
        """D_min_safe violated → emit REDUCE."""
        config = RiskConfig(D_critical=0.03, D_min_safe=0.08)
        monitor = RiskMonitor(config)
        
        # Position approaching liquidation but not critical
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("1"),
                entry_price=Decimal("50000")
            )
        }
        
        account = AccountState(
            equity=Decimal("6000"),  # Lower equity -> higher leverage -> P_liq closer
            margin_available=Decimal("1000"),
            timestamp=100.0
        )
        
        # Mark price dropped but not critical
        mark_prices = {"BTCUSDT": Decimal("48000")}  # ~4% drop
        
        mandates = monitor.check_and_emit(account, positions, mark_prices)
        
        # Should emit REDUCE (not EXIT)
        reduce_mandates = [m for m in mandates if m.type == MandateType.REDUCE and m.symbol == "BTCUSDT"]
        assert len(reduce_mandates) > 0, "Should emit REDUCE when D_liq < D_min_safe"
    
    def test_safe_positions_no_mandates(self):
        """Safe positions → no mandates."""
        monitor = RiskMonitor(RiskConfig())
        
        # Small, safe position
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("0.1"),
                entry_price=Decimal("50000")
            )
        }
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("9500"),
            timestamp=100.0
        )
        
        mark_prices = {"BTCUSDT": Decimal("50000")}
        
        mandates = monitor.check_and_emit(account, positions, mark_prices)
        
        # No risk mandates expected
        assert len(mandates) == 0, "Safe position should not emit mandates"


class TestEntryValidation:
    """Test entry validation logic (Section 11.1)."""
    
    def test_valid_entry_accepted(self):
        """Valid entry passes all checks."""
        monitor = RiskMonitor(RiskConfig(L_max=10.0))
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("8000"),
            timestamp=100.0
        )
        
        positions = {}  # No existing positions
        mark_prices = {}
        
        # Small position, well within limits
        valid, error = monitor.validate_entry(
            symbol="BTCUSDT",
            size=Decimal("0.5"),
            direction="LONG",
            entry_price=Decimal("50000"),
            account=account,
            positions=positions,
            mark_prices=mark_prices
        )
        
        assert valid, f"Valid entry rejected: {error}"
    
    def test_leverage_exceeded_rejected(self):
        """Entry violating I-L1 rejected."""
        monitor = RiskMonitor(RiskConfig(L_max=5.0, L_target=4.0))
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("8000"),
            timestamp=100.0
        )
        
        positions = {}
        mark_prices = {}
        
        # Position would create 6x leverage (violates 5x limit)
        valid, error = monitor.validate_entry(
            symbol="BTCUSDT",
            size=Decimal("1.2"),
            direction="LONG",
            entry_price=Decimal("50000"),
            account=account,
            positions=positions,
            mark_prices=mark_prices
        )
        
        assert not valid, "Should reject leverage violation"
        assert "I-L1" in error, "Should reference invariant I-L1"
    
    def test_insufficient_margin_rejected(self):
        """Entry with insufficient margin rejected."""
        monitor = RiskMonitor(RiskConfig())
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("1000"),  # Not enough margin
            timestamp=100.0
        )
        
        positions = {}
        mark_prices = {}
        
        # Large position requiring more margin than available
        valid, error = monitor.validate_entry(
            symbol="BTCUSDT",
            size=Decimal("2"),
            direction="LONG",
            entry_price=Decimal("50000"),
            account=account,
            positions=positions,
            mark_prices=mark_prices
        )
        
        assert not valid, "Should reject insufficient margin"
        # Note: May be caught by I-L2 first (per-symbol limit)
        assert "I-L2" in error or "I-M1" in error, "Should reference I-L2 or I-M1"

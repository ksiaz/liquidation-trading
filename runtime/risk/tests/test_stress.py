
import pytest
from decimal import Decimal
from typing import Dict

from runtime.risk.monitor import RiskMonitor
from runtime.risk.types import RiskConfig, AccountState, PositionRisk
from runtime.position.types import Position, PositionState, Direction
from runtime.arbitration.types import MandateType

class TestStressScenarios:
    """Stress tests for Risk System (Section 9).
    
    Verifies system behavior under extreme market conditions:
    - Simultaneous adverse moves
    - Flash crashes
    - Leverage limits
    """
    
    def setup_method(self):
        """Setup monitor with standard config."""
        self.config = RiskConfig(
            L_max=10.0,
            L_target=8.0,
            D_min_safe=0.08,  # 8% buffer
            D_critical=0.03   # 3% panic exit
        )
        self.monitor = RiskMonitor(self.config)
        
    def _create_position(self, symbol: str, quantity: str, entry_price: str, direction=Direction.LONG) -> Position:
        """Helper to create active position."""
        return Position(
            symbol=symbol,
            state=PositionState.OPEN,
            direction=direction,
            quantity=Decimal(quantity),
            entry_price=Decimal(entry_price)
        )

    def test_simultaneous_adverse_move(self):
        """Scenario: All positions move 10% against (simulating market crash).
        
        Verify: Monitor emits EXIT/REDUCE mandates for all danger positions.
        """
        # Setup: 2 Long positions with 10x leverage (risky)
        # Entry: 50,000. Liq ~ 45,000 (approx 10% drop)
        positions = {
            "BTCUSDT": self._create_position("BTCUSDT", "1.0", "50000"),
            "ETHUSDT": self._create_position("ETHUSDT", "10.0", "3000")
        }
        
        # Account: Equity 8000. Exposure 80,000. Leverage 10x.
        # This is at L_max.
        account = AccountState(
            equity=Decimal("8000"),
            margin_available=Decimal("0"),
            timestamp=100.0
        )
        
        # Action: Price drops 10% (Adverse move)
        # BTC: 50k -> 45k. ETH: 3k -> 2.7k
        mark_prices = {
            "BTCUSDT": Decimal("45000"),
            "ETHUSDT": Decimal("2700")
        }
        
        # Check mandates
        mandates = self.monitor.check_and_emit(account, positions, mark_prices)
        
        # Expect: EXIT mandates due to critical liquidation distance or REDUCE
        # With 10x leverage and 10% drop, we are likely insolvent or at least critical.
        # Actually with 10x, 10% drop wipes equity. 
        # But let's check what monitor says.
        assert len(mandates) > 0
        
        types = [m.type for m in mandates]
        assert MandateType.EXIT in types or MandateType.REDUCE in types
        
    def test_flash_crash_protection(self):
        """Scenario: Single symbol flashes -15% in <1s.
        
        Verify: Immediate EXIT mandate.
        """
        # Setup: BTC Long 5x leverage (safe-ish usually)
        # Entry 50k. Liq ~40k (+ buffer).
        positions = {
            "BTCUSDT": self._create_position("BTCUSDT", "1.0", "50000")
        }
        
        # Action: Flash crash to 42.5k (15% drop)
        # PnL = 1.0 * (42500 - 50000) = -7500.
        # Equity = 10000 - 7500 = 2500.
        account = AccountState(
            equity=Decimal("2500"),
            margin_available=Decimal("0"),
            timestamp=100.0
        )
        # Distance calculation:
        # P_liq (Long 5x) ~= 50k * (1 - 0.2 + 0.005) = 40.25k
        # P_mark = 42.5k
        # D_liq = (42.5 - 40.25) / 42.5 = 2.25/42.5 ~= 0.05 (5%)
        # D_min_safe = 8%. D_critical = 3%.
        # Result: D_liq < D_min_safe (5% < 8%).
        # Expect: REDUCE (or EXIT if closer).
        
        mark_prices = {
            "BTCUSDT": Decimal("42500")
        }
        
        mandates = self.monitor.check_and_emit(account, positions, mark_prices)
        
        # Should have REDUCE or EXIT
        assert any(m.symbol == "BTCUSDT" for m in mandates)
        assert any(m.type in (MandateType.EXIT, MandateType.REDUCE) for m in mandates)

    def test_leverage_boundary_enforcement(self):
        """Scenario: Equity drop pushes L_actual > L_max.
        
        Verify: BLOCK mandate emitted regarding new entries.
        """
        # Setup: Leverage 10x (Limit). Equity drops slightly.
        positions = {
            "BTCUSDT": self._create_position("BTCUSDT", "2.0", "50000") # 100k exposure
        }
        
        # Equity 9000. Leverage = 100k/9k = 11.1x (> 10x)
        account = AccountState(
            equity=Decimal("9000"),
            margin_available=Decimal("0"),
            timestamp=100.0
        )
        
        mark_prices = {"BTCUSDT": Decimal("50000")}
        
        mandates = self.monitor.check_and_emit(account, positions, mark_prices)
        
        # Expect BLOCK mandate (Global)
        block_mandates = [m for m in mandates if m.type == MandateType.BLOCK]
        assert len(block_mandates) > 0
        assert block_mandates[0].symbol == "*"

    def test_entering_state_skipped_in_crash(self):
        """Scenario: Market crashes while position is ENTERING (not filled).
        
        Verify: No erroneous calculations (missing entry price).
        """
        # Setup: ENTERING position (no entry price yet)
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.ENTERING,
                direction=Direction.LONG,
                quantity=Decimal("1.0"),
                entry_price=None
            )
        }
        
        account = AccountState(equity=Decimal("10000"), margin_available=Decimal("10000"), timestamp=100.0)
        mark_prices = {"BTCUSDT": Decimal("40000")} # Crash price
        
        # Should not raise error
        mandates = self.monitor.check_and_emit(account, positions, mark_prices)
        
        # Should be empty (no active risk)
        assert len(mandates) == 0

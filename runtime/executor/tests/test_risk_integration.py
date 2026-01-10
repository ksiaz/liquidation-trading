"""Integration tests for Risk Integration in ExecutionController.

Tests:
- Integration of risk mandates with arbitration
- Entry validation blocking invalid trades
- Risk limits triggering action
"""

import pytest
from decimal import Decimal

from runtime.executor.controller import ExecutionController
from runtime.arbitration.types import Mandate, MandateType, ActionType
from runtime.risk.types import RiskConfig, AccountState
from runtime.position.types import PositionState


class TestRiskIntegration:
    """Test RiskMonitor integration into ExecutionController."""
    
    def test_entry_validation_blocks_trade(self):
        """Entry validation should block trades violating risk limits."""
        # Config with low L_max to trigger violation
        config = RiskConfig(L_max=1.0, L_target=0.8, L_symbol_max=1.0)
        controller = ExecutionController(risk_config=config)
        
        account = AccountState(
            equity=Decimal("1000"),
            margin_available=Decimal("1000"),
            timestamp=100.0
        )
        mark_prices = {"BTCUSDT": Decimal("50000")}
        
        # Mandate to enter standard position (0.1 BTC = 5000 USD)
        # Exposure 5000 > Equity 1000 (Usage > 1.0x) => Should Block
        # Actually our hardcoded placeholder entry size in controller is 0.1
        # So it will try to check 0.1 * 50000 = 5000.
        # 5000 / 1000 = 5x leverage. 5x > 1.0x config.
        # Should be REJECTED.
        
        mandates = [
            Mandate(
                symbol="BTCUSDT",
                type=MandateType.ENTRY,
                authority=1.0,
                timestamp=100.0
            )
        ]
        
        stats = controller.process_cycle(mandates, account, mark_prices)
        
        assert stats.actions_executed == 0, "Action should be rejected"
        assert stats.actions_rejected == 1, "Action should be counted as rejected"
        
        # Verify log reason
        log = controller.get_execution_log()
        assert len(log) == 1
        assert log[0].success is False
        assert "Risk validation failed" in log[0].error
        assert "Leverage limit violated" in log[0].error
    
    def test_risk_mandates_trigger_action(self):
        """Risk monitor should emit mandates that get executed."""
        # Config with tight liquidation threshold
        config = RiskConfig(D_critical=0.05, D_min_safe=0.08)
        controller = ExecutionController(risk_config=config)
        
        # Setup existing OPEN position that is in danger
        # We need to manually inject position since we don't have full setup
        from runtime.position.types import Position, Direction
        
        controller.state_machine._positions["BTCUSDT"] = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000")
        )
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("5000"),
            timestamp=100.0
        )
        
        # Price drops to 46000 (8% drop)
        # Eq = 10000 + 1*(46000 - 50000) = 6000? No risk monitor uses account state passed
        # Account equity needs to reflect reality for accurate leverage calc
        # Let's say equity dropped to 6000.
        # 6000 equity, 46000 exposure. L = 7.6x.
        # P_liq (approx) = 50000 * (1 - 1/7.6 + 0.005) = 50000 * 0.873 = 43670
        # D_liq = (46000 - 43670) / 46000 = 5%.
        # D_critical is 5%. It triggers EXIT if < 5%.
        # Let's lower equity slightly more to ensure trigger.
        
        account_danger = AccountState(
            equity=Decimal("5000"),  # Higher leverage = higher P_liq = smaller D_liq
            margin_available=Decimal("1000"),
            timestamp=100.0
        )
        mark_prices = {"BTCUSDT": Decimal("46000")}
        
        # No strategy mandates - only relying on risk monitor
        stats = controller.process_cycle([], account_danger, mark_prices)
        
        assert stats.actions_executed == 1, "Should execute risk mandate"
        assert "BTCUSDT" in controller.state_machine._positions
        # State should be CLOSING (EXIT executed, awaiting fill)
        assert controller.state_machine.get_position("BTCUSDT").state == PositionState.CLOSING

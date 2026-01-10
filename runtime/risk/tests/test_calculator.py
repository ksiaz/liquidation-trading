"""Unit Tests for Risk Calculator.

Tests per RISK_EXPOSURE_MATHEMATICS.md:
- Section 2.2: Liquidation mechanics
- Section 3.1: Leverage calculation
- Section 5: Exposure aggregation
- Section 7: Position sizing
"""

import pytest
from decimal import Decimal

from runtime.risk.calculator import RiskCalculator
from runtime.risk.types import RiskConfig, AccountState, PositionRisk
from runtime.position.types import Position, PositionState, Direction


class TestLiquidationPrice:
    """Test liquidation price calculations (Section 2.2)."""
    
    def test_long_liquidation_price(self):
        """LONG: P_liq = P_entry × (1 - 1/L + MMR)."""
        calc = RiskCalculator(RiskConfig())
        
        entry_price = Decimal("50000")
        leverage = 10.0
        mmr = 0.005
        
        liq_price = calc.calculate_liquidation_price(
            Direction.LONG,
            entry_price,
            leverage,
            mmr
        )
        
        # Expected: 50000 × (1 - 0.1 + 0.005) = 50000 × 0.905 = 45250
        expected = Decimal("45250")
        assert abs(liq_price - expected) < Decimal("1"), f"Expected {expected}, got {liq_price}"
    
    def test_short_liquidation_price(self):
        """SHORT: P_liq = P_entry × (1 + 1/L - MMR)."""
        calc = RiskCalculator(RiskConfig())
        
        entry_price = Decimal("50000")
        leverage = 10.0
        mmr = 0.005
        
        liq_price = calc.calculate_liquidation_price(
            Direction.SHORT,
            entry_price,
            leverage,
            mmr
        )
        
        # Expected: 50000 × (1 + 0.1 - 0.005) = 50000 × 1.095 = 54750
        expected = Decimal("54750")
        assert abs(liq_price - expected) < Decimal("1"), f"Expected {expected}, got {liq_price}"
    
    def test_higher_leverage_closer_liquidation(self):
        """Higher leverage → liquidation price closer to entry."""
        calc = RiskCalculator(RiskConfig())
        
        entry_price = Decimal("50000")
        mmr = 0.005
        
        liq_10x = calc.calculate_liquidation_price(Direction.LONG, entry_price, 10.0, mmr)
        liq_20x = calc.calculate_liquidation_price(Direction.LONG, entry_price, 20.0, mmr)
        
        # 20x should be closer to entry than 10x
        dist_10x = abs(entry_price - liq_10x)
        dist_20x = abs(entry_price - liq_20x)
        
        assert dist_20x < dist_10x, "20x liq price should be closer to entry"


class TestLiquidationDistance:
    """Test liquidation distance calculations (Section 2.2)."""
    
    def test_safe_distance(self):
        """D_liq = |P_mark - P_liq| / P_mark."""
        calc = RiskCalculator(RiskConfig())
        
        mark_price = Decimal("50000")
        liq_price = Decimal("45000")
        
        D_liq = calc.calculate_liquidation_distance(mark_price, liq_price)
        
        # Expected: |50000 - 45000| / 50000 = 5000 / 50000 = 0.10 (10%)
        expected = 0.10
        assert abs(D_liq - expected) < 0.001, f"Expected {expected}, got {D_liq}"
    
    def test_critical_distance(self):
        """Near liquidation → small distance."""
        calc = RiskCalculator(RiskConfig())
        
        mark_price = Decimal("50000")
        liq_price = Decimal("49000")
        
        D_liq = calc.calculate_liquidation_distance(mark_price, liq_price)
        
        # Expected: 1000 / 50000 = 0.02 (2%)
        assert D_liq < 0.03, "Should be in critical zone"
    
    def test_zero_distance(self):
        """At liquidation price → zero distance."""
        calc = RiskCalculator(RiskConfig())
        
        mark_price = Decimal("50000")
        liq_price = Decimal("50000")
        
        D_liq = calc.calculate_liquidation_distance(mark_price, liq_price)
        
        assert D_liq == 0.0, "Distance should be zero at liq price"


class TestLeverageCalculation:
    """Test leverage calculations (Section 3.1)."""
    
    def test_single_position_leverage(self):
        """L_actual = Exposure / E."""
        calc = RiskCalculator(RiskConfig())
        
        # Single LONG position
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
            equity=Decimal("10000"),
            margin_available=Decimal("5000"),
            timestamp=100.0
        )
        
        mark_prices = {"BTCUSDT": Decimal("50000")}
        
        leverage = calc.calculate_total_leverage(positions, account, mark_prices)
        
        # Expected: 50000 / 10000 = 5.0x
        assert abs(leverage - 5.0) < 0.01, f"Expected 5.0x, got {leverage}"
    
    def test_multi_position_leverage(self):
        """Multiple positions → sum exposures."""
        calc = RiskCalculator(RiskConfig())
        
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("1"),
                entry_price=Decimal("50000")
            ),
            "ETHUSDT": Position(
                symbol="ETHUSDT",
                state=PositionState.OPEN,
                direction=Direction.SHORT,
                quantity=Decimal("-10"),
                entry_price=Decimal("3000")
            )
        }
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("2000"),
            timestamp=100.0
        )
        
        mark_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000")
        }
        
        leverage = calc.calculate_total_leverage(positions, account, mark_prices)
        
        # Expected: (50000 + 30000) / 10000 = 8.0x
        assert abs(leverage - 8.0) < 0.01, f"Expected 8.0x, got {leverage}"
    
    def test_flat_positions_ignored(self):
        """FL

AT positions don't contribute to leverage."""
        calc = RiskCalculator(RiskConfig())
        
        positions = {
            "BTCUSDT": Position.create_flat("BTCUSDT"),
            "ETHUSDT": Position(
                symbol="ETHUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("10"),
                entry_price=Decimal("3000")
            )
        }
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("7000"),
            timestamp=100.0
        )
        
        mark_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000")
        }
        
        leverage = calc.calculate_total_leverage(positions, account, mark_prices)
        
        # Only ETH counts: 30000 / 10000 = 3.0x
        assert abs(leverage - 3.0) < 0.01, f"Expected 3.0x, got {leverage}"


class TestPositionRisk:
    """Test position risk calculations (Section 5.1)."""
    
    def test_position_exposure(self):
        """Exposure = |Q × P_mark|."""
        calc = RiskCalculator(RiskConfig())
        
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("2"),
            entry_price=Decimal("50000")
        )
        
        mark_price = Decimal("52000")
        leverage = 5.0
        
        pos_risk = calc.calculate_position_risk(position, mark_price, leverage)
        
        # Exposure = 2 × 52000 = 104000
        assert pos_risk.exposure == Decimal("104000")
        assert pos_risk.notional == Decimal("104000")
    
    def test_unrealized_pnl(self):
        """PnL = Q × (P_mark - P_entry)."""
        calc = RiskCalculator(RiskConfig())
        
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("1"),
            entry_price=Decimal("50000")
        )
        
        mark_price = Decimal("52000")
        leverage = 5.0
        
        pos_risk = calc.calculate_position_risk(position, mark_price, leverage)
        
        # PnL = 1 × (52000 - 50000) = 2000
        assert pos_risk.unrealized_pnl == Decimal("2000")
    
    def test_short_position_pnl(self):
        """SHORT position PnL calculation."""
        calc = RiskCalculator(RiskConfig())
        
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.SHORT,
            quantity=Decimal("-1"),
            entry_price=Decimal("50000")
        )
        
        mark_price = Decimal("48000")  # Price dropped
        leverage = 5.0
        
        pos_risk = calc.calculate_position_risk(position, mark_price, leverage)
        
        # PnL = -1 × (48000 - 50000) = -1 × (-2000) = 2000 (profit!)
        assert pos_risk.unrealized_pnl == Decimal("2000")


class TestPositionSizing:
    """Test position sizing calculations (Section 7)."""
    
    def test_max_position_size(self):
        """Q_max = (E_available × L_target) / P_entry."""
        calc = RiskCalculator(RiskConfig())
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("8000"),
            timestamp=100.0
        )
        
        entry_price = Decimal("50000")
        
        Q_max = calc.calculate_max_position_size(
            "BTCUSDT",
            entry_price,
            Direction.LONG,
            account,
            current_leverage=0.0
        )
        
        # Base: (8000 × 8.0) / 50000 = 64000 / 50000 = 1.28
        # With safety: 1.28 × (1 - 0.08 × 8.0) = 1.28 × 0.36 = 0.46
        assert Q_max > Decimal("0"), "Should allow some position"
        assert Q_max < Decimal("2"), "Should apply safety margin"
    
    def test_reduce_quantity(self):
        """Q_reduce = Q × reduction_pct."""
        calc = RiskCalculator(RiskConfig())
        
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("2"),
            entry_price=Decimal("50000")
        )
        
        Q_reduce = calc.calculate_reduce_quantity(position, reduction_pct=0.5)
        
        # 50% of 2 = 1
        assert Q_reduce == Decimal("1")
    
    def test_reduce_custom_percentage(self):
        """Custom reduction percentage."""
        calc = RiskCalculator(RiskConfig())
        
        position = Position(
            symbol="BTCUSDT",
            state=PositionState.OPEN,
            direction=Direction.LONG,
            quantity=Decimal("10"),
            entry_price=Decimal("50000")
        )
        
        Q_reduce = calc.calculate_reduce_quantity(position, reduction_pct=0.3)
        
        # 30% of 10 = 3
        assert Q_reduce == Decimal("3")


class TestPortfolioRisk:
    """Test portfolio aggregation (Section 5)."""
    
    def test_total_exposure(self):
        """Total exposure = sum of all position exposures."""
        calc = RiskCalculator(RiskConfig())
        
        positions = {
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                state=PositionState.OPEN,
                direction=Direction.LONG,
                quantity=Decimal("1"),
                entry_price=Decimal("50000")
            ),
            "ETHUSDT": Position(
                symbol="ETHUSDT",
                state=PositionState.OPEN,
                direction=Direction.SHORT,
                quantity=Decimal("-10"),
                entry_price=Decimal("3000")
            )
        }
        
        account = AccountState(
            equity=Decimal("10000"),
            margin_available=Decimal("2000"),
            timestamp=100.0
        )
        
        mark_prices = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000")
        }
        
        portfolio = calc.calculate_portfolio_risk(positions, account, mark_prices)
        
        # Total: 50000 + 30000 = 80000
        assert portfolio.total_exposure == Decimal("80000")
        assert portfolio.long_exposure == Decimal("50000")
        assert portfolio.short_exposure == Decimal("30000")
        assert portfolio.net_exposure == Decimal("20000")  # 50k - 30k
    
    def test_min_liquidation_distance(self):
        """Portfolio risk = worst symbol's D_liq."""
        calc = RiskCalculator(RiskConfig())
        
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
            equity=Decimal("10000"),
            margin_available=Decimal("5000"),
            timestamp=100.0
        )
        
        mark_prices = {"BTCUSDT": Decimal("50000")}
        
        portfolio = calc.calculate_portfolio_risk(positions, account, mark_prices)
        
        # Should identify worst symbol
        assert portfolio.worst_symbol == "BTCUSDT"
        assert portfolio.min_liquidation_distance > 0

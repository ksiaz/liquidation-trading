"""
Unit tests for strategy state machines (HLP10).

Tests:
- Base state machine transitions and validation
- Geometry strategy (Failed Hunt)
- Kinematics strategy (Post-Liq Inventory)
- Cascade strategy (Sniper)
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from runtime.strategies.base import (
    StrategyStateMachine,
    StrategyState,
    StrategyConfig,
    StrategySetup,
    Mandate,
    MandateType,
)
from runtime.strategies.geometry import (
    GeometryStateMachine,
    GeometryConfig,
    GeometrySetup,
)
from runtime.strategies.kinematics import (
    KinematicsStateMachine,
    KinematicsConfig,
    KinematicsSetup,
)
from runtime.strategies.cascade import (
    CascadeStateMachine,
    CascadeConfig,
    CascadeSetup,
)


# =============================================================================
# Base State Machine Tests
# =============================================================================

class TestStrategyState:
    """Tests for StrategyState enum."""

    def test_all_states_defined(self):
        """Verify all expected states exist."""
        assert StrategyState.DISABLED
        assert StrategyState.SCANNING
        assert StrategyState.PRE_ARMED
        assert StrategyState.ARMED
        assert StrategyState.ENTERED
        assert StrategyState.EXITED
        assert StrategyState.COOLDOWN

    def test_state_values(self):
        """Verify state string values."""
        assert StrategyState.DISABLED.value == "disabled"
        assert StrategyState.SCANNING.value == "scanning"
        assert StrategyState.ARMED.value == "armed"


class TestMandate:
    """Tests for Mandate dataclass."""

    def test_mandate_creation(self):
        """Test creating a mandate."""
        mandate = Mandate(
            mandate_type=MandateType.ENTER_LONG,
            symbol="BTC-PERP",
            strategy_name="test",
            size=1.0,
            price=50000.0,
            stop_price=49500.0,
            take_profit_price=50500.0,
        )

        assert mandate.is_entry
        assert mandate.is_long
        assert not mandate.is_short
        assert mandate.symbol == "BTC-PERP"

    def test_short_mandate(self):
        """Test short entry mandate."""
        mandate = Mandate(
            mandate_type=MandateType.ENTER_SHORT,
            symbol="ETH-PERP",
            strategy_name="test",
        )

        assert mandate.is_entry
        assert mandate.is_short
        assert not mandate.is_long

    def test_exit_mandate(self):
        """Test exit mandate."""
        mandate = Mandate(
            mandate_type=MandateType.EXIT,
            symbol="BTC-PERP",
            strategy_name="test",
        )

        assert not mandate.is_entry


class TestStateTransitions:
    """Tests for state transition validation."""

    def test_valid_transitions(self):
        """Test that valid transitions are defined correctly."""
        # DISABLED can only go to SCANNING
        assert StrategyState.SCANNING in GeometryStateMachine.VALID_TRANSITIONS[StrategyState.DISABLED]

        # SCANNING can go to ARMED, PRE_ARMED, or DISABLED
        scanning_targets = GeometryStateMachine.VALID_TRANSITIONS[StrategyState.SCANNING]
        assert StrategyState.ARMED in scanning_targets
        assert StrategyState.PRE_ARMED in scanning_targets
        assert StrategyState.DISABLED in scanning_targets

        # ARMED can go to ENTERED, SCANNING, or DISABLED
        armed_targets = GeometryStateMachine.VALID_TRANSITIONS[StrategyState.ARMED]
        assert StrategyState.ENTERED in armed_targets
        assert StrategyState.SCANNING in armed_targets
        assert StrategyState.DISABLED in armed_targets

        # ENTERED can only go to EXITED or DISABLED
        entered_targets = GeometryStateMachine.VALID_TRANSITIONS[StrategyState.ENTERED]
        assert StrategyState.EXITED in entered_targets
        assert StrategyState.DISABLED in entered_targets

    def test_invalid_state_skip(self):
        """Test that skipping states is not allowed."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")

        # Start in DISABLED
        assert strategy.state == StrategyState.DISABLED

        # Cannot skip to ARMED (must go through SCANNING)
        result = strategy.transition_to(StrategyState.ARMED, "test")
        assert not result
        assert strategy.state == StrategyState.DISABLED

        # Cannot skip to ENTERED
        result = strategy.transition_to(StrategyState.ENTERED, "test")
        assert not result

    def test_valid_transition_succeeds(self):
        """Test that valid transitions succeed."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")

        # DISABLED -> SCANNING
        result = strategy.transition_to(StrategyState.SCANNING, "test")
        assert result
        assert strategy.state == StrategyState.SCANNING

        # SCANNING -> ARMED
        result = strategy.transition_to(StrategyState.ARMED, "test")
        assert result
        assert strategy.state == StrategyState.ARMED


# =============================================================================
# Geometry Strategy Tests
# =============================================================================

class TestGeometryStateMachine:
    """Tests for Geometry (Failed Hunt) strategy."""

    @pytest.fixture
    def geometry(self):
        """Create geometry strategy instance."""
        config = GeometryConfig(
            oi_elevation_zscore=2.0,
            funding_skew_threshold=0.0015,
            depth_asymmetry_ratio=1.5,
            oi_drop_threshold=0.05,
            armed_timeout_sec=120,
        )
        return GeometryStateMachine(symbol="BTC-PERP", config=config)

    def test_initial_state(self, geometry):
        """Test initial state is DISABLED."""
        assert geometry.state == StrategyState.DISABLED
        assert geometry.name == "geometry"
        assert geometry.symbol == "BTC-PERP"

    def test_enable_with_compatible_regime(self, geometry):
        """Test enabling with compatible regime."""
        result = geometry.enable("sideways")
        assert result
        assert geometry.state == StrategyState.SCANNING

    def test_enable_with_incompatible_regime(self, geometry):
        """Test enabling with incompatible regime."""
        result = geometry.enable("trending")
        assert not result
        assert geometry.state == StrategyState.DISABLED

    def test_arm_conditions_met(self, geometry):
        """Test arming when conditions are met."""
        geometry.enable("sideways")

        market_state = {
            'open_interest': 1000000,
            'oi_zscore': 2.5,  # Above threshold
            'funding_rate': 0.002,  # Skewed
            'bid_depth_1pct': 500000,
            'ask_depth_1pct': 300000,  # Asymmetric
            'mark_price': 50000,
            'liquidation_bands': {
                'long_liq_price': 49500,  # Within 1% of price
                'short_liq_price': 51000,
            },
        }

        setup = geometry._check_arm_conditions(market_state)

        assert setup is not None
        assert setup.is_valid
        assert setup.conditions_met['oi_elevated']
        assert setup.conditions_met['funding_skewed']
        assert setup.conditions_met['depth_asymmetric']

    def test_arm_conditions_not_met(self, geometry):
        """Test not arming when conditions are not met."""
        geometry.enable("sideways")

        market_state = {
            'open_interest': 1000000,
            'oi_zscore': 1.0,  # Below threshold
            'funding_rate': 0.0001,  # Not skewed
            'bid_depth_1pct': 500000,
            'ask_depth_1pct': 480000,  # Not asymmetric
            'mark_price': 50000,
            'liquidation_bands': {},
        }

        setup = geometry._check_arm_conditions(market_state)
        assert setup is None

    def test_trigger_on_oi_drop_and_flow_flip(self, geometry):
        """Test trigger when OI drops and flow flips."""
        geometry.enable("sideways")

        # Create setup
        geometry._setup = GeometrySetup(
            symbol="BTC-PERP",
            detected_at=datetime.now(),
            conditions_met={
                'oi_elevated': True,
                'funding_skewed': True,
                'depth_asymmetric': True,
                'near_liq_band': True,
            },
            oi_at_arm=1000000,
            hunt_direction='long',
        )
        geometry._state = StrategyState.ARMED

        # Simulate OI drop over time
        geometry._oi_history = [(datetime.now() - timedelta(seconds=5), 1000000)]

        market_state = {
            'open_interest': 940000,  # 6% drop
            'mark_price': 50000,
            'aggressive_buy_volume': 800,  # Flow flipped to buying
            'aggressive_sell_volume': 200,
        }

        trigger = geometry._check_trigger_conditions(market_state)

        assert trigger is not None
        assert trigger['triggered']
        assert trigger['entry_direction'] == 'short'  # Opposite of failed hunt

    def test_exit_on_target(self, geometry):
        """Test exit when target is reached."""
        geometry._entry_price = 50000
        geometry._entry_time = datetime.now() - timedelta(seconds=30)
        geometry._position_size = 1.0  # Long

        market_state = {
            'mark_price': 50300,  # 0.6% profit (above 0.5% target)
        }

        exit_result = geometry._check_exit_conditions(market_state)

        assert exit_result is not None
        assert exit_result['exit_type'] == 'target'
        assert exit_result['pnl_pct'] > 0

    def test_exit_on_stop(self, geometry):
        """Test exit when stop is hit."""
        geometry._entry_price = 50000
        geometry._entry_time = datetime.now() - timedelta(seconds=30)
        geometry._position_size = 1.0  # Long

        market_state = {
            'mark_price': 49800,  # 0.4% loss (above 0.3% stop)
        }

        exit_result = geometry._check_exit_conditions(market_state)

        assert exit_result is not None
        assert exit_result['exit_type'] == 'stop'
        assert exit_result['pnl_pct'] < 0

    def test_armed_timeout(self, geometry):
        """Test timeout in ARMED state."""
        geometry.enable("sideways")
        geometry.transition_to(StrategyState.ARMED, "test")

        # Simulate time passing
        geometry._state_entered_at = datetime.now() - timedelta(seconds=130)

        geometry._check_timeouts()

        assert geometry.state == StrategyState.SCANNING

    def test_cooldown_after_exit(self, geometry):
        """Test transition to cooldown after exit."""
        geometry.enable("sideways")
        geometry.transition_to(StrategyState.ARMED, "test")
        geometry.transition_to(StrategyState.ENTERED, "test")
        geometry.transition_to(StrategyState.EXITED, "test")

        # Evaluate should transition to cooldown
        geometry.evaluate({})

        assert geometry.state == StrategyState.COOLDOWN


# =============================================================================
# Kinematics Strategy Tests
# =============================================================================

class TestKinematicsStateMachine:
    """Tests for Kinematics (Post-Liq Inventory) strategy."""

    @pytest.fixture
    def kinematics(self):
        """Create kinematics strategy instance."""
        config = KinematicsConfig(
            oi_collapse_threshold=0.05,
            price_range_threshold=0.01,
            breakout_threshold=0.005,
        )
        return KinematicsStateMachine(symbol="ETH-PERP", config=config)

    def test_initial_state(self, kinematics):
        """Test initial state is DISABLED."""
        assert kinematics.state == StrategyState.DISABLED
        assert kinematics.name == "kinematics"

    def test_enable_in_any_regime(self, kinematics):
        """Test kinematics works in multiple regimes."""
        # Sideways
        result = kinematics.enable("sideways")
        assert result

        kinematics._state = StrategyState.DISABLED

        # Expansion
        result = kinematics.enable("expansion")
        assert result

    def test_setup_properties(self):
        """Test KinematicsSetup properties."""
        setup = KinematicsSetup(
            symbol="ETH-PERP",
            detected_at=datetime.now(),
            conditions_met={
                'oi_collapsed': True,
                'consolidated': True,
                'volume_elevated': True,
            },
            consolidation_high=3100,
            consolidation_low=3000,
        )

        assert setup.is_valid
        assert setup.consolidation_range_pct == pytest.approx(0.0333, rel=0.01)
        assert setup.consolidation_midpoint == 3050

    def test_breakout_trigger_up(self, kinematics):
        """Test breakout trigger to upside."""
        kinematics.enable("sideways")

        kinematics._setup = KinematicsSetup(
            symbol="ETH-PERP",
            detected_at=datetime.now(),
            conditions_met={
                'oi_collapsed': True,
                'consolidated': True,
                'volume_elevated': True,
            },
            consolidation_high=3100,
            consolidation_low=3000,
            consolidation_volume=100000,
        )
        kinematics._state = StrategyState.ARMED

        market_state = {
            'mark_price': 3125,  # Above 3100 + 0.5%
            'volume_1m': 5000,  # 3x consolidation rate
        }

        trigger = kinematics._check_trigger_conditions(market_state)

        assert trigger is not None
        assert trigger['entry_direction'] == 'long'

    def test_trailing_stop_exit(self, kinematics):
        """Test exit on trailing stop."""
        kinematics._entry_price = 3100
        kinematics._entry_time = datetime.now() - timedelta(seconds=60)
        kinematics._position_size = 1.0  # Long
        kinematics._highest_price = 3140  # 1.3% profit at peak

        market_state = {
            'mark_price': 3125,  # Pulled back 0.5% from high
        }

        exit_result = kinematics._check_exit_conditions(market_state)

        # Should hit trailing stop (0.4% from peak)
        assert exit_result is not None
        assert exit_result['exit_type'] == 'trailing_stop'


# =============================================================================
# Cascade Strategy Tests
# =============================================================================

class TestCascadeStateMachine:
    """Tests for Cascade (Sniper) strategy."""

    @pytest.fixture
    def cascade(self):
        """Create cascade strategy instance."""
        config = CascadeConfig(
            liq_band_distance_pct=0.02,
            oi_concentration_threshold=0.3,
            depth_thinning_threshold=0.50,
            price_velocity_threshold=0.001,
        )
        return CascadeStateMachine(symbol="BTC-PERP", config=config)

    def test_initial_state(self, cascade):
        """Test initial state is DISABLED."""
        assert cascade.state == StrategyState.DISABLED
        assert cascade.name == "cascade"

    def test_uses_pre_armed_state(self, cascade):
        """Test cascade uses PRE_ARMED state."""
        assert cascade._use_pre_armed()

    def test_pre_arm_on_liq_band_detection(self, cascade):
        """Test pre-arming when liq bands detected."""
        cascade.enable("expansion")

        market_state = {
            'mark_price': 50000,
            'open_interest': 1000000,
            'liquidation_bands': {
                'long_liq_price': 49500,  # 1% below
                'oi_at_long_liq': 400000,  # 40% of OI
            },
        }

        setup = cascade._check_arm_conditions(market_state)

        assert setup is not None
        assert setup.cascade_direction == 'long'
        assert setup.oi_concentration >= 0.3

    def test_pre_arm_to_arm_on_thinning(self, cascade):
        """Test advancing to ARMED when depth thins."""
        cascade.enable("expansion")

        cascade._setup = CascadeSetup(
            symbol="BTC-PERP",
            detected_at=datetime.now(),
            conditions_met={
                'liq_band_near': True,
                'oi_concentrated': True,
            },
            cascade_direction='long',
            initial_depth=500000,
        )
        cascade._state = StrategyState.PRE_ARMED

        # Add initial depth history entry
        cascade._depth_history.append((datetime.now() - timedelta(seconds=30), 500000))

        market_state = {
            'bid_depth_1pct': 200000,  # 60% thinning
        }

        result = cascade._check_pre_arm_to_arm(market_state)

        assert result
        assert cascade._setup.conditions_met['depth_thinned']

    def test_trigger_on_cascade_start(self, cascade):
        """Test trigger when cascade begins."""
        cascade.enable("expansion")

        cascade._setup = CascadeSetup(
            symbol="BTC-PERP",
            detected_at=datetime.now(),
            conditions_met={
                'liq_band_near': True,
                'oi_concentrated': True,
                'depth_thinned': True,
            },
            cascade_direction='long',
            target_liq_price=49500,
        )
        cascade._state = StrategyState.ARMED

        # Simulate price movement over time
        now = datetime.now()
        cascade._price_history = [
            (now - timedelta(seconds=5), 50000),
        ]

        market_state = {
            'mark_price': 49700,  # 0.6% drop in 5 sec = 0.12%/sec
            'volume_1m': 10000,
            'avg_volume_1m': 2000,  # 5x spike
        }

        trigger = cascade._check_trigger_conditions(market_state)

        assert trigger is not None
        assert trigger['entry_direction'] == 'short'  # Trading with cascade

    def test_exit_on_cascade_exhaustion(self, cascade):
        """Test exit when cascade exhausts."""
        cascade._entry_price = 50000
        cascade._entry_time = datetime.now() - timedelta(seconds=30)
        cascade._position_size = -1.0  # Short
        cascade._peak_velocity = 0.002  # High velocity at entry

        cascade._setup = CascadeSetup(
            symbol="BTC-PERP",
            detected_at=datetime.now(),
            conditions_met={},
            price_velocity=0.0005,  # Dropped to 25% of peak
        )

        market_state = {
            'mark_price': 49800,  # In profit
        }

        exit_result = cascade._check_exit_conditions(market_state)

        assert exit_result is not None
        assert exit_result['exit_type'] == 'exhaustion'

    def test_mandate_urgency(self, cascade):
        """Test cascade mandate has high urgency."""
        cascade._setup = CascadeSetup(
            symbol="BTC-PERP",
            detected_at=datetime.now(),
            conditions_met={},
            cascade_direction='long',
            target_liq_price=49500,
        )

        trigger_result = {
            'current_price': 49700,
            'entry_direction': 'short',
            'reason': 'Cascade detected',
        }

        mandate = cascade._calculate_mandate({}, trigger_result)

        assert mandate is not None
        assert mandate.urgency >= 0.9  # High urgency for cascade


# =============================================================================
# State Machine Integration Tests
# =============================================================================

class TestStateTransitionHistory:
    """Tests for transition history tracking."""

    def test_history_recorded(self):
        """Test that transitions are recorded."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")

        strategy.transition_to(StrategyState.SCANNING, "enable")
        strategy.transition_to(StrategyState.ARMED, "conditions met")

        history = strategy.get_history()

        assert len(history) == 2
        assert history[0]['from'] == 'disabled'
        assert history[0]['to'] == 'scanning'
        assert history[1]['from'] == 'scanning'
        assert history[1]['to'] == 'armed'

    def test_summary(self):
        """Test strategy summary."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")
        strategy.enable("sideways")

        summary = strategy.get_summary()

        assert summary['name'] == 'geometry'
        assert summary['symbol'] == 'BTC-PERP'
        assert summary['state'] == 'scanning'
        assert summary['trade_count'] == 0
        assert not summary['has_position']


class TestFillRecording:
    """Tests for fill recording."""

    def test_record_entry_fill(self):
        """Test recording entry fill."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")

        strategy.record_fill(price=50000, size=1.0, is_entry=True)

        assert strategy._entry_price == 50000
        assert strategy._position_size == 1.0
        assert strategy._entry_time is not None

    def test_set_stop(self):
        """Test setting stop price."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")

        strategy.set_stop(stop_price=49500)

        assert strategy._stop_price == 49500


class TestReset:
    """Tests for strategy reset."""

    def test_geometry_reset(self):
        """Test geometry strategy reset."""
        strategy = GeometryStateMachine(symbol="BTC-PERP")
        strategy.enable("sideways")
        strategy.transition_to(StrategyState.ARMED, "test")

        strategy.reset()

        assert strategy.state == StrategyState.DISABLED
        assert strategy._setup is None
        assert len(strategy._oi_history) == 0

    def test_kinematics_reset(self):
        """Test kinematics strategy reset."""
        strategy = KinematicsStateMachine(symbol="ETH-PERP")
        strategy.enable("sideways")

        strategy.reset()

        assert strategy.state == StrategyState.DISABLED
        assert strategy._highest_price == 0.0
        assert strategy._lowest_price == float('inf')

    def test_cascade_reset(self):
        """Test cascade strategy reset."""
        strategy = CascadeStateMachine(symbol="BTC-PERP")
        strategy.enable("expansion")

        strategy.reset()

        assert strategy.state == StrategyState.DISABLED
        assert strategy._peak_velocity == 0.0

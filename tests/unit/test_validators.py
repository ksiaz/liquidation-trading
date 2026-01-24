"""
Unit tests for HLP25 Validators.

Tests validation logic for each hypothesis.
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from analysis.validators import (
    WaveStructureValidator,
    AbsorptionValidator,
    OIConcentrationValidator,
    CrossAssetValidator,
    FundingSettlementValidator,
    ManipulationValidator,
    FundingLeadValidator,
    ValidationResult
)


# Mock cascade for testing
@dataclass(frozen=True)
class MockCascade:
    """Mock cascade for testing validators."""
    cascade_id: int
    coin: str
    start_ts: int
    end_ts: int
    oi_drop_pct: str
    liquidation_count: int
    wave_count: int
    outcome: Optional[str]
    price_at_start: str = "100.0"
    price_at_end: str = "90.0"
    price_5min_after: Optional[str] = "95.0"
    waves: tuple = tuple()


class TestValidationResult:
    """Test ValidationResult factory methods."""

    def test_validated_result(self):
        """Validated factory creates correct result."""
        result = ValidationResult.validated(
            name="Test",
            total=100,
            supporting=75,
            threshold=0.5
        )

        assert result.status == "VALIDATED"
        assert result.success_rate == 0.75
        assert result.calibrated_threshold == 0.5

    def test_failed_result(self):
        """Failed factory creates correct result."""
        result = ValidationResult.failed(
            name="Test",
            total=100,
            supporting=40
        )

        assert result.status == "FAILED"
        assert result.success_rate == 0.40
        assert result.calibrated_threshold is None

    def test_insufficient_data_result(self):
        """Insufficient data factory creates correct result."""
        result = ValidationResult.insufficient_data(
            name="Test",
            total=10,
            reason="Not enough events"
        )

        assert result.status == "INSUFFICIENT_DATA"
        assert result.success_rate == 0.0
        assert result.details['reason'] == "Not enough events"


class TestWaveStructureValidator:
    """Test wave structure validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds for testing."""
        return WaveStructureValidator(min_sample_size=5)

    def test_insufficient_data(self, validator):
        """Returns insufficient data when sample too small."""
        cascades = [
            MockCascade(i, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL")
            for i in range(3)  # Only 3 samples
        ]

        result = validator.validate(cascades)
        assert result.status == "INSUFFICIENT_DATA"

    def test_validated_when_majority_in_range(self, validator):
        """Validates when majority have 3-5 waves."""
        cascades = [
            MockCascade(1, "BTC", 1000, 1060, "10.0", 3, 3, "REVERSAL"),
            MockCascade(2, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(3, "BTC", 1000, 1060, "10.0", 3, 5, "REVERSAL"),
            MockCascade(4, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(5, "BTC", 1000, 1060, "10.0", 3, 3, "REVERSAL"),
        ]

        result = validator.validate(cascades)
        assert result.status == "VALIDATED"
        assert result.success_rate == 1.0

    def test_failed_when_outside_range(self, validator):
        """Fails when majority outside 3-5 range."""
        cascades = [
            MockCascade(1, "BTC", 1000, 1060, "10.0", 3, 1, "REVERSAL"),
            MockCascade(2, "BTC", 1000, 1060, "10.0", 3, 2, "REVERSAL"),
            MockCascade(3, "BTC", 1000, 1060, "10.0", 3, 7, "REVERSAL"),
            MockCascade(4, "BTC", 1000, 1060, "10.0", 3, 8, "REVERSAL"),
            MockCascade(5, "BTC", 1000, 1060, "10.0", 3, 3, "REVERSAL"),
        ]

        result = validator.validate(cascades)
        assert result.status == "FAILED"
        assert result.success_rate == 0.2  # Only 1/5 in range


class TestAbsorptionValidator:
    """Test absorption validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds."""
        return AbsorptionValidator(min_sample_size=5)

    def test_insufficient_data_no_outcomes(self, validator):
        """Returns insufficient data when no outcomes."""
        cascades = [
            MockCascade(i, "BTC", 1000, 1060, "10.0", 3, 4, None)
            for i in range(10)
        ]

        result = validator.validate(cascades)
        assert result.status == "INSUFFICIENT_DATA"

    def test_validated_when_reversals_dominate(self, validator):
        """Validates when reversals dominate continuations."""
        cascades = [
            MockCascade(1, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(2, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(3, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(4, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(5, "BTC", 1000, 1060, "10.0", 3, 4, "CONTINUATION"),
        ]

        result = validator.validate(cascades)
        assert result.status == "VALIDATED"
        assert result.details['reversal_count'] == 4

    def test_failed_when_continuations_dominate(self, validator):
        """Fails when continuations dominate."""
        cascades = [
            MockCascade(1, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),
            MockCascade(2, "BTC", 1000, 1060, "10.0", 3, 4, "CONTINUATION"),
            MockCascade(3, "BTC", 1000, 1060, "10.0", 3, 4, "CONTINUATION"),
            MockCascade(4, "BTC", 1000, 1060, "10.0", 3, 4, "CONTINUATION"),
            MockCascade(5, "BTC", 1000, 1060, "10.0", 3, 4, "CONTINUATION"),
        ]

        result = validator.validate(cascades)
        assert result.status == "FAILED"


class TestOIConcentrationValidator:
    """Test OI concentration validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds."""
        return OIConcentrationValidator(
            severity_threshold=15.0,
            min_sample_size=5
        )

    def test_insufficient_data(self, validator):
        """Returns insufficient data when sample too small."""
        cascades = [
            MockCascade(i, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL")
            for i in range(3)
        ]

        result = validator.validate(cascades)
        assert result.status == "INSUFFICIENT_DATA"

    def test_classifies_severe_cascades(self, validator):
        """Correctly classifies severe vs moderate cascades."""
        cascades = [
            MockCascade(1, "BTC", 1000, 1060, "20.0", 3, 4, "REVERSAL"),  # Severe
            MockCascade(2, "BTC", 1000, 1060, "18.0", 3, 4, "REVERSAL"),  # Severe
            MockCascade(3, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),  # Moderate
            MockCascade(4, "BTC", 1000, 1060, "8.0", 3, 4, "CONTINUATION"),  # Moderate
            MockCascade(5, "BTC", 1000, 1060, "25.0", 3, 4, "REVERSAL"),  # Severe
            MockCascade(6, "BTC", 1000, 1060, "16.0", 3, 4, "REVERSAL"),  # Severe
            MockCascade(7, "BTC", 1000, 1060, "17.0", 3, 4, "CONTINUATION"),  # Severe
        ]

        result = validator.validate(cascades)

        # Should have classified 5 severe, 2 moderate
        assert result.details['severe_cascade_count'] == 5
        assert result.details['moderate_cascade_count'] == 2


class TestCrossAssetValidator:
    """Test cross-asset validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds."""
        return CrossAssetValidator(min_sample_size=3)

    def test_insufficient_data_single_asset(self, validator):
        """Returns insufficient data with only one asset."""
        cascades = [
            MockCascade(i, "BTC", 1000 + i * 100, 1060 + i * 100, "10.0", 3, 4, "REVERSAL")
            for i in range(10)
        ]

        result = validator.validate(cascades)
        # Should fail or have insufficient data (no pairs)
        assert result.total_events < 3 or result.status in ("INSUFFICIENT_DATA", "FAILED")

    def test_finds_btc_eth_lead_pairs(self, validator):
        """Finds BTC->ETH lead pairs within window."""
        # BTC cascade at t=0, ETH cascade at t=60s (within 30-90s window)
        cascades = [
            MockCascade(1, "BTC", 1000000000000, 1010000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(2, "ETH", 1060000000000, 1070000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(3, "BTC", 2000000000000, 2010000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(4, "ETH", 2060000000000, 2070000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(5, "BTC", 3000000000000, 3010000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(6, "ETH", 3060000000000, 3070000000000, "10.0", 3, 4, "REVERSAL"),
        ]

        result = validator.validate(cascades)

        assert result.details['btc_cascade_count'] == 3
        assert result.details['eth_cascade_count'] == 3
        assert result.details['btc_eth_pairs_found'] >= 3

    def test_categorizes_alt_coins(self, validator):
        """Alt coins correctly identified (not BTC or ETH)."""
        cascades = [
            MockCascade(1, "BTC", 1000000000000, 1010000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(2, "ETH", 1060000000000, 1070000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(3, "SOL", 1150000000000, 1160000000000, "10.0", 3, 4, "REVERSAL"),
            MockCascade(4, "DOGE", 1200000000000, 1210000000000, "10.0", 3, 4, "REVERSAL"),
        ]

        result = validator.validate(cascades)

        assert 'SOL' in result.details['alt_coins']
        assert 'DOGE' in result.details['alt_coins']
        assert result.details['alt_cascade_count'] == 2


class TestFundingSettlementValidator:
    """Test funding settlement timing validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds."""
        return FundingSettlementValidator(
            pre_settlement_window_min=30,
            min_sample_size=5
        )

    def test_insufficient_data(self, validator):
        """Returns insufficient data when sample too small."""
        cascades = [
            MockCascade(i, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL")
            for i in range(3)
        ]

        result = validator.validate(cascades)
        assert result.status == "INSUFFICIENT_DATA"

    def test_minutes_to_settlement_calculation(self, validator):
        """Correctly calculates minutes to nearest settlement."""
        # 07:30 UTC -> 30 min to 08:00 settlement
        ts_0730 = 1700000000000000000  # Some timestamp
        # Just test the method works
        minutes = validator._minutes_to_nearest_settlement(ts_0730)
        assert isinstance(minutes, int)
        assert 0 <= minutes <= 240  # Max is 4 hours (halfway between settlements)

    def test_analyzes_cascade_proximity_to_settlement(self, validator):
        """Analyzes whether cascades cluster near settlements."""
        # Create cascades with various timestamps
        cascades = [
            MockCascade(i, "BTC", 1700000000000000000 + i * 3600_000_000_000,
                       1700000000060000000000 + i * 3600_000_000_000,
                       "10.0", 3, 4, "REVERSAL")
            for i in range(10)
        ]

        result = validator.validate(cascades)

        # Should have details about proximity
        assert 'cascades_near_settlement' in result.details
        assert 'cascades_far_from_settlement' in result.details


class TestManipulationValidator:
    """Test manipulation detection validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds."""
        return ManipulationValidator(
            max_organic_legs=2,
            min_sample_size=5
        )

    def test_insufficient_data(self, validator):
        """Returns insufficient data when sample too small."""
        cascades = [
            MockCascade(i, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL")
            for i in range(3)
        ]

        result = validator.validate(cascades)
        assert result.status == "INSUFFICIENT_DATA"

    def test_classifies_multi_leg_as_potential_manipulation(self, validator):
        """Cascades with >2 legs classified as potential manipulation."""
        cascades = [
            MockCascade(1, "BTC", 1000, 1060, "10.0", 3, 5, "REVERSAL"),  # 5 legs
            MockCascade(2, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL"),  # 4 legs
            MockCascade(3, "BTC", 1000, 1060, "10.0", 3, 3, "REVERSAL"),  # 3 legs
            MockCascade(4, "BTC", 1000, 1060, "10.0", 3, 2, "CONTINUATION"),  # 2 legs
            MockCascade(5, "BTC", 1000, 1060, "10.0", 3, 1, "REVERSAL"),  # 1 leg
        ]

        result = validator.validate(cascades)

        # 3 multi-leg (>2), 2 single-leg (<=2)
        assert result.details['multi_leg_cascades'] == 3
        assert result.details['single_leg_cascades'] == 2

    def test_count_down_legs(self, validator):
        """Correctly counts down-legs in OI series."""
        # Monotonic decrease = 1 leg
        oi_monotonic = [100, 95, 90, 85, 80]
        legs = validator._count_down_legs(oi_monotonic)
        assert legs == 1

        # Drop, pause, drop = 2 legs
        oi_two_legs = [100, 95, 90, 91, 90, 85, 80]
        legs = validator._count_down_legs(oi_two_legs)
        assert legs == 2

    def test_detect_mid_pause(self, validator):
        """Detects OI pause/increase mid-cascade."""
        # Monotonic decrease - no pause
        oi_no_pause = [100, 95, 90, 85, 80, 75, 70]
        assert validator._detect_mid_pause(oi_no_pause) is False

        # OI increase in middle
        oi_with_pause = [100, 95, 90, 92, 88, 83, 78]
        assert validator._detect_mid_pause(oi_with_pause) is True


class TestFundingLeadValidator:
    """Test cross-exchange funding lead validator."""

    @pytest.fixture
    def validator(self):
        """Create validator with reduced thresholds."""
        return FundingLeadValidator(
            divergence_threshold=0.0005,
            min_sample_size=5
        )

    def test_insufficient_data_without_binance_data(self, validator):
        """Returns insufficient data when Binance data missing."""
        cascades = [
            MockCascade(i, "BTC", 1000, 1060, "10.0", 3, 4, "REVERSAL")
            for i in range(10)
        ]

        result = validator.validate(cascades)
        assert result.status == "INSUFFICIENT_DATA"
        assert "Binance" in result.details['reason']

    def test_check_current_divergence_significant(self, validator):
        """Detects significant current divergence."""
        result = validator.check_current_divergence(
            binance_rate=0.001,  # 0.1%
            hl_rate=0.0003,      # 0.03%
            coin="BTC"
        )

        assert result is not None
        assert abs(result['divergence'] - 0.0007) < 1e-10  # 0.07% (float precision)
        assert result['expected_hl_direction'] == 'UP'

    def test_check_current_divergence_insignificant(self, validator):
        """Ignores insignificant divergence."""
        result = validator.check_current_divergence(
            binance_rate=0.0003,
            hl_rate=0.0002,  # Only 0.01% difference
            coin="BTC"
        )

        assert result is None  # Below threshold

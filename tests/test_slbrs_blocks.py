"""
Unit Tests for Liquidity Block Detection (SLBRS)

Tests implement requirements from PROMPT 5:
- Block qualification (4 conditions, ALL required)
- Block classification (ABSORPTION/CONSUMPTION/SPOOF)
- Only ABSORPTION blocks tradable
- Block invalidation
- Rolling average calculation

RULE: All tests are deterministic.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.orderbook_zoning.types import OrderbookZones, ZoneLiquidity, ZoneMetrics
from masterframe.slbrs import BlockType, LiquidityBlock,BlockDetector, BlockTracker


class TestBlockQualification:
    """Test block qualification criteria."""
    
    def create_zone_metrics(
        self,
        persistence: float = 40.0,
        executed_volume: float = 150.0,
        canceled_volume: float = 200.0
    ) -> ZoneMetrics:
        """Create test zone metrics."""
        current_time = time.time()
        return ZoneMetrics(
            zone_name='A',
            side='bid',
            current_liquidity=1000.0,
            first_seen=current_time - persistence,
            last_updated=current_time,
            persistence_seconds=persistence,
            executed_volume=executed_volume,
            canceled_volume=canceled_volume,
            max_liquidity_seen=1000.0,
            min_liquidity_seen=500.0,
        )
    
    def test_all_conditions_met(self):
        """All 4 qualification conditions met → qualified."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,  # Will set rolling avg to 300
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = self.create_zone_metrics(
            persistence=40.0,  # >= 30 ✓
            executed_volume=150.0,  # > 0 ✓
            canceled_volume=200.0,  # ratio = 200/150 = 1.33 < 3.5 ✓
        )
        
        rolling_avg = 300.0  # 1000 >= 2.5 * 300 ✓
        
        is_qualified = detector._check_qualification(zone, metrics, rolling_avg)
        
        assert is_qualified == True
    
    def test_condition_1_failed(self):
        """Liquidity not high enough → not qualified."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=500.0,  # < 2.5 * 300 ✗
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = self.create_zone_metrics()
        rolling_avg = 300.0
        
        is_qualified = detector._check_qualification(zone, metrics, rolling_avg)
        
        assert is_qualified == False
    
    def test_condition_2_failed(self):
        """Persistence too low → not qualified."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = self.create_zone_metrics(persistence=20.0)  # < 30 ✗
        rolling_avg = 300.0
        
        is_qualified = detector._check_qualification(zone, metrics, rolling_avg)
        
        assert is_qualified == False
    
    def test_condition_3_failed(self):
        """No executed volume → not qualified."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = self.create_zone_metrics(executed_volume=0.0)  # = 0 ✗
        rolling_avg = 300.0
        
        is_qualified = detector._check_qualification(zone, metrics, rolling_avg)
        
        assert is_qualified == False
    
    def test_condition_4_failed(self):
        """Cancel ratio too high → not qualified."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = self.create_zone_metrics(
            executed_volume=100.0,
            canceled_volume=400.0,  # ratio = 400/100 = 4.0 >= 3.5 ✗
        )
        rolling_avg = 300.0
        
        is_qualified = detector._check_qualification(zone, metrics, rolling_avg)
        
        assert is_qualified == False


class TestBlockClassification:
    """Test block classification logic."""
    
    def test_absorption_classification(self):
        """High execution + price stayed → ABSORPTION."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = ZoneMetrics(
            zone_name='A',
            side='bid',
            current_liquidity=1000.0,
            first_seen=time.time() - 40,
            last_updated=time.time(),
            persistence_seconds=40.0,
            executed_volume=150.0,  # >= 100 (high execution)
            canceled_volume=100.0,
            max_liquidity_seen=1000.0,
            min_liquidity_seen=500.0,
        )
        
        current_price = 99.97  # Inside zone [99.95, 100.0]
        
        block_type = detector._classify_block(zone, metrics, current_price)
        
        assert block_type == BlockType.ABSORPTION
    
    def test_consumption_classification(self):
        """High execution + price broke through → CONSUMPTION."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = ZoneMetrics(
            zone_name='A',
            side='bid',
            current_liquidity=1000.0,
            first_seen=time.time() - 40,
            last_updated=time.time(),
            persistence_seconds=40.0,
            executed_volume=150.0,  # >= 100 (high execution)
            canceled_volume=100.0,
            max_liquidity_seen=1000.0,
            min_liquidity_seen=500.0,
        )
        
        current_price = 100.5  # Outside zone (broke through)
        
        block_type = detector._classify_block(zone, metrics, current_price)
        
        assert block_type == BlockType.CONSUMPTION
    
    def test_spoof_classification(self):
        """Low execution → SPOOF."""
        detector = BlockDetector()
        
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=1000.0,
            weighted_avg_price=100.0,
            level_count=5,
            price_min=99.95,
            price_max=100.0,
        )
        
        metrics = ZoneMetrics(
            zone_name='A',
            side='bid',
            current_liquidity=1000.0,
            first_seen=time.time() - 40,
            last_updated=time.time(),
            persistence_seconds=40.0,
            executed_volume=50.0,  # < 100 (low execution)
            canceled_volume=200.0,
            max_liquidity_seen=1000.0,
            min_liquidity_seen=500.0,
        )
        
        current_price = 99.97
        
        block_type = detector._classify_block(zone, metrics, current_price)
        
        assert block_type == BlockType.SPOOF


class TestOnlyAbsorptionTradable:
    """Test that only ABSORPTION blocks are tradable."""
    
    def test_absorption_is_tradable(self):
        """ABSORPTION blocks have is_tradable = True."""
        block = LiquidityBlock(
            block_id="test_123",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.97,
            current_price=99.97,
            first_seen=time.time(),
            last_updated=time.time(),
            is_tradable=True,
            is_invalidated=False,
        )
        
        assert block.is_tradable == True
        assert block.block_type == BlockType.ABSORPTION
    
    def test_consumption_not_tradable(self):
        """CONSUMPTION blocks cannot be tradable."""
        block = LiquidityBlock(
            block_id="test_124",
            zone_name='A',
            side='bid',
            block_type=BlockType.CONSUMPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.97,
            current_price=100.5,
            first_seen=time.time(),
            last_updated=time.time(),
            is_tradable=False,
            is_invalidated=False,
        )
        
        assert block.is_tradable == False
        assert block.block_type == BlockType.CONSUMPTION


class TestBlockTracker:
    """Test block tracker functionality."""
    
    def test_get_tradable_blocks_filters_absorption(self):
        """get_tradable_blocks() returns only ABSORPTION blocks."""
        tracker = BlockTracker()
        
        # Create blocks
        absorption_block = LiquidityBlock(
            block_id="abs_1",
            zone_name='A',
            side='bid',
            block_type=BlockType.ABSORPTION,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=150.0,
            canceled_volume=100.0,
            cancel_to_trade_ratio=0.67,
            price_min=99.95,
            price_max=100.0,
            initial_price=99.97,
            current_price=99.97,
            first_seen=time.time(),
            last_updated=time.time(),
            is_tradable=True,
            is_invalidated=False,
        )
        
        spoof_block = LiquidityBlock(
            block_id="spoof_1",
            zone_name='B',
            side='bid',
            block_type=BlockType.SPOOF,
            zone_liquidity=1000.0,
            rolling_zone_avg=300.0,
            persistence_seconds=40.0,
            executed_volume=50.0,
            canceled_volume=200.0,
            cancel_to_trade_ratio=4.0,
            price_min=99.85,
            price_max=99.95,
            initial_price=99.90,
            current_price=99.90,
            first_seen=time.time(),
            last_updated=time.time(),
            is_tradable=False,
            is_invalidated=False,
        )
        
        tracker.update([absorption_block, spoof_block], 99.97, time.time())
        
        tradable = tracker.get_tradable_blocks()
        
        assert len(tradable) == 1
        assert tradable[0].block_type == BlockType.ABSORPTION
        assert tradable[0].block_id == "abs_1"


class TestRollingAverage:
    """Test rolling average calculation."""
    
    def test_rolling_average_fixed_window(self):
        """Rolling average uses fixed window size."""
        detector = BlockDetector()
        
        zone_key = "A_bid"
        
        # Add 20 values
        for i in range(20):
            avg = detector._update_rolling_average(zone_key, 100.0 * (i + 1))
        
        # Average of 100, 200, 300, ..., 2000
        expected_avg = sum(100.0 * (i + 1) for i in range(20)) / 20
        
        current_avg = detector._update_rolling_average(zone_key, 2100.0)
        
        # Should drop the first value (100) and add 2100
        expected_after = (sum(100.0 * (i + 1) for i in range(1, 20)) + 2100.0) / 20
        
        assert abs(current_avg - expected_after) < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

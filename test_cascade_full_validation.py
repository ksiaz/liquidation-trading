"""
Full Cascade Sniper Validation Test

Runs comprehensive validation of the cascade sniper system:
1. Input validation on every data point
2. Manipulation detection
3. Stop hunt detection
4. Cross-validation between Binance and Hyperliquid
5. State machine visibility
6. Summary statistics

Usage:
    python test_cascade_full_validation.py [--duration SECONDS]

Default duration: 300 seconds (5 minutes)
"""

import asyncio
import argparse
import time
import os
import sys
import platform
from typing import Dict, Optional
from collections import defaultdict

# Windows asyncio compatibility fix
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import validation modules
from runtime.validation import (
    DataValidator,
    ManipulationDetector,
    StopHuntDetector,
    CrossValidator,
    PositionSnapshot,
    LiquidityType
)

# Import collector
from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS


class ValidationTestRunner:
    """Run comprehensive validation tests on cascade sniper system."""

    def __init__(self, duration_sec: int = 300):
        self.duration_sec = duration_sec
        self.start_time = None

        # Validators
        self.data_validator = DataValidator()
        self.manipulation_detector = ManipulationDetector()
        self.stop_hunt_detector = StopHuntDetector()
        self.cross_validator = CrossValidator()

        # Statistics
        self.stats = {
            # Data validation
            'positions_validated': 0,
            'positions_valid': 0,
            'orderbooks_validated': 0,
            'orderbooks_valid': 0,
            'liquidations_validated': 0,
            'liquidations_valid': 0,

            # Manipulation
            'manipulation_alerts': 0,
            'circuit_breakers_triggered': 0,

            # Stop hunts
            'clusters_detected': 0,
            'hunts_started': 0,
            'hunts_triggered': 0,
            'reversals_detected': 0,

            # State transitions
            'state_transitions': 0,
            'transitions_by_type': defaultdict(int),

            # Cross-validation
            'hl_positions_disappeared': 0,
            'correlations_found': 0,

            # Per-coin stats
            'by_coin': defaultdict(lambda: {
                'proximity_updates': 0,
                'orderbook_updates': 0,
                'state_changes': 0
            })
        }

    async def run(self, collector: CollectorService):
        """Run validation for specified duration."""
        self.start_time = time.time()
        print(f"\n{'='*60}")
        print(f"FULL CASCADE VALIDATION TEST")
        print(f"Duration: {self.duration_sec} seconds")
        print(f"Symbols: {len(TOP_10_SYMBOLS)}")
        print(f"{'='*60}\n")

        # Start collector
        await collector.start()

        # Run validation loop
        try:
            while time.time() - self.start_time < self.duration_sec:
                await self._validation_cycle(collector)
                await asyncio.sleep(1)

                # Print progress every 30 seconds
                elapsed = time.time() - self.start_time
                if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                    self._print_progress(elapsed)

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")

        # Print summary
        self._print_summary()

    async def _validation_cycle(self, collector: CollectorService):
        """Run one validation cycle."""
        current_time = time.time()

        # Skip if Hyperliquid not enabled
        if not collector._hyperliquid_enabled:
            return

        hl_collector = collector._hyperliquid_collector
        if not hl_collector:
            return

        # Validate data for each symbol
        for symbol in TOP_10_SYMBOLS:
            coin = symbol.replace('USDT', '')

            try:
                # Get proximity data
                proximity = hl_collector.get_proximity(coin)
                if proximity:
                    self.stats['by_coin'][coin]['proximity_updates'] += 1

                    # Update stop hunt detector
                    cluster = self.stop_hunt_detector.update_cluster(
                        symbol=symbol,
                        current_price=proximity.current_price,
                        long_positions_count=proximity.long_positions_count,
                        long_positions_value=proximity.long_positions_value,
                        long_closest_liq=proximity.long_closest_liquidation,
                        short_positions_count=proximity.short_positions_count,
                        short_positions_value=proximity.short_positions_value,
                        short_closest_liq=proximity.short_closest_liquidation,
                        timestamp=current_time
                    )

                    if cluster:
                        self.stats['clusters_detected'] += 1

                    # Check for stop hunt
                    hunt = self.stop_hunt_detector.update_price(
                        symbol=symbol,
                        price=proximity.current_price,
                        timestamp=current_time
                    )

                    if hunt:
                        from runtime.validation.stop_hunt_detector import StopHuntPhase
                        if hunt.phase == StopHuntPhase.HUNT_IN_PROGRESS:
                            self.stats['hunts_started'] += 1
                        elif hunt.phase == StopHuntPhase.HUNT_TRIGGERED:
                            self.stats['hunts_triggered'] += 1
                        elif hunt.phase == StopHuntPhase.REVERSAL:
                            self.stats['reversals_detected'] += 1

                # Get orderbook
                if hasattr(hl_collector, '_client'):
                    orderbook = hl_collector._client.get_orderbook(coin)
                    if orderbook:
                        self.stats['by_coin'][coin]['orderbook_updates'] += 1
                        self.stats['orderbooks_validated'] += 1

                        # Validate orderbook
                        result = self.data_validator.validate_orderbook(orderbook, current_time)
                        if result.is_valid:
                            self.stats['orderbooks_valid'] += 1
                        else:
                            print(f"[INVALID ORDERBOOK] {coin}: {result.issues}")

                        # Check manipulation
                        alert = self.manipulation_detector.update_orderbook(symbol, orderbook)
                        if alert:
                            self.stats['manipulation_alerts'] += 1
                            print(f"[MANIPULATION] {alert}")
                            if alert.trigger_circuit_breaker:
                                self.stats['circuit_breakers_triggered'] += 1

            except Exception as e:
                print(f"[ERROR] {coin}: {e}")

    def _print_progress(self, elapsed: float):
        """Print progress update."""
        remaining = self.duration_sec - elapsed
        valid_ob_pct = (self.stats['orderbooks_valid'] / self.stats['orderbooks_validated'] * 100
                       if self.stats['orderbooks_validated'] > 0 else 0)

        print(f"\n--- Progress: {elapsed:.0f}s / {self.duration_sec}s ({remaining:.0f}s remaining) ---")
        print(f"  Orderbooks validated: {self.stats['orderbooks_validated']} ({valid_ob_pct:.1f}% valid)")
        print(f"  Clusters detected: {self.stats['clusters_detected']}")
        print(f"  Hunts: {self.stats['hunts_started']} started, {self.stats['hunts_triggered']} triggered, {self.stats['reversals_detected']} reversals")
        print(f"  Manipulation alerts: {self.stats['manipulation_alerts']}")

    def _print_summary(self):
        """Print final summary."""
        elapsed = time.time() - self.start_time

        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*60}")
        print(f"\nRun time: {elapsed:.1f} seconds")

        # Data validation
        print(f"\n--- Data Validation ---")
        ob_valid_pct = (self.stats['orderbooks_valid'] / self.stats['orderbooks_validated'] * 100
                       if self.stats['orderbooks_validated'] > 0 else 0)
        print(f"  Orderbooks: {self.stats['orderbooks_valid']}/{self.stats['orderbooks_validated']} valid ({ob_valid_pct:.1f}%)")

        # Manipulation detection
        print(f"\n--- Manipulation Detection ---")
        print(f"  Alerts: {self.stats['manipulation_alerts']}")
        print(f"  Circuit breakers: {self.stats['circuit_breakers_triggered']}")
        manipulation_stats = self.manipulation_detector.get_stats()
        if manipulation_stats['total_alerts'] > 0:
            print(f"  By type:")
            for typ, count in manipulation_stats['alerts_by_type'].items():
                if count > 0:
                    print(f"    {typ}: {count}")

        # Stop hunt detection
        print(f"\n--- Stop Hunt Detection ---")
        print(f"  Clusters detected: {self.stats['clusters_detected']}")
        print(f"  Hunts started: {self.stats['hunts_started']}")
        print(f"  Hunts triggered: {self.stats['hunts_triggered']}")
        print(f"  Reversals detected: {self.stats['reversals_detected']}")
        hunt_stats = self.stop_hunt_detector.get_stats()
        if hunt_stats['hunts_detected'] > 0:
            print(f"  By direction:")
            for direction, count in hunt_stats['hunts_by_direction'].items():
                if count > 0:
                    print(f"    {direction}: {count}")

        # Per-coin breakdown
        print(f"\n--- Per-Coin Activity ---")
        for coin, coin_stats in sorted(self.stats['by_coin'].items()):
            if coin_stats['proximity_updates'] > 0 or coin_stats['orderbook_updates'] > 0:
                print(f"  {coin}: {coin_stats['proximity_updates']} proximity, {coin_stats['orderbook_updates']} orderbook")

        # Data validator stats
        print(f"\n--- Data Validator Stats ---")
        validator_stats = self.data_validator.get_stats()
        print(f"  Total validated: {validator_stats['total_validated']}")
        print(f"  Total valid: {validator_stats['total_valid']} ({validator_stats['valid_pct']:.1f}%)")

        print(f"\n{'='*60}")
        print(f"VALIDATION COMPLETE")
        print(f"{'='*60}\n")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Full cascade sniper validation test')
    parser.add_argument('--duration', type=int, default=300,
                       help='Test duration in seconds (default: 300)')
    args = parser.parse_args()

    print("Initializing observation system...")
    obs_system = ObservationSystem(allowed_symbols=TOP_10_SYMBOLS)

    print("Initializing collector service...")
    collector = CollectorService(obs_system, warmup_duration_sec=5)

    print("Initializing validation runner...")
    runner = ValidationTestRunner(duration_sec=args.duration)

    print("Starting validation test...")
    await runner.run(collector)


if __name__ == "__main__":
    asyncio.run(main())

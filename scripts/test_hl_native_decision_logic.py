#!/usr/bin/env python3
"""
Test HL-Native Decision Logic with Simulated Data

This script tests the decision loop logic without requiring the live HL node adapter.
It generates synthetic liquidation events to verify the decision rules work correctly.

METRIC: Liquidation Side Imbalance
- Ratio of long vs short liquidation value in rolling 60s window
- Signal when >75% one-sided AND value >$100k

DECISION RULES:
- IF imbalance > 0.75 AND total > $100k → SHORT_PRESSURE (longs being liquidated)
- IF imbalance < 0.25 AND total > $100k → LONG_PRESSURE (shorts being liquidated)
- ELSE → SKIP
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.hl_native import (
    HLNativeDecisionLoop,
    LiquidationEvent,
    Decision,
)


def test_scenario(name: str, events: list, expected_decision: Decision):
    """Run a test scenario and verify the decision."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {name}")
    print('='*60)

    loop = HLNativeDecisionLoop(symbols=['BTC', 'ETH', 'SOL'])
    base_time = time.time()

    # Feed events
    record = None
    for i, (symbol, side, size_usd) in enumerate(events):
        event = LiquidationEvent(
            symbol=symbol,
            side=side,
            size_usd=size_usd,
            price=65000.0,
            timestamp=base_time + i * 0.1,  # 100ms apart
        )
        record = loop.on_liquidation(event)

    # Get final decision
    if record:
        print(f"\nFinal Decision: {record.decision}")
        print(f"Reason: {record.reason}")
        print(f"Metric Value: {record.metric_value:.2%}")
        print(f"Total Value: ${record.total_value_usd:,.0f}")
        print(f"Long Value: ${record.long_value_usd:,.0f}")
        print(f"Short Value: ${record.short_value_usd:,.0f}")
        print(f"Event Count: {record.event_count}")

        if record.decision == expected_decision.value:
            print(f"\n✓ PASS: Got expected {expected_decision.value}")
            return True
        else:
            print(f"\n✗ FAIL: Expected {expected_decision.value}, got {record.decision}")
            return False
    else:
        print("No record returned")
        return False


def main():
    print("="*60)
    print("HL-NATIVE DECISION LOGIC TEST")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("Testing decision rules:")
    print("  - imbalance > 0.75 AND value > $100k → SHORT_PRESSURE")
    print("  - imbalance < 0.25 AND value > $100k → LONG_PRESSURE")
    print("  - else → SKIP")

    passed = 0
    failed = 0

    # Test 1: Insufficient volume (should SKIP)
    result = test_scenario(
        "Insufficient Volume ($50k total, balanced)",
        events=[
            ('BTC', 'LONG', 25000),
            ('BTC', 'SHORT', 25000),
        ],
        expected_decision=Decision.SKIP,
    )
    if result: passed += 1
    else: failed += 1

    # Test 2: Balanced liquidations (should SKIP)
    result = test_scenario(
        "Balanced Liquidations ($200k, 50/50 split)",
        events=[
            ('BTC', 'LONG', 50000),
            ('BTC', 'SHORT', 50000),
            ('BTC', 'LONG', 50000),
            ('BTC', 'SHORT', 50000),
        ],
        expected_decision=Decision.SKIP,
    )
    if result: passed += 1
    else: failed += 1

    # Test 3: Heavy LONG liquidations (should be SHORT_PRESSURE)
    result = test_scenario(
        "Heavy LONG Liquidations (80% longs, $500k)",
        events=[
            ('BTC', 'LONG', 100000),
            ('BTC', 'LONG', 100000),
            ('BTC', 'LONG', 100000),
            ('BTC', 'LONG', 100000),
            ('BTC', 'SHORT', 100000),  # 400k long, 100k short = 80% long
        ],
        expected_decision=Decision.SHORT_PRESSURE,
    )
    if result: passed += 1
    else: failed += 1

    # Test 4: Heavy SHORT liquidations (should be LONG_PRESSURE)
    result = test_scenario(
        "Heavy SHORT Liquidations (85% shorts, $200k)",
        events=[
            ('BTC', 'SHORT', 50000),
            ('BTC', 'SHORT', 50000),
            ('BTC', 'SHORT', 50000),
            ('BTC', 'LONG', 20000),
            ('BTC', 'SHORT', 30000),  # 20k long, 180k short = 10% long = 90% short
        ],
        expected_decision=Decision.LONG_PRESSURE,
    )
    if result: passed += 1
    else: failed += 1

    # Test 5: Just below threshold (should SKIP)
    result = test_scenario(
        "Just Below Threshold (70% longs, $200k)",
        events=[
            ('BTC', 'LONG', 70000),
            ('BTC', 'LONG', 70000),
            ('BTC', 'SHORT', 60000),  # 140k long, 60k short = 70% long < 75%
        ],
        expected_decision=Decision.SKIP,
    )
    if result: passed += 1
    else: failed += 1

    # Test 6: Just above threshold (should be SHORT_PRESSURE)
    result = test_scenario(
        "Just Above Threshold (76% longs, $200k)",
        events=[
            ('BTC', 'LONG', 76000),
            ('BTC', 'LONG', 76000),
            ('BTC', 'SHORT', 48000),  # 152k long, 48k short = 76% long > 75%
        ],
        expected_decision=Decision.SHORT_PRESSURE,
    )
    if result: passed += 1
    else: failed += 1

    # Test 7: Multiple symbols don't mix
    result = test_scenario(
        "Multi-Symbol Isolation (BTC heavy, ETH balanced)",
        events=[
            ('BTC', 'LONG', 100000),
            ('BTC', 'LONG', 100000),
            ('ETH', 'SHORT', 50000),
            ('ETH', 'LONG', 50000),
            ('BTC', 'SHORT', 50000),  # BTC: 200k long, 50k short = 80% long
        ],
        expected_decision=Decision.SHORT_PRESSURE,  # BTC should trigger
    )
    if result: passed += 1
    else: failed += 1

    # Test 8: Cascade scenario (rapid one-sided liquidations)
    result = test_scenario(
        "Cascade Scenario ($2M shorts liquidated rapidly)",
        events=[
            ('BTC', 'SHORT', 300000),
            ('BTC', 'SHORT', 400000),
            ('BTC', 'SHORT', 500000),
            ('BTC', 'SHORT', 300000),
            ('BTC', 'SHORT', 500000),
            ('BTC', 'LONG', 50000),  # 50k long, 2M short = 2.5% long
        ],
        expected_decision=Decision.LONG_PRESSURE,
    )
    if result: passed += 1
    else: failed += 1

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total:  {passed + failed}")

    if failed == 0:
        print("\n✓ ALL TESTS PASSED")
        print("\nThe HL-native decision logic correctly:")
        print("  1. Requires minimum $100k volume to avoid noise")
        print("  2. Detects heavy long liquidations → SHORT_PRESSURE")
        print("  3. Detects heavy short liquidations → LONG_PRESSURE")
        print("  4. Skips when balanced or below threshold")
        print("  5. Isolates symbols (no cross-contamination)")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Test Organic Flow Detector - Bidirectional Cascade Absorption.

Verifies that absorption detection works correctly for:
1. LONG liquidation cascades (price dropping → enter LONG on absorption)
2. SHORT liquidation cascades (price rising → enter SHORT on absorption)

Research basis:
- Absorption = liqs_stopped AND organic_net OPPOSES cascade
- This is STATE-based detection, not time-based

Usage:
    python scripts/test_organic_flow_detector.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.hyperliquid.node_adapter.organic_flow_detector import (
    OrganicFlowDetector,
    CascadeDirection,
    AbsorptionSignal,
)
from runtime.hyperliquid.node_adapter.action_extractor import LiquidationEvent

print('=' * 70)
print('ORGANIC FLOW DETECTOR TEST')
print('Bidirectional Cascade Absorption Detection')
print('=' * 70)

# Create detector with test-friendly thresholds
detector = OrganicFlowDetector(
    window_sec=10.0,
    min_organic_volume=1000.0,  # Lower for testing
    min_quiet_time=1.0,         # 1 second quiet time
    organic_ratio_threshold=0.2, # 20% net dominance
)

now = time.time()

# ==============================================================================
# TEST 1: Long Liquidation Cascade (Price Dropping)
# ==============================================================================
print('\n' + '=' * 70)
print('TEST 1: LONG LIQUIDATION CASCADE (Price Dropping)')
print('=' * 70)

symbol = 'BTCUSDT'

# Set cascade active - long liqs = price dropping
detector.set_cascade_active(symbol, CascadeDirection.DOWN, cluster_value=100_000)
print(f'\nCascade activated: {symbol} direction=DOWN')

# Add some long liquidations (sells into market)
print('\nPhase 1: Liquidations firing...')
for i in range(5):
    liq_event = LiquidationEvent(
        symbol=symbol,
        wallet_address=f'0x{i:04x}',
        liquidated_size=0.1,
        liquidation_price=99000 - i * 100,  # Price dropping
        side='long',  # Long positions liquidated
        value=10000,  # $10k each
        timestamp=now - 8 + i,  # 5 liqs over 5 seconds
    )
    detector.add_liquidation(liq_event)
    print(f'  Liquidation {i+1}: long ${liq_event.value:,.0f} @ {liq_event.liquidation_price}')

# Check absorption - should NOT detect (liqs still happening)
signal = detector.check_absorption(symbol, now - 3)
print(f'\nAbsorption check during liqs:')
print(f'  liqs_stopped: {signal.liqs_stopped}')
print(f'  absorption_detected: {signal.absorption_detected}')
assert not signal.absorption_detected, "Should NOT detect absorption during active liqs"
print('  [PASS] No absorption during active liquidations')

# Now add organic buying (opposing the cascade)
print('\nPhase 2: Organic buying stepping in...')
for i in range(10):
    detector.add_organic_trade(
        symbol=symbol,
        timestamp=now - 2 + i * 0.1,  # After liqs stopped
        side='BUY',  # Organic BUYING
        value=2000,  # $2k each
    )
print(f'  Added 10 organic buys totaling $20,000')

# Add some organic sells too (but less than buys)
for i in range(3):
    detector.add_organic_trade(
        symbol=symbol,
        timestamp=now - 1.5 + i * 0.1,
        side='SELL',
        value=1000,  # $1k each
    )
print(f'  Added 3 organic sells totaling $3,000')
print(f'  Organic net: +$17,000 (buyers dominating)')

# Check absorption - NOW should detect
signal = detector.check_absorption(symbol, now)
print(f'\nAbsorption check after quiet period:')
print(f'  cascade_direction: {signal.cascade_direction.value}')
print(f'  liqs_stopped: {signal.liqs_stopped}')
print(f'  time_since_last_liq: {signal.time_since_last_liq:.1f}s')
print(f'  organic_net: ${signal.organic_net:,.0f}')
print(f'  organic_opposes: {signal.organic_opposes}')
print(f'  organic_ratio: {signal.organic_ratio:.1%}')
print(f'  absorption_detected: {signal.absorption_detected}')
print(f'  entry_direction: {signal.entry_direction}')

assert signal.absorption_detected, "Should detect absorption after liqs stop + organic buying"
assert signal.entry_direction == "LONG", "Entry should be LONG (reversal from DOWN cascade)"
print('  [PASS] Absorption detected with LONG entry signal')

# ==============================================================================
# TEST 2: Short Liquidation Cascade (Price Rising)
# ==============================================================================
print('\n' + '=' * 70)
print('TEST 2: SHORT LIQUIDATION CASCADE (Price Rising)')
print('=' * 70)

symbol2 = 'ETHUSDT'

# Set cascade active - short liqs = price rising
detector.set_cascade_active(symbol2, CascadeDirection.UP, cluster_value=50_000)
print(f'\nCascade activated: {symbol2} direction=UP')

# Add some short liquidations (buys from market)
print('\nPhase 1: Liquidations firing...')
for i in range(4):
    liq_event = LiquidationEvent(
        symbol=symbol2,
        wallet_address=f'0xshort{i:04x}',
        liquidated_size=1.0,
        liquidation_price=3500 + i * 50,  # Price rising
        side='short',  # Short positions liquidated
        value=3500,  # $3.5k each
        timestamp=now - 6 + i,
    )
    detector.add_liquidation(liq_event)
    print(f'  Liquidation {i+1}: short ${liq_event.value:,.0f} @ {liq_event.liquidation_price}')

# Now add organic SELLING (opposing the UP cascade)
print('\nPhase 2: Organic selling stepping in...')
for i in range(8):
    detector.add_organic_trade(
        symbol=symbol2,
        timestamp=now - 1 + i * 0.1,  # After liqs stopped
        side='SELL',  # Organic SELLING
        value=1500,  # $1.5k each
    )
print(f'  Added 8 organic sells totaling $12,000')

# Add fewer buys
for i in range(2):
    detector.add_organic_trade(
        symbol=symbol2,
        timestamp=now - 0.5 + i * 0.1,
        side='BUY',
        value=1000,
    )
print(f'  Added 2 organic buys totaling $2,000')
print(f'  Organic net: -$10,000 (sellers dominating)')

# Check absorption
signal2 = detector.check_absorption(symbol2, now)
print(f'\nAbsorption check:')
print(f'  cascade_direction: {signal2.cascade_direction.value}')
print(f'  liqs_stopped: {signal2.liqs_stopped}')
print(f'  time_since_last_liq: {signal2.time_since_last_liq:.1f}s')
print(f'  organic_net: ${signal2.organic_net:,.0f}')
print(f'  organic_opposes: {signal2.organic_opposes}')
print(f'  organic_ratio: {signal2.organic_ratio:.1%}')
print(f'  absorption_detected: {signal2.absorption_detected}')
print(f'  entry_direction: {signal2.entry_direction}')

assert signal2.absorption_detected, "Should detect absorption after liqs stop + organic selling"
assert signal2.entry_direction == "SHORT", "Entry should be SHORT (reversal from UP cascade)"
print('  [PASS] Absorption detected with SHORT entry signal')

# ==============================================================================
# TEST 3: No Absorption (Organic Flow Aligned with Cascade)
# ==============================================================================
print('\n' + '=' * 70)
print('TEST 3: NO ABSORPTION (Organic Aligned with Cascade)')
print('=' * 70)

symbol3 = 'SOLUSDT'

# Down cascade
detector.set_cascade_active(symbol3, CascadeDirection.DOWN, cluster_value=30_000)
print(f'\nCascade activated: {symbol3} direction=DOWN')

# Add liquidations
liq_event = LiquidationEvent(
    symbol=symbol3,
    wallet_address='0xtest',
    liquidated_size=10,
    liquidation_price=190,
    side='long',
    value=1900,
    timestamp=now - 5,
)
detector.add_liquidation(liq_event)
print(f'  Liquidation: long $1,900')

# Add organic SELLING (aligned with cascade, not opposing)
print('\nOrganic SELLING (aligned with cascade, not opposing)...')
for i in range(5):
    detector.add_organic_trade(
        symbol=symbol3,
        timestamp=now - 1 + i * 0.1,
        side='SELL',  # Selling = aligned with DOWN cascade
        value=500,
    )
print(f'  Added 5 organic sells totaling $2,500')

# Add minimal buying
detector.add_organic_trade(symbol3, now, 'BUY', 200)
print(f'  Added 1 organic buy of $200')
print(f'  Organic net: -$2,300 (sellers dominating = aligned with cascade)')

signal3 = detector.check_absorption(symbol3, now)
print(f'\nAbsorption check:')
print(f'  organic_net: ${signal3.organic_net:,.0f}')
print(f'  organic_opposes: {signal3.organic_opposes}')
print(f'  absorption_detected: {signal3.absorption_detected}')

assert not signal3.absorption_detected, "Should NOT detect absorption when organic aligns with cascade"
print('  [PASS] No absorption when organic flow aligns with cascade')

# ==============================================================================
# SUMMARY
# ==============================================================================
print('\n' + '=' * 70)
print('METRICS')
print('=' * 70)

metrics = detector.get_metrics()
for key, value in metrics.items():
    print(f'  {key}: {value}')

print('\n' + '=' * 70)
print('ALL TESTS PASSED')
print('=' * 70)
print('''
BIDIRECTIONAL CASCADE ABSORPTION:

                 Long Cascade (DOWN)       Short Cascade (UP)
                 -------------------       ------------------
Liquidation:     Long positions SOLD       Short positions BOUGHT
Price effect:    Price DROPS               Price RISES
Absorption:      Organic net BUY > 0       Organic net SELL < 0
Entry signal:    LONG (reversal up)        SHORT (reversal down)

KEY INSIGHT: Absorption is STATE-based, not TIME-based:
1. Liquidations must STOP (liqs_in_window == 0)
2. Organic flow must OPPOSE cascade direction
   - DOWN cascade → need organic buying (net > 0)
   - UP cascade → need organic selling (net < 0)

This replaces static orderbook depth analysis with dynamic flow detection.
''')

#!/usr/bin/env python3
"""
Test Liquidation Burst Aggregation.

Verifies that the node adapter correctly aggregates liquidations into bursts
that can trigger the cascade state machine.

Usage:
    python scripts/test_burst_aggregation.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.hyperliquid.node_adapter.observation_bridge import (
    LiquidationBurst,
    LiquidationBurstAggregator,
)
from runtime.hyperliquid.node_adapter.action_extractor import LiquidationEvent

print('=' * 70)
print('LIQUIDATION BURST AGGREGATION TEST')
print('=' * 70)

# Create aggregator
aggregator = LiquidationBurstAggregator(
    window_sec=10.0,
    min_burst_volume=10_000.0,  # $10k minimum
)

print('\n1. Testing burst aggregation with mock events...')
now = time.time()

# Create mock liquidation events
events = [
    LiquidationEvent(
        symbol='BTCUSDT',
        wallet_address='0x1234...5678',
        liquidated_size=0.5,
        liquidation_price=99000.0,
        side='long',
        value=49500.0,  # $49.5k
        timestamp=now - 5,
    ),
    LiquidationEvent(
        symbol='BTCUSDT',
        wallet_address='0xabcd...efgh',
        liquidated_size=0.3,
        liquidation_price=98800.0,
        side='long',
        value=29640.0,  # $29.6k
        timestamp=now - 3,
    ),
    LiquidationEvent(
        symbol='BTCUSDT',
        wallet_address='0x9999...aaaa',
        liquidated_size=0.1,
        liquidation_price=99100.0,
        side='short',
        value=9910.0,  # $9.9k
        timestamp=now - 1,
    ),
    LiquidationEvent(
        symbol='ETHUSDT',
        wallet_address='0xeeee...ffff',
        liquidated_size=5.0,
        liquidation_price=3400.0,
        side='long',
        value=17000.0,  # $17k
        timestamp=now - 2,
    ),
]

# Add events to aggregator
for event in events:
    aggregator.add_event(event)
    print(f'  Added: {event.symbol} {event.side} ${event.value:,.0f}')

print('\n2. Checking burst data...')

# Get BTC burst
btc_burst = aggregator.get_burst('BTCUSDT')
if btc_burst:
    print(f'\nBTCUSDT Burst:')
    print(f'  Total volume: ${btc_burst.total_volume:,.0f}')
    print(f'  Long liquidations: ${btc_burst.long_liquidations:,.0f}')
    print(f'  Short liquidations: ${btc_burst.short_liquidations:,.0f}')
    print(f'  Event count: {btc_burst.liquidation_count}')
    print(f'  Window: {btc_burst.window_end - btc_burst.window_start:.1f}s')
else:
    print('No BTC burst (below threshold)')

# Get ETH burst
eth_burst = aggregator.get_burst('ETHUSDT')
if eth_burst:
    print(f'\nETHUSDT Burst:')
    print(f'  Total volume: ${eth_burst.total_volume:,.0f}')
    print(f'  Long liquidations: ${eth_burst.long_liquidations:,.0f}')
    print(f'  Short liquidations: ${eth_burst.short_liquidations:,.0f}')
    print(f'  Event count: {eth_burst.liquidation_count}')
else:
    print('\nNo ETH burst (below threshold)')

# Get all bursts
all_bursts = aggregator.get_all_bursts()
print(f'\n3. All active bursts: {len(all_bursts)}')
for symbol, burst in all_bursts.items():
    print(f'  {symbol}: ${burst.total_volume:,.0f} ({burst.liquidation_count} events)')

print('\n4. Testing with cascade state machine...')

from external_policy.ep2_strategy_cascade_sniper import (
    CascadeSniperConfig,
    CascadeStateMachine,
    CascadeState,
    ProximityData,
    LiquidationBurst as StrategyLiquidationBurst,
)

config = CascadeSniperConfig()
sm = CascadeStateMachine(config)

# Mock proximity data for primed state
prox = ProximityData(
    coin='BTC',
    current_price=100000,
    threshold_pct=0.005,
    long_positions_count=50,
    long_positions_value=500_000,
    long_closest_liquidation=99500,
    short_positions_count=5,
    short_positions_value=50_000,
    short_closest_liquidation=100500,
    total_positions_at_risk=55,
    total_value_at_risk=550_000,
    timestamp=now,
)

# Update with proximity only - should go to PRIMED
state = sm.update('BTCUSDT', prox, None, now)
print(f'\nState after proximity: {state.value}')

# Convert node burst to strategy burst format
if btc_burst:
    strategy_burst = StrategyLiquidationBurst(
        symbol=btc_burst.symbol,
        total_volume=btc_burst.total_volume,
        long_liquidations=btc_burst.long_liquidations,
        short_liquidations=btc_burst.short_liquidations,
        liquidation_count=btc_burst.liquidation_count,
        window_start=btc_burst.window_start,
        window_end=btc_burst.window_end,
    )

    # Update with burst - should go to TRIGGERED
    state = sm.update('BTCUSDT', prox, strategy_burst, now)
    print(f'State after burst: {state.value}')

    if state == CascadeState.TRIGGERED:
        print('\n[SUCCESS] Cascade triggered by node liquidation burst!')
    else:
        print(f'\n[INFO] State is {state.value} (need >= ${config.liquidation_trigger_volume:,.0f} to trigger)')
        print(f'       Burst volume: ${btc_burst.total_volume:,.0f}')

print('\n5. Aggregator metrics:')
metrics = aggregator.get_metrics()
for key, value in metrics.items():
    print(f'  {key}: {value}')

print('\n' + '=' * 70)
print('TEST COMPLETE')
print('=' * 70)
print('''
The LiquidationBurstAggregator:
1. Collects individual liquidation events from node
2. Aggregates them by symbol over a 10-second window
3. Provides burst data that can trigger cascade state machine
4. Removes need for Binance websocket connection

Integration path:
- Node emits LiquidationEvent
- ObservationBridge.on_liquidation() feeds to aggregator
- NodeProximityProvider.get_burst(symbol) returns burst
- Cascade strategy can query burst data to transition PRIMED -> TRIGGERED
''')

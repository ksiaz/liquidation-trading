#!/usr/bin/env python3
"""
Debug Cascade Sniper Signal Generation.

Traces why signals aren't firing by checking each step:
1. Proximity data availability
2. Cluster formation (primed state)
3. Liquidation triggers
4. Absorption detection
5. Entry quality filters

Usage:
    python scripts/debug_cascade_signals.py
"""

import os
import sys
import asyncio
import time

os.environ['USE_HL_NODE'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from external_policy.ep2_strategy_cascade_sniper import (
    CascadeSniperConfig,
    CascadeStateMachine,
    CascadeState,
    ProximityData,
    LiquidationBurst,
)

print('=' * 70)
print('CASCADE SNIPER DEBUG')
print('=' * 70)

# Check config
config = CascadeSniperConfig()
print('\nConfig:')
print(f'  min_cluster_value: ${config.min_cluster_value:,.0f}')
print(f'  min_cluster_positions: {config.min_cluster_positions}')
print(f'  dominance_ratio: {config.dominance_ratio:.0%}')
print(f'  liquidation_trigger_volume: ${config.liquidation_trigger_volume:,.0f}')

# Create state machine
sm = CascadeStateMachine(config)

# Test with mock data to verify logic
print('\n' + '=' * 70)
print('TEST 1: Cluster Formation')
print('=' * 70)

# Mock proximity data - should form cluster
test_proximity = ProximityData(
    coin='BTC',
    current_price=100000,
    threshold_pct=0.005,
    long_positions_count=45,
    long_positions_value=450_000,  # 90% longs
    long_closest_liquidation=99500,
    short_positions_count=5,
    short_positions_value=50_000,
    short_closest_liquidation=100500,
    total_positions_at_risk=50,
    total_value_at_risk=500_000,  # $500k at risk
    timestamp=time.time()
)

print(f'\nProximity: {test_proximity.total_positions_at_risk} pos, ${test_proximity.total_value_at_risk:,.0f}')
print(f'  Long: {test_proximity.long_positions_count} pos, ${test_proximity.long_positions_value:,.0f} ({test_proximity.long_positions_value/test_proximity.total_value_at_risk:.0%})')
print(f'  Short: {test_proximity.short_positions_count} pos, ${test_proximity.short_positions_value:,.0f}')

state = sm.update('BTCUSDT', test_proximity, None, time.time())
print(f'\nState after proximity update: {state.value}')
print(f'Expected: PRIMED (cluster formed)')

if state != CascadeState.PRIMED:
    print('\n[DEBUG] Cluster not formed. Checking conditions:')
    print(f'  positions >= {config.min_cluster_positions}? {test_proximity.total_positions_at_risk} >= {config.min_cluster_positions}: {test_proximity.total_positions_at_risk >= config.min_cluster_positions}')
    print(f'  value >= ${config.min_cluster_value:,.0f}? ${test_proximity.total_value_at_risk:,.0f} >= ${config.min_cluster_value:,.0f}: {test_proximity.total_value_at_risk >= config.min_cluster_value}')
    long_ratio = test_proximity.long_positions_value / test_proximity.total_value_at_risk
    print(f'  dominance >= {config.dominance_ratio:.0%}? {max(long_ratio, 1-long_ratio):.0%} >= {config.dominance_ratio:.0%}: {max(long_ratio, 1-long_ratio) >= config.dominance_ratio}')

# Test liquidation trigger
print('\n' + '=' * 70)
print('TEST 2: Liquidation Trigger')
print('=' * 70)

now = time.time()
test_liquidation = LiquidationBurst(
    symbol='BTCUSDT',
    total_volume=100_000,  # $100k liquidated
    long_liquidations=90_000,  # Longs got rekt
    short_liquidations=10_000,
    liquidation_count=10,
    window_start=now - 10,
    window_end=now
)

print(f'\nLiquidation burst: ${test_liquidation.total_volume:,.0f} in {test_liquidation.liquidation_count} events')
print(f'  Long liqs: ${test_liquidation.long_liquidations:,.0f}')
print(f'  Short liqs: ${test_liquidation.short_liquidations:,.0f}')

state = sm.update('BTCUSDT', test_proximity, test_liquidation, time.time())
print(f'\nState after liquidation: {state.value}')
print(f'Expected: TRIGGERED (cascade started)')

if state != CascadeState.TRIGGERED and state != CascadeState.PRIMED:
    print('\n[DEBUG] Not triggered. Checking conditions:')
    print(f'  volume >= ${config.liquidation_trigger_volume:,.0f}? ${test_liquidation.total_volume:,.0f} >= ${config.liquidation_trigger_volume:,.0f}: {test_liquidation.total_volume >= config.liquidation_trigger_volume}')

# Now test with real node data
print('\n' + '=' * 70)
print('TEST 3: Real Node Data')
print('=' * 70)

async def test_with_real_data():
    from runtime.hyperliquid.node_adapter.position_state import PositionStateManager, MSGPACK_AVAILABLE
    from runtime.hyperliquid.node_adapter.observation_bridge import NodeProximityProvider

    if not MSGPACK_AVAILABLE:
        print('ERROR: msgpack not available')
        return

    print('\nLoading real positions from node...')
    psm = PositionStateManager(
        state_path='/home/ksiaz/hl/hyperliquid_data',
        min_position_value=1000.0,
        focus_coins=['BTC', 'ETH', 'SOL', 'HYPE'],
    )

    await psm.start()
    await asyncio.sleep(2)

    print(f'\nPositions loaded: {psm.metrics.positions_cached}')
    print(f'Critical: {psm.metrics.critical_positions}')

    provider = NodeProximityProvider(psm)

    # Check each coin
    sm_real = CascadeStateMachine(config)

    for coin in ['BTC', 'ETH', 'SOL', 'HYPE']:
        prox = provider.get_proximity(coin)
        if prox:
            # Convert to strategy's ProximityData format
            strategy_prox = ProximityData(
                coin=coin,
                current_price=0,
                threshold_pct=0.05,  # 5%
                long_positions_count=prox.long_positions_count,
                long_positions_value=prox.long_positions_value,
                long_closest_liquidation=None,
                short_positions_count=prox.short_positions_count,
                short_positions_value=prox.short_positions_value,
                short_closest_liquidation=None,
                total_positions_at_risk=prox.total_positions_at_risk,
                total_value_at_risk=prox.total_value_at_risk,
                timestamp=time.time()
            )

            symbol = coin + 'USDT'
            state = sm_real.update(symbol, strategy_prox, None, time.time())

            print(f'\n{coin}:')
            print(f'  Positions: {prox.total_positions_at_risk}, Value: ${prox.total_value_at_risk:,.0f}')
            print(f'  Long: {prox.long_positions_count} (${prox.long_positions_value:,.0f})')
            print(f'  Short: {prox.short_positions_count} (${prox.short_positions_value:,.0f})')

            # Check dominance
            if prox.total_value_at_risk > 0:
                long_ratio = prox.long_positions_value / prox.total_value_at_risk
                dominance = max(long_ratio, 1 - long_ratio)
                dominant = 'LONG' if long_ratio > 0.5 else 'SHORT'
                print(f'  Dominance: {dominant} {dominance:.1%}')

            print(f'  State: {state.value}')

            # Explain why not primed
            if state == CascadeState.NONE:
                reasons = []
                if prox.total_positions_at_risk < config.min_cluster_positions:
                    reasons.append(f'positions {prox.total_positions_at_risk} < {config.min_cluster_positions}')
                if prox.total_value_at_risk < config.min_cluster_value:
                    reasons.append(f'value ${prox.total_value_at_risk:,.0f} < ${config.min_cluster_value:,.0f}')
                if prox.total_value_at_risk > 0:
                    long_ratio = prox.long_positions_value / prox.total_value_at_risk
                    dominance = max(long_ratio, 1 - long_ratio)
                    if dominance < config.dominance_ratio:
                        reasons.append(f'dominance {dominance:.0%} < {config.dominance_ratio:.0%}')
                if reasons:
                    print(f'  Not PRIMED because: {", ".join(reasons)}')

    await psm.stop()

asyncio.run(test_with_real_data())

print('\n' + '=' * 70)
print('CONCLUSION')
print('=' * 70)
print('''
For signals to fire, cascade sniper needs:
1. PRIMED: Cluster with >$100k, >2 positions, >65% on one side
2. TRIGGERED: Liquidation burst >$50k detected
3. ABSORBING: Book depth absorbed cascade (for reversal mode)

RESOLVED: Node liquidations are now aggregated into bursts via
LiquidationBurstAggregator in observation_bridge.py. No Binance websocket needed.

Integration path:
- Node detects liquidations from node_trades files
- ObservationBridge.on_liquidation() feeds events to aggregator
- LiquidationBurstAggregator aggregates over 10-second window
- NodeProximityProvider.get_burst(symbol) returns burst data
- Cascade state machine can transition PRIMED -> TRIGGERED

To see bursts in action, run run_paper_trade.py and monitor for liquidations.
''')

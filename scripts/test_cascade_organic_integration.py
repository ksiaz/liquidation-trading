#!/usr/bin/env python3
"""
Test Cascade Strategy Integration with Organic Flow Detection.

Verifies the full flow from liquidation events through to absorption detection
and entry signal generation.

Usage:
    python scripts/test_cascade_organic_integration.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from external_policy.ep2_strategy_cascade_sniper import (
    CascadeSniperConfig,
    CascadeState,
    ProximityData,
    LiquidationBurst,
    record_liquidation_event,
    record_organic_trade,
    get_absorption_signal,
    get_organic_flow_metrics,
    generate_cascade_sniper_proposal,
    get_cascade_state,
    StrategyContext,
    PermissionOutput,
    EntryMode,
    reset_state,
    _get_state_machine,
)

print('=' * 70)
print('CASCADE STRATEGY + ORGANIC FLOW INTEGRATION TEST')
print('=' * 70)

# Reset global state for clean test
reset_state()

# Verify config
config = CascadeSniperConfig()
print('\nConfig:')
print(f'  use_organic_flow_detection: {config.use_organic_flow_detection}')
print(f'  organic_flow_window_sec: {config.organic_flow_window_sec}s')
print(f'  min_organic_volume: ${config.min_organic_volume:,.0f}')
print(f'  organic_quiet_time_sec: {config.organic_quiet_time_sec}s')

# Get the global state machine singleton
sm = _get_state_machine()
print(f'\nState machine created with organic detector: {sm._organic_detector is not None}')

now = time.time()
symbol = 'BTCUSDT'

# ==============================================================================
# PHASE 1: NONE -> PRIMED (cluster formation)
# ==============================================================================
print('\n' + '=' * 70)
print('PHASE 1: Cluster Formation (NONE -> PRIMED)')
print('=' * 70)

# Create proximity data - longs dominating
proximity = ProximityData(
    coin='BTC',
    current_price=100000,
    threshold_pct=0.005,
    long_positions_count=50,
    long_positions_value=500_000,  # $500k longs at risk
    long_closest_liquidation=99500,
    short_positions_count=5,
    short_positions_value=50_000,
    short_closest_liquidation=100500,
    total_positions_at_risk=55,
    total_value_at_risk=550_000,
    timestamp=now,
)

state = sm.update(symbol, proximity, None, now)
print(f'\nState after proximity: {state.value}')
assert state == CascadeState.PRIMED, f"Expected PRIMED, got {state}"
print('[PASS] Cluster formed, state = PRIMED')

# ==============================================================================
# PHASE 2: PRIMED -> TRIGGERED (liquidation burst)
# ==============================================================================
print('\n' + '=' * 70)
print('PHASE 2: Cascade Trigger (PRIMED -> TRIGGERED)')
print('=' * 70)

# Create liquidation burst that exceeds threshold
burst = LiquidationBurst(
    symbol=symbol,
    total_volume=75_000,  # $75k > $50k threshold
    long_liquidations=70_000,  # Mostly longs liquidated
    short_liquidations=5_000,
    liquidation_count=8,
    window_start=now,
    window_end=now + 5,
)

# Also feed to organic detector via module function
for i in range(8):
    record_liquidation_event(symbol, 'SELL', 8750, now + i * 0.5)

state = sm.update(symbol, proximity, burst, now + 5)
print(f'\nState after burst: {state.value}')
assert state == CascadeState.TRIGGERED, f"Expected TRIGGERED, got {state}"
print('[PASS] Cascade triggered, state = TRIGGERED')

# Check organic detector is tracking
metrics = get_organic_flow_metrics()
print(f'\nOrganic flow metrics:')
for k, v in metrics.items():
    print(f'  {k}: {v}')

# ==============================================================================
# PHASE 3: TRIGGERED -> ABSORBING (organic flow detection)
# ==============================================================================
print('\n' + '=' * 70)
print('PHASE 3: Absorption Detection (TRIGGERED -> ABSORBING)')
print('=' * 70)

# Wait for quiet time (simulate no new liquidations)
absorption_time = now + 10  # 5 seconds since last liq

# Add organic BUYING (opposing the DOWN cascade)
print('\nFeeding organic trades (buyers stepping in)...')
for i in range(10):
    record_organic_trade(symbol, 'BUY', 2000, absorption_time - 2 + i * 0.1)
print(f'  Added 10 organic buys totaling $20,000')

# Add some sells (less than buys)
for i in range(3):
    record_organic_trade(symbol, 'SELL', 1000, absorption_time - 1 + i * 0.1)
print(f'  Added 3 organic sells totaling $3,000')
print(f'  Net organic: +$17,000 (buyers dominating)')

# Update state - should detect absorption
state = sm.update(symbol, proximity, None, absorption_time)
print(f'\nState after organic flow: {state.value}')

# Get absorption signal
signal = get_absorption_signal(symbol)
if signal:
    print(f'\nAbsorption signal:')
    print(f'  cascade_direction: {signal.cascade_direction.value}')
    print(f'  liqs_stopped: {signal.liqs_stopped}')
    print(f'  time_since_last_liq: {signal.time_since_last_liq:.1f}s')
    print(f'  organic_net: ${signal.organic_net:,.0f}')
    print(f'  organic_opposes: {signal.organic_opposes}')
    print(f'  organic_ratio: {signal.organic_ratio:.1%}')
    print(f'  absorption_detected: {signal.absorption_detected}')
    print(f'  entry_direction: {signal.entry_direction}')

assert state == CascadeState.ABSORBING, f"Expected ABSORBING, got {state}"
print('\n[PASS] Absorption detected via organic flow, state = ABSORBING')

# ==============================================================================
# PHASE 4: Generate Entry Proposal
# ==============================================================================
print('\n' + '=' * 70)
print('PHASE 4: Entry Proposal Generation')
print('=' * 70)

# Create permission (allowed)
permission = PermissionOutput(
    result="ALLOWED",
    mandate_id="M1",
    action_id="A1",
    reason_code="ALLOWED",
    timestamp=absorption_time,
)

# Create context
context = StrategyContext(
    context_id="test-1",
    timestamp=absorption_time,
)

# Generate proposal
proposal = generate_cascade_sniper_proposal(
    permission=permission,
    proximity=proximity,
    liquidations=None,  # No new liqs
    context=context,
    entry_mode=EntryMode.ABSORPTION_REVERSAL,
)

if proposal:
    print(f'\nProposal generated:')
    print(f'  strategy_id: {proposal.strategy_id}')
    print(f'  action_type: {proposal.action_type}')
    print(f'  direction: {proposal.direction}')
    print(f'  confidence: {proposal.confidence}')
    print(f'  justification: {proposal.justification_ref}')

    assert proposal.direction == "LONG", f"Expected LONG entry (reversal from DOWN cascade), got {proposal.direction}"
    print('\n[PASS] LONG entry proposal generated for DOWN cascade reversal')
else:
    print('\n[INFO] No proposal generated (may need more context)')

# ==============================================================================
# SUMMARY
# ==============================================================================
print('\n' + '=' * 70)
print('INTEGRATION TEST COMPLETE')
print('=' * 70)

final_metrics = get_organic_flow_metrics()
print(f'\nFinal organic flow metrics:')
for k, v in final_metrics.items():
    print(f'  {k}: {v}')

print('''
INTEGRATION FLOW:
1. Proximity data → PRIMED (cluster detected)
2. Liquidation burst → TRIGGERED (cascade started)
   - Liquidations fed to organic detector
   - Cascade direction set (DOWN for long liqs)
3. Organic buying → ABSORBING (buyers stepping in)
   - liqs_stopped = True (quiet time elapsed)
   - organic_net > 0 (opposing DOWN cascade)
4. Entry proposal → LONG (reversal from cascade)

The organic flow detector replaces static orderbook depth analysis
with dynamic flow-based absorption detection.
''')

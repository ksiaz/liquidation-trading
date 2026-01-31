# Runbook: Position Mismatch

## Symptoms
- Health dashboard shows "Position mismatch with exchange"
- Local position tracker shows different positions than exchange
- Trading halted due to reconciliation failure
- Alert: "POSITION_MISMATCH_LOCAL_ONLY" or "POSITION_MISMATCH_EXCHANGE_ONLY"

## Severity
**CRITICAL** - Unknown risk exposure, trading must stop

## Immediate Actions

### 1. STOP ALL TRADING
```bash
# Send halt signal
kill -USR1 $(pgrep -f "run_paper_trade.py")

# Or use kill switch
./scripts/emergency/kill_switch.sh --signal
```

### 2. Get Current State
```bash
# Check exchange positions
python3 -c "
import asyncio
from runtime.hyperliquid.client import HyperliquidClient

async def show():
    client = HyperliquidClient()
    positions = await client.get_positions()
    for p in positions:
        if abs(p.get('size', 0)) > 0:
            print(f\"{p['symbol']}: {p['size']:.6f}\")

asyncio.run(show())
"
```

```bash
# Check local tracker state
python3 -c "
from runtime.executor.position_tracker import get_tracker
tracker = get_tracker()
for symbol, pos in tracker.get_all_positions().items():
    print(f'{symbol}: {pos.size:.6f} {pos.side}')
"
```

### 3. Identify Mismatch Type

#### Type A: Local has position, exchange doesn't (GHOST POSITION)
**Risk:** We think we have exposure but we don't
**Cause:** Stop was hit, liquidation occurred, manual close
**Action:** Remove from local tracker

```bash
python3 -c "
from runtime.executor.position_tracker import get_tracker
tracker = get_tracker()
tracker.remove_position('SYMBOL_HERE')
print('Removed ghost position')
"
```

#### Type B: Exchange has position, local doesn't (UNKNOWN EXPOSURE)
**Risk:** We have exposure we don't know about
**Cause:** Manual trade, state lost after crash, fill notification missed
**Action:** Sync to local, ensure stop is set

```bash
# Sync unknown position
python3 -c "
import asyncio
from runtime.hyperliquid.client import HyperliquidClient
from runtime.executor.position_tracker import get_tracker

async def sync():
    client = HyperliquidClient()
    tracker = get_tracker()

    positions = await client.get_positions()
    for p in positions:
        if abs(p.get('size', 0)) > 0:
            tracker.sync_from_exchange(p['symbol'], p)
            print(f'Synced {p[\"symbol\"]}')

asyncio.run(sync())
"

# Verify stop orders exist
python3 -c "
import asyncio
from runtime.hyperliquid.client import HyperliquidClient

async def check():
    client = HyperliquidClient()
    orders = await client.get_open_orders()
    stops = [o for o in orders if 'stop' in o.get('order_type', '').lower()]
    for s in stops:
        print(f\"{s['symbol']}: stop @ {s['price']}\")

asyncio.run(check())
"
```

#### Type C: Size mismatch
**Risk:** Exposure different than expected
**Cause:** Partial fill, additional manual trade
**Action:** Trust exchange, update local

```bash
python3 -c "
from runtime.executor.reconciliation import PositionReconciler
# Run manual reconciliation
import asyncio

async def reconcile():
    from runtime.hyperliquid.client import HyperliquidClient
    from runtime.executor.position_tracker import get_tracker

    reconciler = PositionReconciler(
        exchange_client=HyperliquidClient(),
        position_tracker=get_tracker(),
    )
    result = await reconciler.reconcile()
    print(f'Clean: {result.is_clean}')
    for diff in result.diffs_found:
        print(f'  {diff.symbol}: {diff.diff_type}')
    for action in result.actions_taken:
        print(f'  Action: {action}')

asyncio.run(reconcile())
"
```

## Decision Tree

```
Is local position NOT on exchange?
├── YES (Ghost Position)
│   └── Remove from local tracker
│       └── Investigate why (check logs for stop hit / liquidation)
│
└── NO
    │
    Is exchange position NOT tracked locally?
    ├── YES (Unknown Exposure)
    │   └── Was this a manual trade?
    │       ├── YES → Sync to local, set stop
    │       └── NO → Investigate fill notification issue
    │
    └── NO (Size Mismatch)
        └── Trust exchange, update local
            └── Investigate cause (partial fills, etc.)
```

## Root Cause Investigation

### Check Recent Events
```bash
# Last 10 minutes of logs
tail -1000 logs/trading.log | grep -E "position|fill|order"

# Database query
python3 -c "
import sqlite3
conn = sqlite3.connect('data/trading.db')
cur = conn.cursor()
cur.execute('''
    SELECT * FROM trades
    ORDER BY timestamp DESC
    LIMIT 20
''')
for row in cur.fetchall():
    print(row)
"
```

### Common Causes

| Cause | How to Identify | Prevention |
|-------|----------------|------------|
| Stop order hit | Check execution logs | Normal operation |
| Liquidation | Check funding + price history | Lower leverage |
| Manual trade | Check Hyperliquid dashboard | Document all manual trades |
| Crash/restart | Check process restart times | Improve crash recovery |
| Fill missed | Check WebSocket reconnection logs | Improve fill confirmation |

## Resolution Checklist

- [ ] Trading stopped
- [ ] Exchange positions verified
- [ ] Local state corrected
- [ ] All positions have stop orders
- [ ] Root cause identified
- [ ] Trading can resume

## Resume Trading

Only resume after ALL conditions met:
1. Reconciliation shows clean: `result.is_clean == True`
2. All positions have stops verified
3. Root cause understood and documented

```bash
# Verify clean state
python3 -c "
import asyncio
from runtime.executor.reconciliation import PositionReconciler
from runtime.hyperliquid.client import HyperliquidClient
from runtime.executor.position_tracker import get_tracker

async def verify():
    reconciler = PositionReconciler(
        exchange_client=HyperliquidClient(),
        position_tracker=get_tracker(),
    )
    result = await reconciler.reconcile()
    if result.is_clean:
        print('✓ State is clean, safe to resume')
    else:
        print('✗ Still have mismatches:')
        for diff in result.diffs_found:
            print(f'  {diff.symbol}: {diff.diff_type}')

asyncio.run(verify())
"

# Resume trading
python3 scripts/run_paper_trade.py
```

## Post-Incident

1. Document the incident in incident log
2. Update monitoring if detection was slow
3. Add test case if new failure mode discovered
4. Review and improve reconciliation logic if needed

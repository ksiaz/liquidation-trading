# Runbook: Emergency Shutdown

## When to Use

Use the emergency shutdown when:
- System is behaving erratically
- Positions are being opened unexpectedly
- Circuit breaker should have triggered but didn't
- Network issues causing unpredictable behavior
- Any situation where continuing to trade poses unacceptable risk

## Severity
**CRITICAL** - Immediate action required

## The Kill Switch

### Full Emergency Shutdown
```bash
./scripts/emergency/kill_switch.sh
```

This will:
1. Send SIGUSR1 to all trading processes (graceful stop)
2. Close all open positions at market
3. Cancel all pending orders
4. Log the emergency activation

### Dry Run (See What Would Happen)
```bash
./scripts/emergency/kill_switch.sh --dry-run
```

### Partial Operations
```bash
# Only signal processes (don't touch positions/orders)
./scripts/emergency/kill_switch.sh --signal

# Only close positions
./scripts/emergency/kill_switch.sh --positions

# Only cancel orders
./scripts/emergency/kill_switch.sh --orders
```

## Manual Emergency Procedures

If scripts fail or are unavailable:

### 1. Stop Trading Processes
```bash
# Graceful
pkill -USR1 -f "run_paper_trade.py"

# Forceful (if graceful doesn't work)
pkill -9 -f "run_paper_trade.py"
```

### 2. Close Positions via API
```python
import asyncio
from runtime.hyperliquid.client import HyperliquidClient

async def emergency_close():
    client = HyperliquidClient()
    positions = await client.get_positions()

    for pos in positions:
        if abs(pos.get('size', 0)) > 0:
            symbol = pos['symbol']
            size = pos['size']
            side = 'sell' if size > 0 else 'buy'

            print(f"Closing {symbol}...")
            await client.place_market_order(
                symbol=symbol,
                side=side,
                size=abs(size),
                reduce_only=True,
            )

asyncio.run(emergency_close())
```

### 3. Cancel Orders via API
```python
import asyncio
from runtime.hyperliquid.client import HyperliquidClient

async def emergency_cancel():
    client = HyperliquidClient()
    orders = await client.get_open_orders()

    for order in orders:
        print(f"Cancelling {order['order_id']}...")
        await client.cancel_order(order['symbol'], order['order_id'])

asyncio.run(emergency_cancel())
```

### 4. Via Hyperliquid Dashboard (Last Resort)
If programmatic access fails:
1. Go to https://app.hyperliquid.xyz
2. Connect wallet
3. Navigate to Positions
4. Click "Close All" for each position
5. Navigate to Orders
6. Click "Cancel All"

## Post-Shutdown Checklist

- [ ] All positions verified closed
- [ ] All orders verified cancelled
- [ ] No trading processes running
- [ ] Incident logged with timestamp
- [ ] Root cause investigation started
- [ ] Stakeholders notified (if applicable)

## Verification Commands

```bash
# Verify no positions
python3 -c "
import asyncio
from runtime.hyperliquid.client import HyperliquidClient

async def check():
    client = HyperliquidClient()
    positions = await client.get_positions()
    open_pos = [p for p in positions if abs(p.get('size', 0)) > 0]
    if open_pos:
        print(f'WARNING: {len(open_pos)} positions still open!')
        for p in open_pos:
            print(f'  {p[\"symbol\"]}: {p[\"size\"]}')
    else:
        print('✓ No open positions')

asyncio.run(check())
"

# Verify no orders
python3 -c "
import asyncio
from runtime.hyperliquid.client import HyperliquidClient

async def check():
    client = HyperliquidClient()
    orders = await client.get_open_orders()
    if orders:
        print(f'WARNING: {len(orders)} orders still open!')
    else:
        print('✓ No open orders')

asyncio.run(check())
"

# Verify no processes
pgrep -f "run_paper_trade.py|run_live_trade.py" && echo "WARNING: Processes still running" || echo "✓ No trading processes"
```

## Recovery After Emergency

1. **Wait**: Allow at least 5 minutes before any recovery action
2. **Investigate**: Understand what caused the emergency
3. **Fix**: Address the root cause
4. **Test**: Run in paper mode first
5. **Resume**: Only after verification passes

```bash
# Paper test before live
python3 scripts/run_paper_trade.py --duration 1h

# If paper test passes
python3 scripts/run_live_trade.py
```

## Emergency Contacts

| Role | Contact |
|------|---------|
| System Owner | [Add contact] |
| Backup Operator | [Add contact] |
| Exchange Support | https://discord.gg/hyperliquid |

## Incident Template

```
## Incident Report

**Date/Time:** YYYY-MM-DD HH:MM UTC
**Duration:** X minutes
**Severity:** CRITICAL

### What Happened
[Description]

### Impact
- Positions closed: X
- Orders cancelled: X
- Estimated PnL impact: $X

### Root Cause
[Analysis]

### Actions Taken
1. Kill switch activated at HH:MM
2. [Additional actions]

### Prevention
[What will prevent this in the future]
```

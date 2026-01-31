# Runbook: High Latency

## Symptoms
- Order submission taking >500ms
- Data staleness warnings
- Strategy decisions timing out
- Fills delayed or missed

## Severity
**High** - Active trading may be impaired, risk of missed opportunities or stale executions

## Immediate Actions

### 1. Check Latency Metrics
```bash
# View current latency percentiles
python3 -c "
from runtime.monitoring import get_profiler
p = get_profiler()
print(p.get_percentiles())
"
```

Expected values:
| Stage | Target | Warning | Critical |
|-------|--------|---------|----------|
| strategy_decision | <100μs | >200μs | >500μs |
| risk_validation | <50μs | >100μs | >250μs |
| order_submission | <500μs | >1ms | >2.5ms |
| e2e | <2ms | >4ms | >10ms |

### 2. Check System Resources
```bash
# CPU and memory
top -bn1 | head -20

# Disk I/O
iostat -x 1 3

# Network latency to exchange
ping -c 5 api.hyperliquid.xyz
```

### 3. Check Network Path
```bash
# Traceroute to exchange
traceroute api.hyperliquid.xyz

# DNS resolution time
time nslookup api.hyperliquid.xyz

# WebSocket connectivity
timeout 5 wscat -c wss://api.hyperliquid.xyz/ws -x '{"method":"ping"}'
```

### 4. Check Process State
```bash
# Find trading process
pgrep -f "run_paper_trade.py"

# Check its resource usage
ps aux | grep run_paper_trade

# Check open file descriptors (too many = leak)
lsof -p <PID> | wc -l  # Should be < 1000
```

## Root Causes and Solutions

### High CPU Usage
**Cause:** Strategy computation too complex, runaway loop
```bash
# Profile CPU
py-spy top --pid <PID>

# Solution: Reduce computation frequency, optimize hot paths
```

### High Memory Usage
**Cause:** Memory leak, too much data cached
```bash
# Check memory
ps -o pid,vsz,rss,comm -p <PID>

# Solution: Restart process, investigate leak
python3 scripts/emergency/kill_switch.sh --signal
python3 scripts/run_paper_trade.py
```

### Network Congestion
**Cause:** ISP issues, VPN overhead, exchange issues
```bash
# Check for packet loss
mtr api.hyperliquid.xyz

# Solution:
# - Switch to direct connection (no VPN)
# - Use closer datacenter
# - Check Hyperliquid status page
```

### Garbage Collection Spikes
**Cause:** Python GC pauses during allocation
```bash
# Check GC stats
python3 -c "import gc; gc.set_debug(gc.DEBUG_STATS)"

# Solution: Pre-allocate data structures, use object pools
```

### Exchange Degradation
**Cause:** Hyperliquid infrastructure issues
```bash
# Check Hyperliquid status
curl -s https://api.hyperliquid.xyz/info -d '{"type":"meta"}' | python3 -m json.tool

# Solution: Wait for exchange to recover, reduce trading
```

## Mitigation Steps

### Immediate (< 1 min)
1. **Reduce trading activity**: Set position size multiplier to 0.5
2. **Widen thresholds**: Increase confidence requirements

### Short-term (< 10 min)
1. Restart trading process
2. Clear any caches
3. Switch to backup network if available

### If Latency Persists
1. Activate degradation mode:
```python
from runtime.failure.degradation import DegradationController
controller = DegradationController()
controller.enter_level_1()  # Reduced operation
```

2. If critical (>10ms e2e):
```bash
./scripts/emergency/kill_switch.sh
```

## Verification
After mitigation:
```bash
# Monitor latency for 5 minutes
python3 -c "
import asyncio
from runtime.monitoring import get_profiler

async def monitor():
    p = get_profiler()
    for i in range(30):
        await asyncio.sleep(10)
        summary = p.get_summary()
        print(f'{i*10}s: p95={summary.stages.get(\"order_submission\", {}).get(\"p95_us\", 0)}μs')

asyncio.run(monitor())
"
```

Target: p95 order_submission < 1ms for 5 consecutive minutes

## Escalation
If latency doesn't improve after all steps:
1. Check Hyperliquid Discord/Twitter for outage announcements
2. Consider pausing trading until resolved
3. File issue if suspected exchange bug

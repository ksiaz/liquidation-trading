# Observability UI Reference - Native App v1.0

## Purpose

This document explains every panel, counter, and indicator in the Native Windows Observability App.

**Use this to**: Understand what the UI is showing you and why.

---

## Window Layout

```
┌─────────────────────────────────────────────────────────────┐
│  STATUS BAR (always visible)                                │
├──────────────────────────┬──────────────────────────────────┤
│                          │                                  │
│  System Health Panel     │  Promoted Events Panel           │
│  (stream status)         │  (Peak Pressure events)          │
│                          │                                  │
├──────────────────────────┤                                  │
│                          │                                  │
│  Raw Market Feed Panel   │                                  │
│  - Trades table          │                                  │
│  - Liquidations table    │                                  │
│                          │                                  │
└──────────────────────────┴──────────────────────────────────┘
```

---

## Status Bar (Top)

### Mode

**Display**: `Mode: LIVE_PEAK_PRESSURE`

**Meaning**: System is running in live observation mode (not backtest, not simulation).

**Values**:
- `LIVE_PEAK_PRESSURE`: Normal operation
- `LOADING...`: SystemState not initialized yet (wait for collector)

### Symbols

**Display**: `Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (+5 more)`

**Meaning**: TOP_10 symbols selected at startup by 24h volume.

**Color**: White (informational only)

**If truncated**: Shows first 5 symbols + count of remaining.

**Click behavior**: None (read-only).

### Baselines

**Display**: `Baselines: 7 / 10`

**Meaning**:
- **7**: Number of symbols with warmed baselines (≥60 windows)
- **10**: Total symbols (always 10 in System v1.0)

**Color**:
- 🟢 **Green**: All baselines ready (10/10)
- 🟠 **Orange**: Warming up (< 10/10)

**Interpretation**:
- **0/10**: Just started, < 60 seconds runtime
- **5/10**: ~5 minutes runtime
- **10/10**: All symbols ready for promotion (≥10 min runtime)

**Why it matters**: Promotions disabled until baseline is warm. `7/10` means 3 symbols still ineligible.

### Health

**Display**: `Health: OK` or `Health: DEGRADED`

**Meaning**: Overall ingestion stream health.

**Color**:
- 🟢 **Green (OK)**: All streams nominal
- 🔴 **Red (DEGRADED)**: At least one stream below threshold

**Calculation**:
```
If any stream rate < expected:
    Health = DEGRADED
Else:
    Health = OK
```

**Degraded triggers**:
- Trades rate < 10/s
- Liquidations rate < 0.1/min
- Klines rate < 1/s
- OI rate < 0.2/min

**Action if DEGRADED**: Check System Health Panel for details.

### Windows

**Display**: `Windows: 14,523`

**Meaning**: Total number of 1-second windows processed across all symbols since startup.

**Expected Rate**: ~10 windows/second (10 symbols × 1s windows)

**After 1 hour**: Should be ~36,000 windows

**If frozen**: Collector may have crashed (check console).

**If decreasing**: CRITICAL BUG (should never happen).

### Events

**Display**: `Events: 3`

**Meaning**: Total Peak Pressure events promoted since startup.

**Expected Range**: 0-20 per hour (silence is normal)

**Color**: White (no color coding - any count is valid)

**Not a performance metric**: Zero events does NOT mean system is broken.

---

## System Health Panel (Top Left)

### Purpose

Shows per-stream ingestion rates and explains why events may be dropped.

### Stream Status Section

**Format**:
```
=== SYSTEM HEALTH ===

Trades rate: 427.3/s
Liquidations rate: 3.2/min
Klines rate: 10.1/s
OI rate: 2.1/min
```

**Interpretation**:

| Stream | Healthy Range | Meaning |
|--------|---------------|---------|
| **Trades** | 100-1000/s | Aggregate trades across all 10 symbols |
| **Liquidations** | 0.5-50/min | Forced position closures (varies with volatility) |
| **Klines** | ~10/s | 1s candlesticks (1 per symbol) |
| **OI** | ~2/min | Open Interest polls (every 5s across symbols) |

**If trades = 0**: WebSocket disconnected (should auto-reconnect)

**If liquidations = 0**: No forced closures (normal during low volatility)

**If klines < 10/s**: Some symbols missing kline data (degraded)

**If OI < 1/min**: Polling delayed or API timeout

### Dropped Events Section

**Format**:
```
=== DROPPED EVENTS (Last 60s) ===

Symbol not allowed: 18,492
Baseline not ready: 331
Window not closed: 12
Missing streams: 0
```

**Interpretation**:

#### Symbol not allowed

**Meaning**: Events for non-TOP_10 symbols (rejected immediately).

**Expected**: 10,000s - 100,000s (many symbols trade on Binance)

**Why so high?** Collector receives global liquidation feed, filters to TOP_10.

**Action**: None (working as designed).

#### Baseline not ready

**Meaning**: Window met all 4 conditions BUT baseline not warmed yet.

**Expected**:
- First 10 minutes: 100s - 1000s (normal warmup)
- After 15 minutes: < 10 (all baselines warm)

**If high after 20 min**: Some symbols stuck warming (investigate).

#### Window not closed

**Meaning**: Event arrived with invalid timestamp (timing issue).

**Expected**: 0-10 per hour (rare timing edge case)

**If > 100/hour**: Network latency spikes or system clock drift.

#### Missing streams

**Meaning**: Required stream data unavailable at window close time.

**Expected**: 0-50 per hour (occasional OI polling delay)

**If > 500/hour**: Persistent stream degradation (check WebSocket).

---

## Raw Market Feed Panel (Bottom Left)

### Purpose

Shows **unfiltered** recent market activity. This is intentionally noisy.

### Trades Table

**Columns**:
| Column | Meaning | Example |
|--------|---------|---------|
| Time | Event timestamp (local time) | 14:23:45 |
| Symbol | Trading pair | BTCUSDT |
| Price | Execution price (USDT) | 43,127.50 |
| Qty | Base asset quantity | 0.1250 |
| Side | BUY or SELL | BUY |

**Rows**: Last 20 trades across all symbols (most recent first)

**Update Rate**: Real-time (500ms refresh)

**Why it's noisy**: Shows ALL trades (not filtered for size or surge).

**Use case**: Verify ingestion is working ("is data flowing?").

### Liquidations Table

**Columns**: Same as Trades table

**Rows**: Last 20 liquidations across all symbols

**Why often empty**: Liquidations are rare during normal market conditions.

**If always empty for hours**: Either:
- Market is stable (healthy)
- WebSocket disconnected (check Health panel)

**Use case**: See when forced closures happen (external stress indicator).

---

## Promoted Events Panel (Right)

### Purpose

Shows **only structural break events** that met all 4 promotion conditions.

### Empty State

**Display**:
```
=== NO PEAK PRESSURE EVENTS DETECTED ===

This is expected during:
- Baseline warmup (7 / 10 symbols ready)
- Normal market conditions
- No multi-stream coincidence
```

**Meaning**: Zero events is **normal and healthy**.

**Why three reasons listed**:
1. **Baseline warmup**: Cannot promote without historical context
2. **Normal conditions**: Most market activity does NOT qualify
3. **No coincidence**: Even if 3/4 conditions met, requires ALL 4

**Action**: None. This is correct behavior.

### Event List (When Events Exist)

**Format**:
```
=== PROMOTED STRUCTURAL EVENTS (3) ===

[2026-01-06 14:23:45] BTCUSDT - BUY
  Window: 1.0s
  Stress: liquidations, oi_change
  Flow: 1,247,389.23
  Trades: 127
  Liquidations: 3

[2026-01-06 13:15:22] ETHUSDT - SELL
  Window: 1.0s
  Stress: liquidations
  Flow: 892,441.88
  Trades: 94
  Liquidations: 2

...
```

**Fields Explained**:

#### Timestamp + Symbol + Side

**Example**: `[2026-01-06 14:23:45] BTCUSDT - BUY`

**Meaning**:
- **Timestamp**: Window end time (when event was promoted)
- **Symbol**: Which symbol qualified
- **Side**: BUY or SELL (based on `net_aggression` sign)

**CRITICAL**: `Side` is **metadata only**. NOT a trading signal.

#### Window

**Always**: `1.0s` (fixed window size in v1.0)

#### Stress

**Values**: `liquidations`, `oi_change`, or both

**Meaning**: Which external stress sources were present
- **liquidations**: Liquidations detected in 60s buffer
- **oi_change**: Open Interest changed during this window

**Why it matters**: Peak Pressure requires external stress (Condition 4).

#### Flow

**Example**: `Flow: 1,247,389.23`

**Meaning**: Total absolute flow (buy volume + sell volume) in USDT

**Why shown**: This exceeded baseline P90 (Condition 1).

#### Trades

**Example**: `Trades: 127`

**Meaning**: Number of trades in this 1s window

**Not filtered**: All trades (including small ones) counted.

#### Liquidations

**Example**: `Liquidations: 3`

**Meaning**: Forced closures in 60s retention window (not just this window).

**Why 60s?** Liquidation stress persists (cascade effect).

---

## Color Coding

### Green (Success States)

- Baselines: 10/10 (all ready)
- Health: OK (all streams nominal)

### Orange (Transitional States)

- Baselines: < 10/10 (warming up)

### Red (Degraded States)

- Health: DEGRADED (stream issue)

### White (Neutral/Informational)

- Mode, Symbols, Windows, Events (no state judgment)

**No color = no judgment**. Zero events is not red (silence is valid).

---

## Error States

### "LOADING..." (Status Bar)

**Cause**: SystemState not initialized yet

**Action**: Wait for collector to start (< 5 seconds)

**If persists > 30s**: Collector failed to start (check console)

### Empty Raw Feed Tables

**Cause 1**: Just started (< 5 seconds)  
**Cause 2**: Ingestion health DEGRADED (WebSocket disconnected)

**Action**: Check Health panel for stream status

### Baselines Stuck at X/10

**Example**: Baselines showing `7/10` for > 15 minutes

**Cause**: 3 symbols not receiving data (stream issue)

**Action**: Check System Health panel for which streams degraded

---

## Update Frequency

**Status Bar**: 500ms (2 Hz)  
**Health Panel**: 500ms  
**Raw Feed Tables**: 500ms  
**Promoted Events**: 500ms  

**All updates passive** (UI reads snapshot, never writes).

---

## What Is NOT Shown

### Charts/Graphs

**Why absent?** Violates "render truth" mandate. Charts add interpretation.

**If you need charts**: Export data and visualize externally.

### Predictions

**Why absent?** System observes past, never predicts future.

### Indicators

**Why absent?** (RSI, MACD, etc.) Not part of Peak Pressure detection logic.

### Controls

**Why absent?** UI is read-only. No start/stop, no parameter tuning.

---

## Common Questions

### Q: Why is "Events: 0" not red?

**A**: Because zero events is a valid outcome. Most markets don't exhibit Peak Pressure.

### Q: Why are dropped events so high?

**A**: `symbol_not_allowed` counts ALL non-TOP_10 events (thousands of symbols trade). This is correct.

### Q: Why does the raw feed show trades but no events promoted?

**A**: Raw feed shows ALL trades. Promotion requires large trades + surge + compression + stress. Very rare.

### Q: Can I add a chart to see price action?

**A**: No. This would add interpretation. Use external charting if needed.

### Q: Why does baseline warmup take so long?

**A**: Need 60 windows × 1s = 60s **minimum** per symbol. Staggered starts cause 10-minute total warmup.

---

## Troubleshooting UI Issues

### Status bar not updating

1. Check if collector is running
2. Close and relaunch native app
3. Check `debug/latest_snapshot.json` timestamp

### Raw feed frozen

1. Check Health: If DEGRADED, streams disconnected
2. Check collector console for WebSocket errors
3. Restart collector if needed

### Promoted events not showing despite volatility

1. Check Baselines ready (must be 10/10)
2. Check `debug/latest_snapshot.json` → `counters`
3. Look at `flow_surge_failed`, `stress_failed` etc.
4. Most likely: No external stress (healthy market)

---

## Final Reminder

**This UI does not judge**. It renders what the system observes.

- Zero events? Possible.
- High dropped counts? Expected.
- Empty liquidations? Normal.
- Baseline warmup slow? Deterministic.

**Do not interpret silence as failure. The system tells you what it sees, not what you want to hear.**


## 2026-01-31: HLP Implementation Plan Completed (Phases 1-11)

**Summary:** Completed comprehensive implementation of HLP (Hyperliquid) production-readiness plan covering failure modes, testing, monitoring, reconciliation, backtesting, and storage.

### Phases Completed

| Phase | Component | Tests |
|-------|-----------|-------|
| 1 | Failure Modes (HLP16) - Network handling, data quality, circuit breakers | 45 |
| 2 | Testing Infrastructure (HLP20) - Test framework, fixtures | - |
| 3 | Threshold Discovery (HLP23) - Grid search, walk-forward validation | 34 |
| 4 | Strategy State Machines (HLP10) - Geometry, Kinematics, Cascade | 37 |
| 5 | Event Lifecycle (HLP14) - Event types, lifecycle states, registry | 39 |
| 6 | Capital Management (HLP17) - Position sizing, risk limits | (existing) |
| 7 | Monitoring (HLP19) - Health dashboard, latency profiler | 39 |
| 8 | Position Reconciliation (HLP18) - Exchange sync, ghost detection | 17 |
| 9 | Deployment & Operations (HLP21) - Emergency scripts, runbooks | - |
| 10 | Backtesting (HLP22) - Parameter sweep, determinism checker | 31 |
| 11 | Data Storage (HLP24) - Cold storage, event labeling | 26 |

**Total: 1039 unit tests passing**

### Key Files Created

**Failure Handling:**
- `runtime/failure/network_handler.py` - WebSocket disconnect/reconnect
- `runtime/failure/data_quality.py` - Stale/corrupt data detection
- `runtime/failure/recovery.py` - Post-failure state validation

**Strategies:**
- `runtime/strategies/base.py` - Base state machine with transitions
- `runtime/strategies/geometry/state_machine.py` - Failed Hunt strategy
- `runtime/strategies/kinematics/state_machine.py` - Post-Liq Inventory
- `runtime/strategies/cascade/state_machine.py` - Cascade Sniper

**Events:**
- `runtime/events/lifecycle.py` - DETECTED→TRIGGERED→ACTIVE→COMPLETING→COMPLETED
- `runtime/events/registry.py` - Event tracking with TTL expiration

**Monitoring:**
- `runtime/monitoring/health_dashboard.py` - System health with thresholds
- `runtime/monitoring/latency_profiler.py` - 7-stage pipeline timing

**Reconciliation:**
- `runtime/executor/reconciliation.py` - Exchange as source of truth

**Emergency:**
- `scripts/emergency/kill_switch.sh` - Full emergency shutdown
- `scripts/emergency/close_positions.py` - Market close all positions
- `scripts/emergency/cancel_orders.py` - Cancel all orders
- `docs/runbooks/` - Operational procedures

**Backtesting:**
- `runtime/backtesting/parameter_sweep.py` - Parallel grid search
- `runtime/backtesting/determinism_checker.py` - Reproducibility verification

**Storage:**
- `runtime/storage/cold_storage.py` - SQLite historical data
- `runtime/labeling/event_labeler.py` - CASCADE, HUNT_FAILED, SQUEEZE labels

### Test Configuration

Created `pytest.ini` and `tests/conftest.py` for proper test discovery:
```bash
# Run all unit tests
/home/ksiaz/.local/bin/pytest tests/unit/ -v

# Run specific phase
/home/ksiaz/.local/bin/pytest tests/unit/test_reconciliation.py -v
```

### Remaining

Phase 12 (Wallet Tracking) deferred - requires 90+ days historical position data.

---

## 2026-01-31: Disk Space Management & Data Retention

**Problem:** 2TB SSD nearly full due to unbounded data growth from multiple sources.

### Data Sources & Retention Policies

| Source | Location | Growth Rate | Retention | Cleanup Method |
|--------|----------|-------------|-----------|----------------|
| execution.db | `logs/execution.db` | ~50-500MB/hour | 48 hours | Auto-pruning via CleanupCoordinator |
| HL node fills | `~/hl/data/node_fills/` | ~3GB/day | 6-24 hours | `cleanup_hl_data.py` |
| HL node trades | `~/hl/data/node_trades/` | ~1GB/day | 24 hours | `cleanup_hl_data.py` |
| EVM blocks | `~/hl/data/evm_block_and_receipts/` | ~5GB/day | 24 hours | `cleanup_hl_data.py` |
| HL diagnostics | `~/hl/data/{node_logs,latency_*,...}` | Variable | Delete all | `cleanup_hl_data.py` |
| ABCI states | `~/hl/data/visor_abci_states/` | Variable | Keep 5 recent | `cleanup_hl_data.py` |
| Temp DBs | `tmp/*.db` | Variable | >1 day old | Auto on startup |

### Automatic Cleanup

The paper trader now includes automatic cleanup via CleanupCoordinator (runs every 5 minutes):

1. **execution.db pruning**
   - Deletes data older than 48 hours from all tables
   - Runs VACUUM to reclaim disk space

2. **HL node data cleanup** (`~/hl/data/`)
   - Deletes diagnostic directories (node_logs, latency_*, tcp_traffic, etc.)
   - Prunes hourly data older than 24h (node_fills, node_trades, evm_blocks)
   - Keeps only 5 most recent ABCI state snapshots

3. **Disk space monitoring** - ResourceMonitor checks disk usage
   - Warning at 80% usage
   - Critical at 90% usage
   - Triggers immediate cleanup on warning

4. **Temp database cleanup** - Runs on startup
   - Deletes `tmp/*.db` files older than 1 day

### Manual Cleanup

For immediate HL node cleanup or custom settings:

```bash
# Dry run (show what would be deleted)
python scripts/cleanup_hl_data.py --dry-run

# Clean with default settings (keep 24h)
python scripts/cleanup_hl_data.py

# Keep only 6 hours of data
python scripts/cleanup_hl_data.py --keep-hours 6

# Clean only diagnostics (always safe)
python scripts/cleanup_hl_data.py --diagnostics-only
```

### CRITICAL: HL Node replica_cmds

If `~/hl/data/replica_cmds/` grows massive (100GB/day), restart HL node with:

```bash
~/hl-visor run-non-validator --replica-cmds-style recent-actions
```

This keeps only 2 latest height files instead of full history.

**Update startup script:**
```bash
# ~/start-hl-node.sh
tmux new-session -d -s hl-node "cd /home/ksiaz/hl && LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 ~/hl-visor run-non-validator --write-trades --write-fills --replica-cmds-style recent-actions"
```

### Historical Data Recovery

If you need historical data after cleanup, it's available from HL:
- `s3://hl-mainnet-node-data/node_fills_by_block`
- `s3://hl-mainnet-node-data/replica_cmds`

---

## 2026-01-31: HL Node Zombie Processes

**Issue:** When starting/stopping hl-visor, zombie `[hl-node] <defunct>` processes can appear.

**Cause:** The visor spawns hl-node as a child process. If hl-node crashes during startup or the visor doesn't properly reap the child, zombies remain.

**The visor also has a safety check** that panics if it detects multiple `hl-visor` processes (including command lines that contain "hl-visor"). This can cause startup failures if previous processes weren't fully cleaned up.

**Prevention:**
1. Always kill ALL hl-visor and hl-node processes before starting fresh:
   ```bash
   pkill -9 -f "hl-visor" ; pkill -9 -f "hl-node" ; sleep 2
   ```

2. Verify clean state before starting:
   ```bash
   pgrep -f "^/home/ksiaz/hl-visor" || echo "Clean"
   ps aux | grep defunct | grep hl || echo "No zombies"
   ```

3. After starting, verify no zombies:
   ```bash
   ps aux | grep -E "(hl-visor|hl-node|defunct)" | grep -v grep
   ```

**If zombies appear:** They will be reaped when their parent (visor) exits or when you kill the visor process. They don't consume resources but indicate the child process crashed.

---

## 2026-01-31: OOM Crash - Paper Trader Startup

**Incident:** Starting paper trader with `USE_HL_NODE=true` caused system-wide OOM, killing hl-node, Antigravity, and Claude session.

**Command that triggered it:**
```bash
USE_HL_NODE=true python scripts/run_paper_trade.py --test --use-governance
```

**Timeline (from journalctl):**
```
08:48:52 systemd-journald: Under memory pressure, flushing caches
08:48:53 kernel: oom_reaper: reaped process 2696918 (hl-node)
08:49:42 app-gnome-antigravity: Failed with result 'oom-kill'
```

**Root cause:** `position_state.py:_parse_full_state()` loads ALL positions from HL node state into memory at once. With tens of thousands of wallets (users_with_positions), this creates a massive memory spike on startup.

**Location:** `runtime/hyperliquid/node_adapter/position_state.py:608`
```python
all_positions = await self._parse_full_state()  # Loads EVERYTHING
for wallet, wallet_positions in all_positions.items():
    for coin, pos_data in wallet_positions.items():
        # Process each position...
```

**Analysis:** Code comment at line 761 already notes: "The state file is ~1GB and expands to 5-10GB as Python objects." Caching was added to avoid reloading, but first load still creates 5-10GB spike.

**FULL FIX IMPLEMENTED (2026-01-31):**

1. **Removed cached state** - The 5-10GB `_cached_state` dict was removed entirely
   - Location: `runtime/hyperliquid/node_adapter/position_state.py`
   - Memory now released after each operation instead of cached permanently

2. **Added streaming parser** - New `StreamingStateParser` class
   - Location: `runtime/hyperliquid/node_adapter/streaming_parser.py`
   - Loads file, processes batch, releases memory
   - Batch-based discovery instead of loading everything at once

3. **Bootstrap from node_fills** - New `bootstrap_from_fills()` method
   - Reads recent liquidation events to find wallets at risk
   - No state file needed for initial discovery

4. **Incremental batch discovery** - New `incremental_discovery_batch()` method
   - Processes 500 wallets at a time (configurable)
   - Replaces the dangerous `full_discovery_scan()` in the refresh loop
   - Memory stays bounded to batch size

5. **Memory guards** - Added limits and eviction
   - `max_cached_positions: 50,000`
   - `max_cached_wallets: 10,000`
   - Evicts DISCOVERY tier first, never CRITICAL/WATCHLIST

6. **Default settings changed**:
   - `skip_initial_scan=True` (was False)
   - `enable_fills_bootstrap=True` (new)
   - Refresh loop uses `incremental_discovery_batch()` not `full_discovery_scan()`

Also reduced SYMBOLS from 15 to 10 coins (run_paper_trade.py) for lower overall memory footprint.

**VERIFICATION (09:57 2026-01-31):**
- Paper trader running with `USE_HL_NODE=true` ✅
- Memory: hl-node ~16GB, paper trader ~800MB (was 11.5GB before fix)
- Positions tracked: 387 across BTC, ETH, HYPE, DOGE, etc.
- Candidate zones created with historical context
- No OOM after 5+ minutes (previously crashed in <1 minute)

**Key files modified:**
- `runtime/hyperliquid/node_adapter/position_state.py` - Core refactor
- `runtime/hyperliquid/node_adapter/streaming_parser.py` - New file
- `runtime/hyperliquid/node_adapter/observation_bridge.py` - skip_initial_scan=True
- `scripts/run_paper_trade.py` - Reduced symbols to 10

**How to run (memory-safe):**
```bash
# Start hl-node with jemalloc first
~/start-hl-node.sh

# Then paper trader (no USE_HL_NODE env needed - it's default now)
python scripts/run_paper_trade.py --test --use-governance
```

**RESOLVED:** System now uses live node data without OOM risk.

---

## 2026-01-31: Binance WebSocket Fix (Connection/Reconnection)

**Issue:** Binance websocket would disconnect and never reconnect. System accumulated 403 WAF bans.

**Root causes:**

1. **Exception handling bug** - Inner `except Exception` caught `ConnectionClosedError`, looped forever instead of triggering reconnect
2. **URL-based streams** - Put 51 streams in URL query param instead of dynamic subscription
3. **Aggressive timeouts** - `ping_timeout=300s` too long, `ping_interval=60s` too aggressive

**Fixes applied:**

1. **Re-raise ConnectionClosed** in inner loop:
```python
except websockets.exceptions.ConnectionClosed:
    raise  # Bubble up to outer reconnect loop
except Exception as e:
    # Only catch processing errors
```

2. **Dynamic subscription** instead of URL streams:
```python
base_url = "wss://fstream.binance.com/stream"  # Not /stream?streams=...
await ws.send(json.dumps({
    "method": "SUBSCRIBE",
    "params": streams,
    "id": 1
}))
```

3. **Conservative reconnect backoff**:
```python
reconnect_delay = 5      # Start at 5s (was 1s)
ping_interval = 60       # 60s ping
ping_timeout = 30        # 30s pong timeout
```

**WAF ban info** (from Binance docs):
- HTTP 403 = WAF rule violated (usually excessive requests in 5 min)
- Ban duration: typically 5 minutes, can extend for repeat offenders
- Rate limits: 10 incoming messages/sec, max 1024 streams/connection

**Files modified:**
- `runtime/collector/service.py`

---

## 2026-01-31: Binance Liquidation Forwarding (M2 Node Creation)

**Issue:** HL node `--write-trades` flag not producing `node_trades` output. System had no liquidation data to create M2 nodes → no supply/demand zones → no geometry trades.

**Root cause:** Unknown - HL node syncs correctly and `--write-trades` is set, but `node_trades/hourly/` stays empty. `node_fills` has data but no liquidations. Possibly a HL binary bug or missing config.

**Workaround:** Forward Binance liquidations to M2 node creation path:

1. **Global liquidation stream** (`runtime/collector/service.py`):
   - Add `!forceOrder@arr` to combined Binance streams (catches ALL liquidations)
   - Fix symbol extraction: use `order.get('s')` not `stream.split('@')[0]`

2. **M2 node creation from Binance** (Phase 8 in forceorder handler):
   ```python
   if self._node_bridge is not None:
       liq_event = LiquidationEvent(
           timestamp=timestamp,
           symbol=symbol,
           wallet_address='BINANCE',
           liquidated_size=quantity,
           liquidation_price=price,
           side='LONG' if side == 'SELL' else 'SHORT',
           value=price * quantity,
           event_type='BINANCE_LIQUIDATION',
           exchange='BINANCE'
       )
       self._node_bridge.on_liquidation(liq_event)
   ```

**Limitation:** Binance liquidations are mostly on shitcoins not in our tracked symbols. Still enables cascade sniper detection and validates candidate zones when prices match.

**TODO:** Investigate HL node `--write-trades` not working. Should be primary liquidation source for HL-specific price levels.

---

## 2026-01-30: Oscillation Fix (Entry Grace Period)

**Issue:** System enters trades then exits 1-2 seconds later with $0 PNL. Recurring problem despite multiple previous fixes.

**Root Causes Identified:**

1. **Missing zone_width** in geometry entry context - tolerance check failed, falling back to strict ID comparison
2. **No grace period** - zone/condition changes between cycles trigger immediate EXIT
3. **Cross-strategy exits** - cascade sniper enters, geometry/SLBRS/EFFCS can exit immediately
4. **Zone instability** - supply/demand zones recompute each cycle, IDs drift

**Fixes Applied:**

1. **Geometry strategy** (`ep2_strategy_geometry.py`):
   - Store `zone_width` in `_record_entry_zone()` for proper tolerance check
   - Add 10s grace period before checking zone invalidation

2. **Policy adapter** (`runtime/policy_adapter.py`):
   - Add global `_entry_tracker` to track entry time per symbol
   - Block ALL EXIT proposals within `ENTRY_GRACE_PERIOD_SEC` (10s) of entry
   - Log blocked exits for debugging: `[PolicyAdapter] {symbol}: EXIT blocked (grace period: Xs < 10s)`

**Why this works:**
- Grace period allows zone/conditions to stabilize after entry
- Prevents any strategy from exiting another strategy's position immediately
- Still allows genuine exits after grace period (thesis invalidation)

**Trade-off:** Minimum 10s hold time, even if conditions change immediately. Acceptable because:
- Real thesis invalidation should take longer than 10s to develop
- Prevents noise-driven oscillation
- Can be tuned per-strategy if needed

---

## 2026-01-30: Candidate Zone Archive (Long-term Learning)

**Issue:** Expired zones were deleted, losing all accumulated price action data.

**Root cause:** Original design deleted zones on expiration without archival:
```python
del self._zones[symbol][zone_id]  # Data lost forever
```

**Impact:** System couldn't learn from history - each zone started fresh with no knowledge of what happened at that price level before.

**Fix:** Added `CandidateZoneArchive` class with SQLite persistence:
1. Archive zones on expiration AND validation (both outcomes valuable)
2. Query historical context when creating new zones at similar price levels
3. Enrich new zones with historical strength boost:
   - +0.1 per 5 historical visits (capped at +0.5)
   - +0.2 per validated zone at level (capped at +0.4)

**Database:** `candidate_zones.db` with indexed lookup by symbol/price bucket

**Key methods:**
- `archive_zone(zone, was_validated)` - persist zone data
- `get_historical_context(symbol, price, tolerance)` - aggregate historical stats
- `get_archive_stats()` - monitoring/metrics

**Long-term value:**
- System learns which levels repeatedly attract liquidations
- Validated zones boost confidence at that level in future
- Price action history accumulates across sessions

---

## 2026-01-30: Candidate Zone Memory Leak Fix

**Issue:** Paper trader using 11.5GB RAM with 97.8% CPU. Candidate zones accumulating without expiration.

**Root cause:** Two bugs in candidate zone implementation:
1. `decay_zones()` and `prune_candidate_zones()` methods existed but were never called
2. Decay calculation used `time_since_interaction` repeatedly, causing zones to over-decay on each call (exponential over-decay bug)

**Impact:**
- 800+ zones created but none expired
- Memory grew unboundedly as zones accumulated

**Fix:**
1. Register decay/prune in cleanup coordinator (`run_paper_trade.py`):
   ```python
   cleanup.register_pruner('candidate_zone_decay', service._node_bridge.decay_candidate_zones)
   cleanup.register_pruner('candidate_zone_prune', service._node_bridge.prune_candidate_zones)
   ```

2. Fix decay calculation to track `_last_decay_time` per zone:
   ```python
   last_decay = zone._last_decay_time if zone._last_decay_time > 0 else zone.created_at
   time_since_decay = now - last_decay
   zone.strength *= math.exp(-decay_rate * time_since_decay)
   zone._last_decay_time = now
   ```

3. Add logging when zones expire for observability

**Lesson:** Always verify cleanup/decay mechanisms are actually wired up, not just defined.

---

## 2026-01-30: M2 Node Creation Fix (Constitutional Violation)

**Issue:** System overreacting to tiny price changes, entering/exiting positions every few seconds on noise.

**Root cause:** Commit `fa48ff7` (Jan 29) created M2 nodes from proximity alerts (positions near liquidation) instead of only actual liquidations. This violated M2 constitutional spec:
> "Nodes are created ONLY on liquidation events."

**Impact:**
- 742+ M2 nodes created in 2 minutes from positions that never liquidated
- Geometry strategy created supply/demand zones from this noise
- System traded false zones, causing rapid entry/exit cycling

**Why it happened:** Lack of real liquidation data during initial implementation led to using proximity alerts as a proxy. This was a workaround that violated the design.

**Fix:** Removed M2 node creation from `_handle_proximity_alert()` in `observation_bridge.py`. Proximity data still flows to CASCADE_SNIPER for cluster detection (its intended purpose).

**Related fixes (same session):**
- `fd6b0f2`: Remove spurious EXIT on regime mismatch in SLBRS/EFFCS
- `eaaa41e`: Prevent zone oscillation with stable zone_id and geometric tolerance
- `06d9c6d`: Remove M2 node creation from proximity alerts

**Future enhancement:** Design document created for M2.5 "Candidate Zones" layer that properly bridges proximity data and validated M2 nodes. See `docs/M2_CANDIDATE_ZONES_DESIGN.md`. This would allow:
- Track potential zones from proximity clusters (without creating M2 nodes)
- Accumulate price action evidence at those levels
- When liquidation occurs, M2 node inherits the behavioral context
- Build knowledge over time: "more price action = richer understanding"

---

## 2026-01-30: HL Node Memory Fix (jemalloc)

**Issue:** hl-node has unbounded memory growth due to glibc malloc fragmentation. With 64GB RAM, node crashes after ~2 hours when hl-visor detects 95%+ memory usage and enters restart loop.

**Root cause:** glibc's malloc doesn't return freed memory to OS, causing fragmentation that grows unboundedly.

**Solution:** Use jemalloc memory allocator via LD_PRELOAD.

**Startup script:** `~/start-hl-node.sh`
```bash
#!/bin/bash
tmux kill-session -t hl-node 2>/dev/null
tmux new-session -d -s hl-node "LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 ~/hl-visor run-non-validator"
echo "Started hl-node in tmux session 'hl-node'"
echo "Attach with: tmux attach -t hl-node"
```

**Option 1 - tmux (interactive):**
```bash
# Install jemalloc (one time)
sudo apt install libjemalloc2

# Start node
~/start-hl-node.sh

# Attach to see output
tmux attach -t hl-node
# Ctrl+B, D to detach
```

**Option 2 - systemd (auto-start on boot):**
```bash
# Start/stop
sudo systemctl start hl-visor
sudo systemctl stop hl-visor

# View logs
journalctl -u hl-visor -f
```

Service file: `/etc/systemd/system/hl-visor.service`

**Source:** https://x.com/janklimo/status/1954393065210466695

---

## 2026-01-29: HL Node Startup Fix

**Issue:** Node crashed with "Missing config file: override_gossip_config.json"

**Fix:** Must start from `/home/ksiaz/hl` directory:
```bash
tmux new-session -d -s hl-node "cd /home/ksiaz/hl && /home/ksiaz/hl-node --chain Mainnet run-non-validator"
```

**Monitoring:** Check tmux output:
```bash
tmux capture-pane -t hyperliquid -p | tail -20
```

---

## Claude Session Notes

**Sudo access:** User can provide sudo when needed - just ask.

**DEV_NOTES.md is memory:** Check this file first before re-investigating solved issues. Contains solutions for:
- HL node startup (jemalloc, tmux vs systemd)
- Disk cleanup automation
- OOM fixes
- Zombie process prevention
- WebSocket fixes

**Use dev tools:** When debugging, use registered skills (`analysis`, `database`, `dev-reasoning`, `system-audit`, `validation`) instead of manual exploration.

---

## 2026-01-31: pytest Installation (Ubuntu 24.04)

**Issue:** Ubuntu 24.04 uses PEP 668 which prevents global pip installs. No virtual environment in this project.

**Solution:** Use pipx to install pytest in an isolated environment:

```bash
# Install pytest via pipx (one time)
pipx install pytest
pipx inject pytest pytest-asyncio

# Run tests
PYTHONPATH=. ~/.local/bin/pytest tests/unit/ -v

# Run specific test file
PYTHONPATH=. ~/.local/bin/pytest tests/unit/test_failure_handling.py -v
```

**Note:** `PYTHONPATH=.` is required because the project doesn't have a setup.py/pyproject.toml that installs the `runtime` package.

# Dev Notes

## 2026-02-01: Clock Loop Fix (Node Mode)

**Problem:** Execution cycles not being written to database. Clock loop stuck waiting.

**Root Cause:** `_drive_clock()` had overcomplicated condition:
```python
if self._last_stream_time is not None:  # Binance timestamp
    current_time = self._last_stream_time
elif self._node_bridge and self._node_bridge.get_latest_prices():  # Node has prices
    current_time = time.time()
else:
    await asyncio.sleep(0.5)
    continue  # STUCK HERE
```

The `get_latest_prices()` check was a dict that was empty at startup timing, causing the loop to wait forever even though node data was flowing (14000+ prices forwarded).

**Fix:** In node mode, just use wall clock. The node is synced, data is flowing. Don't wait for anything:
```python
if self._use_node_mode:
    current_time = time.time()
elif self._last_stream_time is not None:
    current_time = self._last_stream_time
else:
    await asyncio.sleep(0.5)
    continue
```

**Lesson:** Keep clock source selection simple. Two price dictionaries (`ObservationBridge._latest_prices` and `CollectorService._current_prices`) was unnecessary complexity. Node mode means we trust the node - use wall clock.

**File:** `runtime/collector/service.py` - `_drive_clock()` method

---

## 2026-02-03: HL-Visor "Duplicate Process" Panic

**Problem:** hl-visor crashes with panic: `more than one matching proc found for keywords`

**Symptoms:**
```
thread 'main' panicked at net_utils/src/system.rs:57:13:
more than one matching proc found for keywords matching_procs={...}
```

**Root Cause:** Claude's bash tool leaves parent shell wrapper processes with full command in `/proc/PID/cmdline`. If that command contains "hl-visor", the visor's process detection sees it as a duplicate.

Example stale process:
```
/bin/bash -c ... eval 'nohup ~/hl-visor run-non-validator ...' ...
```

**Wrong assumption:** Blamed hl-visor's "overly aggressive" detection. Actually, the detection was correct - there WERE multiple processes with "hl-visor" in cmdline.

**Fix:** Check for zombie/stale processes FIRST before assuming external tool bugs:
```bash
ps auxww | grep -E "hl-visor" | grep -v grep
pkill -9 -f "hl-visor"  # Kill all, then restart clean
```

**Lesson:** When external tools fail with "duplicate/conflict" errors, check your own environment first. Don't assume the tool is broken.

---

## 2026-02-03: Startup Script Fixes

**Problems:**
1. `~/hl/start-node.sh` didn't clean zombie processes before starting
2. Wrong adapter script (`run_adapter_service.py` vs `hl-node-adapter/server.py`)
3. Stale checkpoint in `~/.hl-node-adapter/checkpoint.json`
4. No unified startup - 3 separate commands, easy to get wrong

**Fixes:**
1. Updated `~/hl/start-node.sh` to kill zombies first and verify startup
2. Created `scripts/start_system.sh` - unified startup (node → adapter → paper)
3. Added `--fresh` flag to clear checkpoint
4. Created `scripts/stop_system.sh` for clean shutdown

**Correct startup order:**
```bash
./scripts/start_system.sh --fresh  # First time or after issues
./scripts/start_system.sh          # Normal restart
```

**Key files:**
- `~/hl/start-node.sh` - HL node only
- `hl-node-adapter/server.py` - Correct adapter (NOT run_adapter_service.py)
- `~/.hl-node-adapter/checkpoint.json` - Delete if stuck on old data

---

## 2026-02-03: Liquidation Reader Silent Failure Fix

**Problem:** Adapter was broadcasting 0 liquidations despite 19,778 liquidations in node data.

**Root Cause:** `LiquidationReader.initialize()` was seeking to END of file on fresh start:
```python
if self._open_file(latest_date, latest_hour):
    # Start from end of file (skip catchup)
    self._file_handle.seek(0, 2)  # Seek to end  <- SILENT FAILURE
    ...
```

Adapter started at hour 5 when hours 0-4 had 163MB of liquidation data. All skipped.

**Why this is critical:** Trading system relies on liquidation data for:
- Z-score calculations
- Cascade detection
- Regime classification
Starting with 0 data = all these metrics are wrong.

**Fix:** Changed default behavior to read from BEGINNING of current hour file:
```python
if skip_historical:
    # Explicitly requested: start from end of file
    self._file_handle.seek(0, 2)
else:
    # Default: start from beginning of current hour file
    self._file_position = 0
```

**Lesson:** Never silently discard data. If the system "works" with 0 data, it's hiding a failure. Trading systems must fail loudly when data is unavailable.

**File:** `hl-node-adapter/readers/liquidation_reader.py` - `initialize()` method

---

## 2026-02-03: gRPC Streaming vs Startup Ordering

**Problem:** Paper trade shows `liqs_ingested=0` even though adapter broadcast 202 liquidations.

**Root Cause:** gRPC streaming is fire-and-forget - no replay for late subscribers:
1. Adapter starts, reads hour 4 file (202 liquidations), broadcasts them
2. Paper trade starts LATER, subscribes to stream
3. gRPC doesn't buffer or replay - those 202 liquidations are gone
4. Current hour (5) has only 2 liquidations for non-focus symbols
5. Result: Paper trade sees 0 liquidations

**Why focus_symbols filter matters:**
```python
focus_symbols = ['BTC', 'ETH', 'SOL', 'HYPE', 'DOGE', 'XRP', 'BNB']
```
Hour 5's only liquidations: `xyz:SNDK` (not in focus) → filtered out.

**Correct startup order:**
1. Paper trade must start FIRST (or simultaneously)
2. Adapter should wait for at least one subscriber before historical replay
3. OR: Adapter should buffer recent liquidations for late subscribers

**Quick fix:** Start paper trade before adapter, or restart both together.

**Lesson:** Wall clock is authoritative. Node uses UTC hours. gRPC streaming = no history. Late subscribers miss data.

**Complete fix implemented:**
1. `LiquidationReader.initialize()` - Read from beginning with 1-hour lookback (not end of file)
2. `AdapterServer.run()` - Wait for liquidation subscriber before starting historical replay
3. `start_system.sh` - Ensure proper startup order

**Result after fix:**
```
prices_ingested=147, liqs_ingested=158, hl_symbols=6
```

**Files modified:**
- `hl-node-adapter/readers/liquidation_reader.py` - Added `_find_start_hour()`, `lookback_hours` param
- `hl-node-adapter/server.py` - Added subscriber wait before starting reader threads


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
tmux capture-pane -t hl-node -p | tail -20
```

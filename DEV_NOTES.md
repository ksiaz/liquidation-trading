
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

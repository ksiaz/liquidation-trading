# Project Move Plan: liquidation-trading

**From:** `/media/ksiaz/D/liquidation-trading`
**To:** `/home/ksiaz/liquidation-trading` (2TB drive)
**Reason:** Avoid Windows filesystem issues (line endings, access permissions)
**Status:** COMPLETED 2026-02-02

---

## Pre-Move Checklist

- [x] Stop all running processes:
  ```bash
  pkill -f run_paper_trade
  pkill -f hl-visor
  pkill -f "server.py.*50051"
  ```
- [x] Note current git status (any uncommitted changes)
- [x] Backup `.env` file separately (contains API keys)

---

## Step 1: Copy Project - COMPLETED

```bash
# Final path on 2TB drive
NEW_PATH="/home/ksiaz/liquidation-trading"

# Copied via rsync
rsync -av --progress /media/ksiaz/D/liquidation-trading/ "$NEW_PATH/"
```

---

## Step 2: Fix Line Endings - COMPLETED

Windows filesystem caused `\r\n` line endings. Verified clean - no CRLF detected.

```bash
cd /home/ksiaz/liquidation-trading

# Verified: no Windows line endings present
# (Files were already clean or converted during copy)
```

---

## Step 3: Ensure Directory Structure - COMPLETED

```bash
cd /home/ksiaz/liquidation-trading

# Verified: logs/ exists with 4GB execution.db
# All key directories present: hl-node-adapter/, runtime/, external_policy/
```

---

## Step 4: Update Editor - MANUAL

1. Open Antigravity Editor
2. File → Open Folder → Navigate to `/home/ksiaz/liquidation-trading`
3. Or update workspace file if using one

---

## Step 5: Claude Code Settings - NOT REQUIRED

The `.claude/` folder contains important data - DO NOT DELETE:
- `memory/` - Architecture rules, epistemic rules, layer definitions, session context
- `skills/` - 8 dev skills (analysis, database, testing, validation, etc.)
- MCP configs, startup checklist, documentation

**Note:** The `settings.local.json` contains bash permission patterns with old Windows
paths (D:/liquidation-trading). These are historical allowed commands and don't affect
functionality - they're just permission records. No path update needed.

**What's in `.claude/` (keep all of this):**
```
.claude/
├── memory/
│   ├── architecture/     # Layer definitions, epistemic rules
│   ├── current-session/  # Session context, unfinished work
│   ├── reference/        # Common commands, verification checklists
│   └── *.md              # Documentation map, project index
├── skills/               # 8 dev skills
│   ├── analysis/
│   ├── code-verification/
│   ├── database/
│   ├── dev-reasoning/
│   ├── system-audit/
│   ├── testing/
│   └── validation/
├── settings.local.json   # ← ONLY THIS needs path fix
└── *.md                  # MCP setup guides, session status
```

---

## Step 6: Verify .env - COMPLETED

```bash
cat /home/ksiaz/liquidation-trading/.env
# Verified: Contains API keys, no paths
```

Contents verified:
- `DB_HOST`, `DB_PORT`, etc. (PostgreSQL - not used currently)
- `COINGLASS_API_KEY`
- `GITHUB_TOKEN`

---

## Step 7: Test Python Imports - COMPLETED

```bash
cd /home/ksiaz/liquidation-trading

# Verified: imports work
python -c "from runtime.collector.service import CollectorService; print('OK')"
# Result: CollectorService: OK
```

---

## Step 8: Start HL Node (From Terminal, Not Claude)

Due to hl-visor process detection issues, start from a regular terminal:

```bash
# In a tmux or terminal session (NOT via Claude)
cd ~/hl
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 \
  ~/hl-visor run-non-validator \
  --write-fills \
  --write-order-statuses \
  --write-raw-book-diffs \
  --disable-output-file-buffering
```

Or use the existing script:
```bash
cd ~/hl && bash run-node.sh
```

Wait for sync (~20-25 minutes for full catchup).

---

## Step 9: Start Node Adapter

```bash
cd /home/ksiaz/liquidation-trading/hl-node-adapter
python server.py --port 50051 --data-path ~/hl/data
```

---

## Step 10: Start Paper Trading

```bash
cd /home/ksiaz/liquidation-trading
python scripts/run_paper_trade.py
```

---

## Step 11: Verify Data Flow

Check logs for:
```
Status: prices_ingested=XXX, liqs_ingested=XXX, errors=0, hl_symbols=10
```

- `prices_ingested` should be > 0 and incrementing
- `hl_symbols` should be 10
- `errors` should be 0

---

## Files That Reference Old Paths

| File | Type | Action |
|------|------|--------|
| `.claude/settings.local.json` | Claude permissions | `sed` replace paths |
| `.claude/memory/` | Architecture, session context | Keep as-is (no paths) |
| `.claude/skills/` | Dev skills | Keep as-is (no paths) |
| `.env` | API keys only | No changes needed |
| `logs/*.db` | SQLite databases | Relative paths, just copy |
| `hl-node-adapter/` | Node adapter | Relative, just copy |

---

## What Stays at ~/hl (No Move Needed)

The HL node installation stays at `~/hl/`:
- `~/hl-visor` - Visor binary
- `~/hl-node` - Node binary (downloaded by visor)
- `~/hl/data/` - Node data, replica files
- `~/hl/hyperliquid_data/` - State files

The project connects to this via `--data-path ~/hl/data`.

---

## Rollback Plan

If issues occur:
```bash
# Original location still exists
cd /media/ksiaz/D/liquidation-trading
python scripts/run_paper_trade.py
```

---

## Post-Move Cleanup

After confirming everything works on new drive:

```bash
# Optional: Remove old project (keep backup first)
# rm -rf /media/ksiaz/D/liquidation-trading
```

---

## Quick Reference Commands

```bash
# Project path
export PROJ="/home/ksiaz/liquidation-trading"

# Navigate
cd $PROJ

# Check git status
git status

# Run paper trading
python scripts/run_paper_trade.py

# Check logs
tail -f paper_trade.log
```

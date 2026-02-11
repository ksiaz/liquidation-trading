# HL Node Data File Formats

## Overview

The Hyperliquid node writes data to `~/hl/data/`. This document describes the file formats relevant to the node adapter.

---

## 1. replica_cmds (Oracle Prices)

**Path:** `~/hl/data/replica_cmds/{session}/{YYYYMMDD}/{block_number}`

**Structure:**
```
replica_cmds/
  2026-02-01T07:20:39Z/    # Session timestamp (new session on node restart)
    20260201/               # Date directory
      880050000             # Block file (starts at block 880050000)
      880060000             # Next block file
      ...
```

**File format:** JSON lines (one JSON object per line, one block per line)

**Block structure:**
```json
{
  "abci_block": {
    "time": "2026-02-01T07:47:58.120949985",
    "round": 880080042,
    "signed_action_bundles": [
      ["wallet_address", {
        "signed_actions": [
          {
            "action": {
              "type": "SetGlobalAction",
              "pxs": [
                ["78489", "78461"],    // Asset 0 (BTC): [oracle_px, mark_px]
                ["2425.5", "2424.1"],  // Asset 1 (ETH)
                [null, "0.37621"],     // Some assets have null oracle
                ...                    // 228 total assets
              ],
              "externalPerpPxs": [...],
              "usdtUsdcPx": "0.999...",
              "nativePx": "22.32"
            }
          }
        ]
      }]
    ]
  }
}
```

**Key fields:**
- `abci_block.time`: Block timestamp (ISO 8601)
- `abci_block.round`: Block height
- `pxs[asset_id][0]`: Oracle price (authoritative for liquidations)
- `pxs[asset_id][1]`: Mark price (used for unrealized PnL)

**Notes:**
- SetGlobalAction appears every ~40 blocks (not every block)
- 228 assets total, indexed by asset_id
- Oracle price can be null for some assets
- Prices are strings to preserve precision

---

## 2. node_fills (Liquidations)

**Path:** `~/hl/data/node_fills/hourly/{YYYYMMDD}/{hour}`

**Structure:**
```
node_fills/
  hourly/
    20260201/
      0                     # Hour 0 (00:00-00:59)
      1                     # Hour 1 (01:00-01:59)
      ...
      23                    # Hour 23
```

**File format:** JSON lines

**Fill structure:**
```json
["0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00", {
  "coin": "BTC",
  "px": "78215.0",
  "sz": "0.48023",
  "side": "B",              // "B" = buy, "S" = sell
  "time": 1769929473445,    // Unix timestamp (ms)
  "startPosition": "-136.21175",
  "dir": "Close Short",
  "closedPnl": "66.079648",
  "hash": "0x3bb1e94...",
  "oid": 308152002891,
  "crossed": false,
  "fee": "-1.126835",
  "tid": 565157617789996,   // Unique fill ID
  "liquidation": {          // Only present for liquidation fills
    "liquidatedUser": "0x16edade1fda05dda1ccfaf9ca1e9d0615fe691a7",
    "markPx": "78219.0",
    "method": "market"      // or "backstop"
  },
  "feeToken": "USDC"
}]
```

**Key fields for liquidations:**
- `[0]`: Wallet that received the fill (liquidator/HLP)
- `coin`: Asset symbol
- `side`: "B" (buy) or "S" (sell) - the fill side, not position side
- `px`: Execution price
- `sz`: Size filled
- `time`: Timestamp in milliseconds
- `liquidation.liquidatedUser`: Wallet that was liquidated
- `liquidation.markPx`: Mark price at liquidation
- `liquidation.method`: "market" or "backstop"

**Deriving position side:**
- If `side == "B"` and has `liquidation`: SHORT was liquidated (forced buy to close)
- If `side == "S"` and has `liquidation`: LONG was liquidated (forced sell to close)

**Notes:**
- Files are ~100-150MB per hour
- Not all fills are liquidations - check for `liquidation` field
- Approximately 800-1000 liquidations per hour during normal activity

---

## Asset Mapping

| asset_id | symbol |
|----------|--------|
| 0 | BTC |
| 1 | ETH |
| 2 | ATOM |
| 3 | MATIC |
| 4 | DYDX |
| 5 | SOL |
| ... | ... |

Full mapping available in `runtime/hyperliquid/node_adapter/asset_mapping.py` (archived in git).

---

## Reading Strategy

### For prices:
1. Find latest session in `replica_cmds/`
2. Find latest date directory
3. Tail the latest block file
4. Parse each new line, look for `SetGlobalAction` in signed_actions
5. Extract `pxs` array, map asset_id to symbol

### For liquidations:
1. Find latest date in `node_fills/hourly/`
2. Open latest hour file
3. Tail for new lines
4. Parse each line, check for `liquidation` field
5. Extract liquidation details

### File rotation:
- `replica_cmds`: New block file every ~10k blocks (~1.5 hours)
- `node_fills`: New file every hour at :00

---

## Sample Code

```python
# Read latest SetGlobalAction prices
import json
from pathlib import Path

replica_dir = Path.home() / "hl/data/replica_cmds"
latest_session = sorted(replica_dir.iterdir())[-1]
latest_date = sorted(latest_session.iterdir())[-1]
latest_block = sorted(latest_date.iterdir())[-1]

with open(latest_block) as f:
    for line in f:
        block = json.loads(line)
        for wallet, bundle in block['abci_block']['signed_action_bundles']:
            for sa in bundle['signed_actions']:
                if sa['action'].get('type') == 'SetGlobalAction':
                    pxs = sa['action']['pxs']
                    btc_oracle = pxs[0][0]  # "78489"
                    btc_mark = pxs[0][1]    # "78461"
```

```python
# Read liquidations
fills_dir = Path.home() / "hl/data/node_fills/hourly/20260201"
latest_hour = sorted(fills_dir.iterdir())[-1]

with open(latest_hour) as f:
    for line in f:
        data = json.loads(line)
        wallet, fill = data[0], data[1]
        if 'liquidation' in fill:
            print(f"Liquidation: {fill['coin']} {fill['sz']} @ {fill['px']}")
```

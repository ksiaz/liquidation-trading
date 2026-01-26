# Hyperliquid Node Data Discovery Report

**Date:** 2026-01-26
**Node Status:** LIVE (synced)
**Block Height:** ~873,760,000
**Mode:** Reality Snapshot (observation only)

---

## Executive Summary

This report documents all available data streams from a Hyperliquid non-validator node. The node provides:
- **Real-time block data** via file-based streams (JSON-lines)
- **Full exchange state** via msgpack snapshots
- **~14.5 blocks/second** throughput
- **228 assets** with oracle prices
- **21 action types** including orders, cancels, and liquidation triggers

---

## A. Endpoint Inventory

### File-Based Endpoints

| Endpoint | Path | Format | Size | Update Rate |
|----------|------|--------|------|-------------|
| replica_cmds | `/root/hl/data/replica_cmds/` | JSON-lines | 18+ GB/day | ~14.5 msg/sec |
| periodic_abci_states | `/root/hl/data/periodic_abci_states/` | msgpack | ~1 GB/10k blocks | Every ~12 min |
| abci_state.rmp | `/root/hl/hyperliquid_data/abci_state.rmp` | msgpack | ~1 GB | Continuous |
| visor_abci_state.json | `/root/hl/hyperliquid_data/visor_abci_state.json` | JSON | 223 bytes | Continuous |
| evm_block_and_receipts | `/root/hl/data/evm_block_and_receipts/` | Binary | 93 MB | Per EVM block |
| latency_summaries | `/root/hl/data/latency_summaries/` | JSON | 2.4 MB | Periodic |
| tcp_traffic | `/root/hl/data/tcp_traffic/` | JSON | 776 KB | Periodic |
| node_logs | `/root/hl/data/node_logs/` | JSON | 212 KB | Event-driven |

### TCP Endpoints

| Port | Protocol | Purpose | Auth |
|------|----------|---------|------|
| 4001 | Gossip P2P | Peer-to-peer communication | No |
| 4002 | Gossip P2P | Secondary P2P | No |
| 3999 | Internal | Unknown/metrics | Unknown |

---

## B. Primary Data Streams

### B.1 replica_cmds (Block Transaction Stream)

**Location:** `/root/hl/data/replica_cmds/{session}/{date}/{block_start}`

**Format:** Newline-delimited JSON (one block per line)

**Update Rate:** ~14.56 blocks/second (69ms average interval)

**Message Structure:**
```json
{
  "abci_block": {
    "time": "2026-01-26T11:02:39.467487791",
    "round": 1159006387,
    "parent_round": 1159006386,
    "hardfork": {"version": 74, "round": 1156521993},
    "proposer": "0x...",
    "signed_action_bundles": [
      ["wallet_address", {
        "signed_actions": [
          {
            "signature": {"r": "0x...", "s": "0x...", "v": 28},
            "action": { /* action payload */ },
            "nonce": 1769365193359
          }
        ]
      }]
    ]
  },
  "resps": null
}
```

**Payload Statistics:**
- Average: 193.61 KB per block
- Min: 0.66 KB
- Max: 885.31 KB
- Burstiness (CV): 0.27 (steady)

### B.2 visor_abci_state.json (Sync Status)

**Location:** `/root/hl/hyperliquid_data/visor_abci_state.json`

**Sample:**
```json
{
  "initial_height": 871512000,
  "height": 873759938,
  "scheduled_freeze_height": null,
  "consensus_time": "2026-01-26T11:02:32.346725263",
  "wall_clock_time": "2026-01-26T11:02:34.262515308",
  "reference_lag": null
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| initial_height | int | Checkpoint block number |
| height | int | Current block height |
| consensus_time | ISO8601 | Block timestamp |
| wall_clock_time | ISO8601 | Local processing time |
| reference_lag | null/float | Lag behind reference (if applicable) |

### B.3 abci_state.rmp (Full Exchange State)

**Location:** `/root/hl/hyperliquid_data/abci_state.rmp`

**Format:** MessagePack binary

**Size:** ~1 GB (999,470,714 bytes observed)

**Contains:**
- All user accounts (~1.4M users)
- All perp positions (~3,500 wallets with positions)
- Order book state
- Funding rates
- Vault data
- Context (block height, time)

---

## C. Action Types Observed

### C.1 Distribution (from 200 block sample)

| Action Type | Count | Percentage | Category |
|-------------|-------|------------|----------|
| order | 40,122 | 56.7% | EXECUTION |
| cancelByCloid | 14,381 | 20.3% | EXECUTION |
| cancel | 10,042 | 14.2% | EXECUTION |
| noop | 5,219 | 7.4% | INFRASTRUCTURE |
| batchModify | 491 | 0.7% | EXECUTION |
| scheduleCancel | 189 | 0.3% | EXECUTION |
| evmRawTx | 183 | 0.3% | EVM |
| modify | 158 | 0.2% | EXECUTION |
| updateLeverage | 61 | 0.1% | ACCOUNT |
| multiSig | 19 | <0.1% | ACCOUNT |
| perpDeploy | 12 | <0.1% | ADMIN |
| setReferrer | 11 | <0.1% | ACCOUNT |
| spotSend | 7 | <0.1% | TRANSFER |
| updateIsolatedMargin | 6 | <0.1% | ACCOUNT |
| **SetGlobalAction** | 4 | <0.1% | **RISK** |
| approveBuilderFee | 4 | <0.1% | ACCOUNT |
| voteAppHash | 3 | <0.1% | CONSENSUS |
| NetChildVaultPositionsAction | 2 | <0.1% | VAULT |
| approveAgent | 2 | <0.1% | ACCOUNT |
| usdClassTransfer | 1 | <0.1% | TRANSFER |
| twapOrder | 1 | <0.1% | EXECUTION |

### C.2 Action Schemas

#### order
```json
{
  "type": "order",
  "orders": [{
    "a": 103,           // asset ID (int)
    "b": true,          // buy (bool)
    "p": "0.0144",      // price (string)
    "s": "7567.4",      // size (string)
    "r": false,         // reduce-only (bool)
    "t": {"limit": {"tif": "Alo"}}  // order type
  }],
  "grouping": "na"
}
```

**Order Types (tif):**
- `Alo` - Add Liquidity Only (maker)
- `Ioc` - Immediate or Cancel
- `Gtc` - Good Till Cancel

#### cancel
```json
{
  "type": "cancel",
  "cancels": [{
    "a": 50,            // asset ID
    "o": 302979071201   // order ID
  }]
}
```

#### cancelByCloid
```json
{
  "type": "cancelByCloid",
  "cancels": [{
    "asset": 213,
    "cloid": "0x00000000000012487839490224484497"
  }]
}
```

#### batchModify
```json
{
  "type": "batchModify",
  "modifies": [{
    "oid": 302973854462,
    "order": {"a": 168, "b": true, "p": "0.01125", "s": "1800", "r": true, "t": {"limit": {"tif": "Alo"}}}
  }]
}
```

---

## D. SetGlobalAction (Liquidation Trigger)

**Frequency:** 1 every ~2.93 seconds (20.5 per minute)

**Source:** Validators only

**Purpose:** Updates oracle prices and triggers liquidations

### D.1 Structure

```json
{
  "type": "SetGlobalAction",
  "pxs": [
    ["mark_price", "oracle_price"],  // Asset 0 (BTC)
    ["mark_price", "oracle_price"],  // Asset 1 (ETH)
    // ... 228 assets total
  ],
  "externalPerpPxs": [
    ["symbol", "price"],  // 188 external perps
    // ...
  ],
  "usdtUsdcPx": "0.9992505620784411",
  "nativePx": "22.3245"  // HYPE price
}
```

### D.2 Sample Oracle Prices

| Asset | Index | Mark Price | Oracle Price |
|-------|-------|------------|--------------|
| BTC | 0 | $87,919.00 | $87,880.00 |
| ETH | 1 | $2,897.60 | $2,896.30 |
| SOL | 5 | $122.53 | $122.47 |
| DOGE | 12 | $0.12137 | $0.12129 |
| XRP | 16 | $0.3509 | $0.35066 |

### D.3 Key Observations

1. **Mark vs Oracle:** Small divergence (~0.04-0.1%) between mark and oracle prices
2. **Null marks:** Some assets have `null` mark price but valid oracle price
3. **228 assets:** Full price feed for all listed perpetuals
4. **188 external perps:** External reference prices (from CEXs)
5. **USDT/USDC peg:** Tracking at 0.9992 (~0.08% from parity)

### D.4 Liquidation Mechanism

SetGlobalAction does NOT contain explicit liquidation lists. Instead:

1. Validators broadcast oracle price updates via SetGlobalAction
2. Node applies prices to all positions
3. Positions with `margin_ratio < maintenance_margin` are liquidated
4. Liquidations appear as **forceOrder** actions in subsequent blocks

**To detect liquidations:**
- Monitor for `forceOrder` action type
- Track position changes in `abci_state.rmp`
- Compare position snapshots between blocks

---

## E. Data Quality Observations

| Metric | Status | Notes |
|--------|--------|-------|
| Timestamp monotonicity | ✅ PASS | Always increasing |
| Duplicate messages | ✅ PASS | 0 duplicates observed |
| Gap detection | ✅ PASS | No gaps in sequences |
| Field completeness | ✅ PASS | All expected fields present |
| Payload stability | ✅ PASS | Consistent structure |

---

## F. Data Categories

### MARKET_DATA
- `replica_cmds` - Order flow, trades (via order matching)
- `SetGlobalAction.pxs` - Oracle prices

### ACCOUNT_STATE
- `abci_state.rmp` - Positions, margins, balances
- `periodic_abci_states` - Historical snapshots

### EXECUTION
- `order`, `cancel`, `cancelByCloid`, `batchModify`, `modify`
- `twapOrder`, `scheduleCancel`

### RISK
- `SetGlobalAction` - Price updates, liquidation triggers
- `abci_state.rmp` - Liquidation prices, margin data
- `forceOrder` - Liquidation executions (not observed in sample)

### INFRASTRUCTURE
- `visor_abci_state.json` - Sync status
- `node_logs` - Connection health
- `noop`, `voteAppHash` - Consensus overhead

---

## G. Asset ID Mapping (Partial)

| ID | Symbol | ID | Symbol |
|----|--------|----|----- ---|
| 0 | BTC | 10 | LTC |
| 1 | ETH | 11 | ARB |
| 2 | ATOM | 12 | DOGE |
| 3 | MATIC | 13 | INJ |
| 4 | DYDX | 14 | SUI |
| 5 | SOL | 15 | kPEPE |
| 6 | AVAX | 16 | XRP |
| 7 | BNB | 17 | LINK |
| 8 | APE | ... | ... |
| 9 | OP | 227 | (last) |

---

## H. Next Steps for Research

1. **Monitor forceOrder actions** - These are the actual liquidation events
2. **Parse abci_state.rmp** - Extract full position data with liquidation prices
3. **Track position deltas** - Compare state snapshots to detect liquidated positions
4. **Measure SetGlobalAction→forceOrder latency** - Time between price update and liquidation execution

---

## I. File Sizes & Growth

| Directory | Current Size | Growth Rate |
|-----------|-------------|-------------|
| replica_cmds | 18 GB | ~2.5 GB/hour |
| periodic_abci_states | 9.3 GB | ~1 GB/hour |
| abci_state.rmp | 1 GB | Continuous overwrite |
| Total (daily) | ~80+ GB | Estimate |

---

*Report generated: 2026-01-26*
*Node version: hl-node (non-validator)*
*Data source: Local node files*

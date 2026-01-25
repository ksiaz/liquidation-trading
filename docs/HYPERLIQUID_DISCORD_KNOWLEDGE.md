# Hyperliquid Discord Knowledge Base

Extracted from Discord channels on 2026-01-24:
- #node-operators (24,805 messages)
- #api-traders (36,451 messages)
- #builders (23,577 messages)

---

## Table of Contents
1. [Node Operations](#node-operations)
2. [API Trading](#api-trading)
3. [Liquidation Data](#liquidation-data)
4. [Rate Limits](#rate-limits)
5. [Latency & Performance](#latency--performance)
6. [HyperEVM Development](#hyperevm-development)
7. [Common Issues & Solutions](#common-issues--solutions)
8. [Architecture Notes](#architecture-notes)

---

## Node Operations

### "early eof" Error

**Symptom:**
```
WARN >>> hl-node @@ gossip_server_connect_to_peer connected to abci stream from X.X.X.X:4001
WARN >>> hl-node @@ could not read abci state from X.X.X.X: early eof
```

**Cause:** Peers require bidirectional connectivity. They verify they can connect back to you on port 4001.

**Diagnosis:**
```bash
# Check for CGNAT
tracert -h 5 8.8.8.8
# If hop 2 is 100.64.0.0/10 range = CGNAT

# Test port externally
nc -zv <your_public_ip> 4001
```

**Solutions:**
| Problem | Fix |
|---------|-----|
| CGNAT | Request public IP from ISP |
| Router firewall | Forward ports 4000-4010 TCP |
| Windows firewall | Add inbound allow rules |
| iptables not updated | `sudo iptables -I INPUT -p tcp --dport 4001 -j ACCEPT` |
| Port forwarding UDP only | Change to TCP/UDP |
| ISP blocking ports | Call ISP to unblock |

**What WON'T fix it:**
- Adding more seed peers
- Waiting longer
- Restarting the node
- Changing `override_gossip_config.json`

### Getting Seed Peers

```bash
curl -X POST --header "Content-Type: application/json" \
  --data '{"type": "gossipRootIps"}' \
  https://api.hyperliquid.xyz/info
```

### Node Startup Flags

```bash
# Basic
./hl-visor run-non-validator

# With data output
./hl-visor run-non-validator \
  --write-trades \
  --write-fills \
  --write-order-statuses

# With API servers
./hl-visor run-non-validator \
  --serve-info \
  --serve-eth-rpc
```

### Port Requirements

| Port | Protocol | Purpose |
|------|----------|---------|
| 4001-4002 | TCP | Gossip P2P (required) |
| 4000-4010 | TCP | Full range recommended |
| 3001 | TCP | Info/EVM RPC server |

---

## API Trading

### WebSocket Subscriptions

- Max 10 unique users per IP for user-specific subscriptions
- 2000 WebSocket messages per minute limit
- Use WebSocket for orders (async, faster, no rate limit hit)

### Order Types

- **GTC** - Good till cancel
- **IOC** - Immediate or cancel
- **ALO** - Add liquidity only (maker only)
- Cancels and ALO orders are prioritized over GTC/IOC in blocks

### Signing

Two types of signing:
1. **Agent Signing** - for L1 trading actions
2. **User Signing** - for withdrawals, transfers

Reference: `github.com/nktkas/hyperliquid/blob/main/src/api/exchange/_base/_execute.ts`

### Common Gotchas

- **Address must be lowercase** in API calls
- **USA IPs are blocked** - need VPS outside USA
- **HIP-3 assets** (vntl, xyz, flx) need different handling
- **Don't set both limit and trigger** in same order
- **Account must be activated** (have spot balance) before trading
- **Use main account** for `sendAsset` with vaultAddress=null

---

## Liquidation Data

### No Native WebSocket for Market-Wide Liquidations

Multiple users have asked for this. Current options:

1. **Run your own node** with `--write-fills` flag
2. **gRPC service** from Dwellir: `github.com/dwellir-public/gRPC-code-examples/tree/main/hyperliquid-liquidation-bot`
3. **Hydromancer** - third-party service with liquidation fills endpoint
4. **userFills** subscription - shows YOUR liquidations only

### Liquidation Price Formula

From docs:
```
liq_price = entry_price - side × margin_available / position_size / (1 - l × side)
```

**Caveats:**
- Funding payments affect actual liquidation price
- Cross margin: changes in unrealized PnL in other positions affect it
- "The liquidation price shown has the certainty of the entry price, but may not be the actual liquidation price"

### Liquidation Price Code

TypeScript implementation: `github.com/hyperliquid-dex/ts-examples/blob/main/examples/LiquidationPx.tsx`

### Identifying Liquidations from Trades

- `setGlobalAction` updates oracle prices and triggers liquidations
- The hash of a liquidation trade is the `setGlobalAction` hash that triggered it
- No easy way to identify liquidations from the trades WebSocket subscription
- Best option: run non-validator node with `--write-fills`

---

## Rate Limits

### Limits

| Type | Limit |
|------|-------|
| API requests | 1200/min |
| WebSocket messages | 2000/min |
| User subscriptions per IP | 10 unique users |

### Rate Limit Earning

- 1 rate limit per $1 traded
- Growth mode markets (HIP-3): 0.1 per $1 traded
- Makers can pay for additional rate limit directly

### Tips

- Use WebSocket for orders to avoid rate limit consumption
- Batch operations where possible
- For 200+ symbols, rate limits become challenging

---

## Latency & Performance

### Best Region

**Tokyo (AWS ap-northeast-1)** - lowest latency to Hyperliquid

### Typical Latencies

| Operation | Latency |
|-----------|---------|
| Order placement | 200-500ms |
| WebSocket vs HTTP | WS is ~few ms faster |
| Mark price updates | ~1 second via WebSocket |
| HyperCore blocks | ~70ms |

### Tips

- Run in Tokyo for lowest latency
- Use WebSocket for orders (async, no headers)
- WebSocket async allows sending multiple orders without waiting for response
- Non-validator node can help with latency for data access
- Binance/OKX feeds are ~1ms (use for fast trading signals)

### Block Priority

Cancels and ALO (Add Liquidity Only) orders are prioritized over GTC and IOC orders in block inclusion.

---

## HyperEVM Development

### Precompiles

- **Address:** Read precompiles at specific addresses
- **Not all RPCs support precompiles** - verify before using
- Use `PrecompileLib.coreUserExists()` before sending tokens
- EVM→Core transfers happen in the next block

Reference article: `medium.com/@ambitlabs/demystifying-the-hyperliquid-precompiles-and-corewriter`

### CoreWriter

- **Address:** `0x3333333333333333333333333333333333333333`
- **Can fail silently** - no error handling
- **No guarantee** orders will execute
- **Can't modify/close orders** directly - need API wallet
- **Can chain multiple actions** in one call
- Vault transfers and some orders have deliberate delay (few seconds)

### Block Architecture

- **Small block by default**
- Use `evmUserModify` with `usingBigBlocks` to switch
- Account must be activated (have spot balance) for HyperCore txs

### Deployment Tips

- Testnet faucet requires mainnet activity
- HIP-3 uses `RegisterAsset2` (V2)
- Use `--legacy` flag if EIP1559 fails
- Address must be lowercase in API calls

### Multicall3

Deployed on HyperEVM at: `0xcA11bde05977b3631167028862bE2a173976CA11`

---

## Common Issues & Solutions

### "Cannot track more than 10 total users"
You've exceeded the 10 user limit for WebSocket subscriptions per IP.

### "Must deposit before performing actions"
Account not activated. Need spot balance first.

### "Invalid perp DEX"
Using V1 `RegisterAsset` instead of V2 `RegisterAsset2` for HIP-3.

### "Signature mismatch"
- Check `is_mainnet` flag matches your target network
- Verify encoding is correct
- Address must be lowercase

### Orders not executing via CoreWriter
CoreWriter can fail silently. Consider using API keys instead for guaranteed execution.

### VPS connection issues
- USA IPs are blocked
- Some datacenter IP ranges may be blocked
- Try different VPS provider or region

### Node keeps restarting
- Check `visor_abci_state.json` errors
- Verify ports 4001-4002 are accessible externally
- Check for early eof errors indicating connectivity issues

### GraphNode with HyperEVM
Need workaround for genesis block - create RPC proxy that returns fake genesis block for block 0.

---

## Architecture Notes

### HyperCore vs HyperEVM

- **HyperCore (L1)** - Orderbook, trades, liquidations, positions
- **HyperEVM** - EVM-compatible chain for smart contracts
- They interact via **CoreWriter** and **Precompiles**

### Data Sources

| Data Type | Source |
|-----------|--------|
| Real-time trades | WebSocket or node |
| Historical trades | Node with `--write-trades` or S3 |
| Liquidations (yours) | `userFills` subscription |
| Liquidations (all) | Node or gRPC service |
| EVM archive data | nanoreth + S3 |

### Third-Party Services

- **Dwellir** - gRPC API for orderbook and liquidation data
- **Quicknode** - gRPC streams for HyperCore
- **Hydromancer** - Liquidation fills endpoint

---

## Quick Reference

### API Endpoints

```bash
# Gossip peers
curl -X POST -H "Content-Type: application/json" \
  -d '{"type": "gossipRootIps"}' \
  https://api.hyperliquid.xyz/info

# Aligned quote token info
curl -X POST -H "Content-Type: application/json" \
  -d '{"type": "alignedQuoteTokenInfo", "token": <index>}' \
  https://api.hyperliquid.xyz/info
```

### Key GitHub Repos

- Official Python SDK: `github.com/hyperliquid-dex/hyperliquid-python-sdk`
- Official Node: `github.com/hyperliquid-dex/node`
- Liquidation bot: `github.com/dwellir-public/gRPC-code-examples/tree/main/hyperliquid-liquidation-bot`
- Liq price calc: `github.com/hyperliquid-dex/ts-examples/blob/main/examples/LiquidationPx.tsx`
- Archive node: `github.com/hl-archive-node/nanoreth`

### Key Addresses

- CoreWriter: `0x3333333333333333333333333333333333333333`
- Multicall3: `0xcA11bde05977b3631167028862bE2a173976CA11`

---

*Last updated: 2026-01-24*
*See also: HYPERLIQUID_GITHUB_RESOURCES.md, HYPERLIQUID_NODE_TROUBLESHOOTING.md*

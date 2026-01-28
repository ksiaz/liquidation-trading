# Hyperliquid Node Troubleshooting Guide

## Common Error: "early eof"

### Symptom
```
WARN >>> hl-node @@ gossip_server_connect_to_peer connected to abci stream from X.X.X.X:4001
WARN >>> hl-node @@ could not read abci state from X.X.X.X: early eof
```

Node connects outbound to peers but immediately disconnects with "early eof".

### Cause
Peers require **bidirectional connectivity**. They verify they can connect back to you on port 4001 before serving state. If they can't reach you, they close the connection.

### Diagnosis

1. **Check if ports are reachable from outside:**
   ```bash
   # From external server or ask someone
   nc -zv <your_public_ip> 4001
   ```

2. **Check for CGNAT:**
   ```bash
   tracert -h 5 8.8.8.8   # Windows
   traceroute -m 5 8.8.8.8  # Linux
   ```
   If hop 2 is in `100.64.0.0/10` range (e.g., `100.70.x.x`), you're behind CGNAT.

3. **Verify local setup:**
   ```bash
   # Windows - check port proxy
   netsh interface portproxy show all

   # Check firewall rules
   netsh advfirewall firewall show rule name=all dir=in | findstr "4001"

   # WSL - check if node is listening
   ss -tlnp | grep 4001
   ```

### Solutions

| Problem | Fix |
|---------|-----|
| CGNAT | Request public IP from ISP (~$2.5-10/month) |
| Router firewall | Forward ports 4000-4010 TCP to your machine |
| Windows firewall | Add inbound allow rules for ports 4001-4002 |
| ISP blocking ports | Ask ISP to unblock, or use VPS |

### What WON'T fix it
- Adding more seed peers
- Waiting longer
- Restarting the node
- Changing `override_gossip_config.json`

---

## Getting Seed Peers

### API Endpoint
```bash
curl -X POST --header "Content-Type: application/json" \
  --data '{"type": "gossipRootIps"}' \
  https://api.hyperliquid.xyz/info
```

### Generate override_gossip_config.json
```python
python runtime/hyperliquid/fetch_gossip_peers.py
```

### Manual Config
```json
{
  "root_node_ips": [{"Ip": "54.238.174.48"}, {"Ip": "35.190.230.32"}],
  "try_new_peers": true,
  "chain": "Mainnet"
}
```

Save to `~/override_gossip_config.json`

---

## Node Startup Flags

### Basic non-validator
```bash
./hl-visor run-non-validator
```

### Recommended Production Setup (with jemalloc)
```bash
# CRITICAL: Use jemalloc to prevent OOM crashes
# Without jemalloc: ~50GB RAM spikes, OOM with 64GB
# With jemalloc: ~29GB RAM stable

sudo apt install libjemalloc2

LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 \
  ./hl-visor run-non-validator \
  --write-fills \
  --write-order-statuses \
  --write-raw-book-diffs \
  --disable-output-file-buffering
```

### Flag Reference

| Flag | Output Location | Data Volume | Purpose |
|------|-----------------|-------------|---------|
| `--write-fills` | `node_fills/hourly/` | ~300MB/day | **Liquidations** (required for our system) |
| `--write-trades` | `node_trades/hourly/` | ~1.3GB/day | Trade data (overridden by --write-fills) |
| `--write-order-statuses` | `node_order_statuses/hourly/` | **~20GB/hr** | Order status history (for order_book_server) |
| `--write-raw-book-diffs` | `node_raw_book_diffs/hourly/` | **~3GB/hr** | Orderbook deltas (for order_book_server) |
| `--disable-output-file-buffering` | - | - | **Real-time data** (required for low latency) |
| `--batch-by-block` | - | - | One block per line (for order_book_server) |
| `--serve-info` | - | - | Local /info API endpoint |
| `--serve-eth-rpc` | - | - | Local EVM RPC endpoint |

### Flag Dependencies

**For liquidation trading (our use case):**
- `--write-fills` - Required (liquidation data from `node_fills`)
- `--disable-output-file-buffering` - Required (real-time streaming)

**For local orderbook (order_book_server):**
- `--write-order-statuses` - Required
- `--write-raw-book-diffs` - Required
- `--batch-by-block` - Required
- Note: order_book_server has known corruption bug after 30-40 min

### Data Pruning (CRITICAL)

`--write-order-statuses` and `--write-raw-book-diffs` generate **~25GB/hour**.

**Must implement pruning cron job:**
```bash
# /home/user/hl/prune-old-data.sh - keep last 4 hours
find ~/hl/data/node_order_statuses -type f -mmin +240 -delete
find ~/hl/data/node_raw_book_diffs -type f -mmin +240 -delete

# Crontab: 0 * * * * /home/user/hl/prune-old-data.sh
```

### With API servers
```bash
./hl-visor run-non-validator \
  --serve-info \
  --serve-eth-rpc
```

---

## Port Requirements

| Port | Protocol | Purpose |
|------|----------|---------|
| 4001 | TCP | Gossip P2P (required) |
| 4002 | TCP | Gossip P2P (required) |
| 4000-4010 | TCP | Full range recommended |
| 3001 | TCP | Info/EVM RPC server (optional) |

---

## CGNAT Explained

### Normal Setup (Works)
```
Internet → Your Router (Public IP) → Your PC
              Port forwarding works here
```

### CGNAT Setup (Broken)
```
Internet → ISP NAT (Public IP) → ISP Router (100.x.x.x) → Your Router → Your PC
              You don't control this
```

The public IP is shared among many customers. Your router never receives incoming connections because ISP's NAT drops them.

### Detection
```
Hop 1: 192.168.1.1   (your router)
Hop 2: 100.70.0.1    (CGNAT - problem!)
Hop 3+: public internet
```

RFC 6598 reserves `100.64.0.0/10` for CGNAT.

### Fix
Request public/static IP from ISP. Verify after:
- Router WAN IP should match `curl ifconfig.me`
- Hop 2 should NOT be `100.x.x.x`

---

## Other "early eof" - File Parsing

Different error when reading node output files:

### Cause
Reading file while node is still writing → partial line → parse error.

### Fix
- Buffer until newline before parsing
- Increase read delay
- Use inotify/fswatch to wait for write completion

---

## Related Tools

### reth-hl / nanoreth
- HyperEVM archive node based on reth
- Syncs from S3, not P2P (no port 4001 needed)
- For historical EVM data, not real-time L1 data
- GitHub: https://github.com/hl-archive-node/nanoreth

### order_book_server
- Builds local orderbook from node data
- Requires syncing node first
- Known issue: state corruption after 30-40 min (GitHub issue #3)

---

## Useful API Endpoints

### Gossip peers
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"type": "gossipRootIps"}' \
  https://api.hyperliquid.xyz/info
```

### Aligned quote token info
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"type": "alignedQuoteTokenInfo", "token": <token_index>}' \
  https://api.hyperliquid.xyz/info
```

---

## Memory Issues & OOM Prevention

### Problem: OOM Crashes with 64GB RAM

The default glibc malloc causes memory fragmentation, leading to:
- RAM spikes to ~50GB even with 64GB available
- OOM kills by kernel or systemd-oomd
- Session crashes

### Solution: jemalloc

```bash
sudo apt install libjemalloc2

# Run with jemalloc preloaded
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 ./hl-visor run-non-validator ...
```

**Results:**
| Metric | Default malloc | With jemalloc |
|--------|----------------|---------------|
| RAM usage | ~50GB (spikes) | ~29GB (stable) |
| OOM risk | High | Low |

### Official Hardware Requirements

| Node Type | CPU | RAM | Storage |
|-----------|-----|-----|---------|
| Validator | 32 cores | 128 GB | 1 TB SSD |
| Non-validator | 16 cores | 64 GB | 500 GB SSD |

### Data Generation Rates

With all flags enabled, expect:
- **~100 GB/day** total data generation
- `node_order_statuses`: ~20GB/hour
- `node_raw_book_diffs`: ~3GB/hour
- `node_fills`: ~15MB/hour

**Archive or delete old files regularly.**

### Startup Script Location

Production startup script: `~/hl/start-node.sh`
Prune script: `~/hl/prune-old-data.sh`
Cron: hourly prune keeping 4 hours of data

### tmux Session Management

```bash
# Start node (creates tmux session 'hl-node')
~/hl/start-node.sh

# Attach to view output
tmux attach -t hl-node

# Detach (node keeps running)
Ctrl+B, then D

# View logs without attaching
tail -f ~/hl/node.log

# Stop node
tmux kill-session -t hl-node

# Check if running
tmux has-session -t hl-node && echo "Running" || echo "Not running"
```

---

## References

- Node repo: https://github.com/hyperliquid-dex/node
- HyperEVM docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm
- nanoreth: https://github.com/hl-archive-node/nanoreth
- Discord: #node-operators channel
- jemalloc fix source: https://x.com/janklimo/status/1954393065210466695

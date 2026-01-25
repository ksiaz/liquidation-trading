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

### With data output
```bash
./hl-visor run-non-validator \
  --write-trades \
  --write-fills \
  --write-order-statuses
```

### With API servers
```bash
./hl-visor run-non-validator \
  --serve-info \       # /info endpoint
  --serve-eth-rpc      # EVM RPC endpoint
```

### Full setup
```bash
./hl-visor run-non-validator \
  --write-trades \
  --write-fills \
  --write-order-statuses \
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

## References

- Node repo: https://github.com/hyperliquid-dex/node
- HyperEVM docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm
- nanoreth: https://github.com/hl-archive-node/nanoreth
- Discord: #node-operators channel

# System Startup Guide

## Prerequisites

- HL node running (`~/hl/run-node.sh`)
- Python venv activated (`source venv/bin/activate`)

## Startup Order

### 1. HL Node (if not running)

```bash
# Check if running
pgrep -f hl-node

# Start in tmux (recommended)
tmux attach -t hyperliquid || tmux new -s hyperliquid '~/hl/run-node.sh 2>&1 | tee ~/hl/node.log'
```

### 2. gRPC Adapter

Bridges HL node data files to the trading system via gRPC.

```bash
cd ~/liquidation-trading/hl-adapter
source ../venv/bin/activate
nohup python -u server.py > /tmp/hl_adapter.log 2>&1 &

# Verify
tail -f /tmp/hl_adapter.log
# Should see: [GRPC] Server started on port 50051
```

### 3. Paper Trade

```bash
cd ~/liquidation-trading
source venv/bin/activate
nohup python -u scripts/run_paper_trade.py > /tmp/paper_trade.log 2>&1 &

# Verify
tail -f /tmp/paper_trade.log
# Should see: Node mode active: True
```

### 4. Verification Monitor (optional)

```bash
python -u scripts/verify_paper_trade.py --monitor --interval 60 > /tmp/verify_monitor.log 2>&1 &

# Check status
tail /tmp/verify_monitor.log
```

## Quick Start (All-in-One)

```bash
cd ~/liquidation-trading
source venv/bin/activate

# Start adapter
cd hl-adapter && nohup python -u server.py > /tmp/hl_adapter.log 2>&1 &
cd ..

# Wait for adapter
sleep 5

# Start paper trade
nohup python -u scripts/run_paper_trade.py > /tmp/paper_trade.log 2>&1 &

# Verify
sleep 10
tail /tmp/hl_adapter.log
tail /tmp/paper_trade.log
```

## Shutdown

```bash
# Stop paper trade
pkill -f run_paper_trade

# Stop adapter
pkill -f "hl-adapter.*server.py"

# Stop verification
pkill -f verify_paper_trade
```

## Health Checks

```bash
# Check processes
ps aux | grep -E "(paper_trade|server.py|verify)" | grep -v grep

# Check adapter stats
tail -1 /tmp/hl_adapter.log

# Check liquidation flow
tail /tmp/verify_monitor.log | grep "Last 5min"

# Check disk space
df -h /
```

## Troubleshooting

### Adapter not receiving data
```bash
# Check HL node is writing data
ls -la ~/hl/data/node_fills/hourly/$(date +%Y%m%d)/
```

### Paper trade not connecting
```bash
# Verify adapter is on port 50051
ss -tlnp | grep 50051
```

### Disk space low
```bash
# Manual cleanup
python scripts/cleanup_hl_data.py --keep-hours 6
```

## Log Locations

| Component | Log File |
|-----------|----------|
| HL Adapter | `/tmp/hl_adapter.log` |
| Paper Trade | `/tmp/paper_trade.log` |
| Verification | `/tmp/verify_monitor.log` |
| HL Node | `~/hl/node.log` |

#!/bin/bash
# Unified System Startup Script
# Starts: HL Node → Adapter → Paper Trade
#
# Usage: ./scripts/start_system.sh [--fresh]
#   --fresh: Clear adapter checkpoint to start from latest data

set -e
cd "$(dirname "$0")/.."
source venv/bin/activate

FRESH_START=false
if [[ "$1" == "--fresh" ]]; then
    FRESH_START=true
fi

echo "============================================================"
echo "SYSTEM STARTUP"
echo "============================================================"

# Step 1: Start HL Node (uses its own cleanup now)
echo "[1] Starting HL Node..."
~/hl/start-node.sh || exit 1

# Step 2: Wait for node to sync (check state file exists)
echo "[2] Waiting for node sync..."
for i in {1..30}; do
    if [[ -f ~/hl/hyperliquid_data/visor_abci_state.json ]]; then
        CONSENSUS=$(python3 -c "import json; print(json.load(open('$HOME/hl/hyperliquid_data/visor_abci_state.json'))['consensus_time'][:19])" 2>/dev/null || echo "reading...")
        echo "    Consensus: $CONSENSUS"
        break
    fi
    echo "    Waiting... ($i/30)"
    sleep 2
done

# Step 3: Clear checkpoint if fresh start
if [[ "$FRESH_START" == "true" ]]; then
    echo "[3] Clearing adapter checkpoint..."
    rm -f ~/.hl-adapter/checkpoint.json
fi

# Step 4: Start Adapter
echo "[4] Starting Adapter..."
tmux kill-session -t adapter 2>/dev/null || true
sleep 1
tmux new-session -d -s adapter "cd $(pwd)/hl-adapter && source ../venv/bin/activate && python server.py 2>&1 | tee ../adapter.log"
sleep 3

if ! lsof -i :50051 > /dev/null 2>&1; then
    echo "ERROR: Adapter failed. Check adapter.log"
    exit 1
fi
echo "    Adapter running on :50051"

# Step 5: Start Paper Trade
echo "[5] Starting Paper Trade..."
tmux kill-session -t paper 2>/dev/null || true
sleep 1
tmux new-session -d -s paper "source $(pwd)/venv/bin/activate && python scripts/run_paper_trade.py 2>&1 | tee paper_trade.log"
sleep 5

echo ""
echo "============================================================"
echo "SYSTEM STARTED"
echo "============================================================"
tmux list-sessions
echo ""
echo "Logs: tail -f paper_trade.log"
echo "Stop: ./scripts/stop_system.sh"

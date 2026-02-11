#!/bin/bash
# Stop all system components

echo "Stopping system..."

tmux kill-session -t paper 2>/dev/null && echo "  Stopped: paper"
tmux kill-session -t adapter 2>/dev/null && echo "  Stopped: adapter"
tmux kill-session -t hyperliquid 2>/dev/null && echo "  Stopped: hyperliquid (node)"

# Kill any remaining processes
pkill -9 -f "hl-visor" 2>/dev/null || true
pkill -9 -f "hl-node" 2>/dev/null || true

echo "Done."

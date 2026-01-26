#!/bin/bash
# Start the WSL TCP adapter

cd /mnt/d/liquidation-trading
python3 scripts/wsl_tcp_adapter.py --host 0.0.0.0 --port 8090

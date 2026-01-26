#!/usr/bin/env python3
"""
Run the Hyperliquid Node Adapter Service

Start this in WSL where the node data is located:
    python3 scripts/run_adapter_service.py

Then connect from Windows with:
    python scripts/run_adapter_client.py
"""

import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from runtime.hyperliquid.adapter_service.server import main

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Quick node data test - outputs to stdout for capture."""

import json
import time
from pathlib import Path
from datetime import datetime

REPLICA_PATH = '/root/hl/data/replica_cmds'

ASSET_ID_TO_COIN = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX",
    5: "SOL", 6: "BNB", 7: "AVAX", 8: "APE", 9: "OP",
    10: "LTC", 11: "ARB", 12: "DOGE", 13: "INJ", 14: "SUI",
    15: "kPEPE", 16: "LINK", 17: "CRV", 18: "LDO", 19: "RNDR",
}

def find_latest_file():
    """Find the latest replica file."""
    try:
        sessions = sorted(Path(REPLICA_PATH).iterdir(), reverse=True)
        for session in sessions:
            if not session.is_dir():
                continue
            dates = sorted(session.iterdir(), reverse=True)
            for date_dir in dates:
                if not date_dir.is_dir():
                    continue
                files = sorted(date_dir.iterdir(), reverse=True)
                for f in files:
                    if f.is_file() and f.name.isdigit():
                        return str(f)
    except Exception as e:
        print(f"Error finding file: {e}")
    return None

def parse_timestamp(time_str):
    if not time_str:
        return time.time()
    try:
        return datetime.fromisoformat(time_str[:26]).timestamp()
    except:
        return time.time()

def test_blocks(num_blocks=10):
    """Read and parse recent blocks."""
    latest_file = find_latest_file()
    if not latest_file:
        print("ERROR: No replica file found")
        return

    print(f"File: {latest_file}")

    # Read last N lines
    with open(latest_file, 'r') as f:
        lines = f.readlines()

    print(f"Total lines in file: {len(lines)}")

    # Process last N blocks
    blocks_to_process = lines[-num_blocks:] if len(lines) >= num_blocks else lines

    price_count = 0
    order_count = 0

    for i, line in enumerate(blocks_to_process):
        try:
            block = json.loads(line.strip())
            abci = block.get('abci_block', block)
            ts = parse_timestamp(abci.get('time', ''))

            bundles = abci.get('signed_action_bundles', [])

            for bundle in bundles:
                if not isinstance(bundle, list) or len(bundle) < 2:
                    continue

                wallet = bundle[0]
                bundle_data = bundle[1]

                for sa in bundle_data.get('signed_actions', []):
                    action = sa.get('action', {})
                    action_type = action.get('type')

                    if action_type == 'SetGlobalAction':
                        pxs = action.get('pxs', [])
                        # Sample first 5 prices
                        for asset_id in range(min(5, len(pxs))):
                            px = pxs[asset_id]
                            if px and len(px) >= 2 and px[0]:
                                coin = ASSET_ID_TO_COIN.get(asset_id, f"ASSET_{asset_id}")
                                oracle = float(px[0])
                                mark = float(px[1]) if px[1] else None
                                if i == len(blocks_to_process) - 1:  # Last block
                                    print(f"  {coin}: oracle=${oracle:,.2f}, mark=${mark:,.2f if mark else 0}")
                                price_count += 1

                    elif action_type == 'order':
                        for order in action.get('orders', []):
                            order_count += 1

        except Exception as e:
            print(f"Error parsing block {i}: {e}")

    print(f"\nSummary:")
    print(f"  Blocks processed: {len(blocks_to_process)}")
    print(f"  Price updates: {price_count}")
    print(f"  Orders: {order_count}")

if __name__ == '__main__':
    print("=" * 50)
    print("QUICK NODE DATA TEST")
    print("=" * 50)
    test_blocks(10)

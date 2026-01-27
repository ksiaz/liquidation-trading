#!/usr/bin/env python3
"""Sample SetGlobalAction messages from replica_cmds."""

import json
from pathlib import Path
from datetime import datetime

def main():
    # Find latest replica_cmds file
    replica_base = Path('~/hl/data/replica_cmds')

    # Get latest session dir
    session_dirs = sorted([d for d in replica_base.iterdir() if d.is_dir()])
    if not session_dirs:
        print("No session directories found")
        return

    latest_session = session_dirs[-1]
    print(f"Session: {latest_session.name}")

    # Get latest date dir
    date_dirs = sorted([d for d in latest_session.iterdir() if d.is_dir()])
    if not date_dirs:
        print("No date directories found")
        return

    date_dir = date_dirs[-1]

    # Get all block files
    block_files = sorted([f for f in date_dir.iterdir() if f.is_file()])

    print(f"Block files: {len(block_files)}")
    print(f"Scanning all files for SetGlobalAction...")
    print()

    set_global_actions = []
    total_blocks = 0

    for block_file in block_files:
        with open(block_file, 'r') as f:
            for line in f:
                total_blocks += 1
                try:
                    data = json.loads(line.strip())
                    block = data.get('abci_block', {})
                    bundles = block.get('signed_action_bundles', [])

                    for bundle in bundles:
                        if len(bundle) < 2:
                            continue
                        wallet = bundle[0]
                        actions_data = bundle[1]

                        for action in actions_data.get('signed_actions', []):
                            act = action.get('action', {})
                            if act.get('type') == 'SetGlobalAction':
                                set_global_actions.append({
                                    'time': block.get('time'),
                                    'round': block.get('round'),
                                    'file': block_file.name,
                                    'wallet': wallet,
                                    'action': act
                                })
                except Exception as e:
                    pass

    print(f"Total blocks scanned: {total_blocks}")
    print(f"SetGlobalAction messages found: {len(set_global_actions)}")
    print()

    if not set_global_actions:
        print("No SetGlobalAction found in current files.")
        print("These are sent by validators to update oracle prices and trigger liquidations.")
        return

    # Calculate frequency
    if len(set_global_actions) >= 2:
        times = []
        for sga in set_global_actions:
            try:
                dt = datetime.fromisoformat(sga['time'].replace('Z', '+00:00'))
                times.append(dt.timestamp())
            except:
                pass

        if len(times) >= 2:
            total_time = times[-1] - times[0]
            avg_interval = total_time / (len(times) - 1)
            print(f"Time span: {total_time:.1f} seconds")
            print(f"Average interval: {avg_interval:.2f} seconds")
            print(f"Frequency: {1/avg_interval:.2f} per second" if avg_interval > 0 else "")
            print()

    # Show samples
    print("=" * 80)
    print("SAMPLE SetGlobalAction MESSAGES")
    print("=" * 80)

    for i, sga in enumerate(set_global_actions[:10]):
        print()
        print(f"--- SetGlobalAction #{i+1} ---")
        print(f"Time: {sga['time']}")
        print(f"Round: {sga['round']}")
        print(f"File: {sga['file']}")
        print(f"Wallet: {sga['wallet'][:16]}...{sga['wallet'][-8:]}")

        act = sga['action']

        # Oracle prices - BTC and ETH
        pxs = act.get('pxs', [])
        print(f"\nOracle prices (mark, oracle) - {len(pxs)} assets:")

        # Asset mapping for common ones
        asset_names = {0: 'BTC', 1: 'ETH', 5: 'SOL', 12: 'DOGE', 16: 'XRP'}

        for idx, px in enumerate(pxs[:8]):
            name = asset_names.get(idx, f'Asset{idx}')
            if isinstance(px, list) and len(px) >= 2:
                print(f"  [{idx}] {name}: mark={px[0]}, oracle={px[1]}")
            else:
                print(f"  [{idx}] {name}: {px}")

        if len(pxs) > 8:
            print(f"  ... and {len(pxs)-8} more assets")

        # External perp prices
        ext_pxs = act.get('externalPerpPxs', [])
        if ext_pxs:
            print(f"\nExternal perp prices ({len(ext_pxs)}):")
            for px in ext_pxs[:5]:
                print(f"  {px}")
            if len(ext_pxs) > 5:
                print(f"  ... and {len(ext_pxs)-5} more")

        # Other fields
        print(f"\nusdtUsdcPx: {act.get('usdtUsdcPx', 'N/A')}")
        print(f"nativePx: {act.get('nativePx', 'N/A')}")

        # Check for liquidation-specific fields
        if 'liquidations' in act:
            print(f"\n!!! LIQUIDATIONS FIELD PRESENT: {act['liquidations']}")
        if 'forceOrders' in act:
            print(f"\n!!! FORCE ORDERS FIELD PRESENT: {act['forceOrders']}")

    # Full JSON dump of first message
    if set_global_actions:
        print()
        print("=" * 80)
        print("FULL RAW JSON OF FIRST SetGlobalAction")
        print("=" * 80)
        first = set_global_actions[0]
        print(json.dumps(first['action'], indent=2)[:3000])
        if len(json.dumps(first['action'])) > 3000:
            print("... (truncated)")


if __name__ == "__main__":
    main()

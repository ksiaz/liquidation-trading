#!/usr/bin/env python3
"""Extract SetGlobalAction samples from a single file."""

import json
import sys
from pathlib import Path

def main():
    # Use latest file
    file_path = Path('~/hl/data/replica_cmds/2026-01-26T09:46:38Z/20260126/873760000')

    if not file_path.exists():
        # Try to find any file
        base = Path('~/hl/data/replica_cmds')
        for session in sorted(base.iterdir(), reverse=True):
            if not session.is_dir():
                continue
            for date_dir in sorted(session.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                for f in sorted(date_dir.iterdir(), reverse=True):
                    if f.is_file():
                        file_path = f
                        break
                if file_path.exists():
                    break
            if file_path.exists():
                break

    print(f"Scanning: {file_path}")
    print(f"Size: {file_path.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    sga_count = 0
    samples = []

    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f):
            if 'SetGlobalAction' not in line:
                continue

            try:
                data = json.loads(line.strip())
                block = data.get('abci_block', {})

                for bundle in block.get('signed_action_bundles', []):
                    if len(bundle) < 2:
                        continue
                    wallet = bundle[0]

                    for action in bundle[1].get('signed_actions', []):
                        act = action.get('action', {})
                        if act.get('type') == 'SetGlobalAction':
                            sga_count += 1

                            if len(samples) < 5:
                                samples.append({
                                    'time': block.get('time'),
                                    'round': block.get('round'),
                                    'wallet': wallet,
                                    'action': act
                                })
            except Exception as e:
                pass

    print(f"SetGlobalAction count in file: {sga_count}")
    print()

    # Asset names for display
    asset_names = {
        0: 'BTC', 1: 'ETH', 2: 'ATOM', 3: 'MATIC', 4: 'DYDX', 5: 'SOL',
        6: 'AVAX', 7: 'BNB', 8: 'APE', 9: 'OP', 10: 'LTC', 11: 'ARB',
        12: 'DOGE', 13: 'INJ', 14: 'SUI', 15: 'kPEPE', 16: 'XRP', 17: 'LINK'
    }

    print("=" * 80)
    print("SetGlobalAction SAMPLES")
    print("=" * 80)

    for i, sample in enumerate(samples):
        print()
        print(f"### Sample {i+1} ###")
        print(f"Time: {sample['time']}")
        print(f"Round: {sample['round']}")
        print(f"Validator: {sample['wallet'][:16]}...{sample['wallet'][-8:]}")

        act = sample['action']
        pxs = act.get('pxs', [])

        print(f"\nOracle Prices ({len(pxs)} assets):")
        print(f"  Format: [mark_price, oracle_price]")

        for idx in [0, 1, 5, 12, 16]:  # BTC, ETH, SOL, DOGE, XRP
            if idx < len(pxs):
                name = asset_names.get(idx, f'Asset{idx}')
                px = pxs[idx]
                if isinstance(px, list) and len(px) >= 2:
                    print(f"  {name:6s}: mark=${float(px[0]):,.2f}, oracle=${float(px[1]):,.2f}")

        ext_pxs = act.get('externalPerpPxs', [])
        if ext_pxs:
            print(f"\nExternal Perp Prices ({len(ext_pxs)}):")
            for item in ext_pxs[:5]:
                if isinstance(item, list) and len(item) >= 2:
                    print(f"  {item[0]}: {item[1]}")

        print(f"\nUSDT/USDC: {act.get('usdtUsdcPx', 'N/A')}")
        print(f"Native (HYPE): {act.get('nativePx', 'N/A')}")

    # Calculate frequency
    if len(samples) >= 2:
        from datetime import datetime
        times = []
        for s in samples:
            try:
                dt = datetime.fromisoformat(s['time'].replace('Z', '+00:00'))
                times.append(dt.timestamp())
            except:
                pass

        if len(times) >= 2:
            span = times[-1] - times[0]
            interval = span / (len(times) - 1)
            print()
            print(f"Frequency: 1 every {interval:.2f} seconds ({60/interval:.1f} per minute)")

    # Full JSON of first one
    if samples:
        print()
        print("=" * 80)
        print("FULL SetGlobalAction JSON (first sample)")
        print("=" * 80)
        full_json = json.dumps(samples[0]['action'], indent=2)
        if len(full_json) > 4000:
            print(full_json[:4000])
            print("... (truncated)")
        else:
            print(full_json)


if __name__ == "__main__":
    main()

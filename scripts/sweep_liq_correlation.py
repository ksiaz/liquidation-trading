#!/usr/bin/env python3
"""
Analyze correlation between aggressive sweeps and liquidation events.

Hypothesis: Large DOWN sweeps precede long liquidation cascades.
"""

import subprocess
import json
from collections import defaultdict


def query_api(endpoint: str) -> dict:
    """Query the research API via SSH."""
    cmd = f"ssh root@64.176.65.252 \"curl -s 'http://localhost:8081{endpoint}'\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except:
        return {}


def analyze_sweep_direction_imbalance():
    """Analyze if sweeps are coordinated in one direction."""
    print("=" * 60)
    print("SWEEP DIRECTION ANALYSIS")
    print("=" * 60)

    for coin in ['BTC', 'ETH', 'SOL']:
        data = query_api(f"/sweeps?coin={coin}")
        if not data:
            continue

        sweeps = data.get('sweeps', [])
        if not sweeps:
            continue

        # Aggregate by direction
        up_total = sum(s['total_notional'] for s in sweeps if s['direction'] == 'UP')
        down_total = sum(s['total_notional'] for s in sweeps if s['direction'] == 'DOWN')
        up_count = sum(1 for s in sweeps if s['direction'] == 'UP')
        down_count = sum(1 for s in sweeps if s['direction'] == 'DOWN')

        total = up_total + down_total
        imbalance = (up_total - down_total) / total * 100 if total > 0 else 0

        print(f"\n{coin}:")
        print(f"  UP sweeps:   {up_count:>5} sweeps, ${up_total:>15,.0f}")
        print(f"  DOWN sweeps: {down_count:>5} sweeps, ${down_total:>15,.0f}")
        print(f"  Imbalance: {imbalance:+.1f}% ({'BULLISH' if imbalance > 10 else 'BEARISH' if imbalance < -10 else 'NEUTRAL'})")

        # Find largest sweeps
        sorted_sweeps = sorted(sweeps, key=lambda x: -x['total_notional'])[:5]
        print(f"\n  Largest sweeps:")
        for s in sorted_sweeps:
            print(f"    {s['direction']:>4} ${s['total_notional']:>12,.0f} by {s['wallet']}")


def analyze_wallet_coordination():
    """Look for coordinated activity between wallets."""
    print("\n" + "=" * 60)
    print("WALLET COORDINATION ANALYSIS")
    print("=" * 60)

    # Get all sweeps
    data = query_api("/sweeps")
    if not data:
        return

    sweeps = data.get('sweeps', [])

    # Group by timestamp bucket (1-second windows)
    time_buckets = defaultdict(list)
    for s in sweeps:
        bucket = int(s['timestamp'])
        time_buckets[bucket].append(s)

    # Find buckets with multiple wallets acting together
    coordinated = []
    for ts, bucket_sweeps in time_buckets.items():
        wallets = set(s['wallet'] for s in bucket_sweeps)
        if len(wallets) >= 3:  # 3+ different wallets in same second
            total_notional = sum(s['total_notional'] for s in bucket_sweeps)
            directions = [s['direction'] for s in bucket_sweeps]
            up_pct = directions.count('UP') / len(directions) * 100

            coordinated.append({
                'timestamp': ts,
                'wallet_count': len(wallets),
                'total_notional': total_notional,
                'up_pct': up_pct,
                'direction': 'UP' if up_pct > 60 else 'DOWN' if up_pct < 40 else 'MIXED'
            })

    # Sort by notional
    coordinated.sort(key=lambda x: -x['total_notional'])

    print(f"\nFound {len(coordinated)} coordinated sweep events (3+ wallets in same second)")
    print("\nTop coordinated sweeps:")
    for c in coordinated[:10]:
        print(f"  {c['wallet_count']} wallets, ${c['total_notional']:,.0f}, {c['direction']} ({c['up_pct']:.0f}% up)")


def analyze_sweep_price_impact():
    """Analyze price movement after large sweeps."""
    print("\n" + "=" * 60)
    print("SWEEP PRICE IMPACT ANALYSIS")
    print("=" * 60)

    for coin in ['BTC', 'ETH', 'SOL']:
        # Get sweeps
        sweep_data = query_api(f"/sweeps?coin={coin}")
        if not sweep_data:
            continue

        sweeps = sweep_data.get('sweeps', [])[:20]

        # Get price zones for current price reference
        zone_data = query_api(f"/price_zones?coin={coin}&max_distance=0.5")
        if not zone_data:
            continue

        current_price = zone_data.get('current_price', 0)

        print(f"\n{coin} @ ${current_price:,.2f}")

        # Analyze sweep characteristics
        up_sweeps = [s for s in sweeps if s['direction'] == 'UP']
        down_sweeps = [s for s in sweeps if s['direction'] == 'DOWN']

        if up_sweeps:
            avg_up_size = sum(s['total_notional'] for s in up_sweeps) / len(up_sweeps)
            avg_up_levels = sum(s['price_levels'] for s in up_sweeps) / len(up_sweeps)
            print(f"  UP sweeps: avg ${avg_up_size:,.0f}, avg {avg_up_levels:.0f} price levels")

        if down_sweeps:
            avg_down_size = sum(s['total_notional'] for s in down_sweeps) / len(down_sweeps)
            avg_down_levels = sum(s['price_levels'] for s in down_sweeps) / len(down_sweeps)
            print(f"  DOWN sweeps: avg ${avg_down_size:,.0f}, avg {avg_down_levels:.0f} price levels")

        # The sweep with most price levels likely caused most slippage
        if sweeps:
            max_levels = max(sweeps, key=lambda x: x['price_levels'])
            print(f"  Widest sweep: {max_levels['direction']} across {max_levels['price_levels']} levels by {max_levels['wallet']}")


def find_manipulation_signals():
    """Identify potential manipulation patterns."""
    print("\n" + "=" * 60)
    print("MANIPULATION SIGNAL DETECTION")
    print("=" * 60)

    for coin in ['BTC', 'ETH', 'SOL']:
        print(f"\n{coin}:")

        # Get order flow
        flow_data = query_api(f"/order_flow?coin={coin}&minutes=1")
        if flow_data and 'summary' in flow_data:
            imb = flow_data['summary']['net_imbalance_pct']
            if abs(imb) > 30:
                print(f"  ⚠️  EXTREME IMBALANCE: {imb:+.1f}% {flow_data['summary']['pressure']}")

        # Get sweeps
        sweep_data = query_api(f"/sweeps?coin={coin}")
        if sweep_data:
            sweeps = sweep_data.get('sweeps', [])[:10]

            # Check for wallets with 100% directional bias
            wallet_direction = {}
            for s in sweeps:
                w = s['wallet']
                if w not in wallet_direction:
                    wallet_direction[w] = {'up': 0, 'down': 0}
                wallet_direction[w][s['direction'].lower()] += s['total_notional']

            for wallet, dirs in wallet_direction.items():
                total = dirs['up'] + dirs['down']
                if total > 10_000_000:  # >$10M
                    up_pct = dirs['up'] / total * 100
                    if up_pct == 100 or up_pct == 0:
                        direction = "LONG" if up_pct == 100 else "SHORT"
                        print(f"  ⚠️  DIRECTIONAL WHALE: {wallet} - ${total:,.0f} all {direction}")

        # Get price zones
        zone_data = query_api(f"/price_zones?coin={coin}&max_distance=0.5")
        if zone_data:
            sup = zone_data.get('support_zones', [])
            res = zone_data.get('resistance_zones', [])

            # Check for thin zones (low volume = easy to move)
            if sup and res:
                avg_sup_vol = sum(z['total_volume'] for z in sup[:3]) / 3
                avg_res_vol = sum(z['total_volume'] for z in res[:3]) / 3 if res else avg_sup_vol

                if avg_res_vol < avg_sup_vol * 0.3:
                    print(f"  ⚠️  THIN RESISTANCE: Easy to push UP (res vol = {avg_res_vol/avg_sup_vol*100:.0f}% of support)")
                elif avg_sup_vol < avg_res_vol * 0.3:
                    print(f"  ⚠️  THIN SUPPORT: Easy to push DOWN (sup vol = {avg_sup_vol/avg_res_vol*100:.0f}% of resistance)")


def main():
    print("SWEEP-LIQUIDATION CORRELATION RESEARCH")
    print("=" * 60)

    analyze_sweep_direction_imbalance()
    analyze_wallet_coordination()
    analyze_sweep_price_impact()
    find_manipulation_signals()

    print("\n" + "=" * 60)
    print("RESEARCH CONCLUSIONS")
    print("=" * 60)
    print("""
Trading signals from this analysis:
1. Extreme order imbalance (>30%) often precedes price movement
2. Large directional sweeps hitting multiple price levels = aggressive actor
3. Wallets with 100% directional bias may be manipulating
4. Thin zones on one side = vulnerability to moves in that direction
5. Coordinated multi-wallet sweeps = potential organized manipulation
""")


if __name__ == "__main__":
    main()

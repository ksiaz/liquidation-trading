#!/usr/bin/env python3
"""
Run research queries against the VM research API.
"""

import subprocess
import json


def query_api(endpoint: str) -> dict:
    """Query the research API via SSH."""
    cmd = f"ssh root@64.176.65.252 \"curl -s 'http://localhost:8081{endpoint}'\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return {}
    try:
        return json.loads(result.stdout)
    except:
        print(f"Parse error: {result.stdout[:200]}")
        return {}


def analyze_order_flow():
    """Analyze order flow for major coins."""
    print("=" * 60)
    print("ORDER FLOW ANALYSIS")
    print("=" * 60)

    for coin in ['BTC', 'ETH', 'SOL']:
        data = query_api(f"/order_flow?coin={coin}&minutes=1")
        if not data or 'summary' not in data:
            continue

        s = data['summary']
        print(f"\n{coin}:")
        print(f"  Net Imbalance: {s['net_imbalance_pct']:+.1f}% ({s['pressure']} pressure)")
        print(f"  Buy Volume:  ${s['total_buy_volume']:>15,.0f}")
        print(f"  Sell Volume: ${s['total_sell_volume']:>15,.0f}")

        # Show recent windows
        windows = data.get('windows', [])[-10:]
        if windows:
            print("  Recent 1-min windows:")
            for w in windows:
                bar_len = min(20, int(abs(w['imbalance_pct']) / 3))
                bar = '█' * bar_len
                arrow = '↑' if w['imbalance_pct'] > 0 else '↓'
                print(f"    {arrow} {w['imbalance_pct']:+6.1f}% {bar}")


def analyze_price_zones():
    """Analyze support/resistance zones."""
    print("\n" + "=" * 60)
    print("PRICE ZONE ANALYSIS (Magnetism)")
    print("=" * 60)

    for coin in ['BTC', 'ETH', 'SOL']:
        data = query_api(f"/price_zones?coin={coin}&max_distance=1")
        if not data or 'current_price' not in data:
            continue

        print(f"\n{coin} @ ${data['current_price']:,.2f}")

        # Resistance zones
        res = data.get('resistance_zones', [])[:5]
        if res:
            print("  RESISTANCE (above):")
            for z in res:
                imb = "BUY" if z['imbalance_pct'] > 0 else "SELL"
                print(f"    ${z['price']:,.2f} (+{z['distance_pct']:.2f}%) - ${z['total_volume']:,.0f} [{imb} {z['imbalance_pct']:+.0f}%]")

        # Support zones
        sup = data.get('support_zones', [])[:5]
        if sup:
            print("  SUPPORT (below):")
            for z in sup:
                imb = "BUY" if z['imbalance_pct'] > 0 else "SELL"
                print(f"    ${z['price']:,.2f} ({z['distance_pct']:.2f}%) - ${z['total_volume']:,.0f} [{imb} {z['imbalance_pct']:+.0f}%]")


def analyze_sweeps():
    """Analyze aggressive market sweeps."""
    print("\n" + "=" * 60)
    print("AGGRESSIVE SWEEP DETECTION")
    print("=" * 60)

    for coin in ['BTC', 'ETH', 'SOL']:
        data = query_api(f"/sweeps?coin={coin}")
        if not data:
            continue

        print(f"\n{coin}: {data.get('sweep_count', 0)} sweeps detected")

        sweeps = data.get('sweeps', [])[:10]
        up_sweeps = [s for s in sweeps if s['direction'] == 'UP']
        down_sweeps = [s for s in sweeps if s['direction'] == 'DOWN']

        if up_sweeps:
            print("  TOP UP SWEEPS (potential short squeeze):")
            for s in up_sweeps[:3]:
                print(f"    {s['wallet']} - {s['order_count']} orders, ${s['total_notional']:,.0f}")

        if down_sweeps:
            print("  TOP DOWN SWEEPS (potential long liquidation):")
            for s in down_sweeps[:3]:
                print(f"    {s['wallet']} - {s['order_count']} orders, ${s['total_notional']:,.0f}")


def find_suspicious_wallets():
    """Find wallets with suspicious behavior."""
    print("\n" + "=" * 60)
    print("SUSPICIOUS WALLET ANALYSIS")
    print("=" * 60)

    # Get sweeps to find active wallets
    data = query_api("/sweeps?coin=BTC")
    if not data:
        return

    sweeps = data.get('sweeps', [])[:20]

    # Analyze top sweeping wallets
    wallet_stats = {}
    for s in sweeps:
        w = s['wallet']
        if w not in wallet_stats:
            wallet_stats[w] = {'up': 0, 'down': 0, 'total': 0}
        wallet_stats[w][s['direction'].lower()] += s['total_notional']
        wallet_stats[w]['total'] += s['total_notional']

    # Sort by total notional
    sorted_wallets = sorted(wallet_stats.items(), key=lambda x: -x[1]['total'])[:10]

    print("\nTop sweeping wallets:")
    for wallet, stats in sorted_wallets:
        up_pct = stats['up'] / stats['total'] * 100 if stats['total'] > 0 else 0
        direction = "LONG bias" if up_pct > 60 else "SHORT bias" if up_pct < 40 else "Neutral"
        print(f"  {wallet}")
        print(f"    Total: ${stats['total']:,.0f} | UP: ${stats['up']:,.0f} | DOWN: ${stats['down']:,.0f}")
        print(f"    Direction: {direction} ({up_pct:.0f}% up)")


def main():
    print("MANIPULATION RESEARCH - Node Data Analysis")
    print("=" * 60)

    analyze_order_flow()
    analyze_price_zones()
    analyze_sweeps()
    find_suspicious_wallets()

    print("\n" + "=" * 60)
    print("KEY INSIGHTS")
    print("=" * 60)
    print("""
1. Order flow imbalance can signal short-term direction
2. High-activity zones often act as price magnets
3. Large sweeps may precede liquidation cascades
4. Wallets with consistent directional bias may be manipulation
""")


if __name__ == "__main__":
    main()

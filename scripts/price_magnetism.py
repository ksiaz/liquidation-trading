#!/usr/bin/env python3
"""
Price Magnetism Research

Hypothesis: Price tends to be "attracted" to zones where:
1. Stop-loss clusters exist
2. Liquidation prices are concentrated
3. Large resting orders create liquidity walls

This script analyzes node data to find:
- High-activity price zones (where many orders exist)
- Order imbalance at different price levels
- Distance from current price to these zones
- Historical "touches" - did price reach these zones?
"""

import json
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

# Asset mapping
ASSETS = {
    0: "BTC", 1: "ETH", 5: "SOL", 12: "DOGE", 16: "XRP", 11: "ARB",
    6: "AVAX", 7: "BNB", 17: "LINK", 27: "AAVE", 46: "HYPE"
}


@dataclass
class PriceZone:
    """A price level with accumulated order activity."""
    price: float
    buy_volume: float = 0
    sell_volume: float = 0
    buy_count: int = 0
    sell_count: int = 0
    cancel_count: int = 0

    @property
    def total_volume(self) -> float:
        return self.buy_volume + self.sell_volume

    @property
    def imbalance(self) -> float:
        """Positive = buy pressure, negative = sell pressure."""
        total = self.total_volume
        if total == 0:
            return 0
        return (self.buy_volume - self.sell_volume) / total

    @property
    def cancel_rate(self) -> float:
        """Rate of orders that were canceled vs placed."""
        total = self.buy_count + self.sell_count
        if total == 0:
            return 0
        return self.cancel_count / total


def fetch_current_prices() -> Dict[str, float]:
    """Fetch actual current prices from API."""
    import requests
    try:
        # First get meta for coin name mapping
        meta_resp = requests.post('https://api.hyperliquid.xyz/info',
                                  json={'type': 'meta'}, timeout=10)
        if meta_resp.status_code != 200:
            return {}

        meta = meta_resp.json()
        universe = meta.get('universe', [])

        # Build index -> name mapping
        idx_to_name = {}
        for i, asset in enumerate(universe):
            idx_to_name[str(i)] = asset.get('name', f'A{i}')

        # Get all mid prices
        resp = requests.post('https://api.hyperliquid.xyz/info',
                            json={'type': 'allMids'}, timeout=10)
        if resp.status_code == 200:
            raw = resp.json()
            prices = {}
            for sym, price_str in raw.items():
                if price_str:
                    # Convert symbol to name if needed
                    if sym.startswith('@'):
                        idx = sym[1:]
                        name = idx_to_name.get(idx, sym)
                    elif sym.isdigit():
                        name = idx_to_name.get(sym, f'A{sym}')
                    else:
                        name = sym
                    prices[name] = float(price_str)
            return prices
    except Exception as e:
        print(f"Error fetching prices: {e}")
    return {}


def fetch_block_data(num_lines: int = 3000) -> str:
    """Fetch recent block data from node."""
    print(f"Fetching {num_lines} lines of block data...")

    # Get latest block file
    cmd = "ssh root@64.176.65.252 'ls -t ~/hl/data/replica_cmds/*/2*/* | head -1'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return ""

    block_file = result.stdout.strip()
    print(f"Block file: {block_file}")

    # Fetch data
    cmd = f"ssh root@64.176.65.252 'tail -{num_lines} {block_file}'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return ""

    return result.stdout


def parse_orders(block_data: str) -> Tuple[List[dict], Dict[str, float]]:
    """Parse orders from block data."""
    orders = []
    prices = {}

    for line in block_data.split('\n'):
        if not line.strip().startswith('{'):
            continue
        try:
            d = json.loads(line)
            ab = d.get('abci_block', {})

            for bundle in ab.get('signed_action_bundles', []):
                if len(bundle) < 2:
                    continue
                wallet = bundle[0]

                for sa in bundle[1].get('signed_actions', []):
                    action = sa.get('action', {})
                    atype = action.get('type', '')

                    if atype == 'order':
                        for order in action.get('orders', []):
                            asset = order.get('a', 0)
                            coin = ASSETS.get(asset, f"A{asset}")
                            price = float(order.get('p', 0))
                            size = float(order.get('s', 0))
                            side = 'BUY' if order.get('b') else 'SELL'

                            if price > 0 and size > 0:
                                orders.append({
                                    'wallet': wallet,
                                    'coin': coin,
                                    'side': side,
                                    'price': price,
                                    'size': size,
                                    'notional': price * size
                                })
                                prices[coin] = price

                    elif atype in ('cancel', 'cancelByCloid'):
                        orders.append({
                            'wallet': wallet,
                            'coin': '?',
                            'side': 'CANCEL',
                            'price': 0,
                            'size': 0,
                            'notional': 0
                        })
        except:
            pass

    return orders, prices


def build_price_zones(orders: List[dict], zone_size_pct: float = 0.1) -> Dict[str, Dict[float, PriceZone]]:
    """Build price zones for each coin."""
    zones = defaultdict(dict)  # coin -> {zone_price -> PriceZone}

    for o in orders:
        if o['side'] == 'CANCEL' or o['price'] == 0:
            continue

        coin = o['coin']
        price = o['price']

        # Round to zone (e.g., 0.1% increments)
        zone_price = round(price / (price * zone_size_pct / 100)) * (price * zone_size_pct / 100)

        if zone_price not in zones[coin]:
            zones[coin][zone_price] = PriceZone(price=zone_price)

        zone = zones[coin][zone_price]
        if o['side'] == 'BUY':
            zone.buy_volume += o['notional']
            zone.buy_count += 1
        else:
            zone.sell_volume += o['notional']
            zone.sell_count += 1

    return zones


def find_magnetism_zones(zones: Dict[float, PriceZone],
                          current_price: float,
                          top_n: int = 10,
                          max_distance_pct: float = 5.0) -> List[Tuple[PriceZone, float]]:
    """Find zones that might attract price."""
    if not zones:
        return []

    # Calculate distance and filter to nearby zones only
    zone_list = []
    for zone_price, zone in zones.items():
        distance_pct = ((zone_price - current_price) / current_price) * 100
        # Only include zones within max_distance_pct of current price
        if abs(distance_pct) <= max_distance_pct:
            zone_list.append((zone, distance_pct))

    # Sort by total activity
    zone_list.sort(key=lambda x: -x[0].total_volume)

    return zone_list[:top_n]


def analyze_order_flow_imbalance(orders: List[dict], window_count: int = 20) -> Dict[str, List[dict]]:
    """Analyze order flow imbalance over time windows."""
    # Group orders by coin
    by_coin = defaultdict(list)
    for o in orders:
        if o['side'] != 'CANCEL':
            by_coin[o['coin']].append(o)

    results = {}
    for coin, coin_orders in by_coin.items():
        if len(coin_orders) < 100:
            continue

        # Split into windows
        window_size = len(coin_orders) // window_count
        if window_size < 5:
            continue

        windows = []
        for i in range(0, len(coin_orders), window_size):
            window = coin_orders[i:i+window_size]
            buy_vol = sum(o['notional'] for o in window if o['side'] == 'BUY')
            sell_vol = sum(o['notional'] for o in window if o['side'] == 'SELL')
            total = buy_vol + sell_vol

            windows.append({
                'buy_volume': buy_vol,
                'sell_volume': sell_vol,
                'imbalance': (buy_vol - sell_vol) / total if total > 0 else 0,
                'order_count': len(window)
            })

        results[coin] = windows

    return results


def main():
    print("="*60)
    print("PRICE MAGNETISM ANALYSIS")
    print("="*60)

    # Fetch data
    block_data = fetch_block_data(5000)
    if not block_data:
        print("Failed to fetch data")
        return

    # Parse orders
    orders, _ = parse_orders(block_data)
    print(f"Parsed {len(orders):,} orders")

    # Fetch ACTUAL current prices from API (not from order data)
    print("Fetching current prices from API...")
    current_prices = fetch_current_prices()
    print(f"Got prices for {len(current_prices)} coins")

    # Filter to major coins
    coins_of_interest = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP', 'LINK', 'AVAX', 'HYPE']

    print("\n" + "="*60)
    print("PRICE ZONE ANALYSIS")
    print("="*60)

    zones = build_price_zones(orders, zone_size_pct=0.1)

    for coin in coins_of_interest:
        if coin not in zones or coin not in current_prices:
            continue

        current = current_prices[coin]
        magnetism = find_magnetism_zones(zones[coin], current, top_n=10)

        if not magnetism:
            continue

        print(f"\n{coin} (current: ${current:,.4f}):")
        print("-" * 50)

        # Separate zones above and below current price
        above = [(z, d) for z, d in magnetism if d > 0]
        below = [(z, d) for z, d in magnetism if d < 0]

        if above:
            print("  ABOVE current price (resistance/short stops):")
            for zone, dist in sorted(above, key=lambda x: x[1])[:5]:
                direction = "↑"
                imb_str = "BUY" if zone.imbalance > 0 else "SELL"
                print(f"    {direction} ${zone.price:,.4f} (+{dist:.2f}%) - ${zone.total_volume:,.0f} activity, {imb_str} imbalance {zone.imbalance*100:+.0f}%")

        if below:
            print("  BELOW current price (support/long stops):")
            for zone, dist in sorted(below, key=lambda x: -x[1])[:5]:
                direction = "↓"
                imb_str = "BUY" if zone.imbalance > 0 else "SELL"
                print(f"    {direction} ${zone.price:,.4f} ({dist:.2f}%) - ${zone.total_volume:,.0f} activity, {imb_str} imbalance {zone.imbalance*100:+.0f}%")

    print("\n" + "="*60)
    print("ORDER FLOW IMBALANCE OVER TIME")
    print("="*60)

    imbalance = analyze_order_flow_imbalance(orders)

    for coin in coins_of_interest:
        if coin not in imbalance:
            continue

        windows = imbalance[coin]
        print(f"\n{coin}:")

        # Find sustained imbalance periods
        sustained_buy = 0
        sustained_sell = 0
        max_buy_streak = 0
        max_sell_streak = 0

        for w in windows:
            if w['imbalance'] > 0.3:  # >30% buy imbalance
                sustained_buy += 1
                max_buy_streak = max(max_buy_streak, sustained_buy)
                sustained_sell = 0
            elif w['imbalance'] < -0.3:  # >30% sell imbalance
                sustained_sell += 1
                max_sell_streak = max(max_sell_streak, sustained_sell)
                sustained_buy = 0
            else:
                sustained_buy = 0
                sustained_sell = 0

        total_buy = sum(w['buy_volume'] for w in windows)
        total_sell = sum(w['sell_volume'] for w in windows)
        net_imbalance = (total_buy - total_sell) / (total_buy + total_sell) * 100 if (total_buy + total_sell) > 0 else 0

        print(f"  Net imbalance: {net_imbalance:+.1f}% ({'BUY' if net_imbalance > 0 else 'SELL'} pressure)")
        print(f"  Max BUY streak: {max_buy_streak} windows")
        print(f"  Max SELL streak: {max_sell_streak} windows")
        print(f"  Total volume: ${total_buy + total_sell:,.0f}")

    print("\n" + "="*60)
    print("MAGNETISM HYPOTHESIS")
    print("="*60)
    print("""
Key observations for trading:
1. High-activity zones often act as magnets - price tends to visit them
2. Zones with strong BUY imbalance may provide support
3. Zones with strong SELL imbalance may provide resistance
4. Sustained order imbalance can predict short-term direction

For liquidation hunting:
- Liquidation clusters below current price = potential long targets
- Liquidation clusters above current price = potential short targets
- Watch for aggressive sweeps toward these zones
""")


if __name__ == "__main__":
    main()

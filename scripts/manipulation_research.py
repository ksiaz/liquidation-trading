#!/usr/bin/env python3
"""
Manipulation Research - Deep analysis with node data access.

Research questions:
1. Do stop hunts precede liquidation cascades?
2. Which wallets profit from manipulation patterns?
3. Does price show "magnetism" toward stop/liquidation clusters?
4. Can we detect coordinated attacks on specific price levels?
"""

import json
import time
import requests
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import sqlite3

NODE_URL = "http://64.176.65.252:8080"

# Asset mapping
ASSETS = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX", 5: "SOL",
    6: "AVAX", 7: "BNB", 8: "APE", 9: "OP", 10: "LTC", 11: "ARB",
    12: "DOGE", 13: "INJ", 14: "SUI", 15: "kPEPE", 16: "XRP", 17: "LINK",
}


@dataclass
class OrderFlow:
    """Aggregated order flow for analysis."""
    timestamp: float
    coin: str
    buy_volume: float = 0
    sell_volume: float = 0
    buy_orders: int = 0
    sell_orders: int = 0
    cancels: int = 0
    large_orders: List[dict] = field(default_factory=list)  # Orders > threshold


@dataclass
class PriceLevel:
    """Activity at a specific price level."""
    price: float
    buy_volume: float = 0
    sell_volume: float = 0
    cancel_volume: float = 0
    touch_count: int = 0


class ManipulationResearch:
    """Deep manipulation research with node data."""

    def __init__(self, db_path: str = "manipulation_research.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize research database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Order flow aggregates
        c.execute("""
            CREATE TABLE IF NOT EXISTS order_flow (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                coin TEXT,
                interval_sec INTEGER,
                buy_volume REAL,
                sell_volume REAL,
                buy_orders INTEGER,
                sell_orders INTEGER,
                cancels INTEGER,
                imbalance REAL
            )
        """)

        # Detected manipulation events
        c.execute("""
            CREATE TABLE IF NOT EXISTS manipulation_events (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                coin TEXT,
                event_type TEXT,
                wallet TEXT,
                details TEXT,
                price_before REAL,
                price_after_1m REAL,
                price_after_5m REAL,
                profit_direction TEXT
            )
        """)

        # Wallet profiles
        c.execute("""
            CREATE TABLE IF NOT EXISTS wallet_profiles (
                wallet TEXT PRIMARY KEY,
                total_orders INTEGER DEFAULT 0,
                total_cancels INTEGER DEFAULT 0,
                cancel_rate REAL DEFAULT 0,
                layering_events INTEGER DEFAULT 0,
                wash_events INTEGER DEFAULT 0,
                avg_order_lifetime_ms REAL,
                profitable_manips INTEGER DEFAULT 0,
                total_manips INTEGER DEFAULT 0,
                last_seen REAL
            )
        """)

        # Price level activity
        c.execute("""
            CREATE TABLE IF NOT EXISTS price_levels (
                id INTEGER PRIMARY KEY,
                coin TEXT,
                price_level REAL,
                timestamp REAL,
                activity_type TEXT,
                volume REAL,
                order_count INTEGER
            )
        """)

        conn.commit()
        conn.close()

    def parse_block_data(self, block_data: str) -> Tuple[List[dict], Dict[str, float]]:
        """Parse orders and extract prices from block data."""
        orders = []
        prices = {}

        for line in block_data.split('\n'):
            if not line.strip().startswith('{'):
                continue
            try:
                d = json.loads(line)
                ab = d.get('abci_block', {})
                block_time = ab.get('time', '')

                try:
                    ts = datetime.fromisoformat(block_time[:26]).timestamp()
                except:
                    ts = time.time()

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

                                t = order.get('t', {})
                                order_type = list(t.keys())[0] if t else 'unknown'

                                orders.append({
                                    'ts': ts,
                                    'wallet': wallet,
                                    'coin': coin,
                                    'asset': asset,
                                    'side': side,
                                    'price': price,
                                    'size': size,
                                    'type': order_type,
                                    'cloid': order.get('c', ''),
                                    'is_reduce': order.get('r', False)
                                })

                                if price > 0:
                                    prices[coin] = price

                        elif atype in ('cancel', 'cancelByCloid'):
                            orders.append({
                                'ts': ts,
                                'wallet': wallet,
                                'coin': '?',
                                'side': 'CANCEL',
                                'price': 0,
                                'size': 0,
                                'type': 'cancel'
                            })
            except:
                pass

        return orders, prices

    def analyze_order_imbalance(self, orders: List[dict], window_sec: float = 60) -> Dict[str, List[OrderFlow]]:
        """Analyze buy/sell imbalance over time windows."""
        if not orders:
            return {}

        # Group by coin and time window
        flows = defaultdict(lambda: defaultdict(lambda: OrderFlow(0, '')))

        for o in orders:
            if o['type'] == 'cancel':
                continue
            coin = o['coin']
            bucket = int(o['ts'] / window_sec) * window_sec

            flow = flows[coin][bucket]
            flow.timestamp = bucket
            flow.coin = coin

            if o['side'] == 'BUY':
                flow.buy_volume += o['size'] * o['price']
                flow.buy_orders += 1
            else:
                flow.sell_volume += o['size'] * o['price']
                flow.sell_orders += 1

            # Track large orders (> $100k notional for BTC/ETH)
            notional = o['size'] * o['price']
            if notional > 100000:
                flow.large_orders.append(o)

        # Calculate imbalance
        result = {}
        for coin, buckets in flows.items():
            result[coin] = []
            for ts, flow in sorted(buckets.items()):
                total = flow.buy_volume + flow.sell_volume
                if total > 0:
                    imbalance = (flow.buy_volume - flow.sell_volume) / total
                else:
                    imbalance = 0
                flow.imbalance = imbalance
                result[coin].append(flow)

        return result

    def detect_aggressive_sweeps(self, orders: List[dict],
                                  time_window_ms: float = 1000,
                                  min_orders: int = 10) -> List[dict]:
        """
        Detect aggressive market sweeps - rapid sequence of orders
        hitting multiple price levels in one direction.

        This could indicate:
        - Stop hunting (pushing price to trigger stops)
        - Liquidation hunting (pushing to trigger liqs)
        - Momentum ignition (trying to trigger algos)
        """
        sweeps = []

        # Group orders by wallet and small time windows
        wallet_windows = defaultdict(list)
        for o in orders:
            if o['type'] == 'cancel':
                continue
            bucket = int(o['ts'] * 1000 / time_window_ms)
            key = (o['wallet'], o['coin'], bucket)
            wallet_windows[key].append(o)

        for (wallet, coin, bucket), window_orders in wallet_windows.items():
            if len(window_orders) < min_orders:
                continue

            # Check if mostly one direction
            buys = [o for o in window_orders if o['side'] == 'BUY']
            sells = [o for o in window_orders if o['side'] == 'SELL']

            if len(buys) >= min_orders:
                prices = sorted(set(o['price'] for o in buys))
                if len(prices) >= 3:  # Multiple price levels
                    total_size = sum(o['size'] for o in buys)
                    total_notional = sum(o['size'] * o['price'] for o in buys)
                    sweeps.append({
                        'type': 'AGGRESSIVE_SWEEP',
                        'wallet': wallet,
                        'coin': coin,
                        'direction': 'UP',
                        'order_count': len(buys),
                        'price_levels': len(prices),
                        'price_range': (min(prices), max(prices)),
                        'total_size': total_size,
                        'total_notional': total_notional,
                        'timestamp': window_orders[0]['ts']
                    })

            if len(sells) >= min_orders:
                prices = sorted(set(o['price'] for o in sells))
                if len(prices) >= 3:
                    total_size = sum(o['size'] for o in sells)
                    total_notional = sum(o['size'] * o['price'] for o in sells)
                    sweeps.append({
                        'type': 'AGGRESSIVE_SWEEP',
                        'wallet': wallet,
                        'coin': coin,
                        'direction': 'DOWN',
                        'order_count': len(sells),
                        'price_levels': len(prices),
                        'price_range': (min(prices), max(prices)),
                        'total_size': total_size,
                        'total_notional': total_notional,
                        'timestamp': window_orders[0]['ts']
                    })

        return sweeps

    def analyze_price_magnetism(self, orders: List[dict],
                                 prices: Dict[str, float],
                                 zone_tolerance_pct: float = 0.5) -> Dict[str, List[dict]]:
        """
        Analyze if price tends to move toward high-activity zones.

        Theory: Manipulators may target price levels where:
        - Many stop-losses are clustered
        - Liquidation prices are concentrated
        - Large resting orders exist
        """
        # Build price level activity map
        level_activity = defaultdict(lambda: defaultdict(lambda: {
            'buy_volume': 0, 'sell_volume': 0, 'order_count': 0
        }))

        for o in orders:
            if o['type'] == 'cancel' or o['price'] == 0:
                continue
            coin = o['coin']
            # Round to zone
            zone = round(o['price'] / o['price'] * 100 / zone_tolerance_pct) * zone_tolerance_pct * o['price'] / 100

            if o['side'] == 'BUY':
                level_activity[coin][zone]['buy_volume'] += o['size'] * o['price']
            else:
                level_activity[coin][zone]['sell_volume'] += o['size'] * o['price']
            level_activity[coin][zone]['order_count'] += 1

        # Find high-activity zones relative to current price
        magnetism = {}
        for coin, zones in level_activity.items():
            current = prices.get(coin, 0)
            if current == 0:
                continue

            coin_zones = []
            for zone_price, activity in zones.items():
                total_activity = activity['buy_volume'] + activity['sell_volume']
                distance_pct = (zone_price - current) / current * 100

                coin_zones.append({
                    'price': zone_price,
                    'distance_pct': distance_pct,
                    'buy_volume': activity['buy_volume'],
                    'sell_volume': activity['sell_volume'],
                    'total_activity': total_activity,
                    'order_count': activity['order_count'],
                    'imbalance': (activity['buy_volume'] - activity['sell_volume']) / total_activity if total_activity > 0 else 0
                })

            # Sort by activity
            magnetism[coin] = sorted(coin_zones, key=lambda x: -x['total_activity'])[:20]

        return magnetism

    def build_wallet_profile(self, orders: List[dict]) -> Dict[str, dict]:
        """Build behavioral profiles for active wallets."""
        profiles = defaultdict(lambda: {
            'total_orders': 0,
            'total_cancels': 0,
            'buy_orders': 0,
            'sell_orders': 0,
            'total_buy_volume': 0,
            'total_sell_volume': 0,
            'coins_traded': set(),
            'order_times': [],
            'large_orders': 0,
            'rapid_sequences': 0
        })

        for o in orders:
            wallet = o['wallet']
            p = profiles[wallet]

            if o['type'] == 'cancel':
                p['total_cancels'] += 1
            else:
                p['total_orders'] += 1
                p['coins_traded'].add(o['coin'])
                p['order_times'].append(o['ts'])

                notional = o['size'] * o['price']
                if o['side'] == 'BUY':
                    p['buy_orders'] += 1
                    p['total_buy_volume'] += notional
                else:
                    p['sell_orders'] += 1
                    p['total_sell_volume'] += notional

                if notional > 50000:
                    p['large_orders'] += 1

        # Calculate derived metrics
        result = {}
        for wallet, p in profiles.items():
            total = p['total_orders'] + p['total_cancels']
            if total < 10:
                continue

            cancel_rate = p['total_cancels'] / total if total > 0 else 0

            # Check for rapid order sequences
            times = sorted(p['order_times'])
            rapid = 0
            for i in range(1, len(times)):
                if times[i] - times[i-1] < 0.1:  # Less than 100ms apart
                    rapid += 1

            result[wallet] = {
                'total_orders': p['total_orders'],
                'total_cancels': p['total_cancels'],
                'cancel_rate': cancel_rate,
                'buy_sell_ratio': p['buy_orders'] / p['sell_orders'] if p['sell_orders'] > 0 else float('inf'),
                'total_volume': p['total_buy_volume'] + p['total_sell_volume'],
                'coins_count': len(p['coins_traded']),
                'large_orders': p['large_orders'],
                'rapid_sequences': rapid,
                'suspicious_score': cancel_rate * 0.3 + (rapid / total) * 0.4 + (p['large_orders'] / total) * 0.3 if total > 0 else 0
            }

        return result


def fetch_and_analyze(blocks_to_fetch: int = 5000):
    """Fetch recent blocks and run analysis."""
    import subprocess

    print("Fetching recent block data from node...")

    # Get latest block file
    cmd = "ssh root@64.176.65.252 'ls -t ~/hl/data/replica_cmds/*/2*/* | head -1'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return

    block_file = result.stdout.strip()
    print(f"Latest block file: {block_file}")

    # Fetch data
    cmd = f"ssh root@64.176.65.252 'tail -{blocks_to_fetch} {block_file}'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error fetching data: {result.stderr}")
        return

    block_data = result.stdout
    print(f"Fetched {len(block_data)} bytes of block data")

    # Analyze
    research = ManipulationResearch()
    orders, prices = research.parse_block_data(block_data)
    print(f"Parsed {len(orders):,} orders, {len(prices)} coin prices")

    # Order imbalance
    print("\n" + "="*60)
    print("ORDER IMBALANCE ANALYSIS (1-min windows)")
    print("="*60)
    imbalance = research.analyze_order_imbalance(orders, window_sec=60)
    for coin in ['BTC', 'ETH', 'SOL']:
        if coin not in imbalance:
            continue
        flows = imbalance[coin]
        if not flows:
            continue
        print(f"\n{coin}:")
        # Show extreme imbalances
        extremes = [f for f in flows if abs(f.imbalance) > 0.5]
        print(f"  Windows with >50% imbalance: {len(extremes)}/{len(flows)}")
        for f in sorted(extremes, key=lambda x: -abs(x.imbalance))[:3]:
            direction = "BUY" if f.imbalance > 0 else "SELL"
            print(f"    {direction} imbalance {f.imbalance*100:.1f}% - ${f.buy_volume+f.sell_volume:,.0f} volume")

    # Aggressive sweeps
    print("\n" + "="*60)
    print("AGGRESSIVE SWEEP DETECTION")
    print("="*60)
    sweeps = research.detect_aggressive_sweeps(orders, time_window_ms=2000, min_orders=5)
    print(f"Total sweeps detected: {len(sweeps)}")

    # Group by coin
    by_coin = defaultdict(list)
    for s in sweeps:
        by_coin[s['coin']].append(s)

    for coin in ['BTC', 'ETH', 'SOL']:
        if coin not in by_coin:
            continue
        coin_sweeps = by_coin[coin]
        print(f"\n{coin}: {len(coin_sweeps)} sweeps")
        for s in sorted(coin_sweeps, key=lambda x: -x['total_notional'])[:3]:
            print(f"  {s['wallet'][:12]}... {s['direction']} - {s['order_count']} orders across {s['price_levels']} levels, ${s['total_notional']:,.0f}")

    # Wallet profiles
    print("\n" + "="*60)
    print("SUSPICIOUS WALLET PROFILES")
    print("="*60)
    profiles = research.build_wallet_profile(orders)

    # Sort by suspicious score
    suspicious = sorted(profiles.items(), key=lambda x: -x[1]['suspicious_score'])[:10]
    print(f"Top 10 suspicious wallets (of {len(profiles)} active):")
    for wallet, p in suspicious:
        print(f"  {wallet[:16]}...")
        print(f"    Orders: {p['total_orders']:,}, Cancels: {p['total_cancels']:,} ({p['cancel_rate']*100:.1f}%)")
        print(f"    Volume: ${p['total_volume']:,.0f}, Large orders: {p['large_orders']}")
        print(f"    Rapid sequences: {p['rapid_sequences']}, Suspicious score: {p['suspicious_score']:.3f}")

    # Price magnetism
    print("\n" + "="*60)
    print("PRICE LEVEL MAGNETISM")
    print("="*60)
    magnetism = research.analyze_price_magnetism(orders, prices)
    for coin in ['BTC', 'ETH', 'SOL']:
        if coin not in magnetism:
            continue
        zones = magnetism[coin]
        current = prices.get(coin, 0)
        print(f"\n{coin} (current: ${current:,.2f}):")
        print("  High-activity zones:")
        for z in zones[:5]:
            direction = "↑" if z['distance_pct'] > 0 else "↓"
            print(f"    ${z['price']:,.2f} ({direction}{abs(z['distance_pct']):.1f}%) - ${z['total_activity']:,.0f} activity, {z['order_count']} orders")

    return research, orders, prices


if __name__ == "__main__":
    fetch_and_analyze(5000)

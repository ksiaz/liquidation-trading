#!/usr/bin/env python3
"""
Hyperliquid Node Data Proxy v3

Extends v2 with research/analysis endpoints that process data server-side.

New Endpoints:
- /order_flow?coin=BTC&minutes=5 - Order flow analysis (buy/sell imbalance)
- /price_zones?coin=BTC - High-activity price zones (magnetism analysis)
- /sweeps?coin=BTC - Aggressive sweep detection (manipulation)
- /wallet_profile?wallet=0x... - Wallet behavior analysis

All heavy processing happens on the VM, reducing bandwidth.

Deploy: scp node_proxy_v3.py root@64.176.65.252:~/
Start: ssh root@64.176.65.252 'python3 ~/node_proxy_v3.py &'
"""

import json
import time
import os
import glob
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

# Node data paths
HL_DATA = os.path.expanduser("~/hl/data")
REPLICA_CMDS = os.path.join(HL_DATA, "replica_cmds")

# Asset ID to coin mapping
ASSET_ID_TO_COIN = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX", 5: "SOL",
    6: "AVAX", 7: "BNB", 8: "APE", 9: "OP", 10: "LTC", 11: "ARB",
    12: "DOGE", 13: "INJ", 14: "SUI", 15: "kPEPE", 16: "XRP", 17: "LINK",
    18: "CRV", 19: "RNDR", 20: "FTM", 21: "ADA", 22: "FIL", 23: "LDO",
    24: "GMX", 25: "NEAR", 26: "TIA", 27: "AAVE", 28: "SEI", 29: "RUNE",
    30: "DOT", 31: "BLUR", 32: "WLD", 33: "ORDI", 34: "MEME", 35: "PYTH",
    36: "JTO", 37: "STRK", 38: "PENDLE", 39: "W", 40: "ENA", 41: "TON",
    42: "BOME", 43: "WIF", 44: "NOT", 45: "POPCAT", 46: "HYPE",
}

# Cache with TTL
cache = {
    'order_flow': {},  # coin -> analysis
    'order_flow_time': 0,
    'price_zones': {},
    'price_zones_time': 0,
    'sweeps': [],
    'sweeps_time': 0,
    'raw_orders': [],  # Cached parsed orders
    'raw_orders_time': 0,
}

ANALYSIS_CACHE_TTL = 30.0  # 30 seconds


def get_latest_block_file():
    """Get the latest block file."""
    dirs = sorted(glob.glob(os.path.join(REPLICA_CMDS, "*/2*")))
    if not dirs:
        return None
    latest_dir = dirs[-1]
    files = sorted(os.listdir(latest_dir))
    return os.path.join(latest_dir, files[-1]) if files else None


def parse_recent_orders(limit_lines=5000):
    """Parse recent orders from block file. Returns list of order dicts."""
    # Check cache
    now = time.time()
    if now - cache['raw_orders_time'] < 10:  # 10 second cache for raw orders
        return cache['raw_orders']

    block_file = get_latest_block_file()
    if not block_file:
        return []

    orders = []
    prices = {}  # Latest prices by coin

    try:
        with open(block_file, 'r') as f:
            lines = f.readlines()[-limit_lines:]

        for line in lines:
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
                                coin = ASSET_ID_TO_COIN.get(asset, f"A{asset}")
                                price = float(order.get('p', 0))
                                size = float(order.get('s', 0))
                                side = 'BUY' if order.get('b') else 'SELL'

                                if price > 0 and size > 0:
                                    orders.append({
                                        'ts': ts,
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
                                'ts': ts,
                                'wallet': wallet,
                                'coin': '?',
                                'side': 'CANCEL',
                                'price': 0,
                                'size': 0,
                                'notional': 0
                            })
            except:
                pass

    except Exception as e:
        print(f"Error parsing orders: {e}")

    cache['raw_orders'] = orders
    cache['raw_orders_time'] = now
    cache['prices'] = prices

    return orders


def analyze_order_flow(coin=None, window_minutes=5):
    """Analyze order flow for a coin or all coins."""
    orders = parse_recent_orders()

    # Filter by coin if specified
    if coin:
        orders = [o for o in orders if o['coin'] == coin]

    if not orders:
        return {'error': 'No orders found'}

    # Group into time windows
    window_sec = window_minutes * 60
    windows = defaultdict(lambda: {'buy_vol': 0, 'sell_vol': 0, 'buy_count': 0, 'sell_count': 0})

    for o in orders:
        if o['side'] == 'CANCEL':
            continue
        bucket = int(o['ts'] / window_sec) * window_sec

        if o['side'] == 'BUY':
            windows[bucket]['buy_vol'] += o['notional']
            windows[bucket]['buy_count'] += 1
        else:
            windows[bucket]['sell_vol'] += o['notional']
            windows[bucket]['sell_count'] += 1

    # Calculate imbalance for each window
    result = []
    for ts, w in sorted(windows.items()):
        total = w['buy_vol'] + w['sell_vol']
        imbalance = (w['buy_vol'] - w['sell_vol']) / total * 100 if total > 0 else 0
        result.append({
            'timestamp': ts,
            'buy_volume': round(w['buy_vol'], 2),
            'sell_volume': round(w['sell_vol'], 2),
            'imbalance_pct': round(imbalance, 2),
            'buy_count': w['buy_count'],
            'sell_count': w['sell_count']
        })

    # Summary
    total_buy = sum(w['buy_vol'] for w in windows.values())
    total_sell = sum(w['sell_vol'] for w in windows.values())
    net_imbalance = (total_buy - total_sell) / (total_buy + total_sell) * 100 if (total_buy + total_sell) > 0 else 0

    return {
        'coin': coin or 'ALL',
        'window_minutes': window_minutes,
        'windows': result[-20:],  # Last 20 windows
        'summary': {
            'total_buy_volume': round(total_buy, 2),
            'total_sell_volume': round(total_sell, 2),
            'net_imbalance_pct': round(net_imbalance, 2),
            'pressure': 'BUY' if net_imbalance > 0 else 'SELL'
        }
    }


def analyze_price_zones(coin, zone_size_pct=0.1, max_distance_pct=2.0):
    """Find high-activity price zones for a coin."""
    orders = parse_recent_orders()

    # Filter to coin
    coin_orders = [o for o in orders if o['coin'] == coin and o['side'] != 'CANCEL']
    if not coin_orders:
        return {'error': f'No orders for {coin}'}

    # Get current price (latest order price)
    current_price = cache.get('prices', {}).get(coin, coin_orders[-1]['price'])

    # Build zones
    zones = defaultdict(lambda: {'buy_vol': 0, 'sell_vol': 0, 'buy_count': 0, 'sell_count': 0})

    for o in coin_orders:
        # Round to zone
        zone_price = round(o['price'] / (o['price'] * zone_size_pct / 100)) * (o['price'] * zone_size_pct / 100)

        # Only include zones within range of current price
        distance_pct = abs((zone_price - current_price) / current_price * 100)
        if distance_pct > max_distance_pct:
            continue

        if o['side'] == 'BUY':
            zones[zone_price]['buy_vol'] += o['notional']
            zones[zone_price]['buy_count'] += 1
        else:
            zones[zone_price]['sell_vol'] += o['notional']
            zones[zone_price]['sell_count'] += 1

    # Format results
    zone_list = []
    for price, z in zones.items():
        total = z['buy_vol'] + z['sell_vol']
        imbalance = (z['buy_vol'] - z['sell_vol']) / total * 100 if total > 0 else 0
        distance = (price - current_price) / current_price * 100

        zone_list.append({
            'price': round(price, 6),
            'distance_pct': round(distance, 3),
            'total_volume': round(total, 2),
            'buy_volume': round(z['buy_vol'], 2),
            'sell_volume': round(z['sell_vol'], 2),
            'imbalance_pct': round(imbalance, 1),
            'order_count': z['buy_count'] + z['sell_count']
        })

    # Sort by total volume
    zone_list.sort(key=lambda x: -x['total_volume'])

    # Separate above/below
    above = [z for z in zone_list if z['distance_pct'] > 0][:10]
    below = [z for z in zone_list if z['distance_pct'] < 0][:10]

    return {
        'coin': coin,
        'current_price': round(current_price, 6),
        'zone_size_pct': zone_size_pct,
        'resistance_zones': sorted(above, key=lambda x: x['distance_pct']),
        'support_zones': sorted(below, key=lambda x: -x['distance_pct'])
    }


def detect_sweeps(coin=None, time_window_ms=2000, min_orders=5):
    """Detect aggressive market sweeps."""
    orders = parse_recent_orders()

    if coin:
        orders = [o for o in orders if o['coin'] == coin]

    # Filter non-cancel orders
    orders = [o for o in orders if o['side'] != 'CANCEL']

    # Group by wallet and time window
    wallet_windows = defaultdict(list)
    for o in orders:
        bucket = int(o['ts'] * 1000 / time_window_ms)
        key = (o['wallet'], o['coin'], bucket)
        wallet_windows[key].append(o)

    sweeps = []
    for (wallet, coin, bucket), window_orders in wallet_windows.items():
        if len(window_orders) < min_orders:
            continue

        buys = [o for o in window_orders if o['side'] == 'BUY']
        sells = [o for o in window_orders if o['side'] == 'SELL']

        for side_orders, direction in [(buys, 'UP'), (sells, 'DOWN')]:
            if len(side_orders) < min_orders:
                continue

            prices = sorted(set(o['price'] for o in side_orders))
            if len(prices) < 3:
                continue

            total_notional = sum(o['notional'] for o in side_orders)
            sweeps.append({
                'wallet': wallet[:16] + '...',
                'coin': coin,
                'direction': direction,
                'order_count': len(side_orders),
                'price_levels': len(prices),
                'price_range': f"{min(prices):.4f} - {max(prices):.4f}",
                'total_notional': round(total_notional, 2),
                'timestamp': side_orders[0]['ts']
            })

    # Sort by notional
    sweeps.sort(key=lambda x: -x['total_notional'])

    return {
        'coin': coin or 'ALL',
        'sweep_count': len(sweeps),
        'sweeps': sweeps[:50]  # Top 50
    }


def analyze_wallet(wallet):
    """Analyze a wallet's trading behavior."""
    orders = parse_recent_orders()

    # Filter to wallet
    wallet_orders = [o for o in orders if o['wallet'] == wallet]
    if not wallet_orders:
        return {'error': f'No orders for wallet {wallet[:16]}...'}

    # Analyze
    total_orders = len([o for o in wallet_orders if o['side'] != 'CANCEL'])
    total_cancels = len([o for o in wallet_orders if o['side'] == 'CANCEL'])

    buy_vol = sum(o['notional'] for o in wallet_orders if o['side'] == 'BUY')
    sell_vol = sum(o['notional'] for o in wallet_orders if o['side'] == 'SELL')

    coins_traded = set(o['coin'] for o in wallet_orders if o['side'] != 'CANCEL')

    # Count rapid sequences (orders within 100ms)
    times = sorted(o['ts'] for o in wallet_orders if o['side'] != 'CANCEL')
    rapid = sum(1 for i in range(1, len(times)) if times[i] - times[i-1] < 0.1)

    cancel_rate = total_cancels / (total_orders + total_cancels) * 100 if (total_orders + total_cancels) > 0 else 0

    return {
        'wallet': wallet[:16] + '...',
        'total_orders': total_orders,
        'total_cancels': total_cancels,
        'cancel_rate_pct': round(cancel_rate, 1),
        'buy_volume': round(buy_vol, 2),
        'sell_volume': round(sell_vol, 2),
        'net_flow': round(buy_vol - sell_vol, 2),
        'coins_traded': list(coins_traded),
        'rapid_sequences': rapid,
        'suspicious_score': round(cancel_rate * 0.3 + (rapid / max(total_orders, 1)) * 0.4, 3)
    }


class ResearchProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        handlers = {
            '/order_flow': self.handle_order_flow,
            '/price_zones': self.handle_price_zones,
            '/sweeps': self.handle_sweeps,
            '/wallet_profile': self.handle_wallet_profile,
            '/health': self.handle_health,
        }

        handler = handlers.get(path)
        if handler:
            handler(params)
        else:
            self.send_error(404, f"Unknown endpoint: {path}")

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def handle_order_flow(self, params):
        coin = params.get('coin', [None])[0]
        minutes = int(params.get('minutes', [5])[0])
        result = analyze_order_flow(coin, minutes)
        self.send_json(result)

    def handle_price_zones(self, params):
        coin = params.get('coin', ['BTC'])[0]
        zone_size = float(params.get('zone_size', [0.1])[0])
        max_dist = float(params.get('max_distance', [2.0])[0])
        result = analyze_price_zones(coin, zone_size, max_dist)
        self.send_json(result)

    def handle_sweeps(self, params):
        coin = params.get('coin', [None])[0]
        result = detect_sweeps(coin)
        self.send_json(result)

    def handle_wallet_profile(self, params):
        wallet = params.get('wallet', [None])[0]
        if not wallet:
            self.send_json({'error': 'wallet parameter required'})
            return
        result = analyze_wallet(wallet)
        self.send_json(result)

    def handle_health(self, params):
        block_file = get_latest_block_file()
        orders_count = len(parse_recent_orders())
        self.send_json({
            'status': 'ok',
            'block_file': block_file,
            'cached_orders': orders_count,
            'endpoints': ['/order_flow', '/price_zones', '/sweeps', '/wallet_profile']
        })


def run_server(port=8081):
    print(f"Research Proxy v3 starting on port {port}...")
    print("Pre-warming order cache...")
    orders = parse_recent_orders()
    print(f"Cached {len(orders)} orders")

    server = HTTPServer(('0.0.0.0', port), ResearchProxyHandler)
    print(f"Listening on http://0.0.0.0:{port}")
    print("Endpoints:")
    print("  /order_flow?coin=BTC&minutes=5")
    print("  /price_zones?coin=ETH&zone_size=0.1&max_distance=2")
    print("  /sweeps?coin=SOL")
    print("  /wallet_profile?wallet=0x...")
    print("  /health")
    server.serve_forever()


if __name__ == '__main__':
    run_server()

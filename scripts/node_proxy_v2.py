#!/usr/bin/env python3
"""
Hyperliquid Node Data Proxy v2

Runs on the VM (64.176.65.252) and serves node data via HTTP.
This bypasses all API rate limits by reading directly from node state.

Endpoints:
- /mids - All mid prices (real-time from blocks)
- /trades - Recent trades (from replica_cmds)
- /health - Node sync status
- /active_wallets - List of wallets with open perp positions
- /position_sizes - All position sizes (wallet -> asset -> size)

Start: python3 node_proxy_v2.py
"""

import json
import time
import os
import glob
import msgpack
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

# Node data paths
HL_DATA = os.path.expanduser("~/hl/data")
HL_STATE = os.path.expanduser("~/hl/hyperliquid_data")
REPLICA_CMDS = os.path.join(HL_DATA, "replica_cmds")
STATE_FILE = os.path.join(HL_STATE, "abci_state.rmp")

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

# Cache for performance
cache = {
    'mids': {},
    'mids_time': 0,
    'trades': [],
    'trades_time': 0,
    'state': {},
    'state_time': 0,
    'positions': {},  # wallet -> {asset_id -> {side, size}}
    'positions_time': 0,
    'active_wallets': [],
    'active_wallets_time': 0,
}

MIDS_CACHE_TTL = 0.5  # 500ms for prices
POSITIONS_CACHE_TTL = 30.0  # 30s for positions (state file is 927MB, parsing takes time)


def get_latest_replica_dir():
    """Find the latest replica_cmds directory."""
    dirs = sorted(glob.glob(os.path.join(REPLICA_CMDS, "*/2*")))
    return dirs[-1] if dirs else None


def get_latest_block_file(replica_dir):
    """Get the latest block file in a replica dir."""
    files = sorted(os.listdir(replica_dir))
    return os.path.join(replica_dir, files[-1]) if files else None


def parse_recent_blocks(block_file, limit=50):
    """Parse recent blocks from a block file."""
    blocks = []
    try:
        with open(block_file, 'r') as f:
            lines = f.readlines()
            for line in lines[-limit:]:
                line = line.strip()
                if line.startswith('{'):
                    try:
                        blocks.append(json.loads(line))
                    except:
                        pass
    except Exception as e:
        print(f"Error reading blocks: {e}")
    return blocks


def extract_prices_from_blocks(blocks):
    """Extract latest prices from block data."""
    prices = {}
    for block in blocks:
        abci = block.get('abci_block', {})
        bundles = abci.get('signed_action_bundles', [])
        for bundle in bundles:
            if len(bundle) < 2:
                continue
            actions = bundle[1].get('signed_actions', [])
            for signed in actions:
                action = signed.get('action', {})
                atype = action.get('type', '')
                if atype in ('order', 'batchModify'):
                    if atype == 'order':
                        order = action.get('order', {})
                        asset = order.get('a')
                        price = order.get('p')
                        if asset is not None and price:
                            prices[asset] = float(price)
                    elif atype == 'batchModify':
                        for mod in action.get('modifies', []):
                            order = mod.get('order', {})
                            asset = order.get('a')
                            price = order.get('p')
                            if asset is not None and price:
                                prices[asset] = float(price)
    return prices


def extract_trades_from_blocks(blocks):
    """Extract recent trades from blocks."""
    trades = []
    for block in blocks:
        abci = block.get('abci_block', {})
        block_time = abci.get('time', '')
        bundles = abci.get('signed_action_bundles', [])
        for bundle in bundles:
            if len(bundle) < 2:
                continue
            wallet = bundle[0]
            actions = bundle[1].get('signed_actions', [])
            for signed in actions:
                action = signed.get('action', {})
                atype = action.get('type', '')
                if atype == 'order':
                    order = action.get('order', {})
                    trades.append({
                        'time': block_time,
                        'wallet': wallet,
                        'asset': order.get('a'),
                        'side': 'BUY' if order.get('b') else 'SELL',
                        'price': order.get('p'),
                        'size': order.get('s')
                    })
    return trades[-100:]


def get_node_state():
    """Get current node sync state."""
    state_file = os.path.join(HL_STATE, "visor_abci_state.json")
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except:
        return {}


def parse_positions_from_state():
    """Parse all perp positions from abci_state.rmp."""
    positions = {}  # wallet -> {asset_id -> {side, size, notional}}
    active_wallets = []

    try:
        with open(STATE_FILE, "rb") as f:
            data = msgpack.unpack(f, raw=False, strict_map_key=False)

        blp = data.get("exchange", {}).get("blp", {})
        users = blp.get("u", [])

        for item in users:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue

            wallet = item[0]
            user_data = item[1]

            if not isinstance(user_data, dict):
                continue

            t = user_data.get("t", [])
            if not isinstance(t, list):
                continue

            wallet_positions = {}

            for asset_data in t:
                if not isinstance(asset_data, list) or len(asset_data) < 2:
                    continue

                asset_id = asset_data[0]
                pos_list = asset_data[1]

                if not isinstance(pos_list, list) or len(pos_list) < 2:
                    continue

                # pos_list[0] = long position, pos_list[1] = short position
                long_pos = pos_list[0] if isinstance(pos_list[0], dict) else {}
                short_pos = pos_list[1] if len(pos_list) > 1 and isinstance(pos_list[1], dict) else {}

                # Check long position
                if long_pos:
                    s = long_pos.get("s", 0)
                    if s and abs(s) > 1e6:  # Minimum 0.01 size
                        size = s / 1e8
                        coin = ASSET_ID_TO_COIN.get(asset_id, f"ASSET_{asset_id}")
                        wallet_positions[coin] = {
                            "side": "LONG",
                            "size": size,
                            "asset_id": asset_id
                        }

                # Check short position
                if short_pos:
                    s = short_pos.get("s", 0)
                    if s and abs(s) > 1e6:
                        size = s / 1e8
                        coin = ASSET_ID_TO_COIN.get(asset_id, f"ASSET_{asset_id}")
                        wallet_positions[coin] = {
                            "side": "SHORT",
                            "size": size,
                            "asset_id": asset_id
                        }

            if wallet_positions:
                positions[wallet] = wallet_positions
                active_wallets.append(wallet)

        print(f"[Positions] Parsed {len(positions)} wallets with positions")

    except Exception as e:
        print(f"Error parsing positions: {e}")

    return positions, active_wallets


class NodeProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logging for speed

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/mids':
            self.handle_mids()
        elif path == '/trades':
            self.handle_trades()
        elif path == '/health':
            self.handle_health()
        elif path == '/active_wallets':
            self.handle_active_wallets()
        elif path == '/position_sizes':
            self.handle_position_sizes()
        elif path.startswith('/positions/'):
            wallet = path.split('/')[-1]
            self.handle_wallet_positions(wallet)
        else:
            self.send_error(404, "Not Found")

    def handle_mids(self):
        """Return all mid prices."""
        now = time.time()
        if now - cache['mids_time'] > MIDS_CACHE_TTL:
            replica_dir = get_latest_replica_dir()
            if replica_dir:
                block_file = get_latest_block_file(replica_dir)
                if block_file:
                    blocks = parse_recent_blocks(block_file, limit=100)
                    cache['mids'] = extract_prices_from_blocks(blocks)
                    cache['mids_time'] = now

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(cache['mids']).encode())

    def handle_trades(self):
        """Return recent trades."""
        now = time.time()
        if now - cache['trades_time'] > MIDS_CACHE_TTL:
            replica_dir = get_latest_replica_dir()
            if replica_dir:
                block_file = get_latest_block_file(replica_dir)
                if block_file:
                    blocks = parse_recent_blocks(block_file, limit=50)
                    cache['trades'] = extract_trades_from_blocks(blocks)
                    cache['trades_time'] = now

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(cache['trades']).encode())

    def handle_health(self):
        """Return node health/sync status."""
        state = get_node_state()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(state).encode())

    def handle_active_wallets(self):
        """Return list of wallets with open positions."""
        now = time.time()
        if now - cache['positions_time'] > POSITIONS_CACHE_TTL:
            positions, active_wallets = parse_positions_from_state()
            cache['positions'] = positions
            cache['active_wallets'] = active_wallets
            cache['positions_time'] = now

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({
            'count': len(cache['active_wallets']),
            'wallets': cache['active_wallets']
        }).encode())

    def handle_position_sizes(self):
        """Return all position sizes."""
        now = time.time()
        if now - cache['positions_time'] > POSITIONS_CACHE_TTL:
            positions, active_wallets = parse_positions_from_state()
            cache['positions'] = positions
            cache['active_wallets'] = active_wallets
            cache['positions_time'] = now

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(cache['positions']).encode())

    def handle_wallet_positions(self, wallet):
        """Return positions for a specific wallet."""
        now = time.time()
        if now - cache['positions_time'] > POSITIONS_CACHE_TTL:
            positions, active_wallets = parse_positions_from_state()
            cache['positions'] = positions
            cache['active_wallets'] = active_wallets
            cache['positions_time'] = now

        wallet_data = cache['positions'].get(wallet, {})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({
            'wallet': wallet,
            'positions': wallet_data
        }).encode())


def run_server(port=8080):
    # Pre-warm cache
    print("Pre-warming position cache...")
    positions, active_wallets = parse_positions_from_state()
    cache['positions'] = positions
    cache['active_wallets'] = active_wallets
    cache['positions_time'] = time.time()
    print(f"Loaded {len(positions)} wallets with positions")

    server = HTTPServer(('0.0.0.0', port), NodeProxyHandler)
    print(f"Node proxy v2 running on http://0.0.0.0:{port}")
    print(f"Endpoints: /mids, /trades, /health, /active_wallets, /position_sizes, /positions/<wallet>")
    server.serve_forever()


if __name__ == '__main__':
    run_server()

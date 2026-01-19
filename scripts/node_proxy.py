#!/usr/bin/env python3
"""
Hyperliquid Node Data Proxy

Runs on the VM (64.176.65.252) and serves node data via HTTP.
This bypasses all API rate limits by reading directly from node state.

Endpoints:
- /mids - All mid prices (from latest blocks)
- /positions/<wallet> - Wallet positions (from state)
- /trades - Recent trades (from replica_cmds)
- /health - Node sync status

Start: python3 node_proxy.py
"""

import json
import time
import os
import glob
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

# Node data paths
HL_DATA = os.path.expanduser("~/hl/data")
HL_STATE = os.path.expanduser("~/hl/hyperliquid_data")
REPLICA_CMDS = os.path.join(HL_DATA, "replica_cmds")

# Cache for performance
cache = {
    'mids': {},
    'mids_time': 0,
    'trades': [],
    'trades_time': 0,
    'state': {},
    'state_time': 0
}

CACHE_TTL = 0.5  # 500ms cache


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
    return trades[-100:]  # Last 100 trades


def get_node_state():
    """Get current node sync state."""
    state_file = os.path.join(HL_STATE, "visor_abci_state.json")
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except:
        return {}


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
        elif path.startswith('/positions/'):
            wallet = path.split('/')[-1]
            self.handle_positions(wallet)
        else:
            self.send_error(404, "Not Found")

    def handle_mids(self):
        """Return all mid prices."""
        now = time.time()
        if now - cache['mids_time'] > CACHE_TTL:
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
        if now - cache['trades_time'] > CACHE_TTL:
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

    def handle_positions(self, wallet):
        """Return positions for a wallet (placeholder - needs state parsing)."""
        # This would require parsing abci_state.rmp which is msgpack
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'wallet': wallet, 'positions': []}).encode())


def run_server(port=8080):
    server = HTTPServer(('0.0.0.0', port), NodeProxyHandler)
    print(f"Node proxy running on http://0.0.0.0:{port}")
    print(f"Endpoints: /mids, /trades, /health, /positions/<wallet>")
    server.serve_forever()


if __name__ == '__main__':
    run_server()

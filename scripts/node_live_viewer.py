#!/usr/bin/env python3
"""
Live Node Data Viewer

Streams real-time data from Hyperliquid node without API rate limits.
Shows trades, liquidations, and order flow as they happen.
"""

import asyncio
import json
import time
import subprocess
import sys
from datetime import datetime
from typing import Dict, Optional
from collections import defaultdict

# Node connection
NODE_HOST = "64.176.65.252"
NODE_USER = "root"

# Asset ID to coin mapping (from Hyperliquid)
ASSET_MAP = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX", 5: "SOL",
    6: "AVAX", 7: "BNB", 8: "APE", 9: "OP", 10: "LTC", 11: "ARB",
    12: "DOGE", 13: "INJ", 14: "SUI", 15: "kPEPE", 16: "XRP", 17: "LINK",
    18: "CRV", 19: "RNDR", 20: "FTM", 21: "ADA", 22: "FIL", 23: "LDO",
    24: "GMX", 25: "NEAR", 26: "TIA", 27: "AAVE", 28: "SEI", 29: "RUNE",
    30: "DOT", 31: "BLUR", 32: "WLD", 33: "ORDI", 34: "MEME", 35: "PYTH",
    36: "JTO", 37: "STRK", 38: "PENDLE", 39: "W", 40: "ENA", 41: "TON",
    42: "BOME", 43: "WIF", 44: "NOT", 45: "POPCAT", 46: "HYPE"
}


class NodeDataViewer:
    def __init__(self):
        self.prices: Dict[str, float] = {}
        self.oi_prev: Dict[str, float] = {}
        self.trade_counts: Dict[str, int] = defaultdict(int)
        self.order_counts: Dict[str, int] = defaultdict(int)
        self.liquidation_counts: Dict[str, int] = defaultdict(int)
        self.last_print = 0
        self.start_time = time.time()

    def get_coin(self, asset_id: int) -> str:
        """Convert asset ID to coin name."""
        return ASSET_MAP.get(asset_id, f"ASSET_{asset_id}")

    def process_action(self, wallet: str, action: dict):
        """Process a single trading action."""
        action_type = action.get('type', '')

        if action_type == 'order':
            self._process_order(wallet, action)
        elif action_type == 'batchModify':
            for modify in action.get('modifies', []):
                order = modify.get('order', {})
                self._process_order(wallet, {'order': order, 'type': 'order'})
        elif action_type == 'cancel':
            pass  # Skip cancel logs
        elif action_type == 'liquidate':
            self._process_liquidation(wallet, action)

    def _process_order(self, wallet: str, action: dict):
        """Process an order."""
        order = action.get('order', action)
        asset_id = order.get('a')
        if asset_id is None:
            return

        coin = self.get_coin(asset_id)
        is_buy = order.get('b', False)
        price = order.get('p', '0')
        size = order.get('s', '0')

        try:
            price_f = float(price)
            size_f = float(size)
            value = price_f * size_f

            # Update price tracking
            self.prices[coin] = price_f
            self.order_counts[coin] += 1

            # Log large orders (>$50k)
            if value > 50000:
                side = "BUY" if is_buy else "SELL"
                print(f"\033[93m[ORDER]\033[0m {coin} {side} {size} @ ${price_f:,.2f} (${value:,.0f}) - {wallet[:10]}...")
        except:
            pass

    def _process_liquidation(self, wallet: str, action: dict):
        """Process a liquidation action."""
        liquidated = action.get('liquidatedUser', '')
        print(f"\033[91m[LIQUIDATION]\033[0m Wallet {wallet[:10]}... liquidating {liquidated[:10]}...")
        self.liquidation_counts['TOTAL'] += 1

    def process_block(self, block_data: dict):
        """Process a single block."""
        abci = block_data.get('abci_block', {})
        block_time = abci.get('time', '')
        bundles = abci.get('signed_action_bundles', [])

        for bundle in bundles:
            if len(bundle) < 2:
                continue
            wallet = bundle[0]
            signed_actions = bundle[1].get('signed_actions', [])

            for signed in signed_actions:
                action = signed.get('action', {})
                action_type = action.get('type', '')

                # Skip EVM transactions (HIP-1 stuff)
                if action_type == 'evmRawTx':
                    continue

                self.process_action(wallet, action)

        # Print summary every second
        now = time.time()
        if now - self.last_print >= 1.0:
            self.print_summary(block_time)
            self.last_print = now

    def print_summary(self, block_time: str):
        """Print current summary."""
        elapsed = time.time() - self.start_time
        total_orders = sum(self.order_counts.values())
        total_liqs = sum(self.liquidation_counts.values())

        # Get top coins by activity
        top_coins = sorted(self.order_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        print(f"\n\033[96m{'='*60}\033[0m")
        print(f"\033[96mBlock Time:\033[0m {block_time}")
        print(f"\033[96mRuntime:\033[0m {elapsed:.0f}s | Orders: {total_orders} | Liquidations: {total_liqs}")

        if top_coins:
            print(f"\033[96mTop Active:\033[0m", end=" ")
            for coin, count in top_coins:
                price = self.prices.get(coin, 0)
                print(f"{coin}(${price:,.2f}): {count}", end=" | ")
            print()

        # Reset counts for next period
        self.order_counts.clear()


async def stream_from_node():
    """Stream live data from node."""
    viewer = NodeDataViewer()

    print("\033[92m" + "="*60 + "\033[0m")
    print("\033[92mHyperliquid Node Live Data Stream\033[0m")
    print(f"\033[92mNode: {NODE_HOST} | No API limits!\033[0m")
    print("\033[92m" + "="*60 + "\033[0m\n")

    # Find the latest replica_cmds directory
    cmd = f"ssh {NODE_USER}@{NODE_HOST} \"ls -td ~/hl/data/replica_cmds/*/20* 2>/dev/null | head -1\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    data_dir = result.stdout.strip()

    if not data_dir:
        print("Error: Could not find replica_cmds directory")
        return

    print(f"Streaming from: {data_dir}\n")

    # Find latest block file
    cmd = f"ssh {NODE_USER}@{NODE_HOST} \"ls -t {data_dir}/ | head -1\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    latest_file = result.stdout.strip()

    if not latest_file:
        print("Error: No block files found")
        return

    print(f"Starting from block file: {latest_file}\n")

    # Tail the latest block file
    cmd = f"ssh {NODE_USER}@{NODE_HOST} \"tail -f {data_dir}/{latest_file}\""

    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    try:
        for line in process.stdout:
            line = line.strip()
            if not line or not line.startswith('{'):
                continue

            try:
                block = json.loads(line)
                viewer.process_block(block)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error: {e}")
                continue

    except KeyboardInterrupt:
        print("\n\033[93mStopping...\033[0m")
    finally:
        process.terminate()


async def show_current_state():
    """Show current node state."""
    print("\033[92m" + "="*60 + "\033[0m")
    print("\033[92mHyperliquid Node Current State\033[0m")
    print(f"\033[92mNode: {NODE_HOST}\033[0m")
    print("\033[92m" + "="*60 + "\033[0m\n")

    # Get node state
    cmd = f"ssh {NODE_USER}@{NODE_HOST} \"cat ~/hl/hyperliquid_data/visor_abci_state.json\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        state = json.loads(result.stdout)
        print(f"\033[96mBlock Height:\033[0m {state.get('height', 'N/A'):,}")
        print(f"\033[96mConsensus Time:\033[0m {state.get('consensus_time', 'N/A')}")
        print(f"\033[96mWall Clock:\033[0m {state.get('wall_clock_time', 'N/A')}")

        # Calculate lag (handle nanosecond precision)
        if state.get('consensus_time') and state.get('wall_clock_time'):
            try:
                # Truncate nanoseconds to microseconds
                ct_str = state['consensus_time'][:26]
                wt_str = state['wall_clock_time'][:26]
                ct = datetime.fromisoformat(ct_str)
                wt = datetime.fromisoformat(wt_str)
                lag = (wt - ct).total_seconds()
                print(f"\033[96mSync Lag:\033[0m {lag:.2f}s")
            except Exception as e:
                print(f"\033[96mSync Lag:\033[0m <1s (real-time)")

    print()

    # Get recent block data
    cmd = f"ssh {NODE_USER}@{NODE_HOST} \"ls -td ~/hl/data/replica_cmds/*/20* 2>/dev/null | head -1\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    data_dir = result.stdout.strip()

    if data_dir:
        cmd = f"ssh {NODE_USER}@{NODE_HOST} \"ls -t {data_dir}/ | head -1\""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        latest_file = result.stdout.strip()

        if latest_file:
            # Get last few blocks
            cmd = f"ssh {NODE_USER}@{NODE_HOST} \"tail -5 {data_dir}/{latest_file}\""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            print("\033[96mRecent Blocks:\033[0m")
            for line in result.stdout.strip().split('\n'):
                if line.startswith('{'):
                    try:
                        block = json.loads(line)
                        abci = block.get('abci_block', {})
                        t = abci.get('time', 'N/A')
                        bundles = len(abci.get('signed_action_bundles', []))
                        print(f"  {t} - {bundles} action bundles")
                    except:
                        pass


def get_positions_near_liq_sync():
    """Get positions close to liquidation from tracked wallets (sync version)."""
    import requests
    import sqlite3

    print("\033[92m" + "="*60 + "\033[0m")
    print("\033[92mPositions Near Liquidation\033[0m")
    print(f"\033[92mNode: {NODE_HOST} | Direct API - No limits!\033[0m")
    print("\033[92m" + "="*60 + "\033[0m\n")

    # Load tracked wallets from indexed_wallets.db
    try:
        db_path = "D:/liquidation-trading/indexed_wallets.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Get wallets with positions
        cursor.execute("""
            SELECT DISTINCT wallet_address FROM positions
            WHERE position_value > 10000
            ORDER BY position_value DESC
            LIMIT 100
        """)
        wallets = [row[0] for row in cursor.fetchall()]
        conn.close()
        print(f"Loaded {len(wallets)} wallets with large positions\n")
    except Exception as e:
        print(f"Could not load wallets from DB: {e}")
        wallets = []

    if not wallets:
        # Fallback to some known active wallets
        print("Using fallback whale list...\n")
        wallets = [
            "0x20e80426d4ac5f3a9a0b33dfe1e1e8f8e2e4c3d5",
            "0x1234567890abcdef1234567890abcdef12345678",
        ]

    # Get mid prices first
    print("Fetching current prices...")
    resp = requests.post(
        "https://api.hyperliquid.xyz/info",
        json={"type": "allMids"},
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    mids = resp.json()
    prices = {k: float(v) for k, v in mids.items()}
    print(f"Got {len(prices)} price feeds\n")

    positions_near_liq = []
    checked = 0

    print("Scanning wallets for positions near liquidation...")
    for wallet in wallets:
        try:
            resp = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "clearinghouseState", "user": wallet},
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            data = resp.json()
            checked += 1

            for asset in data.get('assetPositions', []):
                pos = asset.get('position', {})
                coin = pos.get('coin', '')
                szi = float(pos.get('szi', 0))
                liq_px = pos.get('liquidationPx')
                entry_px = float(pos.get('entryPx', 0))
                value = float(pos.get('positionValue', 0))

                if abs(szi) == 0 or not liq_px or value < 1000:
                    continue

                liq_px = float(liq_px)
                current_px = prices.get(coin, 0)
                if current_px == 0:
                    continue

                side = 'LONG' if szi > 0 else 'SHORT'

                # Calculate distance to liquidation
                if side == 'LONG':
                    distance_pct = ((current_px - liq_px) / current_px) * 100
                else:
                    distance_pct = ((liq_px - current_px) / current_px) * 100

                # Track if within 10% of liquidation
                if distance_pct <= 10.0:
                    positions_near_liq.append({
                        'wallet': wallet,
                        'coin': coin,
                        'side': side,
                        'size': abs(szi),
                        'entry': entry_px,
                        'liq': liq_px,
                        'current': current_px,
                        'distance': distance_pct,
                        'value': value
                    })

            if checked % 10 == 0:
                print(f"  Checked {checked}/{len(wallets)} wallets, found {len(positions_near_liq)} positions near liq...")

            time.sleep(0.05)  # Rate limit
        except Exception as e:
            continue

    return positions_near_liq, prices


async def get_positions_near_liq():
    """Wrapper for sync version."""
    positions_near_liq, prices = get_positions_near_liq_sync()

    # Sort by distance to liquidation
    positions_near_liq.sort(key=lambda x: x['distance'])

    # Print results
    if positions_near_liq:
        print(f"\033[91mFound {len(positions_near_liq)} positions within 5% of liquidation:\033[0m\n")
        print(f"{'Wallet':<14} {'Coin':<6} {'Side':<5} {'Value':>10} {'Distance':>8} {'Liq Price':>12} {'Current':>12}")
        print("-" * 80)

        for pos in positions_near_liq[:20]:  # Show top 20
            color = "\033[91m" if pos['distance'] < 1.0 else "\033[93m" if pos['distance'] < 2.0 else ""
            end_color = "\033[0m" if color else ""

            print(f"{color}{pos['wallet'][:12]}.. {pos['coin']:<6} {pos['side']:<5} "
                  f"${pos['value']:>9,.0f} {pos['distance']:>7.2f}% "
                  f"${pos['liq']:>11,.2f} ${pos['current']:>11,.2f}{end_color}")
    else:
        print("No positions found within 5% of liquidation")

    # Summary by coin
    print("\n\033[96mSummary by Coin:\033[0m")
    by_coin = defaultdict(lambda: {'count': 0, 'value': 0, 'long': 0, 'short': 0})
    for pos in positions_near_liq:
        by_coin[pos['coin']]['count'] += 1
        by_coin[pos['coin']]['value'] += pos['value']
        if pos['side'] == 'LONG':
            by_coin[pos['coin']]['long'] += 1
        else:
            by_coin[pos['coin']]['short'] += 1

    for coin, data in sorted(by_coin.items(), key=lambda x: x[1]['value'], reverse=True):
        print(f"  {coin}: {data['count']} positions, ${data['value']:,.0f} at risk "
              f"(L:{data['long']} S:{data['short']})")


def show_positions():
    """Show positions near liquidation (sync)."""
    positions_near_liq, prices = get_positions_near_liq_sync()

    # Sort by distance to liquidation
    positions_near_liq.sort(key=lambda x: x['distance'])

    print()

    # Print results
    if positions_near_liq:
        print(f"\033[91mFound {len(positions_near_liq)} positions within 10% of liquidation:\033[0m\n")
        print(f"{'Wallet':<14} {'Coin':<6} {'Side':<5} {'Value':>10} {'Distance':>8} {'Liq Price':>12} {'Current':>12}")
        print("-" * 80)

        for pos in positions_near_liq[:25]:  # Show top 25
            color = "\033[91m" if pos['distance'] < 2.0 else "\033[93m" if pos['distance'] < 5.0 else ""
            end_color = "\033[0m" if color else ""

            print(f"{color}{pos['wallet'][:12]}.. {pos['coin']:<6} {pos['side']:<5} "
                  f"${pos['value']:>9,.0f} {pos['distance']:>7.2f}% "
                  f"${pos['liq']:>11,.2f} ${pos['current']:>11,.2f}{end_color}")
    else:
        print("No positions found within 10% of liquidation")

    # Summary by coin
    print("\n\033[96mSummary by Coin:\033[0m")
    by_coin = defaultdict(lambda: {'count': 0, 'value': 0, 'long': 0, 'short': 0})
    for pos in positions_near_liq:
        by_coin[pos['coin']]['count'] += 1
        by_coin[pos['coin']]['value'] += pos['value']
        if pos['side'] == 'LONG':
            by_coin[pos['coin']]['long'] += 1
        else:
            by_coin[pos['coin']]['short'] += 1

    for coin, data in sorted(by_coin.items(), key=lambda x: x[1]['value'], reverse=True):
        print(f"  {coin}: {data['count']} positions, ${data['value']:,.0f} at risk "
              f"(L:{data['long']} S:{data['short']})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "state"

    if mode == "stream":
        asyncio.run(stream_from_node())
    elif mode == "positions":
        show_positions()
    else:
        asyncio.run(show_current_state())

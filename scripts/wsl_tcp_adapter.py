#!/usr/bin/env python3
"""
WSL TCP Adapter - Standalone Version

Streams blocks from node and serves events via TCP.
Run in WSL to expose events to Windows connector.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, AsyncIterator, Set
from pathlib import Path
from datetime import datetime


# ============ Asset Mapping ============
ASSET_ID_TO_COIN = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX",
    5: "SOL", 6: "BNB", 7: "AVAX", 8: "APE", 9: "OP",
    10: "LTC", 11: "ARB", 12: "DOGE", 13: "INJ", 14: "SUI",
    15: "kPEPE", 16: "LINK", 17: "CRV", 18: "LDO", 19: "RNDR",
    20: "CFX", 21: "APT", 22: "AAVE", 23: "MKR", 24: "COMP",
    25: "WLD", 26: "FXS", 27: "RLB", 28: "UNIBOT", 29: "YGG",
    30: "RUNE", 31: "SNX", 32: "TRX", 33: "kSHIB", 34: "UNI",
    35: "SEI", 36: "FTM", 37: "BLUR", 38: "TON", 39: "CYBER",
    40: "XRP", 41: "GALA", 42: "kLUNC", 43: "CAKE", 44: "ADA",
    45: "PENDLE", 46: "kFLOKI", 47: "FRIEND", 48: "ETC",
}

def get_coin_name(asset_id: int) -> str:
    if asset_id in ASSET_ID_TO_COIN:
        return ASSET_ID_TO_COIN[asset_id]
    return f"ASSET_{asset_id}"


# ============ Replica Streamer ============
class ReplicaCmdStreamer:
    def __init__(self, replica_path: str, start_from_end: bool = True):
        self._replica_path = replica_path
        self._start_from_end = start_from_end
        self._running = False
        self._current_file = None
        self._file_handle = None
        self.blocks_read = 0

    async def start(self) -> None:
        self._running = True
        self._current_file = self._find_latest_file()

    async def stop(self) -> None:
        self._running = False
        if self._file_handle:
            self._file_handle.close()

    def _find_latest_file(self) -> Optional[str]:
        try:
            sessions = sorted(Path(self._replica_path).iterdir(), reverse=True)
            for session in sessions:
                if not session.is_dir():
                    continue
                dates = sorted(session.iterdir(), reverse=True)
                for date_dir in dates:
                    if not date_dir.is_dir():
                        continue
                    files = sorted(date_dir.iterdir(), reverse=True)
                    for f in files:
                        if f.is_file() and f.name.isdigit():
                            return str(f)
        except Exception:
            pass
        return None

    async def stream_blocks(self) -> AsyncIterator[str]:
        if not self._current_file:
            return

        self._file_handle = open(self._current_file, 'r')
        if self._start_from_end:
            self._file_handle.seek(0, 2)

        while self._running:
            line = self._file_handle.readline()
            if line:
                self.blocks_read += 1
                yield line.strip()
            else:
                new_file = self._find_latest_file()
                if new_file and new_file != self._current_file:
                    self._file_handle.close()
                    self._current_file = new_file
                    self._file_handle = open(self._current_file, 'r')
                else:
                    await asyncio.sleep(0.01)


# ============ Event Extraction ============
def parse_timestamp(time_str: str) -> float:
    if not time_str:
        return time.time()
    try:
        clean_str = time_str[:26]
        dt = datetime.fromisoformat(clean_str)
        return dt.timestamp()
    except:
        return time.time()


def extract_events(block_json: str) -> List[Dict]:
    """Extract price and liquidation events from block."""
    events = []
    try:
        block = json.loads(block_json)
        abci = block.get('abci_block', block)
        timestamp = parse_timestamp(abci.get('time', ''))

        bundles = abci.get('signed_action_bundles', [])
        for bundle in bundles:
            if not isinstance(bundle, list) or len(bundle) < 2:
                continue

            wallet = bundle[0]
            bundle_data = bundle[1]
            if not isinstance(bundle_data, dict):
                continue

            for sa in bundle_data.get('signed_actions', []):
                action = sa.get('action', {})
                action_type = action.get('type')

                if action_type == 'SetGlobalAction':
                    pxs = action.get('pxs', [])
                    for asset_id, px_pair in enumerate(pxs):
                        if not isinstance(px_pair, list) or len(px_pair) < 2:
                            continue
                        oracle_str = px_pair[0]
                        mark_str = px_pair[1]
                        if oracle_str is None:
                            continue
                        try:
                            events.append({
                                'event_type': 'HL_PRICE',
                                'timestamp': timestamp,
                                'symbol': get_coin_name(asset_id),
                                'oracle_price': float(oracle_str),
                                'mark_price': float(mark_str) if mark_str else None,
                                'exchange': 'HYPERLIQUID',
                            })
                        except:
                            pass

                elif action_type == 'order':
                    for order in action.get('orders', []):
                        if not order.get('r'):  # Not reduce-only
                            continue
                        try:
                            asset_id = order.get('a', 0)
                            is_buy = order.get('b', False)
                            sz = abs(float(order.get('s', '0')))
                            px = float(order.get('p', '0'))
                            if sz * px < 100:  # Skip small orders
                                continue
                            events.append({
                                'event_type': 'HL_ORDER_ACTIVITY',
                                'timestamp': timestamp,
                                'wallet': wallet,
                                'coin': get_coin_name(asset_id),
                                'side': 'BUY' if is_buy else 'SELL',
                                'size': sz,
                                'price': px,
                                'notional': sz * px,
                                'is_reduce_only': True,
                                'exchange': 'HYPERLIQUID',
                            })
                        except:
                            pass
    except:
        pass
    return events


# ============ TCP Server ============
class TCPAdapter:
    def __init__(self, host: str = '127.0.0.1', port: int = 8090):
        self._host = host
        self._port = port
        self._running = False
        self._server = None
        self._clients: Set = set()
        self._streamer = None
        self.events_sent = 0
        self.price_events = 0

    async def start(self):
        self._running = True

        # Start TCP server
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        print(f"[TCPAdapter] Server listening on {self._host}:{self._port}")

        # Start streamer
        self._streamer = ReplicaCmdStreamer(os.path.expanduser('~/hl/data/replica_cmds'))
        await self._streamer.start()
        print(f"[TCPAdapter] Streaming from: {self._streamer._current_file}")

        # Start processing
        asyncio.create_task(self._process_loop())

    async def stop(self):
        self._running = False
        if self._streamer:
            await self._streamer.stop()
        for writer in list(self._clients):
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
        if self._server:
            self._server.close()

    async def _handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        print(f"[TCPAdapter] Client connected: {addr}")
        self._clients.add(writer)

        # Send welcome
        welcome = {'event_type': 'CONNECTED', 'version': '1.0'}
        try:
            writer.write((json.dumps(welcome) + '\n').encode())
            await writer.drain()
        except:
            pass

        # Wait for disconnect
        try:
            while self._running:
                data = await reader.read(1024)
                if not data:
                    break
                await asyncio.sleep(0.1)
        except:
            pass
        finally:
            self._clients.discard(writer)
            print(f"[TCPAdapter] Client disconnected: {addr}")

    async def _process_loop(self):
        blocks_since_log = 0
        async for block_json in self._streamer.stream_blocks():
            if not self._running:
                break

            events = extract_events(block_json)

            for event in events:
                if event['event_type'] == 'HL_PRICE':
                    self.price_events += 1
                await self._broadcast(event)

            blocks_since_log += 1
            if blocks_since_log >= 500:
                print(f"[TCPAdapter] Blocks: {self._streamer.blocks_read}, "
                      f"Events sent: {self.events_sent}, "
                      f"Price events: {self.price_events}, "
                      f"Clients: {len(self._clients)}")
                blocks_since_log = 0

    async def _broadcast(self, event: Dict):
        if not self._clients:
            return

        data = (json.dumps(event) + '\n').encode()
        disconnected = []

        for writer in self._clients:
            try:
                writer.write(data)
                await writer.drain()
                self.events_sent += 1
            except:
                disconnected.append(writer)

        for writer in disconnected:
            self._clients.discard(writer)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8090)
    args = parser.parse_args()

    print("=" * 60)
    print("HYPERLIQUID TCP ADAPTER")
    print("=" * 60)

    adapter = TCPAdapter(args.host, args.port)

    try:
        await adapter.start()
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await adapter.stop()


if __name__ == '__main__':
    asyncio.run(main())

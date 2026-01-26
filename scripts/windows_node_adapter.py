#!/usr/bin/env python3
"""
Windows-Native Node Adapter

Reads replica_cmds directly from the E: drive mount (no WSL needed).
Serves events via TCP socket.

Usage:
    python scripts/windows_node_adapter.py

Then connect with:
    python scripts/test_adapter_connection.py
"""

import asyncio
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set, AsyncIterator


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
    """Get coin name from asset ID."""
    if asset_id in ASSET_ID_TO_COIN:
        return ASSET_ID_TO_COIN[asset_id]
    return f"ASSET_{asset_id}"


# ============ Replica File Reader ============
class ReplicaReader:
    """Reads replica_cmds files from Windows path."""

    def __init__(self, base_path: str = r"E:\hl\data\replica_cmds"):
        self._base_path = Path(base_path)
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._running = False
        self.blocks_read = 0
        self.current_file_name = ""

    def _find_latest_file(self) -> Optional[Path]:
        """Find the most recent replica file."""
        try:
            # Navigate: replica_cmds / session_dir / date_dir / block_file
            sessions = sorted(self._base_path.iterdir(), reverse=True)
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
                            return f
        except Exception as e:
            print(f"[ReplicaReader] Error finding file: {e}")
        return None

    async def start(self) -> bool:
        """Start the reader."""
        self._current_file = self._find_latest_file()
        if not self._current_file:
            print("[ReplicaReader] No replica files found!")
            return False

        self.current_file_name = str(self._current_file)
        print(f"[ReplicaReader] Starting from: {self._current_file}")

        self._file_handle = open(self._current_file, 'r', encoding='utf-8')
        # Seek to end to get only new blocks
        self._file_handle.seek(0, 2)

        self._running = True
        return True

    async def stop(self) -> None:
        """Stop the reader."""
        self._running = False
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    async def stream_blocks(self) -> AsyncIterator[str]:
        """Stream blocks from replica files."""
        if not self._file_handle:
            return

        while self._running:
            line = self._file_handle.readline()

            if line:
                self.blocks_read += 1
                yield line.strip()
            else:
                # Check for new file
                new_file = self._find_latest_file()
                if new_file and new_file != self._current_file:
                    print(f"[ReplicaReader] Switching to: {new_file}")
                    self._file_handle.close()
                    self._current_file = new_file
                    self.current_file_name = str(new_file)
                    self._file_handle = open(self._current_file, 'r', encoding='utf-8')
                else:
                    # Wait for new data
                    await asyncio.sleep(0.01)


# ============ Event Extraction ============
def parse_timestamp(time_str: str) -> float:
    """Parse ISO timestamp to Unix timestamp."""
    if not time_str:
        return time.time()
    try:
        clean_str = time_str[:26]
        dt = datetime.fromisoformat(clean_str)
        return dt.timestamp()
    except:
        return time.time()


def extract_events(block_json: str) -> List[Dict]:
    """Extract price and action events from a block."""
    events = []

    try:
        block = json.loads(block_json)
        abci = block.get('abci_block', block)
        timestamp = parse_timestamp(abci.get('time', ''))
        block_height = abci.get('height', 0)

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

                # Oracle price updates
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
                                'block_height': block_height,
                                'symbol': get_coin_name(asset_id),
                                'oracle_price': float(oracle_str),
                                'mark_price': float(mark_str) if mark_str else None,
                            })
                        except:
                            pass

                # Force orders (liquidations)
                elif action_type == 'forceOrder':
                    try:
                        asset_id = action.get('a', 0)
                        is_buy = action.get('b', False)
                        sz = abs(float(action.get('s', '0')))
                        px = float(action.get('p', '0'))

                        events.append({
                            'event_type': 'HL_LIQUIDATION',
                            'timestamp': timestamp,
                            'block_height': block_height,
                            'wallet': wallet,
                            'symbol': get_coin_name(asset_id),
                            'side': 'BUY' if is_buy else 'SELL',
                            'size': sz,
                            'price': px,
                            'notional': sz * px,
                        })
                    except:
                        pass

                # Regular orders
                elif action_type == 'order':
                    for order in action.get('orders', []):
                        try:
                            asset_id = order.get('a', 0)
                            is_buy = order.get('b', False)
                            sz = abs(float(order.get('s', '0')))
                            px = float(order.get('p', '0'))
                            is_reduce = order.get('r', False)

                            if sz * px < 100:  # Skip tiny orders
                                continue

                            events.append({
                                'event_type': 'HL_ORDER',
                                'timestamp': timestamp,
                                'block_height': block_height,
                                'wallet': wallet,
                                'symbol': get_coin_name(asset_id),
                                'side': 'BUY' if is_buy else 'SELL',
                                'size': sz,
                                'price': px,
                                'notional': sz * px,
                                'is_reduce_only': is_reduce,
                            })
                        except:
                            pass

    except json.JSONDecodeError:
        pass
    except Exception as e:
        pass

    return events


# ============ TCP Server ============
class NodeAdapter:
    """TCP server that streams events to clients."""

    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 8090,
        replica_path: str = r"E:\hl\data\replica_cmds",
    ):
        self._host = host
        self._port = port
        self._replica_path = replica_path

        self._running = False
        self._server = None
        self._reader: Optional[ReplicaReader] = None
        self._clients: Set[asyncio.StreamWriter] = set()

        # Metrics
        self.blocks_processed = 0
        self.events_sent = 0
        self.price_events = 0
        self.liquidation_events = 0

    async def start(self) -> bool:
        """Start the adapter."""
        print("=" * 60)
        print("HYPERLIQUID NODE ADAPTER (Windows Native)")
        print("=" * 60)

        # Start replica reader
        self._reader = ReplicaReader(self._replica_path)
        if not await self._reader.start():
            print("[Adapter] Failed to start replica reader")
            return False

        # Start TCP server
        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._port,
        )
        print(f"[Adapter] TCP server: {self._host}:{self._port}")

        self._running = True

        # Start processing loop
        asyncio.create_task(self._process_loop())

        print("[Adapter] Running - Press Ctrl+C to stop")
        print("-" * 60)

        return True

    async def stop(self) -> None:
        """Stop the adapter."""
        print("\n[Adapter] Stopping...")
        self._running = False

        if self._reader:
            await self._reader.stop()

        for writer in list(self._clients):
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        print("[Adapter] Stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection."""
        addr = writer.get_extra_info('peername')
        print(f"[Adapter] Client connected: {addr}")
        self._clients.add(writer)

        # Send welcome message
        welcome = {
            'event_type': 'CONNECTED',
            'version': '1.0',
            'server': 'windows_node_adapter',
        }
        try:
            writer.write((json.dumps(welcome) + '\n').encode())
            await writer.drain()
        except:
            pass

        # Keep connection alive until client disconnects
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
            print(f"[Adapter] Client disconnected: {addr}")

    async def _process_loop(self) -> None:
        """Main loop - read blocks and broadcast events."""
        log_interval = 100
        blocks_since_log = 0

        async for block_json in self._reader.stream_blocks():
            if not self._running:
                break

            self.blocks_processed += 1
            events = extract_events(block_json)

            for event in events:
                event_type = event.get('event_type')
                if event_type == 'HL_PRICE':
                    self.price_events += 1
                elif event_type == 'HL_LIQUIDATION':
                    self.liquidation_events += 1

                await self._broadcast(event)

            blocks_since_log += 1
            if blocks_since_log >= log_interval:
                print(
                    f"[Adapter] Blocks: {self.blocks_processed}, "
                    f"Events: {self.events_sent}, "
                    f"Prices: {self.price_events}, "
                    f"Liquidations: {self.liquidation_events}, "
                    f"Clients: {len(self._clients)}"
                )
                blocks_since_log = 0

    async def _broadcast(self, event: Dict) -> None:
        """Broadcast event to all clients."""
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
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Windows Node Adapter')
    parser.add_argument('--host', default='127.0.0.1', help='TCP host')
    parser.add_argument('--port', type=int, default=8090, help='TCP port')
    parser.add_argument(
        '--replica-path',
        default=r'E:\hl\data\replica_cmds',
        help='Path to replica_cmds',
    )

    args = parser.parse_args()

    adapter = NodeAdapter(
        host=args.host,
        port=args.port,
        replica_path=args.replica_path,
    )

    try:
        if await adapter.start():
            # Keep running
            while True:
                await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await adapter.stop()


if __name__ == '__main__':
    asyncio.run(main())

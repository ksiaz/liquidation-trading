#!/usr/bin/env python3
"""
Standalone WSL Adapter Test

Minimal test script that runs in WSL without package dependencies.
Tests block streaming and event extraction from the Hyperliquid node.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, AsyncIterator
from collections import deque
from pathlib import Path

# Try to import inotify for efficient file watching
try:
    import inotify_simple
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False


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


# ============ Data Classes ============
@dataclass
class PriceEvent:
    symbol: str
    oracle_price: float
    mark_price: Optional[float]
    timestamp: float

    def to_dict(self) -> Dict:
        return {
            'event_type': 'HL_PRICE',
            'symbol': self.symbol,
            'oracle_price': self.oracle_price,
            'mark_price': self.mark_price,
            'timestamp': self.timestamp,
            'exchange': 'HYPERLIQUID',
        }


@dataclass
class LiquidationEvent:
    wallet_address: str
    symbol: str
    side: str
    liquidated_size: float
    liquidation_price: float
    value: float
    timestamp: float

    def to_dict(self) -> Dict:
        return {
            'event_type': 'HL_LIQUIDATION',
            'wallet_address': self.wallet_address,
            'symbol': self.symbol,
            'side': self.side,
            'liquidated_size': self.liquidated_size,
            'liquidation_price': self.liquidation_price,
            'value': self.value,
            'timestamp': self.timestamp,
            'exchange': 'HYPERLIQUID',
        }


@dataclass
class StreamerMetrics:
    blocks_read: int = 0
    bytes_read: int = 0
    files_rotated: int = 0
    current_file: str = ""
    start_time: float = field(default_factory=time.time)


# ============ Replica Streamer ============
class ReplicaCmdStreamer:
    """Stream blocks from replica_cmds directory."""

    def __init__(self, replica_path: str, start_from_end: bool = True):
        self._replica_path = replica_path
        self._start_from_end = start_from_end
        self._running = False
        self._current_file = None
        self._file_handle = None
        self.metrics = StreamerMetrics()

    async def start(self) -> None:
        self._running = True
        self._current_file = self._find_latest_file()
        if self._current_file:
            self.metrics.current_file = self._current_file

    async def stop(self) -> None:
        self._running = False
        if self._file_handle:
            self._file_handle.close()

    def _find_latest_file(self) -> Optional[str]:
        """Find the latest block file."""
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
        except Exception as e:
            print(f"Error finding latest file: {e}")
        return None

    async def stream_blocks(self) -> AsyncIterator[str]:
        """Stream blocks as JSON strings."""
        if not self._current_file:
            print("No block file found")
            return

        self._file_handle = open(self._current_file, 'r')

        # Seek to end if requested
        if self._start_from_end:
            self._file_handle.seek(0, 2)

        while self._running:
            line = self._file_handle.readline()
            if line:
                self.metrics.blocks_read += 1
                self.metrics.bytes_read += len(line)
                yield line.strip()
            else:
                # Check for file rotation
                new_file = self._find_latest_file()
                if new_file and new_file != self._current_file:
                    self._file_handle.close()
                    self._current_file = new_file
                    self._file_handle = open(self._current_file, 'r')
                    self.metrics.files_rotated += 1
                    self.metrics.current_file = new_file
                else:
                    await asyncio.sleep(0.01)


# ============ Action Extractor ============
class BlockActionExtractor:
    """Extract events from blocks."""

    def __init__(self, focus_coins: Optional[List[str]] = None):
        self._focus_coins = set(focus_coins) if focus_coins else None
        self.price_events = 0
        self.liquidation_events = 0
        self.set_global_actions = 0

    def extract_from_block(self, block_json: str) -> Tuple[List[PriceEvent], List[LiquidationEvent]]:
        """Extract price and liquidation events from a block."""
        price_events = []
        liq_events = []

        try:
            block = json.loads(block_json)
        except json.JSONDecodeError:
            return price_events, liq_events

        # Handle abci_block wrapper format
        abci_block = block.get('abci_block', block)

        # Get timestamp
        timestamp = self._parse_timestamp(abci_block.get('time', ''))
        if not timestamp:
            return price_events, liq_events

        # Process signed_action_bundles (new format)
        bundles = abci_block.get('signed_action_bundles', [])
        for bundle in bundles:
            if not isinstance(bundle, list) or len(bundle) < 2:
                continue

            wallet = bundle[0]
            bundle_data = bundle[1]

            if not isinstance(bundle_data, dict):
                continue

            # Process signed_actions array
            signed_actions = bundle_data.get('signed_actions', [])
            for signed_action in signed_actions:
                if not isinstance(signed_action, dict):
                    continue

                action = signed_action.get('action', {})
                if not isinstance(action, dict):
                    continue

                action_type = action.get('type')

                # SetGlobalAction - extract prices (using 'pxs' format)
                if action_type == 'SetGlobalAction':
                    self.set_global_actions += 1
                    prices = self._extract_prices(action, timestamp)
                    price_events.extend(prices)
                    self.price_events += len(prices)

                # order with liquidation
                elif action_type == 'order':
                    orders = action.get('orders', [])
                    for order in orders:
                        if order.get('r'):  # reduce_only / liquidation
                            liq = self._extract_liquidation(order, wallet, timestamp)
                            if liq:
                                liq_events.append(liq)
                                self.liquidation_events += 1

        return price_events, liq_events

    def _parse_timestamp(self, t: str) -> Optional[float]:
        """Parse timestamp from block."""
        if not t:
            return None
        try:
            from datetime import datetime
            # Handle the timestamp format
            t = t.replace('Z', '+00:00')
            if '+' not in t and 'T' in t:
                t = t + '+00:00'
            dt = datetime.fromisoformat(t)
            return dt.timestamp()
        except:
            return None

    def _extract_prices(self, action: Dict, timestamp: float) -> List[PriceEvent]:
        """Extract prices from SetGlobalAction."""
        events = []

        # New format: 'pxs' is array of [oracle_price, mark_price] pairs
        pxs = action.get('pxs', [])

        for idx, px_pair in enumerate(pxs):
            if not isinstance(px_pair, list) or len(px_pair) < 2:
                continue

            oracle_str = px_pair[0]
            mark_str = px_pair[1]

            # Skip if no oracle price
            if oracle_str is None:
                continue

            try:
                oracle_price = float(oracle_str)
            except (TypeError, ValueError):
                continue

            try:
                mark_price = float(mark_str) if mark_str else None
            except (TypeError, ValueError):
                mark_price = None

            coin = get_coin_name(idx)
            if self._focus_coins and coin not in self._focus_coins:
                continue

            events.append(PriceEvent(
                symbol=coin,
                oracle_price=oracle_price,
                mark_price=mark_price,
                timestamp=timestamp,
            ))

        return events

    def _extract_liquidation(self, order: Dict, wallet: str, timestamp: float) -> Optional[LiquidationEvent]:
        """Extract liquidation from forceOrder."""
        try:
            asset_id = order.get('a', 0)
            coin = get_coin_name(asset_id)

            if self._focus_coins and coin not in self._focus_coins:
                return None

            is_buy = order.get('b', False)
            side = "SHORT" if is_buy else "LONG"  # Liquidation is opposite of position

            sz_str = order.get('s', '0')
            px_str = order.get('p', '0')

            try:
                sz = abs(float(sz_str))
                px = float(px_str)
            except:
                return None

            value = sz * px

            return LiquidationEvent(
                wallet_address=wallet,
                symbol=coin,
                side=side,
                liquidated_size=sz,
                liquidation_price=px,
                value=value,
                timestamp=timestamp,
            )
        except:
            return None


# ============ Sync Monitor ============
def check_sync_status(state_path: str) -> Dict:
    """Check node sync status."""
    visor_path = os.path.join(state_path, 'visor_abci_state.json')
    try:
        with open(visor_path, 'r') as f:
            data = json.load(f)
        return {
            'height': data.get('height', 0),
            'consensus_time': data.get('consensus_time', ''),
            'wall_clock_time': data.get('wall_clock_time', ''),
        }
    except:
        return {}


# ============ Main Test ============
async def main():
    print("=" * 60)
    print("HYPERLIQUID NODE ADAPTER - WSL TEST")
    print("=" * 60)

    data_path = '/root/hl/data'
    state_path = '/root/hl/hyperliquid_data'

    # Check sync status
    print("\nChecking sync status...")
    status = check_sync_status(state_path)
    print(f"  Block height: {status.get('height', 'N/A')}")
    print(f"  Consensus time: {status.get('consensus_time', 'N/A')}")
    print(f"  Wall clock time: {status.get('wall_clock_time', 'N/A')}")

    # Start streamer
    print("\nStarting block streamer...")
    streamer = ReplicaCmdStreamer(f"{data_path}/replica_cmds", start_from_end=True)
    await streamer.start()
    print(f"  Current file: {streamer.metrics.current_file}")

    # Start extractor
    extractor = BlockActionExtractor()

    print("\nStreaming blocks (Ctrl+C to stop)...")
    print("-" * 60)

    blocks_processed = 0
    start_time = time.time()

    try:
        async for block_json in streamer.stream_blocks():
            price_events, liq_events = extractor.extract_from_block(block_json)
            blocks_processed += 1

            # Print SetGlobalAction prices
            if price_events:
                print(f"\n[Block {blocks_processed}] SetGlobalAction with {len(price_events)} prices")
                for pe in price_events[:5]:
                    print(f"  {pe.symbol}: oracle={pe.oracle_price:.4f}")
                if len(price_events) > 5:
                    print(f"  ... and {len(price_events) - 5} more")

            # Print liquidations
            for le in liq_events:
                print(f"\n[Block {blocks_processed}] LIQUIDATION!")
                print(f"  Wallet: {le.wallet_address[:16]}...")
                print(f"  {le.symbol} {le.side}")
                print(f"  Size: {le.liquidated_size:.4f}")
                print(f"  Price: {le.liquidation_price:.4f}")
                print(f"  Value: ${le.value:,.2f}")

            # Periodic summary
            if blocks_processed % 500 == 0:
                elapsed = time.time() - start_time
                bps = blocks_processed / elapsed
                print(f"\n--- {blocks_processed} blocks ({bps:.1f}/s), "
                      f"{extractor.price_events} prices, "
                      f"{extractor.liquidation_events} liquidations ---")

    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        await streamer.stop()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print(f"  Blocks processed: {blocks_processed}")
    print(f"  SetGlobalActions: {extractor.set_global_actions}")
    print(f"  Price events: {extractor.price_events}")
    print(f"  Liquidation events: {extractor.liquidation_events}")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())

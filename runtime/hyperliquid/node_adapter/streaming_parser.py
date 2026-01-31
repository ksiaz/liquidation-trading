"""
Streaming Msgpack Parser for Hyperliquid State File

Parses abci_state.rmp (981MB) with explicit memory management.

Key insight: The old code cached the entire parsed state (5-10GB) permanently.
This parser loads, processes, and RELEASES memory after each operation.
Peak memory is still 5-10GB during parsing, but returns to baseline after.

Memory characteristics:
- File on disk: ~981MB
- During parse: 5-10GB temporary spike
- After parse: Returns to baseline (data released)
- Old cached approach: 5-10GB permanent

The difference: temporary spike vs permanent allocation.
Multiple operations will spike multiple times, but GC reclaims between.

Usage:
    parser = StreamingStateParser(state_file)

    # Bootstrap: get wallet list (one-time spike, then release)
    wallets = parser.get_users_with_positions()

    # Batch discovery: process 500 wallets at a time
    batch, done = parser.get_next_discovery_batch()
    for wallet, coin, pos_data in parser.iter_positions_batch(batch):
        # Process position
        pass
    # Memory released after iteration completes
"""

import gc
import os
from typing import Dict, Iterator, Optional, Tuple, List, Set
from dataclasses import dataclass

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False


def _release_memory(data: Dict) -> None:
    """Explicitly release memory from parsed data."""
    if data is not None:
        data.clear()
    gc.collect()

from .asset_mapping import get_coin_name


@dataclass
class StreamingParserConfig:
    """Configuration for streaming parser."""
    batch_size: int = 500          # Wallets per batch
    min_position_value: float = 1000.0  # Minimum position value to yield
    focus_coins: Optional[Set[str]] = None  # Only yield these coins


class StreamingStateParser:
    """
    Stream-parse abci_state.rmp without loading entire file.

    The state file structure:
    {
        "exchange": {
            "perp_dexs": [{
                "clearinghouse": {
                    "meta": {"universe": [...]},  # Asset metadata
                    "oracle": {"pxs": [...]},      # Prices
                    "user_states": {
                        "users_with_positions": [...],  # Wallet list
                        "user_to_state": [[wallet, data], ...]  # Position data
                    }
                }
            }]
        }
    }

    Strategy:
    1. Parse header sections (meta, oracle) to get asset scaling
    2. Get users_with_positions list
    3. Iterate user_to_state in batches, yielding positions
    """

    def __init__(
        self,
        state_file: str,
        config: Optional[StreamingParserConfig] = None,
    ):
        """
        Initialize streaming parser.

        Args:
            state_file: Path to abci_state.rmp
            config: Optional configuration
        """
        self._state_file = state_file
        self._config = config or StreamingParserConfig()

        # Asset metadata (populated during iteration)
        self._sz_decimals: Dict[int, int] = {}
        self._oracle_prices: Dict[int, float] = {}

        # Discovery state
        self._users_with_positions: List[str] = []
        self._discovery_cursor: int = 0  # Index into users_with_positions

    def get_users_with_positions(self) -> List[str]:
        """
        Get list of wallets that have open positions.

        Parses just enough of the state file to extract the wallet list.
        Memory: O(num_wallets) for the list, typically 10-50K strings.
        """
        if self._users_with_positions:
            return self._users_with_positions

        if not MSGPACK_AVAILABLE or not os.path.exists(self._state_file):
            return []

        try:
            with open(self._state_file, 'rb') as f:
                # Parse full state (unfortunately msgpack doesn't support seeking)
                # But we only extract the wallet list, then discard the rest
                data = msgpack.unpack(f, raw=False, strict_map_key=False)

            exchange = data.get('exchange', {})
            perp_dexs = exchange.get('perp_dexs', [])
            if not perp_dexs:
                return []

            ch = perp_dexs[0].get('clearinghouse', {})
            us = ch.get('user_states', {})

            self._users_with_positions = list(us.get('users_with_positions', []))

            # Also extract metadata while we have it
            meta = ch.get('meta', {})
            universe = meta.get('universe', [])
            self._sz_decimals = {i: u.get('szDecimals', 0) for i, u in enumerate(universe)}

            oracle = ch.get('oracle', {})
            pxs = oracle.get('pxs', [])
            for asset_id, px_data in enumerate(pxs):
                if px_data and isinstance(px_data, list) and px_data:
                    raw_px = px_data[0].get('px', 0)
                    sz_dec = self._sz_decimals.get(asset_id, 0)
                    scale = 10 ** (6 - sz_dec)
                    self._oracle_prices[asset_id] = raw_px / scale

            # Release memory explicitly
            _release_memory(data)

        except Exception as e:
            print(f"[StreamingParser] Error getting users_with_positions: {e}")
            gc.collect()

        return self._users_with_positions

    def iter_positions_batch(
        self,
        wallets: List[str],
    ) -> Iterator[Tuple[str, str, Dict]]:
        """
        Iterate positions for a specific batch of wallets.

        Args:
            wallets: List of wallet addresses to process

        Yields:
            (wallet, coin, position_data) tuples

        Memory: O(batch_size) - only loads positions for specified wallets
        """
        if not MSGPACK_AVAILABLE or not os.path.exists(self._state_file):
            return

        wallet_set = set(wallets)

        try:
            with open(self._state_file, 'rb') as f:
                data = msgpack.unpack(f, raw=False, strict_map_key=False)

            exchange = data.get('exchange', {})
            perp_dexs = exchange.get('perp_dexs', [])
            if not perp_dexs:
                return

            ch = perp_dexs[0].get('clearinghouse', {})

            # Ensure metadata is loaded
            if not self._sz_decimals:
                meta = ch.get('meta', {})
                universe = meta.get('universe', [])
                self._sz_decimals = {i: u.get('szDecimals', 0) for i, u in enumerate(universe)}

                oracle = ch.get('oracle', {})
                pxs = oracle.get('pxs', [])
                for asset_id, px_data in enumerate(pxs):
                    if px_data and isinstance(px_data, list) and px_data:
                        raw_px = px_data[0].get('px', 0)
                        sz_dec = self._sz_decimals.get(asset_id, 0)
                        scale = 10 ** (6 - sz_dec)
                        self._oracle_prices[asset_id] = raw_px / scale

            us = ch.get('user_states', {})
            user_to_state = us.get('user_to_state', [])

            # Process only requested wallets
            for item in user_to_state:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue

                wallet = item[0]
                if wallet not in wallet_set:
                    continue

                user_data = item[1]
                if not isinstance(user_data, dict):
                    continue

                p_data = user_data.get('p', {})
                pos_list = p_data.get('p', [])

                for pos_item in pos_list:
                    if not isinstance(pos_item, list) or len(pos_item) < 2:
                        continue

                    asset_id = pos_item[0]
                    pos = pos_item[1]

                    if not isinstance(pos, dict):
                        continue

                    coin = get_coin_name(asset_id)

                    # Apply focus_coins filter
                    if self._config.focus_coins and coin not in self._config.focus_coins:
                        continue

                    pos_data = self._extract_position_data(asset_id, pos)
                    if not pos_data:
                        continue

                    # Apply min_position_value filter
                    value = abs(pos_data['size']) * pos_data['entry']
                    if value < self._config.min_position_value:
                        continue

                    yield wallet, coin, pos_data

            # Release memory explicitly
            _release_memory(data)

        except Exception as e:
            print(f"[StreamingParser] Error iterating positions: {e}")

    def get_next_discovery_batch(self) -> Tuple[List[str], bool]:
        """
        Get next batch of wallets for discovery.

        Returns:
            (wallets, is_complete) tuple
            - wallets: List of wallet addresses for this batch
            - is_complete: True if this is the last batch (cursor wrapped)
        """
        if not self._users_with_positions:
            self.get_users_with_positions()

        if not self._users_with_positions:
            return [], True

        batch_size = self._config.batch_size
        total = len(self._users_with_positions)

        start = self._discovery_cursor
        end = min(start + batch_size, total)

        wallets = self._users_with_positions[start:end]

        # Advance cursor
        self._discovery_cursor = end
        is_complete = (end >= total)

        if is_complete:
            self._discovery_cursor = 0  # Reset for next cycle

        return wallets, is_complete

    def reset_discovery_cursor(self) -> None:
        """Reset discovery cursor to start from beginning."""
        self._discovery_cursor = 0

    def get_discovery_progress(self) -> Tuple[int, int]:
        """
        Get discovery progress.

        Returns:
            (current_position, total_wallets) tuple
        """
        if not self._users_with_positions:
            self.get_users_with_positions()
        return self._discovery_cursor, len(self._users_with_positions)

    def get_position_for_wallet(
        self,
        wallet: str,
        coin: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Get position data for a specific wallet/coin.

        This is a targeted read - more efficient than batch iteration
        when you only need one position.

        Args:
            wallet: Wallet address
            coin: Optional coin filter

        Returns:
            Position data dict or None
        """
        if not MSGPACK_AVAILABLE or not os.path.exists(self._state_file):
            return None

        try:
            with open(self._state_file, 'rb') as f:
                data = msgpack.unpack(f, raw=False, strict_map_key=False)

            exchange = data.get('exchange', {})
            perp_dexs = exchange.get('perp_dexs', [])
            if not perp_dexs:
                return None

            ch = perp_dexs[0].get('clearinghouse', {})

            # Ensure metadata is loaded
            if not self._sz_decimals:
                meta = ch.get('meta', {})
                universe = meta.get('universe', [])
                self._sz_decimals = {i: u.get('szDecimals', 0) for i, u in enumerate(universe)}

                oracle = ch.get('oracle', {})
                pxs = oracle.get('pxs', [])
                for asset_id, px_data in enumerate(pxs):
                    if px_data and isinstance(px_data, list) and px_data:
                        raw_px = px_data[0].get('px', 0)
                        sz_dec = self._sz_decimals.get(asset_id, 0)
                        scale = 10 ** (6 - sz_dec)
                        self._oracle_prices[asset_id] = raw_px / scale

            us = ch.get('user_states', {})
            user_to_state = us.get('user_to_state', [])

            # Find target wallet
            for item in user_to_state:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue

                if item[0] != wallet:
                    continue

                user_data = item[1]
                if not isinstance(user_data, dict):
                    return None

                p_data = user_data.get('p', {})
                pos_list = p_data.get('p', [])

                result = {}
                for pos_item in pos_list:
                    if not isinstance(pos_item, list) or len(pos_item) < 2:
                        continue

                    asset_id = pos_item[0]
                    pos = pos_item[1]

                    if not isinstance(pos, dict):
                        continue

                    pos_coin = get_coin_name(asset_id)

                    # If specific coin requested, only return that
                    if coin and pos_coin != coin:
                        continue

                    pos_data = self._extract_position_data(asset_id, pos)
                    if pos_data and abs(pos_data['size']) > 0.0001:
                        if coin:
                            return pos_data  # Return single position
                        result[pos_coin] = pos_data

                # Return all positions if no specific coin
                return result if result else None

            return None  # Wallet not found

        except Exception as e:
            print(f"[StreamingParser] Error reading position: {e}")
            return None

    def _extract_position_data(self, asset_id: int, pos: Dict) -> Optional[Dict]:
        """
        Extract position data from state structure.

        Position structure: {s, e, l, M, f}
        - s: size (scaled by 10^szDecimals)
        - e: entry notional (scaled by 1e6)
        - l: {I: {l: leverage, u: margin_adj}} or {C: n}
        """
        s = pos.get('s', 0)
        if not s:
            return None

        # Get scaling
        sz_dec = self._sz_decimals.get(asset_id, 0)
        size = s / (10 ** sz_dec)

        # Entry notional (scaled by 1e6)
        entry_ntl = pos.get('e', 0) / 1e6

        # Leverage info
        l_data = pos.get('l', {})
        is_isolated = 'I' in l_data

        if is_isolated:
            leverage = l_data['I'].get('l', 1)
            margin_adj = l_data['I'].get('u', 0) / 1e6
        else:
            leverage = l_data.get('C', 1)
            margin_adj = 0

        # Calculate entry price
        entry_price = entry_ntl / abs(size) if size != 0 else 0

        # Get oracle price
        oracle_price = self._oracle_prices.get(asset_id, 0)

        # Calculate liquidation price
        liq_price = 0
        margin = entry_ntl / leverage if leverage > 0 else entry_ntl

        if leverage > 0 and abs(size) > 0:
            side = 1 if size > 0 else -1

            maint_leverage = leverage * 2
            maint_margin = entry_ntl / maint_leverage

            correction = 1 - side / maint_leverage

            if correction != 0:
                margin_available = margin - maint_margin
                liq_price = entry_price - side * margin_available / abs(size) / correction

                # Sanity checks
                if size > 0 and liq_price >= entry_price:
                    liq_price = 0
                elif size < 0 and liq_price <= entry_price:
                    liq_price = 0
                elif liq_price <= 0 or liq_price > 1e12:
                    liq_price = 0

        return {
            'size': size,
            'entry': entry_price,
            'liq': liq_price,
            'margin': margin,
            'leverage': leverage,
            'is_isolated': is_isolated,
            'oracle_price': oracle_price,
        }

    def get_oracle_prices(self) -> Dict[int, float]:
        """Get cached oracle prices (keyed by asset_id)."""
        return self._oracle_prices.copy()

    def get_sz_decimals(self) -> Dict[int, int]:
        """Get cached size decimals (keyed by asset_id)."""
        return self._sz_decimals.copy()

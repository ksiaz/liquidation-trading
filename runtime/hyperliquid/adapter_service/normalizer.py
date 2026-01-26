"""
Event Normalizer for Hyperliquid Node Adapter

Converts raw block data to normalized typed events.
Handles:
- Asset ID to symbol mapping
- Timestamp normalization
- Deduplication within blocks
- Strict ordering
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


# ============ Asset Mapping ============
# Maps asset IDs to symbols. Extend as needed.
ASSET_ID_TO_SYMBOL = {
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
    49: "TIA", 50: "MEME", 51: "ORDI", 52: "HIFI", 53: "BLUR",
    54: "SUPER", 55: "DYM", 56: "PIXEL", 57: "STRK", 58: "JUP",
    59: "DEGEN", 60: "W", 61: "ENA", 62: "ONDO", 63: "MERL",
    # Add more as discovered
}


def get_symbol(asset_id: int) -> str:
    """Get symbol for asset ID."""
    if asset_id in ASSET_ID_TO_SYMBOL:
        return ASSET_ID_TO_SYMBOL[asset_id]
    return f"ASSET_{asset_id}"


# ============ Data Classes ============

@dataclass
class NormalizedPriceEvent:
    """Normalized price event."""
    asset: str
    oracle_price: float
    mark_price: Optional[float]
    timestamp_ms: int
    block_height: int


@dataclass
class NormalizedActionEvent:
    """Normalized action event."""
    block_height: int
    timestamp_ms: int
    wallet: str
    action_type: str  # 'ORDER', 'CANCEL', 'FORCE_ORDER'
    asset: str
    side: str  # 'BUY', 'SELL'
    price: float
    size: float
    order_type: str  # 'LIMIT', 'MARKET', 'TRIGGER'
    is_liquidation: bool
    is_reduce_only: bool
    cloid: Optional[str] = None


# ============ Normalizer ============

class EventNormalizer:
    """
    Normalizes raw block data to typed events.

    Responsibilities:
    - Parse node raw formats
    - Normalize timestamps to milliseconds
    - Normalize asset identifiers (ID → symbol)
    - Extract relevant events (SetGlobalAction, order, forceOrder)
    """

    def __init__(self):
        # Track last seen prices for deduplication
        self._last_prices: Dict[str, Tuple[float, float]] = {}  # asset -> (oracle, mark)

        # Metrics
        self.prices_emitted = 0
        self.actions_emitted = 0
        self.blocks_processed = 0

    def normalize_block(
        self,
        block: Dict,
    ) -> Tuple[List[NormalizedPriceEvent], List[NormalizedActionEvent]]:
        """
        Extract and normalize events from a block.

        Args:
            block: Parsed block dictionary

        Returns:
            Tuple of (price_events, action_events)
        """
        self.blocks_processed += 1

        price_events = []
        action_events = []

        # Extract block metadata
        abci = block.get('abci_block', block)
        timestamp_ms = self._parse_timestamp(abci.get('time', ''))
        block_height = abci.get('height', 0)

        # Process signed action bundles
        bundles = abci.get('signed_action_bundles', [])

        for bundle in bundles:
            if not isinstance(bundle, list) or len(bundle) < 2:
                continue

            wallet = bundle[0]
            bundle_data = bundle[1]

            if not isinstance(bundle_data, dict):
                continue

            for signed_action in bundle_data.get('signed_actions', []):
                action = signed_action.get('action', {})
                action_type = action.get('type')

                if action_type == 'SetGlobalAction':
                    # Extract prices
                    prices = self._extract_prices(
                        action, timestamp_ms, block_height
                    )
                    price_events.extend(prices)

                elif action_type == 'order':
                    # Extract order events
                    orders = self._extract_orders(
                        action, wallet, timestamp_ms, block_height
                    )
                    action_events.extend(orders)

                elif action_type == 'forceOrder':
                    # Extract liquidation
                    liq = self._extract_liquidation(
                        action, wallet, timestamp_ms, block_height
                    )
                    if liq:
                        action_events.append(liq)

        self.prices_emitted += len(price_events)
        self.actions_emitted += len(action_events)

        return price_events, action_events

    def _parse_timestamp(self, time_str: str) -> int:
        """Parse timestamp string to milliseconds."""
        if not time_str:
            return int(time.time() * 1000)

        try:
            # Format: "2024-01-26T15:30:45.123456789Z"
            # Python can only handle microseconds, truncate nanoseconds
            clean_str = time_str[:26]
            if clean_str.endswith('Z'):
                clean_str = clean_str[:-1]

            dt = datetime.fromisoformat(clean_str)
            return int(dt.timestamp() * 1000)
        except Exception:
            return int(time.time() * 1000)

    def _extract_prices(
        self,
        action: Dict,
        timestamp_ms: int,
        block_height: int,
    ) -> List[NormalizedPriceEvent]:
        """Extract price events from SetGlobalAction."""
        events = []

        pxs = action.get('pxs', [])

        for asset_id, price_pair in enumerate(pxs):
            if not isinstance(price_pair, list) or len(price_pair) < 2:
                continue

            # pxs[i] = [oracle_price, mark_price]
            oracle_str = price_pair[0]
            mark_str = price_pair[1]

            if oracle_str is None:
                continue

            try:
                oracle_price = float(oracle_str)
                mark_price = float(mark_str) if mark_str else None

                # Check for duplicate (same price as last)
                asset = get_symbol(asset_id)
                last = self._last_prices.get(asset)

                if last and last[0] == oracle_price and last[1] == mark_price:
                    continue  # Skip duplicate

                self._last_prices[asset] = (oracle_price, mark_price)

                events.append(NormalizedPriceEvent(
                    asset=asset,
                    oracle_price=oracle_price,
                    mark_price=mark_price,
                    timestamp_ms=timestamp_ms,
                    block_height=block_height,
                ))
            except (ValueError, TypeError):
                continue

        return events

    def _extract_orders(
        self,
        action: Dict,
        wallet: str,
        timestamp_ms: int,
        block_height: int,
    ) -> List[NormalizedActionEvent]:
        """Extract order events from order action."""
        events = []

        for order in action.get('orders', []):
            try:
                asset_id = order.get('a', 0)
                is_buy = order.get('b', False)
                size_str = order.get('s', '0')
                price_str = order.get('p', '0')
                is_reduce_only = order.get('r', False)
                cloid = order.get('c')

                size = abs(float(size_str))
                price = float(price_str)

                # Determine order type
                order_type = 'LIMIT'
                if order.get('t'):  # Trigger order
                    order_type = 'TRIGGER'

                events.append(NormalizedActionEvent(
                    block_height=block_height,
                    timestamp_ms=timestamp_ms,
                    wallet=wallet,
                    action_type='ORDER',
                    asset=get_symbol(asset_id),
                    side='BUY' if is_buy else 'SELL',
                    price=price,
                    size=size,
                    order_type=order_type,
                    is_liquidation=False,
                    is_reduce_only=is_reduce_only,
                    cloid=cloid,
                ))
            except (ValueError, TypeError, KeyError):
                continue

        return events

    def _extract_liquidation(
        self,
        action: Dict,
        wallet: str,
        timestamp_ms: int,
        block_height: int,
    ) -> Optional[NormalizedActionEvent]:
        """Extract liquidation from forceOrder action."""
        try:
            asset_id = action.get('a', 0)
            is_buy = action.get('b', False)  # Direction of the liquidation order
            size_str = action.get('s', '0')
            price_str = action.get('p', '0')

            size = abs(float(size_str))
            price = float(price_str)

            # Liquidation: if is_buy=True, they were SHORT and got liquidated
            # The liquidation order buys to close the short
            return NormalizedActionEvent(
                block_height=block_height,
                timestamp_ms=timestamp_ms,
                wallet=wallet,
                action_type='FORCE_ORDER',
                asset=get_symbol(asset_id),
                side='BUY' if is_buy else 'SELL',
                price=price,
                size=size,
                order_type='MARKET',  # Liquidations are market orders
                is_liquidation=True,
                is_reduce_only=True,
                cloid=None,
            )
        except (ValueError, TypeError, KeyError):
            return None

    def get_stats(self) -> Dict:
        """Get normalizer statistics."""
        return {
            'blocks_processed': self.blocks_processed,
            'prices_emitted': self.prices_emitted,
            'actions_emitted': self.actions_emitted,
            'unique_assets_seen': len(self._last_prices),
        }

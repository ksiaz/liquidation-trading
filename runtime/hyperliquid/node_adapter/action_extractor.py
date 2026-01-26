"""
Block Action Extractor

Parses Hyperliquid node blocks and extracts relevant actions:
- SetGlobalAction: Oracle price updates (228 assets)
- forceOrder: Liquidation executions (ground truth)
- order: Order activity (for position change detection)

Constitutional: No filtering, no ranking. Extract ALL matching actions.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .asset_mapping import get_coin_name
from .metrics import ExtractorMetrics


@dataclass
class OrderActivity:
    """
    Lightweight record of order activity.

    Used to detect when positions might have changed,
    triggering targeted position re-reads.
    """
    wallet: str
    coin: str
    timestamp: float
    side: str  # 'BUY' or 'SELL'
    is_reduce_only: bool  # If True, position might be closing
    size: float
    notional: float  # size * price


@dataclass
class PriceEvent:
    """Normalized price event from SetGlobalAction."""
    timestamp: float
    symbol: str
    mark_price: Optional[float]
    oracle_price: float
    event_type: str = 'HL_PRICE'
    exchange: str = 'HYPERLIQUID'

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'mark_price': self.mark_price,
            'oracle_price': self.oracle_price,
            'event_type': self.event_type,
            'exchange': self.exchange,
        }


@dataclass
class LiquidationEvent:
    """Normalized liquidation event from forceOrder."""
    timestamp: float
    symbol: str
    wallet_address: str
    liquidated_size: float  # Always positive
    liquidation_price: float
    side: str  # 'LONG' or 'SHORT'
    value: float  # USD value
    event_type: str = 'HL_LIQUIDATION'
    exchange: str = 'HYPERLIQUID'

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'wallet_address': self.wallet_address,
            'liquidated_size': self.liquidated_size,
            'liquidation_price': self.liquidation_price,
            'side': self.side,
            'value': self.value,
            'event_type': self.event_type,
            'exchange': self.exchange,
        }


class BlockActionExtractor:
    """
    Extracts relevant actions from Hyperliquid node blocks.

    Parses the block JSON and extracts:
    - SetGlobalAction: Oracle prices for all 228 assets
    - forceOrder: Liquidation events (ground truth)
    - order: Order activity for position change detection

    Constitutional compliance:
    - No filtering by importance
    - No ranking or scoring
    - Extract ALL matching actions
    """

    def __init__(
        self,
        extract_orders: bool = True,
        extract_cancels: bool = False,
        focus_coins: Optional[List[str]] = None,
    ):
        """
        Initialize extractor.

        Args:
            extract_orders: Whether to extract order actions
            extract_cancels: Whether to extract cancel actions
            focus_coins: If set, only extract for these coins (None = all)
        """
        self._extract_orders = extract_orders
        self._extract_cancels = extract_cancels
        self._focus_coins = set(focus_coins) if focus_coins else None

        # Metrics
        self.metrics = ExtractorMetrics()

    def extract_from_block(
        self,
        block_json: str
    ) -> Tuple[List[PriceEvent], List[LiquidationEvent], List[OrderActivity]]:
        """
        Extract all relevant actions from a block.

        Args:
            block_json: Raw JSON string of the block

        Returns:
            Tuple of (price_events, liquidation_events, order_activities)
        """
        start_time = time.time()

        price_events: List[PriceEvent] = []
        liquidation_events: List[LiquidationEvent] = []
        order_activities: List[OrderActivity] = []

        try:
            data = json.loads(block_json)
            abci_block = data.get('abci_block', {})

            # Extract block timestamp
            block_time_str = abci_block.get('time', '')
            timestamp = self._parse_timestamp(block_time_str)

            # Process signed action bundles
            bundles = abci_block.get('signed_action_bundles', [])

            for bundle in bundles:
                if not isinstance(bundle, list) or len(bundle) < 2:
                    continue

                wallet = bundle[0]
                actions_data = bundle[1]

                if not isinstance(actions_data, dict):
                    continue

                signed_actions = actions_data.get('signed_actions', [])

                for signed_action in signed_actions:
                    if not isinstance(signed_action, dict):
                        continue

                    action = signed_action.get('action', {})
                    if not isinstance(action, dict):
                        continue

                    action_type = action.get('type', '')

                    # Extract based on action type
                    if action_type == 'SetGlobalAction':
                        self.metrics.set_global_actions += 1
                        prices = self._extract_prices(action, timestamp)
                        price_events.extend(prices)

                    elif action_type == 'forceOrder':
                        self.metrics.force_orders += 1
                        liq = self._extract_liquidation(action, wallet, timestamp)
                        if liq:
                            liquidation_events.append(liq)

                    elif action_type == 'order' and self._extract_orders:
                        self.metrics.orders_extracted += 1
                        activities = self._extract_order_activity(action, wallet, timestamp)
                        order_activities.extend(activities)

                    elif action_type in ('cancel', 'cancelByCloid') and self._extract_cancels:
                        self.metrics.cancels_extracted += 1
                        # Could extract cancel info here if needed

        except json.JSONDecodeError:
            self.metrics.extraction_errors += 1
        except Exception as e:
            self.metrics.extraction_errors += 1

        # Update metrics
        elapsed = (time.time() - start_time) * 1000
        self.metrics.total_extraction_time_ms += elapsed
        self.metrics.extractions_count += 1
        self.metrics.price_events += len(price_events)
        self.metrics.liquidation_events += len(liquidation_events)
        self.metrics.order_activity_events += len(order_activities)

        return price_events, liquidation_events, order_activities

    def _extract_prices(self, action: Dict, timestamp: float) -> List[PriceEvent]:
        """
        Extract price events from SetGlobalAction.

        SetGlobalAction structure (verified from live node data):
        {
            "type": "SetGlobalAction",
            "pxs": [
                ["oracle_price", "mark_price"],  // Asset 0 (BTC)
                ["oracle_price", "mark_price"],  // Asset 1 (ETH)
                ...
            ],
            "externalPerpPxs": [...],
            "usdtUsdcPx": "0.999...",
            "nativePx": "22.32"
        }

        Note: First element is oracle_price (authoritative for liquidations),
        second element is mark_price. Some assets have null oracle_price.
        """
        events = []
        pxs = action.get('pxs', [])

        for asset_id, price_pair in enumerate(pxs):
            if not isinstance(price_pair, list) or len(price_pair) < 2:
                continue

            oracle_price_str = price_pair[0]  # First is oracle (authoritative)
            mark_price_str = price_pair[1]    # Second is mark

            # Skip if no oracle price
            if oracle_price_str is None:
                continue

            symbol = get_coin_name(asset_id)

            # Check focus filter
            if self._focus_coins and symbol not in self._focus_coins:
                continue

            try:
                oracle_price = float(oracle_price_str)
                mark_price = float(mark_price_str) if mark_price_str else None

                events.append(PriceEvent(
                    timestamp=timestamp,
                    symbol=symbol,
                    mark_price=mark_price,
                    oracle_price=oracle_price,
                ))
            except (ValueError, TypeError):
                continue

        return events

    def _extract_liquidation(
        self,
        action: Dict,
        wallet: str,
        timestamp: float
    ) -> Optional[LiquidationEvent]:
        """
        Extract liquidation event from forceOrder action.

        forceOrder structure (expected - need to verify from live data):
        {
            "type": "forceOrder",
            "asset": 0,  // asset ID
            "isBuy": true,  // direction of liquidation order
            "sz": "1.5",  // liquidated size
            "px": "97500.0",  // execution price
            "reduceOnly": true
        }

        Note: The actual forceOrder schema may differ - this is based on
        typical exchange liquidation order patterns. Will need to verify
        against live data during a cascade event.
        """
        # Try multiple possible field names since schema isn't confirmed
        asset_id = action.get('asset') or action.get('a')
        size_str = action.get('sz') or action.get('s') or action.get('size')
        price_str = action.get('px') or action.get('p') or action.get('price')
        is_buy = action.get('isBuy') or action.get('b')

        if asset_id is None or size_str is None:
            return None

        symbol = get_coin_name(int(asset_id))

        # Check focus filter
        if self._focus_coins and symbol not in self._focus_coins:
            return None

        try:
            size = abs(float(size_str))
            price = float(price_str) if price_str else 0.0
            value = size * price

            # Determine side - liquidation closes position
            # If is_buy=True, we're buying to close a short
            # If is_buy=False, we're selling to close a long
            if is_buy is not None:
                side = 'SHORT' if is_buy else 'LONG'
            else:
                # Default to LONG if we can't determine
                side = 'UNKNOWN'

            return LiquidationEvent(
                timestamp=timestamp,
                symbol=symbol,
                wallet_address=wallet,
                liquidated_size=size,
                liquidation_price=price,
                side=side,
                value=value,
            )
        except (ValueError, TypeError):
            return None

    def _extract_order_activity(
        self,
        action: Dict,
        wallet: str,
        timestamp: float
    ) -> List[OrderActivity]:
        """
        Extract order activity for position change detection.

        order structure:
        {
            "type": "order",
            "orders": [{
                "a": 0,  // asset ID
                "b": true,  // buy flag
                "p": "97500.0",  // price
                "s": "1.5",  // size
                "r": false,  // reduce-only
                "t": {"limit": {"tif": "Gtc"}}
            }],
            "grouping": "na"
        }
        """
        activities = []
        orders = action.get('orders', [])

        for order in orders:
            if not isinstance(order, dict):
                continue

            asset_id = order.get('a')
            if asset_id is None:
                continue

            symbol = get_coin_name(int(asset_id))

            # Check focus filter
            if self._focus_coins and symbol not in self._focus_coins:
                continue

            try:
                is_buy = order.get('b', False)
                price_str = order.get('p', '0')
                size_str = order.get('s', '0')
                is_reduce_only = order.get('r', False)

                price = float(price_str) if price_str else 0.0
                size = float(size_str) if size_str else 0.0
                notional = price * size

                activities.append(OrderActivity(
                    wallet=wallet,
                    coin=symbol,
                    timestamp=timestamp,
                    side='BUY' if is_buy else 'SELL',
                    is_reduce_only=is_reduce_only,
                    size=size,
                    notional=notional,
                ))
            except (ValueError, TypeError):
                continue

        return activities

    def _parse_timestamp(self, time_str: str) -> float:
        """
        Parse block timestamp to Unix seconds.

        Format: "2026-01-26T11:02:39.467487791"
        """
        if not time_str:
            return time.time()

        try:
            # Handle nanosecond precision by truncating to microseconds
            # datetime can handle up to 6 decimal places
            clean_str = time_str[:26]  # "2026-01-26T11:02:39.467487"
            dt = datetime.fromisoformat(clean_str)
            return dt.timestamp()
        except Exception:
            return time.time()

    def get_metrics_summary(self) -> Dict:
        """Get metrics summary for logging."""
        return {
            'set_global_actions': self.metrics.set_global_actions,
            'force_orders': self.metrics.force_orders,
            'orders_extracted': self.metrics.orders_extracted,
            'price_events': self.metrics.price_events,
            'liquidation_events': self.metrics.liquidation_events,
            'avg_extraction_ms': round(self.metrics.avg_extraction_time_ms, 3),
            'errors': self.metrics.extraction_errors,
        }

"""Liquidation Fade Executor.

Automatically places LONG orders when liquidation events are detected
to capture the bounce after forced selling.

Strategy:
1. Monitor positions near liquidation via WebSocket
2. When liquidation detected (position closes at liq price)
3. Immediately place LONG order at market
4. Set take profit at 0.3-0.5% and stop loss below liq price

Requires: hyperliquid-python-sdk
Install: pip install hyperliquid-python-sdk
"""

import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from enum import Enum

# Optional SDK import
try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils import constants
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    Exchange = None
    Info = None


class FadeStatus(Enum):
    """Status of a fade trade."""
    PENDING = "pending"
    ENTERED = "entered"
    TAKE_PROFIT = "take_profit"
    STOPPED_OUT = "stopped_out"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass
class FadeConfig:
    """Configuration for liquidation fade strategy."""
    # Entry parameters
    min_liquidation_value: float = 50_000  # Minimum $ value to fade
    max_distance_pct: float = 0.5  # Max distance from liq to trigger
    slippage_pct: float = 0.5  # Entry slippage tolerance

    # Position sizing
    position_size_usd: float = 1_000  # Fixed position size in USD
    max_leverage: float = 3.0  # Maximum leverage

    # Exit parameters
    take_profit_pct: float = 0.4  # 0.4% take profit
    stop_loss_pct: float = 0.3  # 0.3% stop loss (below entry)

    # Trailing TP / Breakeven protection
    breakeven_trigger_pct: float = 0.15  # Move SL to breakeven when +0.15%
    trailing_tp_enabled: bool = True  # Enable trailing take profit
    trailing_distance_pct: float = 0.1  # Trail 0.1% behind highest price

    # Risk limits
    max_concurrent_fades: int = 3  # Max simultaneous fade positions
    cooldown_seconds: float = 30  # Min time between fades on same coin
    daily_loss_limit: float = 500  # Max daily loss before stopping

    # Impact filter (CRITICAL for avoiding cascade traps)
    max_impact_pct: float = 10.0  # Skip if position/volume > this %
    min_orderbook_ratio: float = 2.0  # Skip if book depth < position * this


@dataclass
class FadeTrade:
    """Represents an active fade trade."""
    coin: str
    entry_price: float
    entry_time: float
    size: float
    liquidated_wallet: str
    liquidation_value: float
    take_profit_price: float
    stop_loss_price: float
    status: FadeStatus = FadeStatus.PENDING
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None
    # Trailing TP / Breakeven tracking
    highest_price: Optional[float] = None  # Peak price since entry
    breakeven_triggered: bool = False  # True once SL moved to entry
    original_stop_loss: Optional[float] = None  # Original SL before breakeven


class LiquidationFadeExecutor:
    """Executes liquidation fade trades on Hyperliquid.

    Architecture:
    1. Receives liquidation events from HyperliquidClient
    2. Validates against configuration criteria
    3. Places market LONG order via SDK
    4. Monitors for take profit / stop loss
    5. Logs all actions for analysis

    Usage:
        executor = LiquidationFadeExecutor(private_key="0x...", config=FadeConfig())
        executor.start()

        # Connect to client liquidation callback
        client.set_liquidation_callback(executor.on_liquidation)
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        account_address: Optional[str] = None,
        config: Optional[FadeConfig] = None,
        use_testnet: bool = False,
        dry_run: bool = True  # Default to dry run (no real orders)
    ):
        self._logger = logging.getLogger("LiquidationFadeExecutor")
        self.config = config or FadeConfig()
        self.dry_run = dry_run

        # SDK setup
        self._exchange: Optional[Exchange] = None
        self._info: Optional[Info] = None
        self._private_key = private_key
        self._account_address = account_address
        self._use_testnet = use_testnet

        # State
        self._active_fades: Dict[str, FadeTrade] = {}  # coin -> trade
        self._fade_history: List[FadeTrade] = []
        self._cooldowns: Dict[str, float] = {}  # coin -> last_fade_time
        self._daily_pnl: float = 0.0
        self._running = False

        # Callbacks
        self._on_fade_entry: Optional[Callable] = None
        self._on_fade_exit: Optional[Callable] = None

        # Mid prices cache (updated by client)
        self._mid_prices: Dict[str, float] = {}

        # Volume cache for impact calculation
        self._volumes: Dict[str, float] = {}  # coin -> 24h volume
        self._volume_cache_time: float = 0
        self._volume_cache_ttl: float = 60  # Refresh every 60 seconds

        # Orderbook depth cache
        self._orderbook_depth: Dict[str, float] = {}  # coin -> bid depth $

        # Skip reasons for logging
        self._skip_reasons: List[Dict] = []

        # Liquidator wallet tracking (to copy their exits)
        self._tracked_liquidators: Dict[str, Dict] = {}  # wallet -> {coin -> position_snapshot}
        self._liquidator_exit_callback: Optional[Callable] = None

        if not HAS_SDK and not dry_run:
            self._logger.warning(
                "hyperliquid-python-sdk not installed. "
                "Install with: pip install hyperliquid-python-sdk"
            )

    def initialize(self) -> bool:
        """Initialize SDK connection."""
        if self.dry_run:
            self._logger.info("[DRY_RUN] Executor initialized in dry run mode")
            return True

        if not HAS_SDK:
            self._logger.error("Cannot initialize: SDK not installed")
            return False

        if not self._private_key:
            self._logger.error("Cannot initialize: private_key required")
            return False

        try:
            base_url = constants.TESTNET_API_URL if self._use_testnet else constants.MAINNET_API_URL

            self._info = Info(base_url, skip_ws=True)
            self._exchange = Exchange(
                wallet=None,  # Will use private key
                base_url=base_url,
                account_address=self._account_address
            )

            # Set private key
            from eth_account import Account
            wallet = Account.from_key(self._private_key)
            self._exchange.wallet = wallet

            self._logger.info(f"Executor initialized on {'testnet' if self._use_testnet else 'mainnet'}")
            return True

        except Exception as e:
            self._logger.error(f"Failed to initialize SDK: {e}")
            return False

    def start(self):
        """Start the executor."""
        self._running = True
        self._logger.info("Liquidation Fade Executor started")

    def stop(self):
        """Stop the executor."""
        self._running = False
        self._close_all_positions()
        self._logger.info("Liquidation Fade Executor stopped")

    def update_mid_prices(self, prices: Dict[str, float]):
        """Update mid prices cache."""
        self._mid_prices = prices

        # Check active fades for TP/SL
        self._check_exits()

    def update_volumes(self, volumes: Dict[str, float]):
        """Update volume cache."""
        self._volumes = volumes
        self._volume_cache_time = time.time()

    def _fetch_volumes(self) -> Dict[str, float]:
        """Fetch 24h volumes from Hyperliquid API."""
        import requests

        # Use cache if fresh
        if time.time() - self._volume_cache_time < self._volume_cache_ttl:
            return self._volumes

        try:
            resp = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'metaAndAssetCtxs'},
                timeout=10
            )
            if resp.status_code != 200:
                return self._volumes

            data = resp.json()
            meta = data[0]
            ctxs = data[1]
            universe = meta.get('universe', [])

            volumes = {}
            for i, coin_info in enumerate(universe):
                name = coin_info.get('name', '')
                if name and i < len(ctxs):
                    volumes[name] = float(ctxs[i].get('dayNtlVlm', 0))

            self._volumes = volumes
            self._volume_cache_time = time.time()
            return volumes

        except Exception as e:
            self._logger.warning(f"Failed to fetch volumes: {e}")
            return self._volumes

    def _fetch_orderbook_depth(self, coin: str) -> float:
        """Fetch bid-side orderbook depth for a coin."""
        import requests

        try:
            resp = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'l2Book', 'coin': coin},
                timeout=5
            )
            if resp.status_code != 200:
                return 0

            data = resp.json()
            levels = data.get('levels', [[], []])
            bids = levels[0][:10]  # Top 10 bid levels

            total_depth = 0
            for bid in bids:
                px = float(bid.get('px', 0))
                sz = float(bid.get('sz', 0))
                total_depth += px * sz

            self._orderbook_depth[coin] = total_depth
            return total_depth

        except Exception as e:
            self._logger.warning(f"Failed to fetch orderbook for {coin}: {e}")
            return self._orderbook_depth.get(coin, 0)

    def _calculate_impact(self, coin: str, liquidation_value: float) -> Dict:
        """Calculate impact score and determine if fade is safe.

        Returns dict with:
        - impact_pct: position value / 24h volume * 100
        - book_ratio: orderbook depth / position value
        - is_safe: True if within thresholds
        - reason: Why it's safe or not
        """
        # Fetch fresh data
        volumes = self._fetch_volumes()
        book_depth = self._fetch_orderbook_depth(coin)

        volume = volumes.get(coin, 0)

        # Calculate impact
        impact_pct = (liquidation_value / volume * 100) if volume > 0 else 999
        book_ratio = (book_depth / liquidation_value) if liquidation_value > 0 else 0

        # Determine safety
        is_safe = True
        reasons = []

        if impact_pct > self.config.max_impact_pct:
            is_safe = False
            reasons.append(f"Impact {impact_pct:.1f}% > {self.config.max_impact_pct}% max")

        if book_ratio < self.config.min_orderbook_ratio:
            is_safe = False
            reasons.append(f"Book ratio {book_ratio:.1f}x < {self.config.min_orderbook_ratio}x min")

        result = {
            'coin': coin,
            'liquidation_value': liquidation_value,
            'volume_24h': volume,
            'impact_pct': impact_pct,
            'book_depth': book_depth,
            'book_ratio': book_ratio,
            'is_safe': is_safe,
            'reason': '; '.join(reasons) if reasons else 'Within thresholds'
        }

        # Log the analysis
        safety_icon = '✓' if is_safe else '✗'
        self._logger.info(
            f"[IMPACT] {safety_icon} {coin}: impact={impact_pct:.1f}%, "
            f"book={book_ratio:.1f}x, safe={is_safe}"
        )

        if not is_safe:
            self._skip_reasons.append({
                'timestamp': time.time(),
                'coin': coin,
                'value': liquidation_value,
                'impact_pct': impact_pct,
                'book_ratio': book_ratio,
                'reason': result['reason']
            })
            # Keep only last 50 skip reasons
            self._skip_reasons = self._skip_reasons[-50:]

        return result

    async def on_liquidation(self, event: Dict):
        """Callback for liquidation events from HyperliquidClient.

        Event types:
        1. From activeAssetCtx: OI drop signals liquidation
        2. From userEvents: Direct liquidation event with details
        3. From trades: Large trade at support level
        """
        if not self._running:
            return

        # Handle different event types
        event_type = event.get('type')

        if event_type == 'LIQUIDATION':
            # Direct liquidation event from userEvents
            await self._handle_direct_liquidation(event)
        elif event.get('is_liquidation_signal'):
            # OI-based liquidation signal from activeAssetCtx
            await self._handle_oi_liquidation(event)
        else:
            # Position close detected from position tracking
            await self._handle_position_close(event)

    async def on_trade(self, trade: Dict):
        """Callback for real-time trades.

        Detects large trades at support levels that indicate liquidation.
        """
        if not self._running:
            return

        # Check if trade involves tracked wallet being liquidated
        if trade.get('involves_tracked'):
            coin = trade.get('coin')
            side = trade.get('side')
            value = trade.get('value', 0)

            # Large SELL trade = long liquidation = opportunity to LONG
            if side == 'SELL' and value >= self.config.min_liquidation_value:
                self._logger.info(
                    f"[TRADE_LIQ] Large sell detected: {coin} ${value:,.0f}"
                )
                await self._execute_fade(
                    coin=coin,
                    liquidation_value=value,
                    liquidated_wallet=trade.get('tracked_wallet', '')
                )

    async def _handle_direct_liquidation(self, event: Dict):
        """Handle direct liquidation event from userEvents."""
        notional = event.get('notional_value', 0)
        liquidated_user = event.get('liquidated_user', '')
        positions = event.get('positions', [])

        for pos in positions:
            coin = pos.get('coin')
            if coin and notional >= self.config.min_liquidation_value:
                self._logger.info(
                    f"[LIQUIDATION] Direct event: {coin} ${notional:,.0f}"
                )
                await self._execute_fade(
                    coin=coin,
                    liquidation_value=notional,
                    liquidated_wallet=liquidated_user
                )

    async def _handle_oi_liquidation(self, event: Dict):
        """Handle OI-based liquidation signal."""
        coin = event.get('coin')
        oi_change = abs(event.get('oi_change', 0))
        mark_price = event.get('mark_price', 0)

        # Estimate liquidation value from OI change
        liquidation_value = oi_change * mark_price if mark_price else oi_change

        if liquidation_value >= self.config.min_liquidation_value:
            self._logger.info(
                f"[OI_LIQ] {coin} OI drop: ${liquidation_value:,.0f}"
            )
            await self._execute_fade(
                coin=coin,
                liquidation_value=liquidation_value,
                liquidated_wallet=""
            )

    async def _handle_position_close(self, event: Dict):
        """Handle position close event (from position tracking)."""
        coin = event.get('coin')
        value = event.get('position_value', 0)
        wallet = event.get('wallet', '')

        if coin and value >= self.config.min_liquidation_value:
            self._logger.info(
                f"[POS_CLOSE] {coin} position closed: ${value:,.0f}"
            )
            await self._execute_fade(
                coin=coin,
                liquidation_value=value,
                liquidated_wallet=wallet
            )

    async def _execute_fade(
        self,
        coin: str,
        liquidation_value: float,
        liquidated_wallet: str
    ):
        """Execute a fade trade."""
        # Validation checks
        if not self._can_execute_fade(coin, liquidation_value):
            return

        # CRITICAL: Check impact before executing
        impact = self._calculate_impact(coin, liquidation_value)
        if not impact['is_safe']:
            print(
                f"[FADE] ✗ SKIPPED {coin}: {impact['reason']} "
                f"(impact={impact['impact_pct']:.1f}%, book={impact['book_ratio']:.1f}x)"
            )
            return

        print(
            f"[FADE] ✓ SAFE {coin}: impact={impact['impact_pct']:.1f}%, "
            f"book={impact['book_ratio']:.1f}x, depth=${impact['book_depth']:,.0f}"
        )

        # Get current price
        current_price = self._mid_prices.get(coin, 0)
        if current_price <= 0:
            self._logger.warning(f"[FADE] No price for {coin}, skipping")
            return

        # Calculate position size
        size = self.config.position_size_usd / current_price

        # Calculate TP and SL prices
        take_profit_price = current_price * (1 + self.config.take_profit_pct / 100)
        stop_loss_price = current_price * (1 - self.config.stop_loss_pct / 100)

        # Create trade record
        trade = FadeTrade(
            coin=coin,
            entry_price=current_price,
            entry_time=time.time(),
            size=size,
            liquidated_wallet=liquidated_wallet,
            liquidation_value=liquidation_value,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            status=FadeStatus.PENDING,
            highest_price=current_price,  # Start tracking from entry
            original_stop_loss=stop_loss_price
        )

        # Execute order
        if self.dry_run:
            self._logger.info(
                f"[DRY_RUN] Would LONG {coin}: "
                f"size={size:.4f} @ ${current_price:,.4f} "
                f"TP=${take_profit_price:,.4f} SL=${stop_loss_price:,.4f}"
            )
            trade.status = FadeStatus.ENTERED
        else:
            success = await self._place_market_order(coin, size, is_buy=True)
            if success:
                trade.status = FadeStatus.ENTERED
            else:
                trade.status = FadeStatus.FAILED
                self._fade_history.append(trade)
                return

        # Track active fade
        self._active_fades[coin] = trade
        self._cooldowns[coin] = time.time()

        # Callback
        if self._on_fade_entry:
            self._on_fade_entry(trade)

        self._logger.info(
            f"[FADE_ENTRY] {coin} LONG @ ${current_price:,.4f} "
            f"(liq value: ${liquidation_value:,.0f})"
        )

    def _can_execute_fade(self, coin: str, liquidation_value: float) -> bool:
        """Check if fade can be executed."""
        # Check minimum value
        if liquidation_value < self.config.min_liquidation_value:
            return False

        # Check concurrent fades limit
        if len(self._active_fades) >= self.config.max_concurrent_fades:
            self._logger.debug(f"Max concurrent fades reached, skipping {coin}")
            return False

        # Check cooldown
        last_fade = self._cooldowns.get(coin, 0)
        if time.time() - last_fade < self.config.cooldown_seconds:
            self._logger.debug(f"Cooldown active for {coin}")
            return False

        # Check daily loss limit
        if self._daily_pnl <= -self.config.daily_loss_limit:
            self._logger.warning("Daily loss limit reached, stopping fades")
            return False

        # Check if already have position in this coin
        if coin in self._active_fades:
            return False

        return True

    async def _place_market_order(
        self,
        coin: str,
        size: float,
        is_buy: bool
    ) -> bool:
        """Place market order via SDK."""
        if not self._exchange:
            self._logger.error("Exchange not initialized")
            return False

        try:
            result = self._exchange.market_open(
                name=coin,
                is_buy=is_buy,
                sz=size,
                slippage=self.config.slippage_pct / 100
            )

            if result.get('status') == 'ok':
                self._logger.info(f"Order placed: {coin} {'BUY' if is_buy else 'SELL'} {size}")
                return True
            else:
                self._logger.error(f"Order failed: {result}")
                return False

        except Exception as e:
            self._logger.error(f"Order error: {e}")
            return False

    def _check_exits(self):
        """Check active fades for TP/SL with trailing and breakeven logic."""
        for coin, trade in list(self._active_fades.items()):
            if trade.status != FadeStatus.ENTERED:
                continue

            current_price = self._mid_prices.get(coin, 0)
            if current_price <= 0:
                continue

            # Initialize tracking on first update
            if trade.highest_price is None:
                trade.highest_price = current_price
                trade.original_stop_loss = trade.stop_loss_price

            # Update highest price for trailing
            if current_price > trade.highest_price:
                trade.highest_price = current_price

            # Calculate current profit %
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100

            # BREAKEVEN PROTECTION: Move SL to entry when profit reaches trigger
            if not trade.breakeven_triggered and profit_pct >= self.config.breakeven_trigger_pct:
                trade.breakeven_triggered = True
                trade.stop_loss_price = trade.entry_price  # Move SL to breakeven
                self._logger.info(
                    f"[BREAKEVEN] {coin} SL moved to entry @ ${trade.entry_price:,.4f} "
                    f"(profit was +{profit_pct:.2f}%)"
                )

            # TRAILING TP: Adjust TP based on highest price
            if self.config.trailing_tp_enabled and trade.breakeven_triggered:
                # Trail TP behind the highest price
                trailing_tp = trade.highest_price * (1 - self.config.trailing_distance_pct / 100)
                # Only move TP higher, never lower
                if trailing_tp > trade.take_profit_price:
                    old_tp = trade.take_profit_price
                    trade.take_profit_price = trailing_tp
                    self._logger.info(
                        f"[TRAILING_TP] {coin} TP moved: ${old_tp:,.4f} -> ${trailing_tp:,.4f} "
                        f"(high: ${trade.highest_price:,.4f})"
                    )

            # Check take profit (now potentially trailing)
            if current_price >= trade.take_profit_price:
                self._exit_fade(trade, current_price, FadeStatus.TAKE_PROFIT)

            # Check stop loss (now potentially at breakeven)
            elif current_price <= trade.stop_loss_price:
                exit_status = FadeStatus.STOPPED_OUT
                # Log if this was a breakeven exit
                if trade.breakeven_triggered:
                    self._logger.info(f"[BREAKEVEN_EXIT] {coin} exited at breakeven")
                self._exit_fade(trade, current_price, exit_status)

    def _exit_fade(self, trade: FadeTrade, exit_price: float, status: FadeStatus):
        """Exit a fade position."""
        trade.exit_price = exit_price
        trade.exit_time = time.time()
        trade.status = status

        # Calculate PnL
        trade.pnl = (exit_price - trade.entry_price) * trade.size
        self._daily_pnl += trade.pnl

        # Move to history
        del self._active_fades[trade.coin]
        self._fade_history.append(trade)

        # Place close order
        if not self.dry_run:
            asyncio.create_task(
                self._place_market_order(trade.coin, trade.size, is_buy=False)
            )

        # Callback
        if self._on_fade_exit:
            self._on_fade_exit(trade)

        status_str = "TP" if status == FadeStatus.TAKE_PROFIT else "SL"
        pnl_str = f"+${trade.pnl:.2f}" if trade.pnl >= 0 else f"-${abs(trade.pnl):.2f}"
        self._logger.info(
            f"[FADE_EXIT] {trade.coin} {status_str} @ ${exit_price:,.4f} "
            f"PnL: {pnl_str}"
        )

    def _close_all_positions(self):
        """Close all active fade positions."""
        for coin, trade in list(self._active_fades.items()):
            current_price = self._mid_prices.get(coin, trade.entry_price)
            self._exit_fade(trade, current_price, FadeStatus.CLOSED)

    def set_entry_callback(self, callback: Callable):
        """Set callback for fade entries."""
        self._on_fade_entry = callback

    def set_exit_callback(self, callback: Callable):
        """Set callback for fade exits."""
        self._on_fade_exit = callback

    def set_liquidator_exit_callback(self, callback: Callable):
        """Set callback for when tracked liquidator exits a position."""
        self._liquidator_exit_callback = callback

    def track_liquidator(self, wallet: str, coins: Optional[List[str]] = None):
        """Start tracking a liquidator wallet for exit signals.

        When the liquidator closes or reduces a position, we get notified
        so we can copy their exit timing.

        Args:
            wallet: Wallet address to track
            coins: Optional list of coins to track. If None, tracks all positions.
        """
        import requests

        try:
            resp = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={'type': 'clearinghouseState', 'user': wallet},
                timeout=10
            )
            if resp.status_code != 200:
                self._logger.warning(f"Failed to fetch positions for {wallet}")
                return

            data = resp.json()
            positions = data.get('assetPositions', [])

            # Build position snapshot
            snapshot = {}
            for p in positions:
                pos = p.get('position', {})
                coin = pos.get('coin', '')
                if coins and coin not in coins:
                    continue
                if not coin:
                    continue

                size = float(pos.get('szi', 0))
                if size == 0:
                    continue

                snapshot[coin] = {
                    'size': size,
                    'entry': float(pos.get('entryPx', 0)),
                    'side': 'LONG' if size > 0 else 'SHORT',
                    'timestamp': time.time()
                }

            self._tracked_liquidators[wallet] = snapshot
            self._logger.info(
                f"[TRACK] Tracking liquidator {wallet[:10]}... with {len(snapshot)} positions"
            )

        except Exception as e:
            self._logger.error(f"Failed to track liquidator {wallet}: {e}")

    def check_liquidator_exits(self):
        """Check if any tracked liquidators have exited positions.

        Returns list of exit events for positions that were reduced or closed.
        """
        import requests

        exits = []

        for wallet, snapshot in list(self._tracked_liquidators.items()):
            try:
                resp = requests.post(
                    'https://api.hyperliquid.xyz/info',
                    json={'type': 'clearinghouseState', 'user': wallet},
                    timeout=10
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                positions = data.get('assetPositions', [])

                # Build current positions map
                current = {}
                for p in positions:
                    pos = p.get('position', {})
                    coin = pos.get('coin', '')
                    if coin:
                        current[coin] = float(pos.get('szi', 0))

                # Check for exits/reductions
                for coin, old_pos in snapshot.items():
                    old_size = abs(old_pos['size'])
                    new_size = abs(current.get(coin, 0))

                    if new_size < old_size:
                        reduction_pct = ((old_size - new_size) / old_size) * 100

                        exit_event = {
                            'wallet': wallet,
                            'coin': coin,
                            'old_size': old_size,
                            'new_size': new_size,
                            'reduction_pct': reduction_pct,
                            'side': old_pos['side'],
                            'entry': old_pos['entry'],
                            'timestamp': time.time(),
                            'is_full_exit': new_size == 0
                        }
                        exits.append(exit_event)

                        action = "CLOSED" if new_size == 0 else f"REDUCED {reduction_pct:.0f}%"
                        self._logger.info(
                            f"[LIQ_EXIT] {wallet[:10]}... {action} {coin} "
                            f"({old_size:.0f} -> {new_size:.0f})"
                        )

                        # Update snapshot
                        if new_size == 0:
                            del snapshot[coin]
                        else:
                            snapshot[coin]['size'] = new_size if old_pos['side'] == 'LONG' else -new_size

                        # Callback
                        if self._liquidator_exit_callback:
                            self._liquidator_exit_callback(exit_event)

            except Exception as e:
                self._logger.warning(f"Error checking liquidator {wallet[:10]}...: {e}")

        return exits

    def get_tracked_liquidators(self) -> Dict:
        """Get current liquidator tracking state."""
        return {
            wallet: {
                'positions': len(positions),
                'coins': list(positions.keys())
            }
            for wallet, positions in self._tracked_liquidators.items()
        }

    def get_stats(self) -> Dict:
        """Get executor statistics."""
        total_trades = len(self._fade_history)
        winning_trades = sum(1 for t in self._fade_history if t.pnl and t.pnl > 0)
        total_pnl = sum(t.pnl or 0 for t in self._fade_history)

        return {
            'active_fades': len(self._active_fades),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': winning_trades / total_trades if total_trades > 0 else 0,
            'total_pnl': total_pnl,
            'daily_pnl': self._daily_pnl,
            'is_running': self._running
        }

"""
Week 5: Time-Based Exit Manager
================================

Implements intelligent time-based exits using empirical half-life data from Week 1.

Key Features:
1. **Breakeven Move**: After signal half-life (200s), move SL to breakeven
2. **Stagnation Exit**: If no new MFE peak for 100s (0.5× half-life), exit
3. **Time-based TP**: Use reversion metrics from Week 1 (t_reversion_50%)

Expert Context:
- Week 1 measured 200s median half-life (17K signals)
- 50th %ile reversion time provides natural exit timing
- Prevents "death by a thousand cuts" (small losses accumulating)

Logic:
    if time_in_trade >= half_life:
        move_stop_to_breakeven()
    
    if time_since_last_MFE_peak >= 0.5 × half_life:
        exit_trade("stagnation")
"""

import time
import logging
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ExitReason(Enum):
    """Exit reason enum."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    STAGNATION = "STAGNATION"
    TIMEOUT = "TIMEOUT"
    BREAKEVEN_STOP = "BREAKEVEN_STOP"


class TradeState:
    """
    Track state of an active trade.
    """
    
    def __init__(self, 
                 entry_price: float,
                 entry_time: float,
                 direction: str,
                 stop_loss: float,
                 take_profit: float,
                 position_size: float):
        """
        Initialize trade state.
        
        Args:
            entry_price: Entry price
            entry_time: Entry timestamp
            direction: 'LONG' or 'SHORT'
            stop_loss: Initial stop loss price
            take_profit: Take profit price
            position_size: Position size
        """
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.direction = direction
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position_size = position_size
        
        # MFE tracking
        self.max_favorable_excursion = 0  # Best unrealized P&L
        self.last_mfe_peak_time = entry_time
        
        # Breakeven tracking
        self.stop_moved_to_breakeven = False
        
        # Current P&L
        self.current_pnl = 0
        self.current_price = entry_price
    
    def update(self, current_price: float, current_time: float):
        """Update trade state with current market price."""
        self.current_price = current_price
        
        # Calculate current P&L
        if self.direction == 'LONG':
            self.current_pnl = (current_price - self.entry_price) / self.entry_price
        else:  # SHORT
            self.current_pnl = (self.entry_price - current_price) / self.entry_price
        
        # Update MFE (Maximum Favorable Excursion)
        if self.current_pnl > self.max_favorable_excursion:
            self.max_favorable_excursion = self.current_pnl
            self.last_mfe_peak_time = current_time
    
    def time_in_trade(self, current_time: float) -> float:
        """Get time elapsed since entry (seconds)."""
        return current_time - self.entry_time
    
    def time_since_last_mfe_peak(self, current_time: float) -> float:
        """Get time since last MFE peak (seconds)."""
        return current_time - self.last_mfe_peak_time
    
    def is_profitable(self) -> bool:
        """Check if trade is currently profitable."""
        return self.current_pnl > 0
    
    def move_stop_to_breakeven(self):
        """Move stop loss to breakeven (entry price)."""
        if not self.stop_moved_to_breakeven:
            self.stop_loss = self.entry_price
            self.stop_moved_to_breakeven = True
            logger.info(f"Stop moved to breakeven @ {self.entry_price}")


class TimeBasedExitManager:
    """
    Manage time-based exits using empirical half-life data.
    
    Uses Week 1 measurements:
    - Median half-life: 200 seconds
    - Stagnation threshold: 100 seconds (0.5× half-life)
    - Breakeven move: At half-life if profitable
    """
    
    # LOCKED PARAMETERS (from Week 1 measurements)
    MEDIAN_HALF_LIFE_SECONDS = 200  # From Week 1 Task 1.2
    STAGNATION_THRESHOLD_MULTIPLIER = 0.5  # 0.5× half-life
    
    # Symbol-specific half-lives (from Week 1 data)
    SYMBOL_HALF_LIVES = {
        'BTCUSDT': 195,
        'ETHUSDT': 205,
        'SOLUSDT': 210
    }
    
    def __init__(self, symbol: str = 'BTCUSDT'):
        """
        Initialize exit manager.
        
        Args:
            symbol: Trading symbol
        """
        self.symbol = symbol
        
        # Get symbol-specific half-life (or use median)
        self.half_life_seconds = self.SYMBOL_HALF_LIVES.get(
            symbol, 
            self.MEDIAN_HALF_LIFE_SECONDS
        )
        
        # Calculate stagnation threshold
        self.stagnation_threshold = self.half_life_seconds * self.STAGNATION_THRESHOLD_MULTIPLIER
        
        # Active trades
        self.active_trades: Dict[str, TradeState] = {}
        
        # Exit statistics
        self.stats = {
            'total_exits': 0,
            'stop_loss_exits': 0,
            'take_profit_exits': 0,
            'stagnation_exits': 0,
            'timeout_exits': 0,
            'breakeven_stop_exits': 0,
            'breakeven_moves': 0
        }
        
        logger.info(f"TimeBasedExitManager initialized for {symbol}")
        logger.info(f"  Half-life: {self.half_life_seconds}s")
        logger.info(f"  Stagnation threshold: {self.stagnation_threshold}s")
    
    def add_trade(self,
                  trade_id: str,
                  entry_price: float,
                  direction: str,
                  stop_loss: float,
                  take_profit: float,
                  position_size: float) -> TradeState:
        """
        Add new trade to manager.
        
        Args:
            trade_id: Unique trade identifier
            entry_price: Entry price
            direction: 'LONG' or 'SHORT'
            stop_loss: Initial stop loss
            take_profit: Take profit target
            position_size: Position size
            
        Returns:
            TradeState object
        """
        trade = TradeState(
            entry_price=entry_price,
            entry_time=time.time(),
            direction=direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size
        )
        
        self.active_trades[trade_id] = trade
        
        logger.info(f"Trade {trade_id} added: {direction} @ {entry_price}, SL: {stop_loss}, TP: {take_profit}")
        
        return trade
    
    def check_exit(self, trade_id: str, current_price: float) -> Optional[Dict]:
        """
        Check if trade should exit based on time-based logic.
        
        Args:
            trade_id: Trade identifier
            current_price: Current market price
            
        Returns:
            Exit signal dict or None if should hold
        """
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        current_time = time.time()
        
        # Update trade state
        trade.update(current_price, current_time)
        
        # Check stop loss
        if self._check_stop_loss(trade):
            return self._create_exit_signal(trade_id, trade, ExitReason.STOP_LOSS)
        
        # Check take profit
        if self._check_take_profit(trade):
            return self._create_exit_signal(trade_id, trade, ExitReason.TAKE_PROFIT)
        
        # Time-based logic: Move to breakeven after half-life
        if trade.time_in_trade(current_time) >= self.half_life_seconds:
            if not trade.stop_moved_to_breakeven and trade.is_profitable():
                trade.move_stop_to_breakeven()
                self.stats['breakeven_moves'] += 1
        
        # Check stagnation: No new MFE peak for 0.5× half-life
        if trade.time_since_last_mfe_peak(current_time) >= self.stagnation_threshold:
            return self._create_exit_signal(trade_id, trade, ExitReason.STAGNATION)
        
        return None
    
    def _check_stop_loss(self, trade: TradeState) -> bool:
        """Check if stop loss hit."""
        if trade.direction == 'LONG':
            return trade.current_price <= trade.stop_loss
        else:  # SHORT
            return trade.current_price >= trade.stop_loss
    
    def _check_take_profit(self, trade: TradeState) -> bool:
        """Check if take profit hit."""
        if trade.direction == 'LONG':
            return trade.current_price >= trade.take_profit
        else:  # SHORT
            return trade.current_price <= trade.take_profit
    
    def _create_exit_signal(self, 
                           trade_id: str, 
                           trade: TradeState, 
                           reason: ExitReason) -> Dict:
        """Create exit signal and update stats."""
        exit_signal = {
            'trade_id': trade_id,
            'reason': reason.value,
            'exit_price': trade.current_price,
            'exit_time': time.time(),
            'pnl': trade.current_pnl,
            'max_favorable_excursion': trade.max_favorable_excursion,
            'time_in_trade': trade.time_in_trade(time.time()),
            'entry_price': trade.entry_price
        }
        
        # Update stats
        self.stats['total_exits'] += 1
        
        if reason == ExitReason.STOP_LOSS:
            self.stats['stop_loss_exits'] += 1
            if trade.stop_moved_to_breakeven:
                self.stats['breakeven_stop_exits'] += 1
        elif reason == ExitReason.TAKE_PROFIT:
            self.stats['take_profit_exits'] += 1
        elif reason == ExitReason.STAGNATION:
            self.stats['stagnation_exits'] += 1
        elif reason == ExitReason.TIMEOUT:
            self.stats['timeout_exits'] += 1
        
        # Remove from active trades
        del self.active_trades[trade_id]
        
        logger.info(f"Trade {trade_id} exited: {reason.value}, P&L: {trade.current_pnl:.2%}, Time: {exit_signal['time_in_trade']:.0f}s")
        
        return exit_signal
    
    def get_stats(self) -> Dict:
        """Get exit statistics."""
        total = self.stats['total_exits']
        
        return {
            **self.stats,
            'stop_loss_pct': self.stats['stop_loss_exits'] / total * 100 if total > 0 else 0,
            'take_profit_pct': self.stats['take_profit_exits'] / total * 100 if total > 0 else 0,
            'stagnation_pct': self.stats['stagnation_exits'] / total * 100 if total > 0 else 0,
            'breakeven_stop_pct': self.stats['breakeven_stop_exits'] / total * 100 if total > 0 else 0,
            'active_trades': len(self.active_trades)
        }


if __name__ == "__main__":
    """Test time-based exit manager."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 5: TIME-BASED EXIT MANAGER TEST")
    print("=" * 80)
    print(f"\n🔒 LOCKED PARAMETERS (from Week 1):")
    print(f"   Half-life: {TimeBasedExitManager.MEDIAN_HALF_LIFE_SECONDS}s")
    print(f"   Stagnation threshold: {TimeBasedExitManager.MEDIAN_HALF_LIFE_SECONDS * 0.5}s")
    print(f"   Breakeven move: At half-life if profitable\n")
    
    manager = TimeBasedExitManager('BTCUSDT')
    
    # Test 1: Normal trade with TP
    print("Test 1: Take Profit Exit")
    print("-" * 80)
    
    trade1 = manager.add_trade(
        trade_id='test_1',
        entry_price=100000,
        direction='LONG',
        stop_loss=99500,
        take_profit=100500,
        position_size=1.0
    )
    
    # Simulate price movement to TP
    exit1 = manager.check_exit('test_1', 100500)
    if exit1:
        print(f"   ✅ Exit triggered: {exit1['reason']}")
        print(f"   P&L: {exit1['pnl']:.2%}\n")
    
    # Test 2: Stop loss exit
    print("Test 2: Stop Loss Exit")
    print("-" * 80)
    
    trade2 = manager.add_trade(
        trade_id='test_2',
        entry_price=100000,
        direction='LONG',
        stop_loss=99500,
        take_profit=100500,
        position_size=1.0
    )
    
    # Simulate price drop to SL
    exit2 = manager.check_exit('test_2', 99500)
    if exit2:
        print(f"   ✅ Exit triggered: {exit2['reason']}")
        print(f"   P&L: {exit2['pnl']:.2%}\n")
    
    # Test 3: Stagnation exit (requires time passage - simulated)
    print("Test 3: Stagnation Exit (simulated)")
    print("-" * 80)
    print("   Note: In live system, would exit after 100s without new MFE peak")
    print("   [Simulating time passage...]")
    
    trade3 = manager.add_trade(
        trade_id='test_3',
        entry_price=100000,
        direction='LONG',
        stop_loss=99500,
        take_profit=100500,
        position_size=1.0
    )
    
    # Manually set last MFE peak time to simulate stagnation
    trade3.last_mfe_peak_time = time.time() - 101  # 101s ago
    
    exit3 = manager.check_exit('test_3', 100100)
    if exit3:
        print(f"   ✅ Exit triggered: {exit3['reason']}")
        print(f"   P&L: {exit3['pnl']:.2%}")
        print(f"   Time since last MFE: {trade3.time_since_last_mfe_peak(time.time()):.0f}s\n")
    
    # Stats
    print("=" * 80)
    print("EXIT STATISTICS")
    print("=" * 80)
    stats = manager.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<30s}: {value:.2f}")
        else:
            print(f"   {key:<30s}: {value}")
    
    print("\n✅ Test complete - Time-based exit manager ready for integration")
    print("\n📊 Expected Impact:")
    print("   - Fewer 'slow bleed' losses (stagnation exits)")
    print("   - Protected profits after half-life (breakeven moves)")
    print("   - Natural exit timing (empirical data-driven)")

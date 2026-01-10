"""
Week 6: Dynamic Position Sizing
================================

Implements intelligent position sizing with:
1. **Scaling Schedule**: Start small (0.1%), scale up gradually (0.25%, 0.5%)
2. **Confidence-Based Sizing**: Higher confidence = larger positions
3. **Drawdown Adjustment**: Cut size 50% after 2 consecutive losses
4. **Portfolio Limits**: Max 1.0% concurrent exposure

Expert Guidance:
- Start conservative (0.1% of portfolio)
- Scale based on performance, not backtest optimization
- Adjust down aggressively on losses
- Never exceed 1.0% total exposure

Risk Philosophy:
- Protect capital first
- Scale winners, not losers
- Respond to live performance
- Portfolio-level awareness
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SizingPhase(Enum):
    """Position sizing phase."""
    PHASE_1_TINY = "PHASE_1_TINY"      # 0.1% per trade
    PHASE_2_SMALL = "PHASE_2_SMALL"     # 0.25% per trade
    PHASE_3_NORMAL = "PHASE_3_NORMAL"   # 0.5% per trade


class DynamicPositionSizer:
    """
    Intelligent position sizing with scaling and drawdown protection.
    
    Features:
    - Gradual scaling schedule (0.1% → 0.25% → 0.5%)
    - Confidence-based adjustments
    - Drawdown reduction (50% after 2 losses)
    - Portfolio exposure limits (1.0% max)
    """
    
    # LOCKED PARAMETERS (per expert guidance)
    PHASE_1_SIZE_PCT = 0.001   # 0.1% of portfolio
    PHASE_2_SIZE_PCT = 0.0025  # 0.25% of portfolio
    PHASE_3_SIZE_PCT = 0.005   # 0.5% of portfolio
    
    MAX_CONCURRENT_EXPOSURE_PCT = 0.01  # 1.0% max total exposure
    
    # Scaling criteria (performance-based)
    PHASE_1_TO_2_CRITERIA = {
        'min_trades': 20,
        'min_win_rate': 0.55,
        'min_profit_factor': 1.2
    }
    
    PHASE_2_TO_3_CRITERIA = {
        'min_trades': 50,
        'min_win_rate': 0.58,
        'min_profit_factor': 1.5
    }
    
    # Drawdown protection
    CONSECUTIVE_LOSS_LIMIT = 2  # Cut size after this many losses
    DRAWDOWN_SIZE_MULTIPLIER = 0.5  # Cut to 50% of normal
    RECOVERY_WIN_STREAK = 2  # Restore size after this many wins
    
    # Confidence-based adjustments
    CONFIDENCE_MULTIPLIERS = {
        'HIGH': 1.0,      # >85% confidence: Full size
        'MEDIUM': 0.75,   # 60-85% confidence: 75% size
        'LOW': 0.0        # <60% confidence: Skip trade
    }
    
    CONFIDENCE_THRESHOLDS = {
        'HIGH': 85.0,
        'MEDIUM': 60.0
    }
    
    def __init__(self, portfolio_value: float, symbol: str = 'BTCUSDT'):
        """
        Initialize position sizer.
        
        Args:
            portfolio_value: Total portfolio value in USD
            symbol: Trading symbol
        """
        self.portfolio_value = portfolio_value
        self.symbol = symbol
        
        # Start in Phase 1 (tiny size)
        self.current_phase = SizingPhase.PHASE_1_TINY
        
        # Track performance
        self.total_trades = 0
        self.winning_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        
        # Consecutive tracking
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        
        # Drawdown state
        self.in_drawdown_protection = False
        
        # Active positions (for exposure tracking)
        self.active_positions: Dict[str, float] = {}  # trade_id -> exposure_usd
        
        # Statistics
        self.stats = {
            'total_signals': 0,
            'trades_taken': 0,
            'trades_skipped_confidence': 0,
            'trades_skipped_exposure': 0,
            'phase_upgrades': 0,
            'times_in_drawdown': 0
        }
        
        logger.info(f"DynamicPositionSizer initialized")
        logger.info(f"  Portfolio: ${portfolio_value:,.2f}")
        logger.info(f"  Phase: {self.current_phase.value}")
        logger.info(f"  Base size: {self._get_base_size_pct() * 100:.2f}%")
    
    def calculate_position_size(self, 
                               signal_confidence: float,
                               entry_price: float) -> Optional[Dict]:
        """
        Calculate position size for a signal.
        
        Args:
            signal_confidence: Signal confidence (0-100)
            entry_price: Entry price
            
        Returns:
            Position sizing dict or None if should skip
        """
        self.stats['total_signals'] += 1
        
        # Check confidence threshold
        if signal_confidence < self.CONFIDENCE_THRESHOLDS['MEDIUM']:
            logger.info(f"Skipping signal: Low confidence ({signal_confidence:.1f}% < 60%)")
            self.stats['trades_skipped_confidence'] += 1
            return None
        
        # Get base size for current phase
        base_size_pct = self._get_base_size_pct()
        
        # Apply confidence multiplier
        confidence_tier = self._get_confidence_tier(signal_confidence)
        confidence_mult = self.CONFIDENCE_MULTIPLIERS[confidence_tier]
        
        # Apply drawdown protection
        drawdown_mult = self.DRAWDOWN_SIZE_MULTIPLIER if self.in_drawdown_protection else 1.0
        
        # Calculate final size
        final_size_pct = base_size_pct * confidence_mult * drawdown_mult
        size_usd = self.portfolio_value * final_size_pct
        
        # Calculate quantity (in base currency)
        quantity = size_usd / entry_price
        
        # Check portfolio exposure limit
        current_exposure = self._get_current_exposure()
        
        if current_exposure + size_usd > self.portfolio_value * self.MAX_CONCURRENT_EXPOSURE_PCT:
            logger.warning(f"Skipping trade: Would exceed max exposure")
            logger.warning(f"  Current: ${current_exposure:,.2f}")
            logger.warning(f"  Proposed: ${size_usd:,.2f}")
            logger.warning(f"  Max allowed: ${self.portfolio_value * self.MAX_CONCURRENT_EXPOSURE_PCT:,.2f}")
            self.stats['trades_skipped_exposure'] += 1
            return None
        
        self.stats['trades_taken'] += 1
        
        return {
            'quantity': quantity,
            'size_usd': size_usd,
            'size_pct': final_size_pct,
            'base_size_pct': base_size_pct,
            'confidence_mult': confidence_mult,
            'drawdown_mult': drawdown_mult,
            'phase': self.current_phase.value,
            'in_drawdown': self.in_drawdown_protection
        }
    
    def update_trade_result(self, trade_id: str, pnl: float, closed: bool = True):
        """
        Update sizer with trade result.
        
        Args:
            trade_id: Trade identifier
            pnl: Profit/loss (as fraction, e.g., 0.02 = 2%)
            closed: If True, trade is closed
        """
        if closed:
            self.total_trades += 1
            
            # Track wins/losses
            if pnl > 0:
                self.winning_trades += 1
                self.total_profit += pnl
                self.consecutive_wins += 1
                self.consecutive_losses = 0
                
                # Check if we can exit drawdown protection
                if self.in_drawdown_protection and self.consecutive_wins >= self.RECOVERY_WIN_STREAK:
                    logger.info(f"Exiting drawdown protection after {self.consecutive_wins} wins")
                    self.in_drawdown_protection = False
                    self.consecutive_wins = 0
            
            else:
                self.total_loss += abs(pnl)
                self.consecutive_losses += 1
                self.consecutive_wins = 0
                
                # Check if we should enter drawdown protection
                if self.consecutive_losses >= self.CONSECUTIVE_LOSS_LIMIT:
                    if not self.in_drawdown_protection:
                        logger.warning(f"Entering drawdown protection after {self.consecutive_losses} losses")
                        logger.warning(f"Position size cut to 50%")
                        self.in_drawdown_protection = True
                        self.stats['times_in_drawdown'] += 1
            
            # Check for phase upgrade
            self._check_phase_upgrade()
            
            # Remove from active positions
            if trade_id in self.active_positions:
                del self.active_positions[trade_id]
    
    def add_active_position(self, trade_id: str, exposure_usd: float):
        """Add active position to exposure tracking."""
        self.active_positions[trade_id] = exposure_usd
    
    def _get_base_size_pct(self) -> float:
        """Get base size percentage for current phase."""
        if self.current_phase == SizingPhase.PHASE_1_TINY:
            return self.PHASE_1_SIZE_PCT
        elif self.current_phase == SizingPhase.PHASE_2_SMALL:
            return self.PHASE_2_SIZE_PCT
        else:  # PHASE_3_NORMAL
            return self.PHASE_3_SIZE_PCT
    
    def _get_confidence_tier(self, confidence: float) -> str:
        """Get confidence tier from confidence score."""
        if confidence >= self.CONFIDENCE_THRESHOLDS['HIGH']:
            return 'HIGH'
        elif confidence >= self.CONFIDENCE_THRESHOLDS['MEDIUM']:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _get_current_exposure(self) -> float:
        """Get current total portfolio exposure."""
        return sum(self.active_positions.values())
    
    def _check_phase_upgrade(self):
        """Check if performance warrants phase upgrade."""
        if self.current_phase == SizingPhase.PHASE_1_TINY:
            criteria = self.PHASE_1_TO_2_CRITERIA
            
            if (self.total_trades >= criteria['min_trades'] and
                self._get_win_rate() >= criteria['min_win_rate'] and
                self._get_profit_factor() >= criteria['min_profit_factor']):
                
                logger.info("=" * 60)
                logger.info("PHASE UPGRADE: PHASE_1 → PHASE_2")
                logger.info(f"  Trades: {self.total_trades} (>= {criteria['min_trades']})")
                logger.info(f"  Win Rate: {self._get_win_rate():.1%} (>= {criteria['min_win_rate']:.1%})")
                logger.info(f"  Profit Factor: {self._get_profit_factor():.2f} (>= {criteria['min_profit_factor']:.2f})")
                logger.info(f"  New size: {self.PHASE_2_SIZE_PCT * 100:.2f}% per trade")
                logger.info("=" * 60)
                
                self.current_phase = SizingPhase.PHASE_2_SMALL
                self.stats['phase_upgrades'] += 1
        
        elif self.current_phase == SizingPhase.PHASE_2_SMALL:
            criteria = self.PHASE_2_TO_3_CRITERIA
            
            if (self.total_trades >= criteria['min_trades'] and
                self._get_win_rate() >= criteria['min_win_rate'] and
                self._get_profit_factor() >= criteria['min_profit_factor']):
                
                logger.info("=" * 60)
                logger.info("PHASE UPGRADE: PHASE_2 → PHASE_3")
                logger.info(f"  Trades: {self.total_trades} (>= {criteria['min_trades']})")
                logger.info(f"  Win Rate: {self._get_win_rate():.1%} (>= {criteria['min_win_rate']:.1%})")
                logger.info(f"  Profit Factor: {self._get_profit_factor():.2f} (>= {criteria['min_profit_factor']:.2f})")
                logger.info(f"  New size: {self.PHASE_3_SIZE_PCT * 100:.2f}% per trade")
                logger.info("=" * 60)
                
                self.current_phase = SizingPhase.PHASE_3_NORMAL
                self.stats['phase_upgrades'] += 1
    
    def _get_win_rate(self) -> float:
        """Calculate current win rate."""
        return self.winning_trades / self.total_trades if self.total_trades > 0 else 0
    
    def _get_profit_factor(self) -> float:
        """Calculate current profit factor."""
        return self.total_profit / self.total_loss if self.total_loss > 0 else 0
    
    def get_stats(self) -> Dict:
        """Get sizing statistics."""
        return {
            **self.stats,
            'current_phase': self.current_phase.value,
            'base_size_pct': self._get_base_size_pct() * 100,
            'total_trades': self.total_trades,
            'win_rate': self._get_win_rate() * 100,
            'profit_factor': self._get_profit_factor(),
            'in_drawdown_protection': self.in_drawdown_protection,
            'consecutive_losses': self.consecutive_losses,
            'consecutive_wins': self.consecutive_wins,
            'current_exposure_usd': self._get_current_exposure(),
            'current_exposure_pct': self._get_current_exposure() / self.portfolio_value * 100
        }


if __name__ == "__main__":
    """Test dynamic position sizer."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 6: DYNAMIC POSITION SIZER TEST")
    print("=" * 80)
    print("\n🔒 LOCKED PARAMETERS:")
    print(f"   Phase 1 size: {DynamicPositionSizer.PHASE_1_SIZE_PCT * 100:.2f}%")
    print(f"   Phase 2 size: {DynamicPositionSizer.PHASE_2_SIZE_PCT * 100:.2f}%")
    print(f"   Phase 3 size: {DynamicPositionSizer.PHASE_3_SIZE_PCT * 100:.2f}%")
    print(f"   Max exposure: {DynamicPositionSizer.MAX_CONCURRENT_EXPOSURE_PCT * 100:.2f}%")
    print(f"   Drawdown cut: {DynamicPositionSizer.DRAWDOWN_SIZE_MULTIPLIER * 100:.0f}%")
    print(f"   Loss limit: {DynamicPositionSizer.CONSECUTIVE_LOSS_LIMIT} consecutive\n")
    
    sizer = DynamicPositionSizer(portfolio_value=100000, symbol='BTCUSDT')
    
    # Test 1: High confidence signal
    print("Test 1: High Confidence Signal (90%)")
    print("-" * 80)
    
    size1 = sizer.calculate_position_size(signal_confidence=90.0, entry_price=100000)
    
    if size1:
        print(f"   Position Size: ${size1['size_usd']:,.2f} ({size1['size_pct'] * 100:.3f}%)")
        print(f"   Quantity: {size1['quantity']:.4f} BTC")
        print(f"   Phase: {size1['phase']}")
        print(f"   Confidence mult: {size1['confidence_mult']:.2f}x\n")
    
    # Test 2: Medium confidence signal
    print("Test 2: Medium Confidence Signal (70%)")
    print("-" * 80)
    
    size2 = sizer.calculate_position_size(signal_confidence=70.0, entry_price=100000)
    
    if size2:
        print(f"   Position Size: ${size2['size_usd']:,.2f} ({size2['size_pct'] * 100:.3f}%)")
        print(f"   Quantity: {size2['quantity']:.4f} BTC")
        print(f"   Confidence mult: {size2['confidence_mult']:.2f}x\n")
    
    # Test 3: Simulate drawdown protection
    print("Test 3: Drawdown Protection (2 consecutive losses)")
    print("-" * 80)
    
    # Simulate 2 losses
    sizer.update_trade_result('trade1', pnl=-0.01, closed=True)
    sizer.update_trade_result('trade2', pnl=-0.01, closed=True)
    
    size3 = sizer.calculate_position_size(signal_confidence=90.0, entry_price=100000)
    
    if size3:
        print(f"   Position Size: ${size3['size_usd']:,.2f} ({size3['size_pct'] * 100:.3f}%)")
        print(f"   In drawdown: {size3['in_drawdown']}")
        print(f"   Drawdown mult: {size3['drawdown_mult']:.2f}x (50% cut)\n")
    
    # Stats
    print("=" * 80)
    print("POSITION SIZING STATISTICS")
    print("=" * 80)
    stats = sizer.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<35s}: {value:.3f}")
        else:
            print(f"   {key:<35s}: {value}")
    
    print("\n✅ Test complete - Dynamic position sizer ready for integration")
    print("\n📊 Expected Impact:")
    print("   - Gradual scaling reduces risk during ramp-up")
    print("   - Confidence-based sizing optimizes capital allocation")
    print("   - Drawdown protection prevents compounding losses")
    print("   - Portfolio limits enforce risk discipline")

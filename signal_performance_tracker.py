"""
Signal Performance Tracker

Tracks signal outcomes (win/loss) and calculates performance metrics.
"""

import time
import logging
from typing import Dict, List, Optional
from collections import deque
import json

logger = logging.getLogger(__name__)


class SignalPerformanceTracker:
    """
    Track signal performance and outcomes.
    
    For each signal, tracks:
    - Entry price
    - Target price
    - Stop loss
    - Actual outcome (hit target, hit stop, or still open)
    - P&L
    """
    
    def __init__(self, db_path: str = "liquidation_data.db"):
        # Active signals (not yet resolved)
        self.active_signals = {}
        
        # Historical signals (resolved)
        self.history = deque(maxlen=1000)
        
        # Performance stats
        self.stats = {
            'total_signals': 0,
            'wins': 0,
            'losses': 0,
            'open': 0,
            'win_rate': 0.0,
            'avg_rr_realized': 0.0,
            'total_pnl_pct': 0.0
        }
        
        # Database for persistence (PostgreSQL)
        try:
            from postgres_signal_database import PostgresSignalDatabase
            self.db = PostgresSignalDatabase()
            self._load_active_signals_from_db()
            logger.info("PostgreSQL signal database persistence enabled")
        except Exception as e:
            logger.warning(f"Signal database not available: {e}")
            self.db = None

    
    def add_signal(self, signal: Dict):
        """
        Add a new signal to track.
        
        Args:
            signal: {
                'id': unique identifier,
                'symbol': 'BTCUSDT',
                'direction': 'LONG' or 'SHORT',
                'entry': 95000,
                'target': 96500,
                'stop': 94500,
                'timestamp': time.time(),
                'type': 'FUNDING_FADE',
                'confidence': 0.85
            }
        """
        signal_id = signal.get('id', f"{signal['symbol']}_{int(signal['timestamp'])}")
        
        self.active_signals[signal_id] = {
            **signal,
            'id': signal_id,
            'status': 'OPEN',
            'outcome': None,
            'exit_price': None,
            'exit_time': None,
            'pnl_pct': 0.0,
            'duration_seconds': 0
        }
        
        self.stats['total_signals'] += 1
        self.stats['open'] += 1
        
        # Save to database
        if self.db:
            self.db.save_signal(self.active_signals[signal_id])
        
        logger.info(f"📊 Tracking signal: {signal_id} ({signal['direction']} {signal['symbol']})")
    
    def update_prices(self, prices: Dict[str, float]):
        """
        Update with current prices to check if signals hit targets/stops.
        Also updates live position metrics.
        
        Args:
            prices: {'BTCUSDT': 95500, 'ETHUSDT': 3500, ...}
        """
        for signal_id, signal in list(self.active_signals.items()):
            symbol = signal['symbol']
            if symbol not in prices:
                continue
            
            current_price = prices[symbol]
            direction = signal['direction']
            entry = signal['entry']
            target = signal['target']
            stop = signal['stop']
            
            # Update live metrics
            if direction == 'LONG':
                unrealized_pnl = ((current_price - entry) / entry) * 100
                distance_to_target = ((target - current_price) / current_price) * 100
                distance_to_stop = ((current_price - stop) / current_price) * 100
            else:  # SHORT
                unrealized_pnl = ((entry - current_price) / entry) * 100
                distance_to_target = ((current_price - target) / current_price) * 100
                distance_to_stop = ((stop - current_price) / current_price) * 100
            
            # Update signal with live data
            signal['current_price'] = current_price
            signal['unrealized_pnl_pct'] = unrealized_pnl
            signal['distance_to_target_pct'] = distance_to_target
            signal['distance_to_stop_pct'] = distance_to_stop
            signal['duration_seconds'] = time.time() - signal['timestamp']
            
            # Check if target hit
            if direction == 'LONG':
                if current_price >= target:
                    self._resolve_signal(signal_id, 'WIN', current_price, 'Target hit')
                elif current_price <= stop:
                    self._resolve_signal(signal_id, 'LOSS', current_price, 'Stop hit')
            else:  # SHORT
                if current_price <= target:
                    self._resolve_signal(signal_id, 'WIN', current_price, 'Target hit')
                elif current_price >= stop:
                    self._resolve_signal(signal_id, 'LOSS', current_price, 'Stop hit')
    
    def _resolve_signal(self, signal_id: str, outcome: str, exit_price: float, reason: str):
        """Resolve a signal as win or loss."""
        if signal_id not in self.active_signals:
            return
        
        signal = self.active_signals[signal_id]
        
        # Calculate P&L
        entry = signal['entry']
        direction = signal['direction']
        
        if direction == 'LONG':
            pnl_pct = ((exit_price - entry) / entry) * 100
        else:  # SHORT
            pnl_pct = ((entry - exit_price) / entry) * 100
        
        # Update signal
        signal['status'] = 'CLOSED'
        signal['outcome'] = outcome
        signal['exit_price'] = exit_price
        signal['exit_time'] = time.time()
        signal['pnl_pct'] = pnl_pct
        signal['duration_seconds'] = signal['exit_time'] - signal['timestamp']
        signal['close_reason'] = reason
        
        # Move to history
        self.history.append(signal)
        del self.active_signals[signal_id]
        
        # Update stats
        self.stats['open'] -= 1
        if outcome == 'WIN':
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        
        self._recalculate_stats()
        
        # Update database
        if self.db:
            self.db.update_signal_status(
                signal_id, 'CLOSED', outcome, exit_price, pnl_pct, reason
            )
        
        # Log outcome
        emoji = '✅' if outcome == 'WIN' else '❌'
        logger.info(f"{emoji} Signal closed: {signal_id} - {outcome} ({pnl_pct:+.2f}%) - {reason}")
    
    def _recalculate_stats(self):
        """Recalculate performance statistics."""
        closed_signals = self.stats['wins'] + self.stats['losses']
        
        if closed_signals > 0:
            self.stats['win_rate'] = (self.stats['wins'] / closed_signals) * 100
        
        # Calculate average R/R realized and total P&L
        if self.history:
            total_pnl = sum(s['pnl_pct'] for s in self.history)
            self.stats['total_pnl_pct'] = total_pnl
            self.stats['avg_pnl_per_trade'] = total_pnl / len(self.history)
            
            # Calculate average R/R for wins
            wins = [s for s in self.history if s['outcome'] == 'WIN']
            if wins:
                avg_win_rr = sum(abs(s['pnl_pct']) for s in wins) / len(wins)
                losses = [s for s in self.history if s['outcome'] == 'LOSS']
                if losses:
                    avg_loss_rr = sum(abs(s['pnl_pct']) for s in losses) / len(losses)
                    self.stats['avg_rr_realized'] = avg_win_rr / avg_loss_rr if avg_loss_rr > 0 else 0
    
    def get_stats(self) -> Dict:
        """Get current performance statistics."""
        return {
            **self.stats,
            'active_signals': len(self.active_signals),
            'history_count': len(self.history)
        }
    
    def get_recent_signals(self, limit: int = 20) -> List[Dict]:
        """Get recent signals (both active and closed)."""
        # Combine active and history
        all_signals = list(self.active_signals.values()) + list(self.history)
        
        # Sort by timestamp (newest first)
        all_signals.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return all_signals[:limit]
    
    def get_performance_by_type(self) -> Dict:
        """Get performance breakdown by signal type."""
        by_type = {}
        
        for signal in self.history:
            sig_type = signal.get('type', 'UNKNOWN')
            if sig_type not in by_type:
                by_type[sig_type] = {
                    'total': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0
                }
            
            by_type[sig_type]['total'] += 1
            if signal['outcome'] == 'WIN':
                by_type[sig_type]['wins'] += 1
            else:
                by_type[sig_type]['losses'] += 1
            
            by_type[sig_type]['total_pnl'] += signal['pnl_pct']
        
        # Calculate win rates
        for sig_type in by_type:
            total = by_type[sig_type]['total']
            if total > 0:
                by_type[sig_type]['win_rate'] = (by_type[sig_type]['wins'] / total) * 100
        
        return by_type
    
    def _load_active_signals_from_db(self):
        """Load active signals from database on startup for crash recovery."""
        if not self.db:
            return
        
        try:
            active_signals = self.db.load_active_signals()
            
            for signal in active_signals:
                signal_id = signal['id']
                self.active_signals[signal_id] = signal
                self.stats['total_signals'] += 1
                self.stats['open'] += 1
            
            if active_signals:
                logger.info(f"✅ Recovered {len(active_signals)} active signals from database")
            
        except Exception as e:
            logger.error(f"Failed to load active signals from database: {e}")


if __name__ == "__main__":
    """Test signal performance tracker."""
    
    logging.basicConfig(level=logging.INFO)
    
    tracker = SignalPerformanceTracker()
    
    # Add test signal
    signal = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'entry': 95000,
        'target': 96500,
        'stop': 94500,
        'timestamp': time.time(),
        'type': 'FUNDING_FADE',
        'confidence': 0.85
    }
    
    tracker.add_signal(signal)
    
    print("\n" + "="*60)
    print("INITIAL STATE")
    print("="*60)
    print(json.dumps(tracker.get_stats(), indent=2))
    
    # Simulate price hitting target
    print("\n" + "="*60)
    print("SIMULATING TARGET HIT")
    print("="*60)
    tracker.update_prices({'BTCUSDT': 96500})
    
    print("\n" + "="*60)
    print("FINAL STATS")
    print("="*60)
    print(json.dumps(tracker.get_stats(), indent=2))
    
    print("\n" + "="*60)
    print("RECENT SIGNALS")
    print("="*60)
    for sig in tracker.get_recent_signals():
        print(f"{sig['symbol']} {sig['direction']}: {sig['status']} - {sig.get('outcome', 'N/A')}")

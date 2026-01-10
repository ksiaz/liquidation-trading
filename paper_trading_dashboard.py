"""
Paper Trading Dashboard
Real-Time Monitoring Interface

Displays live performance metrics, signals, positions, and backtest comparison.
Provides comprehensive visibility into paper trading validation.

Features:
- Real-time performance metrics
- Live signal feed
- Open positions tracker
- Backtest comparison
- Alert notifications
- Session tracking
"""

import time
import os
import logging
from datetime import datetime
from typing import Dict, List
from collections import deque

logger = logging.getLogger(__name__)


class PaperTradingDashboard:
    """
    Console-based dashboard for paper trading monitoring.
    
    Displays real-time metrics updated every 5 seconds.
    """
    
    def __init__(self, engine):
        """
        Initialize dashboard.
        
        Args:
            engine: PaperTradingEngine instance
        """
        self.engine = engine
        self.backtest_targets = {
            'win_rate': 0.62,
            'signals_per_session': 18,
            'avg_pnl_pct': 1.7,  # Per trade
            'sharpe': 1.65,
        }
        
        # Performance history (for charts)
        self.pnl_history = deque(maxlen=100)
        self.wr_history = deque(maxlen=100)
        
        # Alert tracking
        self.alerts = deque(maxlen=10)
    
    def clear_screen(self):
        """Clear console screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def render(self):
        """Render dashboard (call every 5 seconds)."""
        self.clear_screen()
        
        # Get current data
        perf = self.engine.get_performance_summary()
        session = self.engine.current_session
        session_count = self.engine.session_signals.get(session, 0)
        session_limit = self.engine.params['session_limits'].get(session, 100)
        
        # Build dashboard
        lines = []
        
        # Header
        lines.append("╔" + "═" * 78 + "╗")
        lines.append("║" + "  PAPER TRADING DASHBOARD - Week 14/15 Validation".ljust(78) + "║")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "🟢 LIVE" if self.engine.running else "🔴 STOPPED"
        lines.append("║" + f"  {status} | {now} | Uptime: {self._format_uptime()}".ljust(78) + "║")
        lines.append("╚" + "═" * 78 + "╝")
        lines.append("")
        
        # Session info & Performance (side by side)
        lines.append("┌" + "─" * 38 + "┬" + "─" * 39 + "┐")
        lines.append("│" + "  SESSION INFO".ljust(38) + "│" + "  PERFORMANCE (Today)".ljust(39) + "│")
        lines.append("├" + "─" * 38 + "┼" + "─" * 39 + "┤")
        
        # Session info
        session_pct = (session_count / session_limit * 100) if session_limit > 0 else 0
        session_status = "✅ OK" if session_count < session_limit * 0.9 else "⚠️ NEAR LIMIT"
        
        lines.append("│" + f"  Current: {session or 'N/A'}".ljust(38) + 
                    "│" + f"  Signals: {perf['fills']} / {self.backtest_targets['signals_per_session']} target".ljust(39) + "│")
        lines.append("│" + f"  Limit: {session_limit} ({session_count} used, {session_pct:.0f}%)".ljust(38) + 
                    "│" + f"  Fill Rate: {perf['fills']/(perf['total_signals'] or 1)*100:.0f}%".ljust(39) + "│")
        lines.append("│" + f"  Status: {session_status}".ljust(38) + 
                    "│" + f"  Win Rate: {perf['win_rate']*100:.1f}% ({perf['wins']}W-{perf['losses']}L)".ljust(39) + "│")
        lines.append("│" + "".ljust(38) + 
                    "│" + f"  Net P&L: {perf['total_pnl_pct']:+.2f}% (simulated)".ljust(39) + "│")
        lines.append("│" + "".ljust(38) + 
                    "│" + f"  Sharpe: {perf['sharpe']:.2f}".ljust(39) + "│")
        
        lines.append("└" + "─" * 38 + "┴" + "─" * 39 + "┘")
        lines.append("")
        
        # Open positions
        lines.append("┌" + "─" * 78 + "┐")
        lines.append("│" + f"  OPEN POSITIONS (Simulated) - {len(self.engine.open_positions)} active".ljust(78) + "│")
        lines.append("├" + "─" * 78 + "┤")
        
        if self.engine.open_positions:
            # Header
            lines.append("│ " + "Symbol".ljust(8) + "Entry".ljust(10) + "Current".ljust(10) + 
                        "P&L".ljust(10) + "Time".ljust(8) + "Exit Plan".ljust(30) + " │")
            lines.append("├" + "─" * 78 + "┤")
            
            for signal in list(self.engine.open_positions.values())[:5]:  # Show 5 max
                # Get current price
                ob = self.engine.ws_client.get_orderbook(signal.symbol)
                current_price = ob['bids'][0][0] if (ob and ob.get('bids')) else signal.fill_price
                
                unrealized_pnl = (current_price - signal.fill_price) / signal.fill_price
                hold_time = int(time.time() - signal.fill_time)
                
                # Exit plan
                if hold_time >= 200:
                    exit_plan = "Half-life reached"
                elif hold_time >= 100:
                    exit_plan = "Stagnation watch"
                else:
                    exit_plan = f"Monitor ({200-hold_time}s to half-life)"
                
                lines.append("│ " + 
                            signal.symbol.ljust(8) +
                            f"{signal.fill_price:.2f}".ljust(10) +
                            f"{current_price:.2f}".ljust(10) +
                            f"{unrealized_pnl*100:+.2f}%".ljust(10) +
                            f"{hold_time}s".ljust(8) +
                            exit_plan[:29].ljust(30) +
                            " │")
        else:
            lines.append("│" + "  No open positions".ljust(78) + "│")
        
        lines.append("└" + "─" * 78 + "┘")
        lines.append("")
        
        # Recent signals
        lines.append("┌" + "─" * 78 + "┐")
        lines.append("│" + "  RECENT SIGNALS (Last 5)".ljust(78) + "│")
        lines.append("├" + "─" * 78 + "┤")
        lines.append("│ " + "Time".ljust(10) + "Symbol".ljust(10) + "Regime".ljust(12) + 
                    "Conf".ljust(8) + "Outcome".ljust(12) + "P&L".ljust(12) + "Hold".ljust(12) + " │")
        lines.append("├" + "─" * 78 + "┤")
        
        recent = list(self.engine.recent_signals)[-5:]
        if recent:
            for signal in reversed(recent):
                ts = datetime.fromtimestamp(signal.timestamp).strftime("%H:%M:%S")
                
                if signal.status.value == 'OPEN':
                    outcome = "OPEN"
                    pnl_str = "---"
                    hold_str = f"{int(time.time() - signal.fill_time)}s"
                elif signal.status.value == 'NO_FILL':
                    outcome = "NO FILL"
                    pnl_str = "---"
                    hold_str = "---"
                else:
                    outcome = "WIN" if signal.winner else "LOSS"
                    pnl_str = f"{signal.pnl_pct*100:+.2f}%"
                    hold_str = f"{signal.hold_time_sec:.0f}s"
                
                lines.append("│ " +
                            ts.ljust(10) +
                            signal.symbol.ljust(10) +
                            signal.regime[:11].ljust(12) +
                            f"{signal.confidence*100:.0f}%".ljust(8) +
                            outcome.ljust(12) +
                            pnl_str.ljust(12) +
                            hold_str.ljust(12) +
                            " │")
        else:
            lines.append("│" + "  No signals yet...".ljust(78) + "│")
        
        lines.append("└" + "─" * 78 + "┘")
        lines.append("")
        
        # Backtest comparison
        lines.append("┌" + "─" * 78 + "┐")
        lines.append("│" + "  BACKTEST COMPARISON".ljust(78) + "│")
        lines.append("├" + "─" * 78 + "┤")
        lines.append("│ " + "Metric".ljust(20) + "Backtest".ljust(15) + "Live".ljust(15) + 
                    "Delta".ljust(15) + "Status".ljust(10) + " │")
        lines.append("├" + "─" + "─" * 77 + "┤")
        
        # Win rate comparison
        wr_delta = perf['win_rate'] - self.backtest_targets['win_rate']
        wr_status = "✅" if wr_delta >= -0.03 else "⚠️"
        lines.append("│ " + 
                    "Win Rate".ljust(20) +
                    f"{self.backtest_targets['win_rate']*100:.1f}%".ljust(15) +
                    f"{perf['win_rate']*100:.1f}%".ljust(15) +
                    f"{wr_delta*100:+.1f} pts".ljust(15) +
                    wr_status.ljust(10) +
                    " │")
        
        # Signals comparison (need at least one closed trade)
        if perf['closed_positions'] > 0:
            signals_delta_pct = (perf['fills'] / self.backtest_targets['signals_per_session'] - 1) * 100
            signals_status = "✅" if abs(signals_delta_pct) <= 20 else "⚠️"
        else:
            signals_delta_pct = 0
            signals_status = "⏳"
        
        lines.append("│ " + 
                    "Signals/Session".ljust(20) +
                    f"{self.backtest_targets['signals_per_session']:.0f}".ljust(15) +
                    f"{perf['fills']:.0f}".ljust(15) +
                    f"{signals_delta_pct:+.0f}%".ljust(15) +
                    signals_status.ljust(10) +
                    " │")
        
        # Sharpe comparison
        sharpe_delta = perf['sharpe'] - self.backtest_targets['sharpe']
        sharpe_status = "✅" if perf['sharpe'] >= self.backtest_targets['sharpe'] * 0.8 else "⚠️"
        lines.append("│ " + 
                    "Sharpe Ratio".ljust(20) +
                    f"{self.backtest_targets['sharpe']:.2f}".ljust(15) +
                    f"{perf['sharpe']:.2f}".ljust(15) +
                    f"{sharpe_delta:+.2f}".ljust(15) +
                    sharpe_status.ljust(10) +
                    " │")
        
        lines.append("└" + "─" * 78 + "┘")
        lines.append("")
        
        # Alerts
        if self.alerts:
            lines.append("┌" + "─" * 78 + "┐")
            lines.append("│" + "  RECENT ALERTS".ljust(78) + "│")
            lines.append("├" + "─" * 78 + "┤")
            
            for alert in list(self.alerts)[-3:]:
                lines.append("│ " + alert[:76].ljust(76) + " │")
            
            lines.append("└" + "─" * 78 + "┘")
            lines.append("")
        
        # Print dashboard
        print("\n".join(lines))
        
        # Check for alerts
        self._check_alerts(perf)
    
    def _format_uptime(self) -> str:
        """Format engine uptime."""
        # Simplified - in production would track start time
        return "Running"
    
    def _check_alerts(self, perf: Dict):
        """Check performance and generate alerts."""
        # Win rate alert
        if perf['closed_positions'] >= 20:
            if perf['win_rate'] < 0.55:
                self.add_alert("🛑 CRITICAL: Win rate <55%")
            elif perf['win_rate'] < 0.59:
                self.add_alert("⚠️ WARNING: Win rate below target (59%)")
        
        # Circuit breaker alert
        if self.engine.current_session:
            session_count = self.engine.session_signals.get(self.engine.current_session, 0)
            session_limit = self.engine.params['session_limits'].get(self.engine.current_session, 100)
            
            if session_count >= session_limit * 0.9:
                self.add_alert(f"⚠️ Circuit breaker: {session_count}/{session_limit} signals")
    
    def add_alert(self, message: str):
        """Add alert to feed."""
        ts = datetime.now().strftime("%H:%M:%S")
        alert = f"{ts} | {message}"
        
        # Only add if not duplicate
        if not self.alerts or self.alerts[-1] != alert:
            self.alerts.append(alert)
            logger.info(f"ALERT: {message}")


def run_dashboard_demo():
    """Run dashboard demo (requires paper trading engine)."""
    from paper_trading_engine import PaperTradingEngine
    
    print("Starting paper trading engine...")
    engine = PaperTradingEngine(
        symbols=['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        fill_rate=0.45,
    )
    engine.start()
    
    print("Starting dashboard...")
    time.sleep(3)
    
    dashboard = PaperTradingDashboard(engine)
    
    try:
        while True:
            dashboard.render()
            time.sleep(5)  # Update every 5 seconds
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        engine.stop()
        print("Demo complete")


if __name__ == '__main__':
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    run_dashboard_demo()


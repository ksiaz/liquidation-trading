#!/usr/bin/env python3
"""
Terminal Application for Liquidation Trading System

Clean terminal interface with structured logging and real-time status.
Optimized for debugging and monitoring.

Usage:
    python runtime/terminal_app/main.py [--no-warmup] [--warmup-sec N] [--debug]
"""
import sys
import os

# Add project root to path FIRST
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Configure temp directories to use D drive (must be early, before other imports)
import runtime.env_setup  # noqa: F401

import asyncio
import argparse
import signal
from datetime import datetime
from typing import Dict

from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService

# ANSI color codes for terminal output
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'

class TerminalApp:
    """Terminal application with clean logging and status updates."""

    def __init__(self, warmup_sec: int = 5, enable_debug: bool = False):
        self.warmup_sec = warmup_sec
        self.enable_debug = enable_debug
        self.collector = None
        self.running = False

        # Status tracking
        self.start_time = None
        self.last_status_time = 0
        self.status_interval = 5.0  # Print status every 5 seconds

    def log(self, level: str, message: str, **kwargs):
        """Structured logging with colors and metadata."""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        # Color by level
        level_colors = {
            'INFO': Colors.CYAN,
            'SUCCESS': Colors.GREEN,
            'WARNING': Colors.YELLOW,
            'ERROR': Colors.RED,
            'DEBUG': Colors.GRAY,
            'MANDATE': Colors.MAGENTA,
            'REGIME': Colors.BLUE
        }
        color = level_colors.get(level, Colors.RESET)

        # Format message
        output = f"{Colors.GRAY}[{timestamp}]{Colors.RESET} {color}[{level:8s}]{Colors.RESET} {message}"

        # Add metadata if present
        if kwargs:
            meta_str = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
            output += f" {Colors.GRAY}({meta_str}){Colors.RESET}"

        print(output, flush=True)

    def print_banner(self):
        """Print startup banner."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  Liquidation Trading System - Terminal Mode{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")

        print(f"{Colors.BOLD}Configuration:{Colors.RESET}")
        print(f"  Warmup Period: {self.warmup_sec}s")
        print(f"  Debug Mode: {'Enabled' if self.enable_debug else 'Disabled'}")
        print(f"  Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n{Colors.GRAY}Press Ctrl+C to stop{Colors.RESET}\n")

    def print_status(self, collector: CollectorService):
        """Print periodic status update."""
        # Calculate uptime
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
        else:
            uptime = 0

        print(f"\n{Colors.BOLD}{Colors.CYAN}{'─'*70}{Colors.RESET}")
        print(f"{Colors.BOLD}System Status (uptime: {uptime:.1f}s){Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}")

        # Warmup status
        if collector._startup_time and collector._warmup_duration_sec:
            if collector._last_stream_time:
                elapsed = collector._last_stream_time - collector._startup_time
                progress = min(100, (elapsed / collector._warmup_duration_sec) * 100)
                status = "Complete" if collector._warmup_complete else f"{progress:.1f}%"
                print(f"  Warmup: {status} ({elapsed:.1f}s / {collector._warmup_duration_sec}s)")
            else:
                print(f"  Warmup: Waiting for first event...")

        # Trade statistics
        symbols_with_trades = []
        if hasattr(collector._obs, '_m1'):
            for symbol in collector._obs._allowed_symbols:
                trade_count = len(collector._obs._m1.raw_trades.get(symbol, []))
                if trade_count > 0:
                    symbols_with_trades.append(f"{symbol}:{trade_count}")

        if symbols_with_trades:
            print(f"  Trades: {' | '.join(symbols_with_trades[:5])}")  # Show first 5
        else:
            print(f"  Trades: None yet")

        # Regime states
        if hasattr(collector, '_regime_states') and collector._regime_states:
            regimes = []
            for symbol, state in collector._regime_states.items():
                regimes.append(f"{symbol}:{state.name}")
            print(f"  Regimes: {' | '.join(regimes[:5])}")  # Show first 5

        # Position states
        if hasattr(collector, 'executor') and hasattr(collector.executor, 'state_machine'):
            open_positions = []
            for symbol in collector._obs._allowed_symbols:
                pos = collector.executor.state_machine.get_position(symbol)
                if pos and pos.state.name != 'FLAT':
                    open_positions.append(f"{symbol}:{pos.state.name}")

            if open_positions:
                print(f"  {Colors.GREEN}Open Positions: {' | '.join(open_positions)}{Colors.RESET}")
            else:
                print(f"  Open Positions: None")

        print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}\n")

    async def status_printer(self):
        """Periodically print status updates."""
        while self.running:
            await asyncio.sleep(self.status_interval)
            if self.collector and self.running:
                self.print_status(self.collector)

    async def run(self):
        """Main application loop."""
        self.print_banner()

        try:
            # Initialize observation system
            self.log('INFO', 'Initializing observation system...')

            TOP_10_SYMBOLS = [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
                "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
                "TRXUSDT", "DOTUSDT"
            ]

            obs_system = ObservationSystem(allowed_symbols=TOP_10_SYMBOLS)
            self.log('SUCCESS', f'Observation system initialized', symbols=len(TOP_10_SYMBOLS))

            # Initialize collector service
            self.log('INFO', f'Initializing collector service...', warmup=f'{self.warmup_sec}s')
            self.collector = CollectorService(
                observation_system=obs_system,
                warmup_duration_sec=self.warmup_sec
            )

            self.log('SUCCESS', 'Collector service initialized')

            # Set running flag
            self.running = True
            self.start_time = datetime.now()

            # Start status printer
            status_task = asyncio.create_task(self.status_printer())

            # Start collector
            self.log('INFO', 'Starting collector service...')
            self.log('INFO', 'Connecting to Binance WebSocket...')

            try:
                await self.collector.start()
            except asyncio.CancelledError:
                self.log('INFO', 'Collector service stopped')
            finally:
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass

        except KeyboardInterrupt:
            self.log('INFO', 'Shutdown requested by user')
        except Exception as e:
            self.log('ERROR', f'Fatal error: {e}')
            import traceback
            traceback.print_exc()
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Clean shutdown."""
        self.running = False

        self.log('INFO', 'Shutting down...')

        if self.collector:
            self.collector._running = False

        # Print final status
        if self.collector:
            print()
            self.print_status(self.collector)

        self.log('SUCCESS', 'Shutdown complete')
        print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}\n")

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print(f"\n{Colors.YELLOW}Received interrupt signal, shutting down...{Colors.RESET}")
    raise KeyboardInterrupt

def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description='Liquidation Trading System - Terminal Mode',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--no-warmup',
        action='store_true',
        help='Disable warmup period (start trading immediately)'
    )

    parser.add_argument(
        '--warmup-sec',
        type=int,
        default=5,
        help='Warmup period in seconds (default: 5)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Set warmup
    warmup_sec = 0 if args.no_warmup else args.warmup_sec

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Set event loop policy for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Create and run app
    app = TerminalApp(warmup_sec=warmup_sec, enable_debug=args.debug)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass  # Already handled by signal_handler

if __name__ == '__main__':
    main()

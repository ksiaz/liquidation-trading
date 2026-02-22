#!/usr/bin/env python3
"""
Terminal Position Monitor

Standalone script to display live position status in terminal.
Run in tmux alongside paper trade for real-time monitoring.

Usage:
    python scripts/position_monitor.py
    python scripts/position_monitor.py --interval 1
"""

import argparse
import json
import os
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import grpc

# Add project root to path
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

# Add hl-adapter protos to path
_hl_adapter_path = _project_root / 'hl-adapter'
sys.path.insert(0, str(_hl_adapter_path))
import events_pb2
import events_pb2_grpc

# Initialize PG pool
from runtime.logging.pg_pool import init_pool, get_conn, put_conn
init_pool()



# ANSI Colors
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'


# Box drawing characters
BOX_TL = '╔'
BOX_TR = '╗'
BOX_BL = '╚'
BOX_BR = '╝'
BOX_H = '═'
BOX_V = '║'
BOX_ML = '╠'
BOX_MR = '╣'
LINE = '─'

WIDTH = 78


def clear_screen():
    """Clear terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


# ==============================================================================
# gRPC Price Streamer (background thread)
# ==============================================================================

_grpc_prices: Dict[str, float] = {}
_grpc_lock = threading.Lock()
_grpc_status: str = "INIT"  # INIT | CONNECTING | HANDSHAKE | STREAMING | ERROR:<reason>
_grpc_last_error_log: float = 0.0  # Rate-limit error logging

GRPC_HOST = 'localhost'
GRPC_PORT = 50051
RECONNECT_DELAY = 5.0


def _log_grpc(msg: str):
    """Print timestamped gRPC diagnostic."""
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[MONITOR gRPC {ts}] {msg}", file=sys.stderr, flush=True)


def _grpc_price_stream():
    """Background thread: one persistent channel streaming prices from HL adapter."""
    global _grpc_status, _grpc_last_error_log

    channel = grpc.insecure_channel(
        f'{GRPC_HOST}:{GRPC_PORT}',
        options=[
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.keepalive_permit_without_calls', 1),
        ]
    )

    while True:
        try:
            # Step 1: Wait for channel ready
            _grpc_status = "CONNECTING"
            try:
                grpc.channel_ready_future(channel).result(timeout=10)
            except grpc.FutureTimeoutError:
                _grpc_status = "ERROR:channel_timeout"
                now = time.time()
                if now - _grpc_last_error_log > 30:
                    _log_grpc("Channel not ready after 10s — adapter down?")
                    _grpc_last_error_log = now
                time.sleep(RECONNECT_DELAY)
                continue

            stub = events_pb2_grpc.HLNodeAdapterStub(channel)

            # Step 2: Handshake + status
            _grpc_status = "HANDSHAKE"
            try:
                hs_req = events_pb2.HandshakeRequest(
                    client_version=events_pb2.SchemaVersion(major=1, minor=1, patch=0),
                    client_id="position_monitor"
                )
                hs_resp = stub.Handshake(hs_req, timeout=5)
                sv = hs_resp.server_version
                _log_grpc(f"Handshake OK: server v{sv.major}.{sv.minor}.{sv.patch}, "
                          f"compatible={hs_resp.compatible}, uptime={hs_resp.server_uptime_seconds}s")
                if not hs_resp.compatible:
                    _grpc_status = "ERROR:incompatible"
                    _log_grpc(f"Schema incompatible: {hs_resp.message}")
                    time.sleep(RECONNECT_DELAY)
                    continue
            except grpc.RpcError as e:
                _log_grpc(f"Handshake failed: {e.code().name}: {e.details()}")
                # Non-fatal — adapter might not implement Handshake; continue to stream

            try:
                status_resp = stub.GetStatus(events_pb2.Empty(), timeout=5)
                _log_grpc(f"Adapter status: {status_resp.status} block={status_resp.latest_block_height} "
                          f"lag={status_resp.blocks_behind}")
            except grpc.RpcError:
                pass  # Non-fatal

            # Step 3: Stream prices
            _grpc_status = "CONNECTING"
            request = events_pb2.StreamRequest()
            stream = stub.StreamPrices(request)

            first_event = True
            for event in stream:
                if first_event:
                    _grpc_status = "STREAMING"
                    _log_grpc(f"First price received — streaming OK")
                    first_event = False

                symbol = f"{event.symbol}USDT"
                try:
                    price = float(event.oracle_price)
                    with _grpc_lock:
                        _grpc_prices[symbol] = price
                except (ValueError, TypeError):
                    pass

            # Stream ended cleanly (server shutdown?)
            _grpc_status = "ERROR:stream_ended"
            _log_grpc("Price stream ended (server closed)")

        except grpc.RpcError as e:
            code = e.code().name if hasattr(e, 'code') else 'UNKNOWN'
            details = e.details() if hasattr(e, 'details') else str(e)
            _grpc_status = f"ERROR:{code}"
            now = time.time()
            if now - _grpc_last_error_log > 30:
                _log_grpc(f"RpcError: {code}: {details}")
                _grpc_last_error_log = now

        except Exception as e:
            import traceback
            _grpc_status = f"ERROR:{type(e).__name__}"
            now = time.time()
            if now - _grpc_last_error_log > 30:
                _log_grpc(f"Exception: {traceback.format_exc()}")
                _grpc_last_error_log = now

        # Clear stale prices on disconnect
        with _grpc_lock:
            _grpc_prices.clear()

        time.sleep(RECONNECT_DELAY)


def start_price_stream():
    """Start the background gRPC price stream."""
    t = threading.Thread(target=_grpc_price_stream, daemon=True, name="grpc-prices")
    t.start()


# ==============================================================================
# WebSocket Mid Price Streamer (background thread)
# ==============================================================================

_ws_prices: Dict[str, float] = {}
_ws_lock = threading.Lock()
_ws_status: str = "INIT"  # INIT | CONNECTING | STREAMING | ERROR:<reason>

WS_URL = "wss://api.hyperliquid.xyz/ws"
WS_RECONNECT_DELAY = 5.0


def _ws_price_stream():
    """Background thread: subscribe to allMids for real-time mid prices."""
    global _ws_status

    try:
        import websocket
    except ImportError:
        _ws_status = "ERROR:no_websocket_lib"
        _log_grpc("websocket-client not installed, WS prices unavailable")
        return

    while True:
        try:
            _ws_status = "CONNECTING"
            ws = websocket.create_connection(WS_URL, timeout=10)
            # Subscribe to allMids
            ws.send(json.dumps({
                "method": "subscribe",
                "subscription": {"type": "allMids"}
            }))
            _ws_status = "STREAMING"
            _log_grpc("WS allMids connected")

            while True:
                raw = ws.recv()
                if not raw:
                    break
                try:
                    data = json.loads(raw)
                    if data.get('channel') == 'allMids':
                        mids = data.get('data', {}).get('mids', {})
                        with _ws_lock:
                            for coin, price_str in mids.items():
                                try:
                                    _ws_prices[f"{coin}USDT"] = float(price_str)
                                except (ValueError, TypeError):
                                    pass
                except (json.JSONDecodeError, KeyError):
                    pass

            _ws_status = "ERROR:stream_ended"
            ws.close()

        except Exception as e:
            _ws_status = f"ERROR:{type(e).__name__}"
            now = time.time()
            # Rate-limit error logging (reuse grpc pattern)
            _log_grpc(f"WS error: {e}")

        with _ws_lock:
            _ws_prices.clear()
        time.sleep(WS_RECONNECT_DELAY)


def start_ws_price_stream():
    """Start the background WebSocket mid price stream."""
    t = threading.Thread(target=_ws_price_stream, daemon=True, name="ws-prices")
    t.start()


def get_live_prices(symbols: List[str]) -> Dict[str, float]:
    """Get latest prices — prefer WS mid prices, fall back to gRPC oracle."""
    result = {}
    with _grpc_lock:
        for s in symbols:
            if s in _grpc_prices:
                result[s] = _grpc_prices[s]
    # Override with WS mid prices (more accurate, lower latency)
    with _ws_lock:
        for s in symbols:
            if s in _ws_prices:
                result[s] = _ws_prices[s]
    return result


def get_open_positions() -> List[dict]:
    """Get open positions from PostgreSQL.

    Primary source: ghost_positions table
    Fallback: positions table (executor state machine)
    """
    positions = []

    conn = get_conn()
    try:
        cur = conn.cursor()

        # Try ghost_positions first
        try:
            cur.execute('''
                SELECT symbol, side, qty, entry_price, entry_time, strategy_id, trade_id
                FROM ghost_positions
                WHERE status = 'OPEN'
            ''')
            for row in cur.fetchall():
                positions.append({
                    'symbol': row[0],
                    'direction': row[1],
                    'quantity': float(row[2]) if row[2] else 0,
                    'entry_price': float(row[3]) if row[3] else 0,
                    'entry_time': row[4],
                    'strategy': row[5],
                    'trade_id': row[6]
                })
        except Exception:
            conn.rollback()

        # Fallback to positions table
        if not positions:
            try:
                cur = conn.cursor()
                cur.execute('''
                    SELECT symbol, direction, quantity, entry_price, created_at, strategy_id
                    FROM positions
                    WHERE state = 'OPEN'
                ''')
                for row in cur.fetchall():
                    positions.append({
                        'symbol': row[0],
                        'direction': row[1],
                        'quantity': float(row[2]) if row[2] else 0,
                        'entry_price': float(row[3]) if row[3] else 0,
                        'entry_time': row[4],
                        'strategy': row[5],
                        'trade_id': f'RECOVERED_{row[0]}'
                    })
            except Exception:
                conn.rollback()

        # Fill in missing strategy from ghost_trades
        for pos in positions:
            if not pos.get('strategy'):
                try:
                    cur = conn.cursor()
                    cur.execute('''
                        SELECT winning_policy_name FROM ghost_trades
                        WHERE symbol = %s AND is_entry = 1
                        ORDER BY id DESC LIMIT 1
                    ''', (pos['symbol'],))
                    row = cur.fetchone()
                    if row and row[0]:
                        pos['strategy'] = row[0]
                except Exception:
                    conn.rollback()
    finally:
        put_conn(conn)

    return positions


def get_trailing_stop_info(trade_id: str, symbol: str = None) -> Optional[dict]:
    """Get trailing stop state from PostgreSQL.

    Tries trade_id first, then falls back to RECOVERED_{symbol} for recovered positions.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        # Try original trade_id first
        cur.execute('''
            SELECT current_stop_price, initial_stop_price, highest_price, lowest_price,
                   break_even_triggered, entry_price, direction
            FROM trailing_stops
            WHERE entry_order_id = %s
        ''', (trade_id,))
        row = cur.fetchone()

        # If not found and symbol provided, try RECOVERED_{symbol}
        if not row and symbol:
            cur.execute('''
                SELECT current_stop_price, initial_stop_price, highest_price, lowest_price,
                       break_even_triggered, entry_price, direction
                FROM trailing_stops
                WHERE entry_order_id = %s
            ''', (f"RECOVERED_{symbol}",))
            row = cur.fetchone()

        if row:
            return {
                'current_stop': row[0],
                'initial_stop': row[1],
                'highest_price': row[2],
                'lowest_price': row[3],
                'break_even_triggered': bool(row[4]),
                'entry_price': row[5],
                'direction': row[6]
            }
    except Exception:
        conn.rollback()
    finally:
        put_conn(conn)

    return None


def get_recent_exits(limit: int = 10) -> List[dict]:
    """Get recent exit trades from PostgreSQL."""
    exits = []
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT e.symbol, e.side, e.quantity, e.price, e.timestamp, e.pnl,
                   e.holding_duration_sec, e.exit_reason,
                   (SELECT winning_policy_name FROM ghost_trades
                    WHERE symbol = e.symbol AND is_entry = 1 AND id < e.id
                    ORDER BY id DESC LIMIT 1) as strategy
            FROM ghost_trades e
            WHERE e.is_entry = 0
            ORDER BY e.id DESC
            LIMIT %s
        ''', (limit,))
        for row in cur.fetchall():
            symbol, side, qty, price, ts, pnl, hold, exit_reason, strategy = row
            direction = 'SHORT' if side == 'BUY' else 'LONG'
            exits.append({
                'symbol': symbol,
                'direction': direction,
                'quantity': qty,
                'exit_price': price,
                'timestamp': ts,
                'pnl': pnl or 0,
                'hold_sec': hold or 0,
                'exit_reason': exit_reason,
                'strategy': strategy
            })
    except Exception:
        conn.rollback()
    finally:
        put_conn(conn)

    return exits


def get_session_stats() -> dict:
    """Get session statistics from today's trades."""
    stats = {'trades': 0, 'wins': 0, 'losses': 0, 'net_pnl': 0.0}

    conn = get_conn()
    try:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = today.timestamp()

        cur = conn.cursor()
        cur.execute('''
            SELECT pnl FROM ghost_trades
            WHERE is_entry = 0 AND timestamp > %s
        ''', (today_ts,))

        for (pnl,) in cur.fetchall():
            if pnl is not None:
                stats['trades'] += 1
                stats['net_pnl'] += pnl
                if pnl >= 0:
                    stats['wins'] += 1
                else:
                    stats['losses'] += 1
    except Exception:
        conn.rollback()
    finally:
        put_conn(conn)

    return stats


def get_account_balance() -> float:
    """Get current paper account balance from PostgreSQL."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute('SELECT account_balance_after FROM ghost_trades ORDER BY id DESC LIMIT 1')
        row = cur.fetchone()
        if row and row[0]:
            return float(row[0])
    except Exception:
        conn.rollback()
    finally:
        put_conn(conn)

    return 1000.0


def get_exit_criteria(strategy: Optional[str], direction: str, entry_price: float) -> dict:
    """Get exit criteria based on strategy type.

    Returns dict with:
        - description: Human readable exit condition
        - stop_price: Approximate stop loss price (if applicable)
        - target_price: Approximate target price (if applicable)
    """
    result = {
        'description': 'Unknown',
        'stop_price': None,
        'target_price': None
    }

    strategy_upper = (strategy or '').upper()

    # Geometry strategy: exits on zone invalidation
    if 'GEOMETRY' in strategy_upper:
        # Approximate stop: ~2% adverse move invalidates zone
        stop_pct = 0.02
        if direction == 'LONG':
            result['stop_price'] = entry_price * (1 - stop_pct)
            result['target_price'] = entry_price * 1.03  # ~3% target
        else:  # SHORT
            result['stop_price'] = entry_price * (1 + stop_pct)
            result['target_price'] = entry_price * 0.97
        result['description'] = 'Zone break'

    # Kinematics strategy: momentum-based exit
    elif 'KINEMATICS' in strategy_upper:
        stop_pct = 0.015
        if direction == 'LONG':
            result['stop_price'] = entry_price * (1 - stop_pct)
            result['target_price'] = entry_price * 1.02
        else:
            result['stop_price'] = entry_price * (1 + stop_pct)
            result['target_price'] = entry_price * 0.98
        result['description'] = 'Momentum reversal'

    # Cascade strategy: cascade exhaustion
    elif 'CASCADE' in strategy_upper:
        stop_pct = 0.025
        if direction == 'LONG':
            result['stop_price'] = entry_price * (1 - stop_pct)
            result['target_price'] = entry_price * 1.04
        else:
            result['stop_price'] = entry_price * (1 + stop_pct)
            result['target_price'] = entry_price * 0.96
        result['description'] = 'Cascade exhaustion'

    # Absence strategy
    elif 'ABSENCE' in strategy_upper:
        stop_pct = 0.02
        if direction == 'LONG':
            result['stop_price'] = entry_price * (1 - stop_pct)
        else:
            result['stop_price'] = entry_price * (1 + stop_pct)
        result['description'] = 'Activity resumes'

    else:
        # Default fallback
        stop_pct = 0.02
        if direction == 'LONG':
            result['stop_price'] = entry_price * (1 - stop_pct)
        else:
            result['stop_price'] = entry_price * (1 + stop_pct)
        result['description'] = 'SL/TP'

    return result


def format_price(price: float) -> str:
    """Format price with appropriate precision based on magnitude."""
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:,.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


def format_pnl(pnl: float) -> str:
    """Format PnL with color."""
    if pnl >= 0:
        return f"{Colors.GREEN}+${pnl:.2f}{Colors.RESET}"
    else:
        return f"{Colors.RED}-${abs(pnl):.2f}{Colors.RESET}"


def format_direction(direction: str) -> str:
    """Format direction with color."""
    if direction == 'LONG':
        return f"{Colors.GREEN}LONG {Colors.RESET}"
    else:
        return f"{Colors.RED}SHORT{Colors.RESET}"


def print_header(balance: float = 1000.0):
    """Print header row with account balance."""
    now = datetime.now().strftime('%H:%M:%S')
    title = "POSITION MONITOR"
    bal_str = f"${balance:,.2f}"

    print(f"{BOX_TL}{BOX_H * (WIDTH - 2)}{BOX_TR}")

    # Title line
    padding = WIDTH - len(title) - len(now) - 4
    print(f"{BOX_V}  {Colors.BOLD}{title}{Colors.RESET}{' ' * padding}{Colors.DIM}{now}{Colors.RESET}  {BOX_V}")

    # Balance + price source status line
    bal_color = Colors.GREEN if balance >= 1000 else Colors.RED
    n_ws = len(_ws_prices)
    n_grpc = len(_grpc_prices)
    ws_st = _ws_status
    grpc_st = _grpc_status
    if ws_st == "STREAMING" and n_ws > 0:
        price_disp = f"{Colors.GREEN}WS mid{Colors.RESET}"
        price_plain = "WS mid"
    elif grpc_st == "STREAMING":
        price_disp = f"{Colors.YELLOW}gRPC oracle{Colors.RESET}"
        price_plain = "gRPC oracle"
    elif grpc_st.startswith("ERROR"):
        reason = grpc_st.split(":", 1)[1] if ":" in grpc_st else "unknown"
        price_disp = f"{Colors.RED}ERROR:{reason}{Colors.RESET}"
        price_plain = f"ERROR:{reason}"
    else:
        price_disp = f"{Colors.YELLOW}{grpc_st}{Colors.RESET}"
        price_plain = grpc_st
    n_total = max(n_ws, n_grpc)
    bal_line = f"  Account: {bal_color}{bal_str}{Colors.RESET}  |  {price_disp} ({n_total} prices)"
    bal_visible = len(f"  Account: {bal_str}  |  {price_plain} ({n_total} prices)")
    bal_padding = WIDTH - bal_visible - 2
    print(f"{BOX_V}{bal_line}{' ' * max(0, bal_padding)}{BOX_V}")


def print_section_header(title: str):
    """Print section header."""
    print(f"{BOX_ML}{BOX_H * (WIDTH - 2)}{BOX_MR}")
    print(f"{BOX_V}  {Colors.CYAN}{title}{Colors.RESET}{' ' * (WIDTH - len(title) - 4)}{BOX_V}")
    print(f"{BOX_V}  {LINE * (WIDTH - 6)}  {BOX_V}")


def format_strategy(strategy: Optional[str]) -> str:
    """Format strategy name (shortened)."""
    if not strategy:
        return f"{Colors.DIM}???{Colors.RESET}"
    # Shorten common prefixes
    s = strategy.replace('EP2-', '').replace('-V2', '').replace('-V1', '')
    return f"{Colors.MAGENTA}{s[:8]}{Colors.RESET}"


def print_positions(positions: List[dict], prices: Dict[str, float]):
    """Print open positions with exit criteria."""
    print_section_header("OPEN POSITIONS")

    if not positions:
        print(f"{BOX_V}  {Colors.DIM}No open positions{Colors.RESET}{' ' * (WIDTH - 21)}{BOX_V}")
    else:
        for pos in positions:
            symbol = pos['symbol']
            direction = pos['direction']
            qty = pos['quantity']
            entry = pos['entry_price']
            current = prices.get(symbol)
            strategy = pos.get('strategy')
            trade_id = pos.get('trade_id')

            # Calculate unrealized PnL only if live price available
            if current is not None:
                if direction == 'LONG':
                    pnl = (current - entry) * qty
                else:  # SHORT
                    pnl = (entry - current) * qty
            else:
                pnl = None

            # Try to get trailing stop info first
            trailing_info = None
            if trade_id:
                trailing_info = get_trailing_stop_info(trade_id, symbol)
            elif symbol:
                # For positions without trade_id, try RECOVERED lookup directly
                trailing_info = get_trailing_stop_info("", symbol)

            # Get exit criteria (use trailing stop if available, otherwise strategy-based)
            if trailing_info:
                stop = trailing_info['current_stop']
                be_triggered = trailing_info['break_even_triggered']
                if be_triggered:
                    exit_desc = 'Trailing (BE)'
                else:
                    exit_desc = 'Trailing stop'
            else:
                exit_info = get_exit_criteria(strategy, direction, entry)
                stop = exit_info['stop_price']
                exit_desc = exit_info['description']

            # Format main line
            dir_str = format_direction(direction)
            pnl_str = format_pnl(pnl) if pnl is not None else f"{Colors.DIM}n/a{Colors.RESET}"
            strat_str = format_strategy(strategy)

            entry_str = format_price(entry)
            curr_str = format_price(current) if current is not None else "N/A"
            line = f"  {symbol:<10} {dir_str} @ {entry_str:>10} → {curr_str:>10}  {pnl_str}  {strat_str}"
            visible_len = len(f"  {symbol:<10} SHORT @ {entry_str:>10} → {curr_str:>10}  +$0.00  GEOMETRY")
            padding = WIDTH - visible_len - 2
            print(f"{BOX_V}{line}{' ' * max(0, padding)}{BOX_V}")

            # Format exit criteria line
            if stop:
                if current is None:
                    stop_str = f"${stop:,.2f}" if stop >= 100 else (f"${stop:.3f}" if stop >= 1 else f"${stop:.5f}")
                    note = f"    {Colors.DIM}Stop: {stop_str} (live price unavailable){Colors.RESET}"
                    note_visible = len(f"    Stop: {stop_str} (live price unavailable)")
                    note_padding = WIDTH - note_visible - 2
                    print(f"{BOX_V}{note}{' ' * max(0, note_padding)}{BOX_V}")
                    continue

                # Calculate distance to stop
                if direction == 'LONG':
                    dist_pct = ((current - stop) / stop) * 100
                else:
                    dist_pct = ((stop - current) / current) * 100

                # Color and warning based on how close to stop
                if dist_pct < 0:
                    dist_color = Colors.RED
                    warn = f" {Colors.RED}⚠ TRIGGERED{Colors.RESET}"
                    warn_len = 11
                elif dist_pct < 0.3:
                    dist_color = Colors.RED
                    warn = f" {Colors.RED}⚠ IMMINENT{Colors.RESET}"
                    warn_len = 10
                elif dist_pct < 0.7:
                    dist_color = Colors.YELLOW
                    warn = f" {Colors.YELLOW}! CLOSE{Colors.RESET}"
                    warn_len = 7
                else:
                    dist_color = Colors.GRAY
                    warn = ""
                    warn_len = 0

                # Format stop price with appropriate precision
                if stop < 1:
                    stop_str = f"${stop:.5f}"
                elif stop < 100:
                    stop_str = f"${stop:.3f}"
                else:
                    stop_str = f"${stop:,.2f}"
                exit_line = f"    {Colors.DIM}Stop: {stop_str} ({dist_color}{dist_pct:.2f}%{Colors.RESET}{Colors.DIM} away){Colors.RESET}{warn}"
                exit_visible = len(f"    Stop: {stop_str} (0.00% away)") + warn_len
                exit_padding = WIDTH - exit_visible - 2
                print(f"{BOX_V}{exit_line}{' ' * max(0, exit_padding)}{BOX_V}")


def print_exits(exits: List[dict]):
    """Print recent exits."""
    print_section_header("RECENT EXITS")

    if not exits:
        print(f"{BOX_V}  {Colors.DIM}No recent exits{Colors.RESET}{' ' * (WIDTH - 19)}{BOX_V}")
    else:
        for ex in exits[:10]:
            ts = datetime.fromtimestamp(ex['timestamp']).strftime('%H:%M') if ex['timestamp'] else '??:??'
            symbol = ex['symbol']
            direction = ex['direction']
            pnl = ex['pnl']
            hold_min = int(ex['hold_sec'] / 60) if ex['hold_sec'] else 0
            strategy = ex.get('strategy')

            dir_str = format_direction(direction)
            pnl_str = format_pnl(pnl)
            strat_str = format_strategy(strategy)

            line = f"  {ts}  {symbol:<10} {dir_str}  {pnl_str}  ({hold_min}m)  {strat_str}"
            visible_len = len(f"  {ts}  {symbol:<10} SHORT  +$0.00  ({hold_min}m)  GEOMETRY")
            padding = WIDTH - visible_len - 2
            print(f"{BOX_V}{line}{' ' * max(0, padding)}{BOX_V}")


def print_stats(stats: dict):
    """Print session statistics."""
    print(f"{BOX_ML}{BOX_H * (WIDTH - 2)}{BOX_MR}")

    trades = stats['trades']
    net = stats['net_pnl']
    win_rate = (stats['wins'] / trades * 100) if trades > 0 else 0

    net_str = format_pnl(net)

    line = f"  SESSION: {trades} trades | {net_str} net | {win_rate:.0f}% win"
    visible_len = len(f"  SESSION: {trades} trades | +$0.00 net | {win_rate:.0f}% win")
    padding = WIDTH - visible_len - 2
    print(f"{BOX_V}{line}{' ' * max(0, padding)}{BOX_V}")


def print_footer():
    """Print footer."""
    print(f"{BOX_BL}{BOX_H * (WIDTH - 2)}{BOX_BR}")


def main():
    parser = argparse.ArgumentParser(description='Terminal Position Monitor')
    parser.add_argument('--interval', '-i', type=float, default=2.0,
                        help='Refresh interval in seconds (default: 2)')
    args = parser.parse_args()

    print(f"{Colors.CYAN}Starting position monitor (Ctrl+C to exit)...{Colors.RESET}")
    start_price_stream()
    start_ws_price_stream()
    # Wait until gRPC stream has prices (up to 5s)
    for _ in range(50):
        if _grpc_status == "STREAMING":
            break
        time.sleep(0.1)

    try:
        while True:
            # Fetch data
            positions = get_open_positions()
            symbols = [p['symbol'] for p in positions]
            prices = get_live_prices(symbols) if symbols else {}
            exits = get_recent_exits()
            stats = get_session_stats()
            balance = get_account_balance()

            # Render
            clear_screen()
            print_header(balance)
            print_positions(positions, prices)
            print_exits(exits)
            print_stats(stats)
            print_footer()
            print(f"\n{Colors.DIM}Refreshing every {args.interval}s | Ctrl+C to exit{Colors.RESET}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Monitor stopped.{Colors.RESET}")
        sys.exit(0)


if __name__ == '__main__':
    main()

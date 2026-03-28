"""
Bracket exit manager for OB-target trades.

Fixed TP/SL bracket with time cutoff. No trailing.
Research: OB target exit → 89% WR, +42bp avg, 14.1x PF at SL=30bp.
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class BracketConfig:
    sl_bps: float = 30.0
    max_hold_sec: float = 3600


@dataclass
class _BracketState:
    entry_id: str
    symbol: str
    direction: str
    entry_price: float
    tp_price: float
    sl_price: float
    entry_ts: float
    max_hold_sec: float


class BracketExitManager:
    def __init__(self):
        self._brackets: Dict[str, _BracketState] = {}

    def register(self, entry_id, symbol, direction, entry_price, tp_price,
                 sl_bps=30.0, max_hold_sec=3600, entry_ts=None):
        if entry_ts is None:
            entry_ts = time.time()
        if direction == "LONG":
            sl_price = entry_price * (1 - sl_bps / 10000)
        else:
            sl_price = entry_price * (1 + sl_bps / 10000)
        self._brackets[entry_id] = _BracketState(
            entry_id=entry_id, symbol=symbol, direction=direction,
            entry_price=entry_price, tp_price=tp_price, sl_price=sl_price,
            entry_ts=entry_ts, max_hold_sec=max_hold_sec)

    def unregister(self, entry_id):
        self._brackets.pop(entry_id, None)

    def check_exits(self, symbol, price, now=None):
        if now is None:
            now = time.time()
        exits = []
        for entry_id, state in list(self._brackets.items()):
            if state.symbol != symbol:
                continue
            reason = None
            if state.direction == "LONG" and price >= state.tp_price:
                reason = "BRACKET_TP"
            elif state.direction == "SHORT" and price <= state.tp_price:
                reason = "BRACKET_TP"
            if reason is None:
                if state.direction == "LONG" and price <= state.sl_price:
                    reason = "BRACKET_SL"
                elif state.direction == "SHORT" and price >= state.sl_price:
                    reason = "BRACKET_SL"
            if reason is None:
                if now - state.entry_ts >= state.max_hold_sec:
                    reason = "BRACKET_TIMEOUT"
            if reason:
                exits.append({
                    'entry_id': entry_id, 'reason': reason, 'price': price,
                    'entry_price': state.entry_price, 'tp_price': state.tp_price,
                    'sl_price': state.sl_price, 'hold_sec': now - state.entry_ts})
                self._brackets.pop(entry_id)
        return exits

    def get_bracket(self, entry_id):
        return self._brackets.get(entry_id)

    def has_bracket(self, symbol):
        return any(s.symbol == symbol for s in self._brackets.values())

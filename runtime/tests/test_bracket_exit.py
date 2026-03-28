import pytest
from runtime.liquidations.bracket_exit import BracketExitManager, BracketConfig

class TestBracketExit:
    def test_no_brackets_no_exit(self):
        mgr = BracketExitManager()
        result = mgr.check_exits("BTC", 70000)
        assert result == []

    def test_long_tp_hit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        exits = mgr.check_exits("BTC", 70050, now=1100)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_TP'
        assert exits[0]['entry_id'] == 'trade1'

    def test_long_sl_hit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        # 30bp of 70000 = 210 points, SL at 69790
        exits = mgr.check_exits("BTC", 69789, now=1100)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_SL'

    def test_short_tp_hit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="SHORT",
                      entry_price=70000, tp_price=69950, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        exits = mgr.check_exits("BTC", 69950, now=1100)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_TP'

    def test_max_hold_exit(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        exits = mgr.check_exits("BTC", 70010, now=1000 + 3660)
        assert len(exits) == 1
        assert exits[0]['reason'] == 'BRACKET_TIMEOUT'

    def test_unregister(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        mgr.unregister("trade1")
        exits = mgr.check_exits("BTC", 70050, now=1100)
        assert exits == []

    def test_no_exit_in_range(self):
        mgr = BracketExitManager()
        mgr.register("trade1", symbol="BTC", direction="LONG",
                      entry_price=70000, tp_price=70050, sl_bps=30,
                      max_hold_sec=3600, entry_ts=1000)
        exits = mgr.check_exits("BTC", 70025, now=1100)
        assert exits == []

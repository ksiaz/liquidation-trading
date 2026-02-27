"""
Unit tests for SLBRS kill-switch rebuild from history.

Verifies that:
1. rebuild_from_history() restores per-symbol and global consecutive loss counters
2. rebuild_from_history() restores trade_results deque for winrate checks
3. Global consecutive loss kill switch blocks entry after 5 losses across symbols
"""

import pytest

from external_policy.ep2_slbrs_strategy import SLBRSStrategy


class TestSLBRSRebuild:
    """Test rebuild_from_history() restores kill-switch state."""

    def test_empty_history(self):
        """No trades = clean state."""
        s = SLBRSStrategy()
        s.rebuild_from_history([])
        assert s._global_consecutive_losses == 0
        assert len(s._consecutive_losses) == 0
        assert len(s._trade_results) == 0

    def test_single_win(self):
        """Single winning trade resets counters."""
        s = SLBRSStrategy()
        s.rebuild_from_history([("SOLUSDT", 0.50)])
        assert s._global_consecutive_losses == 0
        assert s._consecutive_losses.get("SOLUSDT") == 0
        assert len(s._trade_results) == 1
        assert s._trade_results[0] is True

    def test_single_loss(self):
        """Single losing trade increments counters."""
        s = SLBRSStrategy()
        s.rebuild_from_history([("SOLUSDT", -0.30)])
        assert s._global_consecutive_losses == 1
        assert s._consecutive_losses["SOLUSDT"] == 1
        assert len(s._trade_results) == 1
        assert s._trade_results[0] is False

    def test_consecutive_losses_per_symbol(self):
        """3 consecutive losses on SOL tracked correctly."""
        s = SLBRSStrategy()
        s.rebuild_from_history([
            ("SOLUSDT", -0.10),
            ("SOLUSDT", -0.20),
            ("SOLUSDT", -0.30),
        ])
        assert s._consecutive_losses["SOLUSDT"] == 3
        assert s._global_consecutive_losses == 3

    def test_win_resets_global(self):
        """A win in the middle resets global counter but not other symbols' per-symbol."""
        s = SLBRSStrategy()
        s.rebuild_from_history([
            ("SOLUSDT", -0.10),   # SOL per-sym=1, global=1
            ("SOLUSDT", -0.20),   # SOL per-sym=2, global=2
            ("BTCUSDT", 0.50),    # BTC per-sym=0, global=0 (win resets global)
            ("SOLUSDT", -0.30),   # SOL per-sym=3 (per-sym NOT reset by BTC win), global=1
        ])
        assert s._consecutive_losses["SOLUSDT"] == 3  # Per-symbol tracks SOL only
        assert s._consecutive_losses["BTCUSDT"] == 0
        assert s._global_consecutive_losses == 1  # Only 1 loss after the BTC win

    def test_cross_symbol_global_counter(self):
        """Global counter spans symbols: SOL loss + BTC loss + ETH loss = 3."""
        s = SLBRSStrategy()
        s.rebuild_from_history([
            ("SOLUSDT", -0.10),
            ("BTCUSDT", -0.20),
            ("ETHUSDT", -0.30),
        ])
        assert s._consecutive_losses["SOLUSDT"] == 1
        assert s._consecutive_losses["BTCUSDT"] == 1
        assert s._consecutive_losses["ETHUSDT"] == 1
        assert s._global_consecutive_losses == 3

    def test_five_global_losses_triggers_kill(self):
        """5 consecutive losses across symbols should trigger global kill switch."""
        s = SLBRSStrategy()
        s.rebuild_from_history([
            ("SOLUSDT", -0.10),
            ("BTCUSDT", -0.20),
            ("SOLUSDT", -0.15),
            ("ETHUSDT", -0.30),
            ("SOLUSDT", -0.25),
        ])
        assert s._global_consecutive_losses == 5
        assert s._global_consecutive_losses >= s._MAX_GLOBAL_CONSECUTIVE_LOSSES

    def test_winrate_rebuilt(self):
        """Trade results deque populated for winrate checks."""
        s = SLBRSStrategy()
        # 6W/15L = 28.6% WR (matches actual SLBRS history)
        trades = (
            [("SOLUSDT", 0.50)] * 6 +
            [("SOLUSDT", -0.30)] * 15
        )
        s.rebuild_from_history(trades)
        assert len(s._trade_results) == 20  # Capped at maxlen=20
        winrate = sum(s._trade_results) / len(s._trade_results)
        assert winrate < s._MIN_WINRATE  # 28.6% < 35%

    def test_null_pnl_is_loss(self):
        """None pnl (e.g. MANDATE_EXIT with no fill) counts as loss."""
        s = SLBRSStrategy()
        s.rebuild_from_history([("SOLUSDT", None)])
        assert s._global_consecutive_losses == 1
        assert s._consecutive_losses["SOLUSDT"] == 1
        assert s._trade_results[0] is False

    def test_zero_pnl_is_loss(self):
        """Zero pnl counts as loss (not a win)."""
        s = SLBRSStrategy()
        s.rebuild_from_history([("SOLUSDT", 0.0)])
        assert s._global_consecutive_losses == 1
        assert s._trade_results[0] is False

    def test_rebuild_clears_previous_state(self):
        """Calling rebuild twice replaces previous state."""
        s = SLBRSStrategy()
        s.rebuild_from_history([("SOLUSDT", -0.10), ("SOLUSDT", -0.20)])
        assert s._global_consecutive_losses == 2

        # Second rebuild with different data
        s.rebuild_from_history([("BTCUSDT", 0.50)])
        assert s._global_consecutive_losses == 0
        assert s._consecutive_losses.get("SOLUSDT") is None
        assert s._consecutive_losses["BTCUSDT"] == 0

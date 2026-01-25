"""Unit tests for TradeJournal."""

import pytest
import time
from unittest.mock import MagicMock, patch

from runtime.analytics.trade_journal import TradeJournal, JournalConfig
from runtime.analytics.types import TradeOutcome


class TestTradeJournal:
    """Tests for TradeJournal."""

    def test_init_defaults(self):
        """Test journal initialization with defaults."""
        journal = TradeJournal()
        assert len(journal._trades) == 0
        assert len(journal._open_trades) == 0
        assert len(journal._closed_trades) == 0

    def test_init_custom_config(self):
        """Test journal initialization with custom config."""
        config = JournalConfig(
            persist_to_file=False,
            max_memory_trades=500
        )
        journal = TradeJournal(config=config)
        assert journal._config.max_memory_trades == 500

    def test_generate_trade_id(self):
        """Test trade ID generation."""
        journal = TradeJournal()
        id1 = journal._generate_trade_id()
        id2 = journal._generate_trade_id()
        assert id1 != id2
        assert id1.startswith("trade_")
        assert id2.startswith("trade_")

    def test_open_trade(self):
        """Test opening a trade."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test_strategy",
            direction="LONG",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_123",
            stop_price=49000.0,
            target_price=52000.0
        )

        assert trade.symbol == "BTC-PERP"
        assert trade.strategy == "test_strategy"
        assert trade.direction == "LONG"
        assert trade.entry_price == 50000.0
        assert trade.entry_size == 1.0
        assert trade.stop_price == 49000.0
        assert trade.target_price == 52000.0
        assert trade.outcome == TradeOutcome.OPEN

        # Check storage
        assert trade.trade_id in journal._trades
        assert trade.trade_id in journal._open_trades

    def test_close_trade_win(self):
        """Test closing a trade with profit."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test",
            direction="LONG",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
        )

        closed = journal.close_trade(
            trade_id=trade.trade_id,
            exit_price=51000.0,
            exit_reason="TARGET",
            fees=10.0
        )

        assert closed is not None
        assert closed.exit_price == 51000.0
        assert closed.exit_reason == "TARGET"
        assert closed.realized_pnl == 1000.0
        assert closed.net_pnl == 990.0  # 1000 - 10 fees
        assert closed.outcome == TradeOutcome.WIN

        # Check storage moved
        assert trade.trade_id not in journal._open_trades
        assert closed in journal._closed_trades

    def test_close_trade_loss(self):
        """Test closing a trade with loss."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test",
            direction="LONG",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
        )

        closed = journal.close_trade(
            trade_id=trade.trade_id,
            exit_price=49000.0,
            exit_reason="STOP",
            fees=10.0
        )

        assert closed.realized_pnl == -1000.0
        assert closed.net_pnl == -1010.0
        assert closed.outcome == TradeOutcome.LOSS

    def test_close_trade_short(self):
        """Test closing a short trade."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test",
            direction="SHORT",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
        )

        closed = journal.close_trade(
            trade_id=trade.trade_id,
            exit_price=49000.0,
            exit_reason="TARGET",
            fees=10.0
        )

        # Short: profit = (entry - exit) * size = (50000 - 49000) * 1 = 1000
        assert closed.realized_pnl == 1000.0
        assert closed.net_pnl == 990.0
        assert closed.outcome == TradeOutcome.WIN

    def test_close_trade_not_found(self):
        """Test closing non-existent trade."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        result = journal.close_trade(
            trade_id="nonexistent",
            exit_price=50000.0,
            exit_reason="MANUAL"
        )
        assert result is None

    def test_close_trade_already_closed(self):
        """Test closing already closed trade."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test",
            direction="LONG",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1"
        )

        journal.close_trade(trade.trade_id, 51000.0, "TARGET")
        result = journal.close_trade(trade.trade_id, 52000.0, "TARGET")

        # Should return existing closed trade, not re-close
        assert result.exit_price == 51000.0

    def test_update_stop(self):
        """Test updating stop price."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test",
            direction="LONG",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1",
            stop_price=49000.0
        )

        journal.update_stop(trade.trade_id, 49500.0, "stop_order_1")

        updated = journal.get_trade(trade.trade_id)
        assert updated.stop_price == 49500.0
        assert updated.stop_order_id == "stop_order_1"

    def test_update_target(self):
        """Test updating target price."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))
        trade = journal.open_trade(
            symbol="BTC-PERP",
            strategy="test",
            direction="LONG",
            entry_price=50000.0,
            entry_size=1.0,
            entry_order_id="order_1",
            target_price=52000.0
        )

        journal.update_target(trade.trade_id, 53000.0, "target_order_1")

        updated = journal.get_trade(trade.trade_id)
        assert updated.target_price == 53000.0
        assert updated.target_order_id == "target_order_1"

    def test_get_open_trades(self):
        """Test getting open trades."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        trade1 = journal.open_trade(
            symbol="BTC-PERP", strategy="test", direction="LONG",
            entry_price=50000.0, entry_size=1.0, entry_order_id="1"
        )
        trade2 = journal.open_trade(
            symbol="ETH-PERP", strategy="test", direction="SHORT",
            entry_price=3000.0, entry_size=10.0, entry_order_id="2"
        )

        open_trades = journal.get_open_trades()
        assert len(open_trades) == 2

        journal.close_trade(trade1.trade_id, 51000.0, "TARGET")

        open_trades = journal.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].symbol == "ETH-PERP"

    def test_get_open_trade_for_symbol(self):
        """Test getting open trade for symbol."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        journal.open_trade(
            symbol="BTC-PERP", strategy="test", direction="LONG",
            entry_price=50000.0, entry_size=1.0, entry_order_id="1"
        )

        btc_trade = journal.get_open_trade_for_symbol("BTC-PERP")
        assert btc_trade is not None
        assert btc_trade.symbol == "BTC-PERP"

        eth_trade = journal.get_open_trade_for_symbol("ETH-PERP")
        assert eth_trade is None

    def test_get_trades_by_strategy(self):
        """Test getting trades by strategy."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        # Open and close some trades
        for i, strategy in enumerate(["strat_a", "strat_a", "strat_b"]):
            trade = journal.open_trade(
                symbol="BTC-PERP", strategy=strategy, direction="LONG",
                entry_price=50000.0 + i * 100, entry_size=1.0, entry_order_id=str(i)
            )
            journal.close_trade(trade.trade_id, 51000.0 + i * 100, "TARGET")

        strat_a_trades = journal.get_trades_by_strategy("strat_a")
        assert len(strat_a_trades) == 2

        strat_b_trades = journal.get_trades_by_strategy("strat_b")
        assert len(strat_b_trades) == 1

    def test_get_trades_by_symbol(self):
        """Test getting trades by symbol."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        for symbol in ["BTC-PERP", "BTC-PERP", "ETH-PERP"]:
            trade = journal.open_trade(
                symbol=symbol, strategy="test", direction="LONG",
                entry_price=50000.0, entry_size=1.0, entry_order_id=symbol
            )
            journal.close_trade(trade.trade_id, 51000.0, "TARGET")

        btc_trades = journal.get_trades_by_symbol("BTC-PERP")
        assert len(btc_trades) == 2

    def test_get_summary(self):
        """Test getting journal summary."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        # Create 3 wins and 2 losses
        for i in range(5):
            trade = journal.open_trade(
                symbol="BTC-PERP", strategy="test", direction="LONG",
                entry_price=50000.0, entry_size=1.0, entry_order_id=str(i)
            )
            exit_price = 51000.0 if i < 3 else 49000.0
            journal.close_trade(trade.trade_id, exit_price, "TARGET")

        summary = journal.get_summary()

        assert summary['total_trades'] == 5
        assert summary['wins'] == 3
        assert summary['losses'] == 2
        assert summary['win_rate'] == 0.6

    def test_callbacks(self):
        """Test trade open/close callbacks."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        open_callback = MagicMock()
        close_callback = MagicMock()

        journal.set_trade_open_callback(open_callback)
        journal.set_trade_close_callback(close_callback)

        trade = journal.open_trade(
            symbol="BTC-PERP", strategy="test", direction="LONG",
            entry_price=50000.0, entry_size=1.0, entry_order_id="1"
        )
        open_callback.assert_called_once()

        journal.close_trade(trade.trade_id, 51000.0, "TARGET")
        close_callback.assert_called_once()

    def test_trim_memory(self):
        """Test memory trimming."""
        config = JournalConfig(persist_to_file=False, max_memory_trades=5)
        journal = TradeJournal(config=config)

        # Create 10 trades
        for i in range(10):
            trade = journal.open_trade(
                symbol="BTC-PERP", strategy="test", direction="LONG",
                entry_price=50000.0, entry_size=1.0, entry_order_id=str(i)
            )
            journal.close_trade(trade.trade_id, 51000.0, "TARGET")

        # Should only keep last 5
        assert len(journal._closed_trades) == 5

    def test_daily_stats(self):
        """Test daily stats tracking."""
        journal = TradeJournal(config=JournalConfig(persist_to_file=False))

        # Create some trades
        trade = journal.open_trade(
            symbol="BTC-PERP", strategy="test", direction="LONG",
            entry_price=50000.0, entry_size=1.0, entry_order_id="1"
        )
        journal.close_trade(trade.trade_id, 51000.0, "TARGET", fees=10.0)

        # Get today's stats
        stats = journal.get_daily_stats()
        assert stats is not None
        assert stats.trades == 1
        assert stats.wins == 1
        assert stats.pnl == 1000.0
        assert stats.fees == 10.0

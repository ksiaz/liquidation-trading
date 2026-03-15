"""Tests for BinanceDataProvider message parsing and callback dispatch."""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from runtime.binance.data_provider import BinanceDataProvider


SYMBOLS = ["BTCUSDT", "ETHUSDT"]


class TestAggTradeParser:
    """Test aggTrade message → _handle_hl_fill callback."""

    def test_taker_buy(self):
        """m=false means seller is maker → taker is buyer → side='B'."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_fill = MagicMock()
        provider.on_fill = mock_fill

        msg = {
            "e": "aggTrade", "s": "BTCUSDT", "p": "71000.5",
            "q": "0.5", "m": False, "T": 1773580200000
        }
        provider._handle_agg_trade(msg)

        mock_fill.assert_called_once_with("BTC", "B", 71000.5, 0.5, 1773580200.0)

    def test_taker_sell(self):
        """m=true means buyer is maker → taker is seller → side='A'."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_fill = MagicMock()
        provider.on_fill = mock_fill

        msg = {
            "e": "aggTrade", "s": "ETHUSDT", "p": "2100.0",
            "q": "1.0", "m": True, "T": 1773580200000
        }
        provider._handle_agg_trade(msg)

        mock_fill.assert_called_once_with("ETH", "A", 2100.0, 1.0, 1773580200.0)

    def test_ignored_symbol(self):
        """Fills for symbols not in our list are dropped."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_fill = MagicMock()
        provider.on_fill = mock_fill

        msg = {
            "e": "aggTrade", "s": "SHIBUSDT", "p": "0.00001",
            "q": "1000000", "m": False, "T": 1773580200000
        }
        provider._handle_agg_trade(msg)

        mock_fill.assert_not_called()


class TestForceOrderParser:
    """Test forceOrder message → _handle_hl_liquidation callback."""

    def test_long_liquidation(self):
        """S='SELL' means long position liquidated → side='LONG'."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_liq = MagicMock()
        provider.on_liquidation = mock_liq

        msg = {
            "e": "forceOrder",
            "o": {
                "s": "BTCUSDT", "S": "SELL", "p": "70000",
                "q": "0.1", "ap": "69950", "T": 1773580200000
            }
        }
        provider._handle_force_order(msg)

        mock_liq.assert_called_once_with("BTC", "LONG", 69950.0, 0.1, 1773580200.0)

    def test_short_liquidation(self):
        """S='BUY' means short position liquidated → side='SHORT'."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_liq = MagicMock()
        provider.on_liquidation = mock_liq

        msg = {
            "e": "forceOrder",
            "o": {
                "s": "ETHUSDT", "S": "BUY", "p": "2200",
                "q": "5.0", "ap": "2205", "T": 1773580200000
            }
        }
        provider._handle_force_order(msg)

        mock_liq.assert_called_once_with("ETH", "SHORT", 2205.0, 5.0, 1773580200.0)

    def test_ignored_symbol(self):
        """Liquidations for symbols not in our list are dropped."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_liq = MagicMock()
        provider.on_liquidation = mock_liq

        msg = {
            "e": "forceOrder",
            "o": {"s": "XYZUSDT", "S": "SELL", "p": "1", "q": "1", "ap": "1", "T": 0}
        }
        provider._handle_force_order(msg)

        mock_liq.assert_not_called()


class TestDepthParser:
    """Test depth20 message → _handle_hl_orderbook callback."""

    def test_orderbook_format(self):
        """Depth message converts to {coin, bids:[{price,size}], asks:[{price,size}]}."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_ob = MagicMock()
        provider.on_orderbook = mock_ob

        msg = {
            "e": "depthUpdate", "s": "BTCUSDT",
            "b": [["71000.0", "1.5"], ["70999.0", "2.0"]],
            "a": [["71001.0", "0.8"], ["71002.0", "1.2"]]
        }
        provider._handle_depth(msg)

        mock_ob.assert_called_once()
        ob = mock_ob.call_args[0][0]
        assert ob["coin"] == "BTC"
        assert ob["bids"][0]["price"] == 71000.0
        assert ob["bids"][0]["size"] == 1.5
        assert ob["asks"][0]["price"] == 71001.0
        assert ob["asks"][0]["size"] == 0.8
        assert len(ob["bids"]) == 2
        assert len(ob["asks"]) == 2


class TestMarkPriceParser:
    """Test markPrice message → _handle_hl_price callback."""

    def test_mark_price(self):
        provider = BinanceDataProvider(SYMBOLS)
        mock_price = MagicMock()
        provider.on_price = mock_price

        msg = {
            "e": "markPriceUpdate", "s": "BTCUSDT",
            "p": "71500.25", "E": 1773580200000
        }
        provider._handle_mark_price(msg)

        mock_price.assert_called_once_with("BTC", 71500.25, 1773580200.0)

    def test_ignored_symbol(self):
        provider = BinanceDataProvider(SYMBOLS)
        mock_price = MagicMock()
        provider.on_price = mock_price

        msg = {"e": "markPriceUpdate", "s": "SHIBUSDT", "p": "0.001", "E": 0}
        provider._handle_mark_price(msg)

        mock_price.assert_not_called()


class TestSymbolMapping:
    """Test symbol normalization."""

    def test_strip_usdt(self):
        provider = BinanceDataProvider(SYMBOLS)
        assert provider._to_coin("BTCUSDT") == "BTC"
        assert provider._to_coin("ETHUSDT") == "ETH"

    def test_symbol_set(self):
        provider = BinanceDataProvider(["BTCUSDT", "ETHUSDT", "PEPEUSDT"])
        assert "BTCUSDT" in provider._symbol_set
        assert "PEPEUSDT" in provider._symbol_set

    def test_stream_names(self):
        provider = BinanceDataProvider(["BTCUSDT", "ETHUSDT"])
        streams = provider._build_stream_names()
        assert "btcusdt@aggTrade" in streams
        assert "ethusdt@aggTrade" in streams
        assert "!forceOrder@arr" in streams
        assert "btcusdt@depth20@100ms" in streams
        assert "!markPrice@arr@1s" in streams


class TestDispatchArray:
    """Test _dispatch handles markPrice array messages."""

    def test_mark_price_array(self):
        """markPrice@arr sends array of all mark prices at once."""
        provider = BinanceDataProvider(SYMBOLS)
        mock_price = MagicMock()
        provider.on_price = mock_price

        # Binance sends array of markPriceUpdate dicts
        msg = [
            {"e": "markPriceUpdate", "s": "BTCUSDT", "p": "71000", "E": 1773580200000},
            {"e": "markPriceUpdate", "s": "ETHUSDT", "p": "2100", "E": 1773580200000},
            {"e": "markPriceUpdate", "s": "SHIBUSDT", "p": "0.001", "E": 1773580200000},
        ]
        provider._dispatch(msg)

        # Should fire for BTC and ETH (in symbol set), skip SHIB
        assert mock_price.call_count == 2

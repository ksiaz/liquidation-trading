"""
M1 Ingestion Engine Comprehensive Test Suite

Tests the M1 ingestion layer responsible for normalizing raw market data.
Constitutional: No semantic interpretation, factual normalization only.

Authority: EPISTEMIC_CONSTITUTION.md (M1-M5 observation constraints)
"""

import pytest
import sys
from collections import deque

sys.path.append('D:/liquidation-trading')

from observation.internal.m1_ingestion import M1IngestionEngine


# ============================================================================
# TEST SUITE 1: Trade Normalization
# ============================================================================

class TestM1TradeNormalization:
    @pytest.fixture
    def engine(self):
        return M1IngestionEngine()

    def test_normalize_trade_valid_payload(self, engine):
        """Verify trade normalization with valid Binance payload."""
        payload = {
            'p': '50000.0',      # price
            'q': '1.5',          # quantity
            'T': 1700000000000,  # timestamp (ms)
            'm': False           # is_buyer_maker
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result is not None
        assert result['symbol'] == 'BTCUSDT'
        assert result['price'] == 50000.0
        assert result['quantity'] == 1.5
        assert result['timestamp'] == 1700000000.0  # Converted to seconds
        assert result['side'] == 'BUY'  # maker=False → taker=BUY
        assert result['base_qty'] == 1.5
        assert result['quote_qty'] == 50000.0 * 1.5

    def test_normalize_trade_side_interpretation_buy(self, engine):
        """Verify side interpretation: m=False → BUY (taker bought)."""
        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False  # Maker was seller → Taker bought → BUY
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result['side'] == 'BUY'

    def test_normalize_trade_side_interpretation_sell(self, engine):
        """Verify side interpretation: m=True → SELL (taker sold)."""
        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': True  # Maker was buyer → Taker sold → SELL
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result['side'] == 'SELL'

    def test_normalize_trade_appends_to_buffer(self, engine):
        """Verify trade appended to raw_trades buffer."""
        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        engine.normalize_trade('BTCUSDT', payload)

        assert len(engine.raw_trades['BTCUSDT']) == 1
        assert engine.raw_trades['BTCUSDT'][0]['price'] == 50000.0

    def test_normalize_trade_updates_recent_prices(self, engine):
        """Verify trade updates recent_prices deque (for absorption detection)."""
        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        engine.normalize_trade('BTCUSDT', payload)

        assert len(engine.recent_prices['BTCUSDT']) == 1
        ts, price = engine.recent_prices['BTCUSDT'][0]
        assert ts == 1700000000.0
        assert price == 50000.0

    def test_normalize_trade_increments_counter(self, engine):
        """Verify trades counter increments on success."""
        payload = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        assert engine.counters['trades'] == 0
        engine.normalize_trade('BTCUSDT', payload)
        assert engine.counters['trades'] == 1

    def test_normalize_trade_error_handling(self, engine):
        """Verify malformed payload increments error counter."""
        payload = {
            'p': 'invalid',  # Invalid price
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result is None
        assert engine.counters['errors'] == 1
        assert engine.counters['trades'] == 0

    def test_normalize_trade_missing_field(self, engine):
        """Verify missing required field returns None and increments error counter."""
        payload = {
            'p': '50000.0',
            # 'q' is missing
            'T': 1700000000000,
            'm': False
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result is None
        assert engine.counters['errors'] == 1

    def test_normalize_trade_zero_quantity(self, engine):
        """Verify zero quantity is accepted (edge case)."""
        payload = {
            'p': '50000.0',
            'q': '0.0',
            'T': 1700000000000,
            'm': False
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result is not None
        assert result['quantity'] == 0.0

    def test_normalize_trade_multiple_symbols_isolated(self, engine):
        """Verify trades for different symbols are isolated."""
        payload_btc = {
            'p': '50000.0',
            'q': '1.0',
            'T': 1700000000000,
            'm': False
        }
        payload_eth = {
            'p': '3000.0',
            'q': '5.0',
            'T': 1700000001000,
            'm': True
        }

        engine.normalize_trade('BTCUSDT', payload_btc)
        engine.normalize_trade('ETHUSDT', payload_eth)

        assert len(engine.raw_trades['BTCUSDT']) == 1
        assert len(engine.raw_trades['ETHUSDT']) == 1
        assert engine.raw_trades['BTCUSDT'][0]['price'] == 50000.0
        assert engine.raw_trades['ETHUSDT'][0]['price'] == 3000.0

    def test_normalize_trade_recent_prices_deque_maxlen(self, engine):
        """Verify recent_prices respects maxlen=10 (circular buffer)."""
        for i in range(15):
            payload = {
                'p': f'{50000 + i}.0',
                'q': '1.0',
                'T': 1700000000000 + i * 1000,
                'm': False
            }
            engine.normalize_trade('BTCUSDT', payload)

        # Should only have last 10 prices
        assert len(engine.recent_prices['BTCUSDT']) == 10
        # First price should be from iteration 5 (50005.0)
        _, first_price = engine.recent_prices['BTCUSDT'][0]
        assert first_price == 50005.0

    def test_normalize_trade_large_quantity(self, engine):
        """Verify large quantity values are handled."""
        payload = {
            'p': '50000.0',
            'q': '1000000.0',
            'T': 1700000000000,
            'm': False
        }

        result = engine.normalize_trade('BTCUSDT', payload)

        assert result is not None
        assert result['quantity'] == 1000000.0
        assert result['quote_qty'] == 50000000000.0

    def test_normalize_trade_small_price(self, engine):
        """Verify small price values (altcoins) are handled."""
        payload = {
            'p': '0.0001',
            'q': '100000.0',
            'T': 1700000000000,
            'm': False
        }

        result = engine.normalize_trade('DOGEUSDT', payload)

        assert result is not None
        assert result['price'] == 0.0001
        assert result['quote_qty'] == 10.0


# ============================================================================
# TEST SUITE 2: Liquidation Normalization
# ============================================================================

class TestM1LiquidationNormalization:
    @pytest.fixture
    def engine(self):
        return M1IngestionEngine()

    def test_normalize_liquidation_valid_payload(self, engine):
        """Verify liquidation normalization with valid Binance ForceOrder payload."""
        payload = {
            'E': 1700000000000,  # Event time (ms)
            'o': {
                'p': '50000.0',  # price
                'q': '10.0',     # quantity
                'S': 'SELL'      # side
            }
        }

        result = engine.normalize_liquidation('BTCUSDT', payload)

        assert result is not None
        assert result['symbol'] == 'BTCUSDT'
        assert result['price'] == 50000.0
        assert result['quantity'] == 10.0
        assert result['timestamp'] == 1700000000.0  # Converted to seconds
        assert result['side'] == 'SELL'
        assert result['base_qty'] == 10.0
        assert result['quote_qty'] == 500000.0

    def test_normalize_liquidation_buy_side(self, engine):
        """Verify BUY liquidations are processed."""
        payload = {
            'E': 1700000000000,
            'o': {
                'p': '50000.0',
                'q': '5.0',
                'S': 'BUY'
            }
        }

        result = engine.normalize_liquidation('BTCUSDT', payload)

        assert result is not None
        assert result['side'] == 'BUY'

    def test_normalize_liquidation_appends_to_buffer(self, engine):
        """Verify liquidation appended to raw_liquidations buffer."""
        payload = {
            'E': 1700000000000,
            'o': {
                'p': '50000.0',
                'q': '10.0',
                'S': 'SELL'
            }
        }

        engine.normalize_liquidation('BTCUSDT', payload)

        assert len(engine.raw_liquidations['BTCUSDT']) == 1
        assert engine.raw_liquidations['BTCUSDT'][0]['price'] == 50000.0

    def test_normalize_liquidation_increments_counter(self, engine):
        """Verify liquidations counter increments on success."""
        payload = {
            'E': 1700000000000,
            'o': {
                'p': '50000.0',
                'q': '10.0',
                'S': 'SELL'
            }
        }

        assert engine.counters['liquidations'] == 0
        engine.normalize_liquidation('BTCUSDT', payload)
        assert engine.counters['liquidations'] == 1

    def test_normalize_liquidation_error_handling(self, engine):
        """Verify malformed payload increments error counter."""
        payload = {
            'E': 1700000000000,
            'o': {
                'p': 'invalid',  # Invalid price
                'q': '10.0',
                'S': 'SELL'
            }
        }

        result = engine.normalize_liquidation('BTCUSDT', payload)

        assert result is None
        assert engine.counters['errors'] == 1
        assert engine.counters['liquidations'] == 0

    def test_normalize_liquidation_missing_o_field(self, engine):
        """Verify missing 'o' field returns None."""
        payload = {
            'E': 1700000000000,
            # 'o' field missing
        }

        result = engine.normalize_liquidation('BTCUSDT', payload)

        assert result is None
        assert engine.counters['errors'] == 1

    def test_normalize_liquidation_multiple_symbols(self, engine):
        """Verify liquidations for different symbols are isolated."""
        payload_btc = {
            'E': 1700000000000,
            'o': {'p': '50000.0', 'q': '10.0', 'S': 'SELL'}
        }
        payload_eth = {
            'E': 1700000001000,
            'o': {'p': '3000.0', 'q': '20.0', 'S': 'BUY'}
        }

        engine.normalize_liquidation('BTCUSDT', payload_btc)
        engine.normalize_liquidation('ETHUSDT', payload_eth)

        assert len(engine.raw_liquidations['BTCUSDT']) == 1
        assert len(engine.raw_liquidations['ETHUSDT']) == 1

    def test_normalize_liquidation_large_liquidation(self, engine):
        """Verify large liquidation sizes are handled."""
        payload = {
            'E': 1700000000000,
            'o': {
                'p': '50000.0',
                'q': '100000.0',  # Large liquidation
                'S': 'SELL'
            }
        }

        result = engine.normalize_liquidation('BTCUSDT', payload)

        assert result is not None
        assert result['quantity'] == 100000.0
        assert result['quote_qty'] == 5000000000.0


# ============================================================================
# TEST SUITE 3: Depth Normalization
# ============================================================================

class TestM1DepthNormalization:
    @pytest.fixture
    def engine(self):
        return M1IngestionEngine()

    def test_normalize_depth_valid_payload(self, engine):
        """Verify depth normalization with valid Binance depth payload."""
        payload = {
            'E': 1700000000000,
            'b': [  # bids (price, size)
                ['50000.0', '10.0'],
                ['49999.0', '5.0'],
                ['49998.0', '3.0'],
                ['49997.0', '2.0'],
                ['49996.0', '1.0']
            ],
            'a': [  # asks
                ['50001.0', '8.0'],
                ['50002.0', '4.0'],
                ['50003.0', '2.0'],
                ['50004.0', '1.0'],
                ['50005.0', '0.5']
            ]
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        assert result is not None
        assert result['symbol'] == 'BTCUSDT'
        assert result['timestamp'] == 1700000000.0
        assert result['bid_size'] == 21.0  # Sum of top 5: 10+5+3+2+1
        assert result['ask_size'] == 15.5  # Sum of top 5: 8+4+2+1+0.5
        assert result['best_bid_price'] == 50000.0
        assert result['best_ask_price'] == 50001.0
        assert result['bid_levels'] == 5
        assert result['ask_levels'] == 5

    def test_normalize_depth_top_5_levels_only(self, engine):
        """Verify only top 5 levels are aggregated."""
        payload = {
            'E': 1700000000000,
            'b': [
                ['50000.0', '10.0'],
                ['49999.0', '10.0'],
                ['49998.0', '10.0'],
                ['49997.0', '10.0'],
                ['49996.0', '10.0'],
                ['49995.0', '10.0'],  # 6th level (should be ignored)
                ['49994.0', '10.0'],  # 7th level (should be ignored)
            ],
            'a': [
                ['50001.0', '5.0'],
                ['50002.0', '5.0'],
                ['50003.0', '5.0'],
                ['50004.0', '5.0'],
                ['50005.0', '5.0'],
                ['50006.0', '5.0'],  # 6th level (should be ignored)
            ]
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        # Should only sum first 5 levels
        assert result['bid_size'] == 50.0  # 10 * 5
        assert result['ask_size'] == 25.0  # 5 * 5

    def test_normalize_depth_updates_latest_depth(self, engine):
        """Verify depth updates latest_depth for symbol."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        engine.normalize_depth('BTCUSDT', payload)

        assert 'BTCUSDT' in engine.latest_depth
        assert engine.latest_depth['BTCUSDT']['bid_size'] == 10.0
        assert engine.latest_depth['BTCUSDT']['ask_size'] == 8.0

    def test_normalize_depth_preserves_previous_depth(self, engine):
        """Verify previous depth is preserved before updating latest."""
        payload1 = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }
        payload2 = {
            'E': 1700000001000,
            'b': [['50000.0', '15.0']],  # Size changed
            'a': [['50001.0', '12.0']]
        }

        engine.normalize_depth('BTCUSDT', payload1)
        assert 'BTCUSDT' not in engine.previous_depth  # First update, no previous

        engine.normalize_depth('BTCUSDT', payload2)

        # Previous should have first depth
        assert 'BTCUSDT' in engine.previous_depth
        assert engine.previous_depth['BTCUSDT']['bid_size'] == 10.0
        assert engine.previous_depth['BTCUSDT']['ask_size'] == 8.0

        # Latest should have second depth
        assert engine.latest_depth['BTCUSDT']['bid_size'] == 15.0
        assert engine.latest_depth['BTCUSDT']['ask_size'] == 12.0

    def test_normalize_depth_empty_bids(self, engine):
        """Verify empty bids list is handled (no bid liquidity)."""
        payload = {
            'E': 1700000000000,
            'b': [],  # No bids
            'a': [['50001.0', '8.0']]
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        assert result is not None
        assert result['bid_size'] == 0.0
        assert result['best_bid_price'] is None
        assert result['ask_size'] == 8.0
        assert result['best_ask_price'] == 50001.0

    def test_normalize_depth_empty_asks(self, engine):
        """Verify empty asks list is handled (no ask liquidity)."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': []  # No asks
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        assert result is not None
        assert result['bid_size'] == 10.0
        assert result['best_bid_price'] == 50000.0
        assert result['ask_size'] == 0.0
        assert result['best_ask_price'] is None

    def test_normalize_depth_appends_to_buffer(self, engine):
        """Verify depth appended to raw_depth buffer."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        engine.normalize_depth('BTCUSDT', payload)

        assert len(engine.raw_depth['BTCUSDT']) == 1
        assert engine.raw_depth['BTCUSDT'][0]['bid_size'] == 10.0

    def test_normalize_depth_increments_counter(self, engine):
        """Verify depth counter increments on success."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        assert engine.counters['depth'] == 0
        engine.normalize_depth('BTCUSDT', payload)
        assert engine.counters['depth'] == 1

    def test_normalize_depth_error_handling(self, engine):
        """Verify malformed payload increments error counter."""
        payload = {
            'E': 1700000000000,
            'b': [['invalid', 'invalid']],  # Invalid data
            'a': [['50001.0', '8.0']]
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        assert result is None
        assert engine.counters['errors'] == 1
        assert engine.counters['depth'] == 0

    def test_normalize_depth_missing_E_field(self, engine):
        """Verify missing timestamp defaults to 0."""
        payload = {
            # 'E' missing
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        assert result is not None
        assert result['timestamp'] == 0.0

    def test_normalize_depth_multiple_symbols_isolated(self, engine):
        """Verify depth for different symbols are isolated."""
        payload_btc = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }
        payload_eth = {
            'E': 1700000001000,
            'b': [['3000.0', '20.0']],
            'a': [['3001.0', '15.0']]
        }

        engine.normalize_depth('BTCUSDT', payload_btc)
        engine.normalize_depth('ETHUSDT', payload_eth)

        assert engine.latest_depth['BTCUSDT']['bid_size'] == 10.0
        assert engine.latest_depth['ETHUSDT']['bid_size'] == 20.0

    def test_normalize_depth_single_level(self, engine):
        """Verify single bid/ask level is handled."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],  # Only 1 level
            'a': [['50001.0', '8.0']]   # Only 1 level
        }

        result = engine.normalize_depth('BTCUSDT', payload)

        assert result is not None
        assert result['bid_size'] == 10.0
        assert result['ask_size'] == 8.0
        assert result['bid_levels'] == 1
        assert result['ask_levels'] == 1


# ============================================================================
# TEST SUITE 4: State Management
# ============================================================================

class TestM1StateManagement:
    @pytest.fixture
    def engine(self):
        return M1IngestionEngine()

    def test_latest_depth_per_symbol_isolation(self, engine):
        """Verify latest_depth maintains per-symbol isolation."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        engine.normalize_depth('BTCUSDT', payload)
        engine.normalize_depth('ETHUSDT', payload)

        assert 'BTCUSDT' in engine.latest_depth
        assert 'ETHUSDT' in engine.latest_depth
        assert engine.latest_depth['BTCUSDT'] != engine.latest_depth['ETHUSDT']

    def test_previous_depth_sliding_window(self, engine):
        """Verify previous_depth implements sliding window (last 2 updates)."""
        payloads = [
            {'E': 1700000000000 + i * 1000, 'b': [[f'{50000 + i}.0', '10.0']], 'a': [['50001.0', '8.0']]}
            for i in range(3)
        ]

        engine.normalize_depth('BTCUSDT', payloads[0])
        assert 'BTCUSDT' not in engine.previous_depth  # No previous on first

        engine.normalize_depth('BTCUSDT', payloads[1])
        assert engine.previous_depth['BTCUSDT']['best_bid_price'] == 50000.0

        engine.normalize_depth('BTCUSDT', payloads[2])
        assert engine.previous_depth['BTCUSDT']['best_bid_price'] == 50001.0  # payloads[1] is now previous

    def test_recent_prices_per_symbol_isolation(self, engine):
        """Verify recent_prices maintains per-symbol deques."""
        payload_btc = {'p': '50000.0', 'q': '1.0', 'T': 1700000000000, 'm': False}
        payload_eth = {'p': '3000.0', 'q': '5.0', 'T': 1700000001000, 'm': True}

        engine.normalize_trade('BTCUSDT', payload_btc)
        engine.normalize_trade('ETHUSDT', payload_eth)

        assert len(engine.recent_prices['BTCUSDT']) == 1
        assert len(engine.recent_prices['ETHUSDT']) == 1
        _, btc_price = engine.recent_prices['BTCUSDT'][0]
        _, eth_price = engine.recent_prices['ETHUSDT'][0]
        assert btc_price == 50000.0
        assert eth_price == 3000.0

    def test_recent_prices_maxlen_enforcement(self, engine):
        """Verify recent_prices deque maxlen=10 (circular buffer)."""
        for i in range(15):
            payload = {'p': f'{50000 + i}.0', 'q': '1.0', 'T': 1700000000000 + i * 1000, 'm': False}
            engine.normalize_trade('BTCUSDT', payload)

        assert len(engine.recent_prices['BTCUSDT']) == 10
        # Oldest should be from iteration 5
        _, first_price = engine.recent_prices['BTCUSDT'][0]
        assert first_price == 50005.0

    def test_recent_prices_tuple_format(self, engine):
        """Verify recent_prices stores (timestamp, price) tuples."""
        payload = {'p': '50000.0', 'q': '1.0', 'T': 1700000000000, 'm': False}
        engine.normalize_trade('BTCUSDT', payload)

        ts, price = engine.recent_prices['BTCUSDT'][0]
        assert isinstance(ts, float)
        assert isinstance(price, float)
        assert ts == 1700000000.0
        assert price == 50000.0


# ============================================================================
# TEST SUITE 5: Buffer Management
# ============================================================================

class TestM1BufferManagement:
    @pytest.fixture
    def engine(self):
        return M1IngestionEngine()

    def test_trade_buffer_circular_overflow(self, engine):
        """Verify trade buffer respects maxlen=500 (circular buffer)."""
        # Default maxlen=500
        for i in range(600):
            payload = {'p': '50000.0', 'q': '1.0', 'T': 1700000000000 + i * 1000, 'm': False}
            engine.normalize_trade('BTCUSDT', payload)

        assert len(engine.raw_trades['BTCUSDT']) == 500
        # First trade should be from iteration 100
        assert engine.raw_trades['BTCUSDT'][0]['timestamp'] == 1700000100.0

    def test_liquidation_buffer_circular_overflow(self, engine):
        """Verify liquidation buffer respects maxlen=200."""
        # Default maxlen=200
        for i in range(250):
            payload = {
                'E': 1700000000000 + i * 1000,
                'o': {'p': '50000.0', 'q': '10.0', 'S': 'SELL'}
            }
            engine.normalize_liquidation('BTCUSDT', payload)

        assert len(engine.raw_liquidations['BTCUSDT']) == 200

    def test_depth_buffer_circular_overflow(self, engine):
        """Verify depth buffer respects maxlen=100."""
        # Default maxlen=100
        for i in range(150):
            payload = {
                'E': 1700000000000 + i * 1000,
                'b': [['50000.0', '10.0']],
                'a': [['50001.0', '8.0']]
            }
            engine.normalize_depth('BTCUSDT', payload)

        assert len(engine.raw_depth['BTCUSDT']) == 100

    def test_get_buffers_returns_copy(self, engine):
        """Verify get_buffers() returns copy, not reference."""
        payload_trade = {'p': '50000.0', 'q': '1.0', 'T': 1700000000000, 'm': False}
        engine.normalize_trade('BTCUSDT', payload_trade)

        buffers = engine.get_buffers()

        # Modify returned buffers
        buffers['trades']['BTCUSDT'].append({'test': 'data'})

        # Original should be unchanged
        assert len(engine.raw_trades['BTCUSDT']) == 1
        assert 'test' not in engine.raw_trades['BTCUSDT'][0]

    def test_get_buffers_list_conversion(self, engine):
        """Verify get_buffers() converts deque to list."""
        payload = {'p': '50000.0', 'q': '1.0', 'T': 1700000000000, 'm': False}
        engine.normalize_trade('BTCUSDT', payload)

        buffers = engine.get_buffers()

        assert isinstance(buffers['trades']['BTCUSDT'], list)
        assert not isinstance(buffers['trades']['BTCUSDT'], deque)


# ============================================================================
# TEST SUITE 6: Counter Tracking
# ============================================================================

class TestM1CounterTracking:
    @pytest.fixture
    def engine(self):
        return M1IngestionEngine()

    def test_counter_initialization(self, engine):
        """Verify all counters initialize to zero."""
        assert engine.counters['trades'] == 0
        assert engine.counters['liquidations'] == 0
        assert engine.counters['klines'] == 0
        assert engine.counters['oi'] == 0
        assert engine.counters['depth'] == 0
        assert engine.counters['errors'] == 0

    def test_trades_counter_increments(self, engine):
        """Verify trades counter increments correctly."""
        payload = {'p': '50000.0', 'q': '1.0', 'T': 1700000000000, 'm': False}

        for i in range(5):
            engine.normalize_trade('BTCUSDT', payload)

        assert engine.counters['trades'] == 5

    def test_liquidations_counter_increments(self, engine):
        """Verify liquidations counter increments correctly."""
        payload = {
            'E': 1700000000000,
            'o': {'p': '50000.0', 'q': '10.0', 'S': 'SELL'}
        }

        for i in range(3):
            engine.normalize_liquidation('BTCUSDT', payload)

        assert engine.counters['liquidations'] == 3

    def test_depth_counter_increments(self, engine):
        """Verify depth counter increments correctly."""
        payload = {
            'E': 1700000000000,
            'b': [['50000.0', '10.0']],
            'a': [['50001.0', '8.0']]
        }

        for i in range(4):
            engine.normalize_depth('BTCUSDT', payload)

        assert engine.counters['depth'] == 4

    def test_errors_counter_increments(self, engine):
        """Verify errors counter increments on failures."""
        invalid_trade = {'p': 'invalid', 'q': '1.0', 'T': 1700000000000, 'm': False}
        invalid_liq = {'E': 1700000000000, 'o': {'p': 'invalid', 'q': '10.0', 'S': 'SELL'}}

        engine.normalize_trade('BTCUSDT', invalid_trade)
        engine.normalize_liquidation('BTCUSDT', invalid_liq)

        assert engine.counters['errors'] == 2

    def test_record_kline(self, engine):
        """Verify record_kline() increments klines counter."""
        assert engine.counters['klines'] == 0
        engine.record_kline('BTCUSDT')
        assert engine.counters['klines'] == 1

    def test_record_oi(self, engine):
        """Verify record_oi() increments oi counter."""
        assert engine.counters['oi'] == 0
        engine.record_oi('BTCUSDT')
        assert engine.counters['oi'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

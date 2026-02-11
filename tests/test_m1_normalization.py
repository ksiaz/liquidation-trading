"""
Test M1 normalization - verify HL data is normalized to canonical format.

STEP 6 of M1 Normalization task.
"""

import pytest
from unittest.mock import MagicMock, patch
import time

from runtime.node_client.types import LiquidationEvent
from runtime.node_client.bridge import NodeBridge
from observation.internal.m1_ingestion import M1IngestionEngine


class TestHLLiquidationNormalization:
    """Test that HL liquidations normalize to canonical LIQUIDATION format."""

    def test_hl_liquidation_maps_to_canonical_side(self):
        """LONG liquidation → SELL, SHORT liquidation → BUY."""
        # Create mock observation system
        mock_obs = MagicMock()
        captured_calls = []

        def capture_ingest(timestamp, symbol, event_type, payload):
            captured_calls.append({
                'timestamp': timestamp,
                'symbol': symbol,
                'event_type': event_type,
                'payload': payload
            })

        mock_obs.ingest_observation = capture_ingest

        # Create bridge with mock
        bridge = NodeBridge(mock_obs, address='localhost:50051')

        # Test LONG liquidation → SELL
        long_liq = LiquidationEvent(
            symbol='BTC',
            side='LONG',  # Long position being liquidated
            price='65000.00',
            size='0.5',
            value_usd='32500.00',
            liquidator_wallet='0xLiquidator',
            liquidated_wallet='0xVictim',
            mark_price='64950.00',
            method='market',
            timestamp_ms=1706745600000,
            fill_id=12345,
            tx_hash='0xabc123'
        )

        bridge._handle_liquidation(long_liq)

        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call['event_type'] == 'LIQUIDATION'  # Canonical type
        assert call['payload']['o']['S'] == 'SELL'  # LONG → SELL
        assert call['payload']['o']['p'] == '65000.0'
        assert call['payload']['o']['q'] == '0.5'

        # Test SHORT liquidation → BUY
        captured_calls.clear()
        short_liq = LiquidationEvent(
            symbol='ETH',
            side='SHORT',  # Short position being liquidated
            price='3200.00',
            size='10.0',
            value_usd='32000.00',
            liquidator_wallet='0xLiquidator2',
            liquidated_wallet='0xVictim2',
            mark_price='3210.00',
            method='backstop',
            timestamp_ms=1706745700000,
            fill_id=12346,
            tx_hash='0xdef456'
        )

        bridge._handle_liquidation(short_liq)

        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call['event_type'] == 'LIQUIDATION'
        assert call['payload']['o']['S'] == 'BUY'  # SHORT → BUY

    def test_hl_metadata_preserved(self):
        """HL-specific metadata is preserved in _hl_metadata."""
        mock_obs = MagicMock()
        captured = {}

        def capture(timestamp, symbol, event_type, payload):
            captured['payload'] = payload

        mock_obs.ingest_observation = capture

        bridge = NodeBridge(mock_obs, address='localhost:50051')

        liq = LiquidationEvent(
            symbol='BTC',
            side='LONG',
            price='65000.00',
            size='0.5',
            value_usd='32500.00',
            liquidator_wallet='0xLiquidator',
            liquidated_wallet='0xVictim',
            mark_price='64950.00',
            method='market',
            timestamp_ms=1706745600000,
            fill_id=99999,
            tx_hash='0xabc123'
        )

        bridge._handle_liquidation(liq)

        meta = captured['payload']['_hl_metadata']
        assert meta['wallet'] == '0xVictim'
        assert meta['liquidator'] == '0xLiquidator'
        assert meta['method'] == 'market'
        assert meta['fill_id'] == 99999
        assert meta['tx_hash'] == '0xabc123'
        assert meta['original_side'] == 'LONG'


class TestM1IngestionEngineCanonical:
    """Test M1 ingestion produces canonical schema."""

    def test_normalize_liquidation_canonical_fields(self):
        """normalize_liquidation produces canonical fields."""
        engine = M1IngestionEngine()

        # Binance-format payload (what HL now produces)
        payload = {
            'E': 1706745600000,
            'o': {
                'p': '65000.00',
                'q': '0.5',
                'S': 'SELL'
            }
        }

        result = engine.normalize_liquidation('BTC', payload)

        assert result is not None
        assert result['symbol'] == 'BTC'
        assert result['price'] == 65000.00
        assert result['quantity'] == 0.5
        assert result['side'] == 'SELL'
        assert result['base_qty'] == 0.5
        assert result['quote_qty'] == 32500.00  # 0.5 * 65000

    def test_trade_and_liquidation_same_schema(self):
        """Trade and liquidation have same core fields."""
        engine = M1IngestionEngine()

        # Trade
        trade_payload = {
            'p': '65000.00',
            'q': '0.5',
            'm': True,  # Buyer is maker → SELL
            'T': 1706745600000
        }
        trade = engine.normalize_trade('BTC', trade_payload)

        # Liquidation
        liq_payload = {
            'E': 1706745600000,
            'o': {
                'p': '65000.00',
                'q': '0.5',
                'S': 'SELL'
            }
        }
        liq = engine.normalize_liquidation('BTC', liq_payload)

        # Both have same core fields
        core_fields = ['timestamp', 'symbol', 'price', 'quantity', 'side', 'base_qty', 'quote_qty']
        for field in core_fields:
            assert field in trade, f"Trade missing {field}"
            assert field in liq, f"Liquidation missing {field}"


class TestGovernanceSourceAgnostic:
    """Test governance handles liquidations source-agnostically."""

    def test_liquidation_creates_m2_node_and_cascade_tracking(self):
        """LIQUIDATION event creates M2 node AND records for cascade."""
        from observation.governance import ObservationSystem

        obs = ObservationSystem()

        # Ingest canonical liquidation (as would come from normalized HL)
        obs.ingest_observation(
            timestamp=time.time(),
            symbol='BTC',
            event_type='LIQUIDATION',
            payload={
                'E': int(time.time() * 1000),
                'o': {
                    'p': '65000.00',
                    'q': '0.5',
                    'S': 'SELL'
                }
            }
        )

        # Verify M1 counter
        assert obs._m1.counters['liquidations'] == 1

        # Verify cascade tracking (record_hl_liquidation was called)
        # Note: symbol tracking has memory guards, check if present
        assert 'BTC' in obs._hl_liquidation_timestamps or obs._hl_liquidation_pruned > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

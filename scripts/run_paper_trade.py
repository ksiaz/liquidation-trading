#!/usr/bin/env python3
"""
Paper Trading Mode with Node Integration.

Runs the full system with:
- Node adapter for real-time liquidation data (USE_HL_NODE=true)
- Cascade Sniper strategy enabled
- Paper trade mode (no real orders, logged to paper_trades.db)

Usage:
    python scripts/run_paper_trade.py

View results:
    sqlite3 paper_trades.db "SELECT * FROM paper_trades ORDER BY entry_time DESC LIMIT 20"
"""

import os
import sys
import asyncio
import logging
import signal

# Enable node mode
os.environ['USE_HL_NODE'] = 'true'
os.environ['ENABLE_DIAG'] = 'false'  # Reduce noise

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('paper_trade.log')
    ]
)

# Reduce noise from some loggers
logging.getLogger('runtime.hyperliquid.node_adapter.observation_bridge').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

logger = logging.getLogger('PaperTrade')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService


# Symbols to trade
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'HYPEUSDT',
    'DOGEUSDT', 'XRPUSDT', 'BNBUSDT'
]


async def run_paper_trade():
    """Run paper trading session."""
    logger.info('=' * 60)
    logger.info('PAPER TRADE MODE')
    logger.info('=' * 60)
    logger.info(f'Symbols: {SYMBOLS}')
    logger.info('Node mode: USE_HL_NODE=true')
    logger.info('Dry run: True (no real orders)')
    logger.info('=' * 60)

    # Create observation system
    logger.info('Creating ObservationSystem...')
    obs = ObservationSystem(allowed_symbols=SYMBOLS)

    # Create collector service (will use node mode due to env var)
    logger.info('Creating CollectorService...')
    service = CollectorService(obs, warmup_duration_sec=10)

    logger.info(f'Node mode active: {service._use_node_mode}')
    logger.info(f'HL enabled: {service._hyperliquid_enabled}')

    if service._use_node_mode and service._node_psm:
        logger.info('Position tracking enabled')

    # Graceful shutdown handler
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info('Shutdown requested...')
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start service
    logger.info('Starting service...')
    service_task = asyncio.create_task(service.start())

    # Monitor loop
    try:
        while not shutdown_event.is_set():
            await asyncio.sleep(60)  # Status update every minute

            # Log status
            if service._node_bridge:
                metrics = service._node_bridge.get_metrics()
                logger.info(
                    f'Status: prices={metrics["prices_forwarded"]}, '
                    f'liqs={metrics["liquidations_forwarded"]}, '
                    f'alerts={metrics["proximity_alerts"]}'
                )

            if service._node_psm:
                logger.info(
                    f'Positions: {service._node_psm.metrics.positions_cached}, '
                    f'Critical: {service._node_psm.metrics.critical_positions}'
                )

            # Log proximity data
            if obs._hl_collector:
                for coin in ['BTC', 'ETH', 'HYPE']:
                    prox = obs._hl_collector.get_proximity(coin)
                    if prox and prox.total_positions_at_risk > 0:
                        logger.info(
                            f'{coin}: {prox.total_positions_at_risk} at risk, '
                            f'${prox.total_value_at_risk:,.0f}'
                        )

    except asyncio.CancelledError:
        pass
    finally:
        # Cleanup
        logger.info('Stopping...')
        service._running = False

        if service._node_integration:
            await service._node_integration.stop()
        if service._node_psm:
            await service._node_psm.stop()

        service_task.cancel()
        try:
            await service_task
        except asyncio.CancelledError:
            pass

    logger.info('Paper trade session ended.')


if __name__ == '__main__':
    try:
        asyncio.run(run_paper_trade())
    except KeyboardInterrupt:
        pass

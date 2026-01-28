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

# Add project root to path early
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService
from runtime.monitoring import ResourceMonitor, HealthStatus, CleanupCoordinator


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

    # Create resource monitor
    logger.info('Creating ResourceMonitor...')
    monitor = ResourceMonitor(
        warn_pct=70.0,
        critical_pct=85.0,
        log_interval_sec=60.0,
        enable_gc_on_warning=True,
    )

    # Critical callback - log and potentially take action
    def on_critical(report):
        logger.error(f"CRITICAL MEMORY: {report.memory.rss_mb:.0f}MB ({report.memory.percent:.1f}%)")
        logger.error(f"Available: {report.memory.available_mb:.0f}MB")
        for comp in report.components:
            logger.error(f"  {comp.name}: {comp.estimated_mb:.1f}MB ({comp.item_count} items)")

    monitor.set_critical_callback(on_critical)

    # Create observation system
    logger.info('Creating ObservationSystem...')
    obs = ObservationSystem(allowed_symbols=SYMBOLS)

    # Create collector service (will use node mode due to env var)
    logger.info('Creating CollectorService...')
    service = CollectorService(obs, warmup_duration_sec=10)

    # Register components with monitor
    monitor.register_component('collector_service', service)
    if service._node_bridge:
        monitor.register_component('observation_bridge', service._node_bridge)
    if service._node_psm:
        monitor.register_component('position_state_manager', service._node_psm)

    # Register cascade state machine if available
    sm = None
    try:
        from external_policy.ep2_strategy_cascade_sniper import _get_state_machine
        sm = _get_state_machine()
        monitor.register_component('cascade_state_machine', sm)
    except Exception as e:
        logger.debug(f"Could not register cascade state machine: {e}")

    # Create cleanup coordinator (Phase 2: Memory Guards)
    logger.info('Creating CleanupCoordinator...')
    cleanup = CleanupCoordinator(interval_sec=300.0)  # Every 5 minutes

    # Register pruners for each component
    if service._node_bridge:
        burst_agg = getattr(service._node_bridge, '_burst_aggregator', None)
        if burst_agg:
            cleanup.register_pruner('burst_aggregator', burst_agg.prune_stale)

    if service._node_psm:
        cleanup.register_pruner('position_manager_wallets', service._node_psm.prune_empty_wallets)
        cleanup.register_pruner('position_manager_prices', service._node_psm.prune_stale_prices)

    if sm and hasattr(sm, '_organic_detector') and sm._organic_detector:
        cleanup.register_pruner('organic_flow_detector', sm._organic_detector.prune_stale)

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

    # Start resource monitor
    logger.info('Starting resource monitor...')
    await monitor.start()

    # Start cleanup coordinator
    logger.info('Starting cleanup coordinator...')
    await cleanup.start()

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

        # Log final resource report
        final_report = monitor.get_report()
        logger.info(f"Final memory: {final_report.memory.rss_mb:.1f}MB ({final_report.memory.percent:.1f}%)")
        trend = monitor.get_trend()
        logger.info(f"Memory trend: {trend['growth_rate_mb_per_min']:.2f} MB/min over {trend['duration_min']:.1f} min")

        # Log cleanup stats
        cleanup_metrics = cleanup.get_metrics()
        logger.info(f"Cleanup: {cleanup_metrics['cycles_completed']} cycles, {cleanup_metrics['total_items_pruned']} items pruned")

        # Stop cleanup coordinator
        await cleanup.stop()

        # Stop monitor
        await monitor.stop()

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

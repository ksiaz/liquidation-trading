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
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

logger = logging.getLogger('PaperTrade')

from pathlib import Path
import time

from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService
from runtime.monitoring import ResourceMonitor, HealthStatus, CleanupCoordinator
from runtime.stability_observer import stability_observer
from trade_stream import BinanceTradeStream
from external_policy.ep2_strategy_cascade_sniper import record_organic_trade, record_liquidation_event
# UI server disabled pending node adapter redesign
# See docs/NODE_ADAPTER_REDESIGN.md


def cleanup_temp_databases(tmp_dir: str = None, max_age_days: int = 1) -> int:
    """Remove orphaned temp databases on startup.

    These accumulate from test runs with delete=False.

    Args:
        tmp_dir: Directory to clean (default: project tmp/)
        max_age_days: Delete files older than this many days

    Returns:
        Number of files deleted
    """
    if tmp_dir is None:
        # Default to project tmp directory
        project_root = Path(__file__).parent.parent
        tmp_dir = project_root / 'tmp'

    tmp_path = Path(tmp_dir)
    if not tmp_path.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0

    for db_file in tmp_path.glob('tmp*.db'):
        try:
            if db_file.stat().st_mtime < cutoff:
                db_file.unlink()
                deleted += 1
        except (OSError, PermissionError):
            pass

    # Also clean up any WAL/SHM files
    for wal_file in tmp_path.glob('tmp*.db-wal'):
        try:
            if wal_file.stat().st_mtime < cutoff:
                wal_file.unlink()
        except (OSError, PermissionError):
            pass

    for shm_file in tmp_path.glob('tmp*.db-shm'):
        try:
            if shm_file.stat().st_mtime < cutoff:
                shm_file.unlink()
        except (OSError, PermissionError):
            pass

    return deleted


# Symbols to trade - 15 highest volume coins (must exist in HL asset map)
# Include both Binance format (BTCUSDT) and HL format (BTC) for cross-exchange support
BINANCE_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT',
    'AVAXUSDT', 'LINKUSDT', 'HYPEUSDT', 'SUIUSDT', 'NEARUSDT',
    'LTCUSDT', 'ATOMUSDT', 'AAVEUSDT', 'APTUSDT', 'ARBUSDT',
]
HL_SYMBOLS = [s.replace('USDT', '') for s in BINANCE_SYMBOLS]
SYMBOLS = BINANCE_SYMBOLS + HL_SYMBOLS  # Both formats for observation whitelist


async def run_paper_trade():
    """Run paper trading session."""
    logger.info('=' * 60)
    logger.info('PAPER TRADE MODE')
    logger.info('=' * 60)
    logger.info(f'Symbols: {SYMBOLS}')
    logger.info('Node mode: USE_HL_NODE=true')
    logger.info('Dry run: True (no real orders)')
    logger.info('=' * 60)

    # Cleanup orphaned temp databases on startup
    deleted = cleanup_temp_databases()
    if deleted > 0:
        logger.info(f'Cleaned up {deleted} orphaned temp databases')

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

    # Wire HL node fills for organic flow detection
    # This feeds taker buy/sell data to the absorption detector via gRPC
    # Replaces BinanceTradeStream - now uses native HL fill data
    trade_stream = None  # Only used if node bridge unavailable
    if service._node_bridge:
        def on_hl_fill(symbol: str, side: str, price: float, size: float, timestamp: float):
            """Feed organic fills from HL node to the cascade sniper's absorption detector."""
            # HL symbols don't have USDT suffix - add it for consistency
            normalized_symbol = f"{symbol}USDT" if not symbol.endswith('USDT') else symbol
            # Calculate value from price * size
            value = price * size
            # Map side: "B" -> "BUY", "A" -> "SELL"
            order_side = "BUY" if side == "B" else "SELL"
            record_organic_trade(
                symbol=normalized_symbol,
                side=order_side,
                value=value,
                timestamp=timestamp
            )

        service._node_bridge.on_organic_fill(on_hl_fill)
        logger.info('Wired HL node fills to absorption detector (via gRPC adapter)')

        # Wire HL liquidations for cascade detector AND burst aggregator
        def on_hl_liquidation(symbol: str, side: str, price: float, size: float, timestamp: float):
            """Feed liquidations from HL node to the cascade sniper's detector."""
            # HL symbols don't have USDT suffix - add it for consistency
            normalized_symbol = f"{symbol}USDT" if not symbol.endswith('USDT') else symbol
            # Convert position side (LONG/SHORT) to order side (BUY/SELL)
            # LONG liquidation = forced SELL, SHORT liquidation = forced BUY
            order_side = "SELL" if side == "LONG" else "BUY"
            # Calculate value from price * size
            value = price * size

            # Feed to OrganicFlowDetector (for absorption ratio)
            record_liquidation_event(
                symbol=normalized_symbol,
                side=order_side,
                value=value,
                timestamp=timestamp
            )

            # Feed to burst aggregator (for cascade state machine triggering)
            # This is critical - without it, cascade states never transition
            # because the state machine uses liquidation_burst from the aggregator
            if hasattr(service, '_liquidation_burst_aggregator'):
                service._liquidation_burst_aggregator.add_event(
                    timestamp=timestamp,
                    symbol=normalized_symbol,
                    side=order_side,
                    price=price,
                    quantity=size
                )

        service._node_bridge.on_hl_liquidation(on_hl_liquidation)
        logger.info('Wired HL node liquidations to cascade detector AND burst aggregator')
    else:
        # Fallback to Binance trade stream if node bridge unavailable
        logger.warning('Node bridge not available, falling back to BinanceTradeStream')
        trade_stream = BinanceTradeStream(BINANCE_SYMBOLS)

        def on_organic_trade(symbol: str, trade: dict):
            """Feed organic trades to the cascade sniper's absorption detector."""
            value = trade['price'] * trade['quantity']
            record_organic_trade(
                symbol=symbol,
                side=trade['side'],
                value=value,
                timestamp=trade['timestamp']
            )

        trade_stream.add_callback(on_organic_trade)
        trade_stream.start()
        logger.info(f'Binance trade stream started for {len(BINANCE_SYMBOLS)} symbols')

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
        cleanup.register_pruner('organic_flow_detector', lambda: sm._organic_detector.cleanup(time.time()))

    # Register collector calculator pruning
    cleanup.register_pruner('collector_calculators', service.prune_stale_calculators)

    # Register governance liquidation tracking pruning
    cleanup.register_pruner('governance_liquidations', obs.prune_hl_liquidation_tracking)

    # Register M2 archived nodes pruning (prevents memory leak from old nodes)
    cleanup.register_pruner('m2_archived_nodes', obs._m2_store.prune_archived_nodes)

    # Register candidate zone decay and pruning (prevents memory leak from unbounded zones)
    # Note: Only available on ObservationBridge, not NodeBridge
    if service._node_bridge and hasattr(service._node_bridge, 'decay_candidate_zones'):
        cleanup.register_pruner('candidate_zone_decay', service._node_bridge.decay_candidate_zones)
        cleanup.register_pruner('candidate_zone_prune', service._node_bridge.prune_candidate_zones)

    # Register execution.db pruning (48h retention to prevent unbounded growth)
    # Run every cleanup cycle - the prune method is fast when little to prune
    if hasattr(service, '_execution_db') and hasattr(service._execution_db, '_db'):
        cleanup.register_pruner(
            'execution_db',
            lambda: service._execution_db._db.prune_old_data(max_age_hours=48).get('total_deleted', 0)
        )

    # Register HL node data cleanup (keeps 24h of data, cleans diagnostics)
    # Import here to avoid circular imports
    from scripts.cleanup_hl_data import cleanup_hl_data
    cleanup.register_pruner(
        'hl_node_data',
        lambda: cleanup_hl_data(
            data_dir='~/hl/data',
            keep_hours=24,
            keep_abci_states=5,
            dry_run=False,
            verbose=False
        ).get('total_files', 0)
    )

    logger.info(f'Node mode active: {service._use_node_mode}')
    logger.info(f'HL enabled: {service._hyperliquid_enabled}')

    if service._use_node_mode and service._node_psm:
        logger.info('Position tracking enabled')

    # UI server disabled pending node adapter redesign
    # See docs/NODE_ADAPTER_REDESIGN.md

    # Graceful shutdown handler
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info('Shutdown requested...')
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wire up cleanup coordinator with resource monitor for disk space warnings
    monitor.set_cleanup_coordinator(cleanup)

    # Start resource monitor
    logger.info('Starting resource monitor...')
    await monitor.start()

    # Start cleanup coordinator
    logger.info('Starting cleanup coordinator...')
    await cleanup.start()

    # Optional: Start observatory server
    observatory_server = None
    if os.environ.get('ENABLE_OBSERVATORY', 'false').lower() == 'true':
        try:
            import uvicorn
            from runtime.observatory import app, configure

            configure(stability_observer, monitor)

            config = uvicorn.Config(app, host='127.0.0.1', port=8080, log_level='warning')
            observatory_server = uvicorn.Server(config)
            asyncio.create_task(observatory_server.serve())
            logger.info('Observatory server started on http://127.0.0.1:8080')
        except ImportError as e:
            logger.warning(f'Could not start observatory server: {e}')
        except Exception as e:
            logger.warning(f'Observatory server failed to start: {e}')

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
                hl_prices = service._obs.get_all_hl_prices()
                logger.info(
                    f'Status: prices={metrics["prices_ingested"]}, '
                    f'liqs={metrics["liquidations_ingested"]}→{metrics.get("liquidations_forwarded", 0)}, '
                    f'fills={metrics["fills_ingested"]}→{metrics.get("organic_fills_forwarded", 0)}, '
                    f'errors={metrics["errors"]}, symbols={len(hl_prices)}'
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

            # Log trade stream stats (WebSocket mode only)
            if trade_stream:
                ts_stats = trade_stream.get_stats()
                logger.info(f'Trade stream: {ts_stats["trades_received"]} trades received')

            if sm and sm._organic_detector:
                for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                    metrics = sm._organic_detector.get_metrics(symbol)
                    if metrics and (metrics['buying_volume'] > 0 or metrics['liq_selling_volume'] > 0):
                        logger.info(
                            f'{symbol} flow: buy=${metrics["buying_volume"]:,.0f}, '
                            f'liq=${metrics["liq_selling_volume"]:,.0f}, '
                            f'ratio={metrics["buying_ratio"]:.1%}, '
                            f'absorbing={metrics["is_absorbing"]}'
                        )

    except asyncio.CancelledError:
        pass
    finally:
        # Cleanup
        logger.info('Stopping...')
        service._running = False
        if trade_stream:
            trade_stream.stop()
            logger.info('Trade stream stopped')
        elif service._node_bridge:
            logger.info('HL node bridge will be stopped with service')

        # Phase E: Log stability observer summary
        stability_summary = stability_observer.summary()
        logger.info(f"Stability status: {stability_summary['status']}")
        logger.info(f"Total mandates: {stability_summary['total_mandates']}, actions: {stability_summary['total_actions']}")
        if stability_summary['issues_total'] > 0:
            logger.warning(f"Stability issues detected: {stability_summary['issues_total']}")
            for issue in stability_observer.get_recent_issues(5):
                logger.warning(f"  {issue['issue']}: {issue['symbol']} ({issue['severity']})")

        # Log final resource report
        final_report = monitor.get_report()
        logger.info(f"Final memory: {final_report.memory.rss_mb:.1f}MB ({final_report.memory.percent:.1f}%)")
        trend = monitor.get_trend()
        duration = trend.get('duration_min', 0.0)
        logger.info(f"Memory trend: {trend['growth_rate_mb_per_min']:.2f} MB/min over {duration:.1f} min")

        # Log cleanup stats
        cleanup_metrics = cleanup.get_metrics()
        logger.info(f"Cleanup: {cleanup_metrics['cycles_completed']} cycles, {cleanup_metrics['total_items_pruned']} items pruned")

        # Stop observatory server
        if observatory_server:
            observatory_server.should_exit = True
            logger.info('Observatory server stopped')

        # Stop cleanup coordinator
        await cleanup.stop()

        # Stop monitor
        await monitor.stop()

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

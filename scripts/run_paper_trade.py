#!/usr/bin/env python3
"""
Paper Trading Mode with Binance Futures Data.

Runs the full system with:
- Binance Futures WebSocket data (fills, liquidations, orderbook, prices)
- Cascade Sniper strategy enabled
- Paper trade mode (no real orders, logged to PostgreSQL)

Usage:
    python scripts/run_paper_trade.py

View results:
    psql -U liqtrade -d liquidation_trading -c "SELECT * FROM paper_trades ORDER BY entry_time DESC LIMIT 20"
"""

import os
import sys
import asyncio
import logging
import logging.handlers
import signal

os.environ['ENABLE_DIAG'] = 'false'  # Reduce noise

# Add project root to path early
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging — RotatingFileHandler caps disk usage at ~60MB (3 × 20MB)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            'paper_trade.log',
            maxBytes=20 * 1024 * 1024,  # 20MB per file
            backupCount=3,               # Keep 3 rotated copies
        ),
    ]
)

# Reduce noise from some loggers
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

logger = logging.getLogger('PaperTrade')

from pathlib import Path
import time

# Initialize PostgreSQL connection pool BEFORE anything imports DB modules
from runtime.logging.pg_pool import init_pool, get_conn, put_conn, close_pool
from runtime.logging.pg_schema import ensure_schema

init_pool()
_schema_conn = get_conn()
ensure_schema(_schema_conn)
put_conn(_schema_conn)
print("[PG] Schema initialized", flush=True)

from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService
from runtime.monitoring import ResourceMonitor, HealthStatus, CleanupCoordinator
from runtime.stability_observer import stability_observer
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


def prune_stale_log_files(max_age_hours: int = 72) -> int:
    """Remove stale log files older than max_age_hours.

    Cleans up:
    - Rotated paper_trade.log.N backups
    - One-off test/debug logs (dry_run_*, test_*, *_test.log, *_output.log)
    - Old logs in logs/ directory
    - node.log truncation (keep last 50k lines ≈ 72h at normal rate)

    Returns:
        Number of files deleted
    """
    project_root = Path(__file__).parent.parent
    cutoff = time.time() - (max_age_hours * 3600)
    deleted = 0

    # 1. Delete stale one-off log files in project root
    stale_patterns = [
        'dry_run_*.log', 'test_*.log', '*_test.log', '*_output.log',
        'final_*.log', 'warmup_*.log', 'detailed_*.log', 'direct_*.log',
        'console_*.log', 'error_capture_*.log', 'full_debug_*.log',
        'reduced_*.log', 'dev_mode_*.log', 'monitor.log', 'adapter.log',
        'mcp_debug.log', 'THREAD_ERRORS.log',
    ]
    for pattern in stale_patterns:
        for log_file in project_root.glob(pattern):
            try:
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
                    deleted += 1
            except (OSError, PermissionError):
                pass

    # 2. Delete stale logs in logs/ subdirectory
    logs_dir = project_root / 'logs'
    if logs_dir.exists():
        for log_file in logs_dir.glob('*.log'):
            try:
                # Keep paper_trade.log (active), delete old ones
                if log_file.name == 'paper_trade.log':
                    continue
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
                    deleted += 1
            except (OSError, PermissionError):
                pass

    # 3. Delete stale THREAD_ERRORS.log in subdirectories
    for log_file in project_root.rglob('THREAD_ERRORS.log'):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                deleted += 1
        except (OSError, PermissionError):
            pass

    # 4. Truncate node.log if it exceeds 50k lines (~72h of normal output)
    node_log = Path.home() / 'hl' / 'node.log'
    if node_log.exists():
        try:
            line_count = sum(1 for _ in node_log.open('r', errors='replace'))
            if line_count > 50_000:
                # Keep last 50k lines
                lines = node_log.read_text(errors='replace').splitlines()
                node_log.write_text('\n'.join(lines[-50_000:]) + '\n')
                logger.info(f'Truncated node.log from {line_count} to 50000 lines')
        except (OSError, PermissionError):
            pass

    return deleted


# Symbols to trade — top 20 Binance Futures by sustained volume
# Must match TOP_10_SYMBOLS in runtime/collector/service.py
BINANCE_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT',
    'BNBUSDT', 'TRUMPUSDT', 'TAOUSDT', 'SUIUSDT', 'ADAUSDT',
    'LINKUSDT', 'AVAXUSDT', 'PEPEUSDT', 'LTCUSDT', 'DOTUSDT',
    'APTUSDT', 'NEARUSDT', 'AAVEUSDT', 'HYPEUSDT', 'ZECUSDT',
]
SYMBOLS = BINANCE_SYMBOLS


async def run_paper_trade():
    """Run paper trading session."""
    logger.info('=' * 60)
    logger.info('PAPER TRADE MODE')
    logger.info('=' * 60)
    logger.info(f'Symbols: {SYMBOLS}')
    logger.info('Data source: Binance Futures WebSocket')
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

    # Register cascade state machine if available
    sm = None
    try:
        from external_policy.ep2_strategy_cascade_sniper import _get_state_machine
        sm = _get_state_machine()
        monitor.register_component('cascade_state_machine', sm)
    except Exception as e:
        logger.debug(f"Could not register cascade state machine: {e}")

    # Fills + liquidations wired via BinanceDataProvider → CollectorService._handle_hl_fill/liquidation
    logger.info('Binance fills + liquidations wired via CollectorService callbacks')

    # Create cleanup coordinator (Phase 2: Memory Guards)
    logger.info('Creating CleanupCoordinator...')
    cleanup = CleanupCoordinator(interval_sec=300.0)  # Every 5 minutes

    # Register pruners for each component
    if sm and hasattr(sm, '_organic_detector') and sm._organic_detector:
        cleanup.register_pruner('organic_flow_detector', lambda: sm._organic_detector.cleanup(time.time()))

    # Register capitulation tracker pruning
    if hasattr(service, '_capitulation_tracker'):
        cleanup.register_pruner('capitulation_tracker', lambda: service._capitulation_tracker.cleanup(time.time()))

    # Register collector calculator pruning
    cleanup.register_pruner('collector_calculators', service.prune_stale_calculators)

    # Register governance liquidation tracking pruning
    cleanup.register_pruner('governance_liquidations', obs.prune_hl_liquidation_tracking)

    # Register M2 archived nodes pruning (prevents memory leak from old nodes)
    cleanup.register_pruner('m2_archived_nodes', obs._m2_store.prune_archived_nodes)

    # Register execution.db pruning (48h retention to prevent unbounded growth)
    # MUST use prune_safe() to go through BRD's lock. Direct _db access
    # bypasses the lock and corrupts transaction state, losing ghost trades.
    if hasattr(service, '_execution_db') and hasattr(service._execution_db, 'prune_safe'):
        cleanup.register_pruner(
            'execution_db',
            lambda: service._execution_db.prune_safe(max_age_hours=48)
        )

    # Register log file pruning (72h retention for stale logs, node.log truncation)
    cleanup.register_pruner('log_files', lambda: prune_stale_log_files(max_age_hours=72))

    logger.info(f'Data source: Binance Futures WS')
    logger.info(f'Symbols: {len(SYMBOLS)}')

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

            # Log Binance data provider stats
            if hasattr(service, '_binance_provider'):
                bp = service._binance_provider
                logger.info(
                    f'Status: fills={bp.fills_received}, '
                    f'liqs={bp.liqs_received}, '
                    f'depth={bp.depth_received}, '
                    f'prices={bp.prices_received}'
                )

            # Data freshness breaker status
            if hasattr(service, '_data_breaker') and service._data_breaker and service._data_breaker.is_open:
                logger.warning(f'DATA BREAKER OPEN: {service._data_breaker._trip_reason} — entries blocked')

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

        # Flush BRD buffer FIRST — prevents exit row loss on graceful shutdown.
        # kill -9 still loses buffer (handled by _backfill_missing_exits on restart).
        if hasattr(service, '_execution_db'):
            try:
                service._execution_db.flush()
                logger.info('Flushed execution.db buffer')
            except Exception as e:
                logger.warning(f'Failed to flush execution.db: {e}')

        # Stop Binance data provider
        if hasattr(service, '_binance_provider'):
            import asyncio as _asyncio
            try:
                _asyncio.get_event_loop().run_until_complete(service._binance_provider.stop())
            except Exception:
                pass
            logger.info('Binance data provider stopped')

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

    # Close PostgreSQL connection pool
    close_pool()
    logger.info('Paper trade session ended.')


if __name__ == '__main__':
    try:
        asyncio.run(run_paper_trade())
    except KeyboardInterrupt:
        pass

"""
Observatory Server - Read-Only FastAPI Backend.

CONSTITUTIONAL CONSTRAINT: GET methods only. No POST/PUT/DELETE.

This server provides read-only observation of the liquidation trading
system state. It cannot influence execution in any way.
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from .repository import ObservatoryRepository
from .schemas import (
    ExecutionCycleResponse, MandateResponse, ArbitrationRoundResponse,
    ZoneResponse, LiquidationResponse, PositionResponse, CascadeEventResponse,
    StabilityResponse, HealthResponse, ObservatorySnapshot,
    MandateCountsResponse, TableCountsResponse, StabilityStatusEnum,
    ErrorResponse, GhostTradeResponse, GhostSummaryResponse
)

logger = logging.getLogger(__name__)

# =========================================
# Application Setup
# =========================================

app = FastAPI(
    title="Liquidation Trading Observatory",
    description="Read-only observation of system state. No execution influence.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS - GET only (constitutional constraint)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET"],  # GET ONLY - constitutional constraint
    allow_headers=["*"],
)

# Repository instance
repo = ObservatoryRepository()

# Runtime references (injected at startup)
_stability_observer = None
_resource_monitor = None
_start_time: Optional[datetime] = None


def configure(
    stability_observer=None,
    resource_monitor=None,
):
    """Configure server with runtime references.

    Args:
        stability_observer: StabilityObserver instance (read-only access)
        resource_monitor: ResourceMonitor instance (read-only access)
    """
    global _stability_observer, _resource_monitor, _start_time, repo

    _stability_observer = stability_observer
    _resource_monitor = resource_monitor
    _start_time = datetime.now()
    repo = ObservatoryRepository()

    logger.info("Observatory server configured")


# =========================================
# Health & Status Endpoints
# =========================================

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def get_health():
    """Get system health status.

    Returns memory usage, uptime, and cycle statistics.
    """
    memory_mb = 0.0
    memory_pct = 0.0

    if _resource_monitor:
        try:
            report = _resource_monitor.get_report()
            memory_mb = report.memory.rss_mb
            memory_pct = report.memory.percent
        except Exception as e:
            logger.warning(f"Failed to get resource report: {e}")

    uptime = 0.0
    if _start_time:
        uptime = (datetime.now() - _start_time).total_seconds()

    cycles = repo.get_recent_cycles(1)
    last_cycle = cycles[0]['timestamp'] if cycles else None
    cycle_count = len(repo.get_recent_cycles(100000))

    return HealthResponse(
        status="RUNNING" if _start_time else "STANDALONE",
        memory_mb=memory_mb,
        memory_percent=memory_pct,
        uptime_seconds=uptime,
        cycles_completed=cycle_count,
        last_cycle_at=last_cycle
    )


@app.get("/api/stability", response_model=StabilityResponse, tags=["Health"])
def get_stability():
    """Get current stability observer status.

    Returns mandate/action counts and any stability issues.
    """
    if _stability_observer is None:
        return StabilityResponse(
            status=StabilityStatusEnum.UNKNOWN,
            total_mandates=0,
            total_actions=0,
            issues_total=0,
            recent_issues=[]
        )

    try:
        summary = _stability_observer.summary()
        recent = _stability_observer.get_recent_issues(10)

        return StabilityResponse(
            status=StabilityStatusEnum(summary.get('status', 'UNKNOWN')),
            total_mandates=summary.get('total_mandates', 0),
            total_actions=summary.get('total_actions', 0),
            issues_total=summary.get('issues_total', 0),
            recent_issues=recent
        )
    except Exception as e:
        logger.warning(f"Failed to get stability status: {e}")
        return StabilityResponse(
            status=StabilityStatusEnum.UNKNOWN,
            total_mandates=0,
            total_actions=0,
            issues_total=0,
            recent_issues=[]
        )


@app.get("/api/stability/{symbol}", tags=["Health"])
def get_symbol_stability(symbol: str):
    """Get stability status for specific symbol."""
    if _stability_observer is None:
        return {"error": "Observer not configured"}

    try:
        return _stability_observer.get_symbol_status(symbol)
    except Exception as e:
        return {"error": str(e)}


# =========================================
# Execution Endpoints
# =========================================

@app.get("/api/cycles", response_model=List[ExecutionCycleResponse], tags=["Execution"])
def get_cycles(limit: int = Query(100, ge=1, le=10000)):
    """Get recent execution cycles."""
    return repo.get_recent_cycles(limit)


@app.get("/api/cycles/{cycle_id}", response_model=ExecutionCycleResponse, tags=["Execution"])
def get_cycle(cycle_id: int):
    """Get single execution cycle by ID."""
    cycle = repo.get_cycle(cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return cycle


# =========================================
# Mandate Endpoints
# =========================================

@app.get("/api/mandates", response_model=List[MandateResponse], tags=["Mandates"])
def get_mandates(
    symbol: Optional[str] = None,
    mandate_type: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=10000)
):
    """Get mandate history with optional filters.

    Args:
        symbol: Filter by trading symbol (e.g., BTC, ETH)
        mandate_type: Filter by type (ENTRY, EXIT, BLOCK)
        hours: Time window in hours (default 24)
        limit: Maximum records to return
    """
    since = datetime.now() - timedelta(hours=hours)
    return repo.get_mandates(
        symbol=symbol,
        since=since,
        mandate_type=mandate_type,
        limit=limit
    )


@app.get("/api/mandates/{mandate_id}", response_model=MandateResponse, tags=["Mandates"])
def get_mandate(mandate_id: int):
    """Get single mandate by ID."""
    mandate = repo.get_mandate(mandate_id)
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return mandate


@app.get("/api/mandates/counts", response_model=MandateCountsResponse, tags=["Mandates"])
def get_mandate_counts(hours: int = Query(24, ge=1, le=168)):
    """Get mandate counts by type."""
    counts = repo.count_mandates_by_type(hours)
    return MandateCountsResponse(
        entry=counts.get('ENTRY', 0),
        exit=counts.get('EXIT', 0),
        block=counts.get('BLOCK', 0),
        total=sum(counts.values())
    )


# =========================================
# Arbitration Endpoints
# =========================================

@app.get("/api/arbitration", response_model=List[ArbitrationRoundResponse], tags=["Arbitration"])
def get_arbitration(
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=10000)
):
    """Get arbitration round history."""
    return repo.get_arbitration_rounds(symbol=symbol, limit=limit)


# =========================================
# Zone Endpoints
# =========================================

@app.get("/api/zones", response_model=List[ZoneResponse], tags=["Zones"])
def get_zones(symbol: Optional[str] = None):
    """Get active M2 supply/demand zones.

    Returns only zones that have not been invalidated.
    """
    return repo.get_active_zones(symbol)


@app.get("/api/zones/history", response_model=List[ZoneResponse], tags=["Zones"])
def get_zone_history(
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=10000)
):
    """Get zone history including invalidated zones."""
    return repo.get_zone_history(symbol=symbol, limit=limit)


# =========================================
# Liquidation Endpoints
# =========================================

@app.get("/api/liquidations", response_model=List[LiquidationResponse], tags=["Liquidations"])
def get_liquidations(
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(500, ge=1, le=10000)
):
    """Get liquidation events.

    Args:
        symbol: Filter by trading symbol
        side: Filter by side (LONG, SHORT)
        hours: Time window in hours
        limit: Maximum records to return
    """
    since = datetime.now() - timedelta(hours=hours)
    return repo.get_liquidations(
        symbol=symbol,
        since=since,
        side=side,
        limit=limit
    )


@app.get("/api/cascades", response_model=List[CascadeEventResponse], tags=["Liquidations"])
def get_cascade_events(
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=10000)
):
    """Get cascade liquidation events."""
    return repo.get_cascade_events(symbol=symbol, limit=limit)


# =========================================
# Position Endpoints
# =========================================

@app.get("/api/positions", response_model=List[PositionResponse], tags=["Positions"])
def get_positions(symbol: Optional[str] = None):
    """Get current HL positions."""
    return repo.get_positions(symbol)


@app.get("/api/positions/proximity", tags=["Positions"])
def get_position_proximity(
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Get position proximity to liquidation."""
    return repo.get_position_proximity(symbol=symbol, limit=limit)


# =========================================
# Ghost Trades (Paper Trading) Endpoints
# =========================================

@app.get("/api/ghost-trades", tags=["Ghost Trades"])
def get_ghost_trades(
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Get ghost trades (paper trades).

    Returns completed paper trades with entry/exit details and PnL.
    """
    return repo.get_ghost_trades(symbol=symbol, limit=limit)


@app.get("/api/ghost-trades/summary", tags=["Ghost Trades"])
def get_ghost_summary():
    """Get ghost trading summary statistics.

    Returns total trades, PnL, win rate, and current balance.
    """
    return repo.get_ghost_summary()


# =========================================
# Market Data Endpoints
# =========================================

@app.get("/api/candles/{symbol}", tags=["Market Data"])
def get_candles(
    symbol: str,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(1000, ge=1, le=10000)
):
    """Get OHLC candle data for symbol."""
    since = datetime.now() - timedelta(hours=hours)
    return repo.get_candles(symbol, since=since, limit=limit)


@app.get("/api/prices", tags=["Market Data"])
def get_mark_prices(
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Get mark price snapshots."""
    return repo.get_mark_prices(symbol=symbol, limit=limit)


# =========================================
# System State Endpoints
# =========================================

@app.get("/api/catastrophes", tags=["System State"])
def get_catastrophes(limit: int = Query(100, ge=1, le=1000)):
    """Get system catastrophe events."""
    return repo.get_catastrophe_events(limit)


@app.get("/api/gating", tags=["System State"])
def get_gating_decisions(limit: int = Query(100, ge=1, le=1000)):
    """Get execution gating decisions."""
    return repo.get_gating_decisions(limit)


@app.get("/api/killswitch", tags=["System State"])
def get_kill_switch():
    """Get current kill switch state."""
    state = repo.get_kill_switch_state()
    if not state:
        return {"triggered": False, "message": "No kill switch state"}
    return state


# =========================================
# Snapshot Endpoint
# =========================================

@app.get("/api/snapshot", response_model=ObservatorySnapshot, tags=["Snapshot"])
def get_snapshot():
    """Get point-in-time snapshot of all observatory data.

    This is the primary endpoint for dashboard overview.
    """
    stability = get_stability()
    health = get_health()
    mandate_counts = get_mandate_counts(hours=24)
    table_counts = repo.get_table_counts()

    return ObservatorySnapshot(
        timestamp=datetime.now(),
        stability=stability,
        health=health,
        mandate_counts=mandate_counts,
        table_counts=TableCountsResponse(**table_counts),
        active_zones_count=len(repo.get_active_zones()),
        recent_liquidations_count=len(repo.get_liquidations(limit=500))
    )


# =========================================
# Statistics Endpoints
# =========================================

@app.get("/api/stats/tables", response_model=TableCountsResponse, tags=["Statistics"])
def get_table_stats():
    """Get row counts for main tables."""
    counts = repo.get_table_counts()
    return TableCountsResponse(**counts)


# =========================================
# Root Endpoint
# =========================================

@app.get("/", tags=["Root"])
def root():
    """Observatory API root."""
    return {
        "name": "Liquidation Trading Observatory",
        "version": "1.0.0",
        "description": "Read-only observation of system state",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "stability": "/api/stability",
            "snapshot": "/api/snapshot",
            "mandates": "/api/mandates",
            "zones": "/api/zones",
            "liquidations": "/api/liquidations"
        }
    }

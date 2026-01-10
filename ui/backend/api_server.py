"""
Observability API Server - Phase V1-LIVE

Serves audit events, ghost execution records, and snapshots to UI.
Read-only interface for live monitoring and replay.

Authority: Observability UI Specification
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import asyncio
import sys
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
import numpy as np

# Add scripts directory to path for peak_pressure_detector import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from peak_pressure_detector import PeakPressureDetector

app = FastAPI(title="Live-Run Observability API")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Data Storage Paths
# ==============================================================================

# Use absolute path relative to project root
ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data/v1_live_validation"
METRICS_FILE = DATA_DIR / "metrics.parquet"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"


# ==============================================================================
# WebSocket Connections (Live Streaming)
# ==============================================================================

class ConnectionManager:
    """Manages WebSocket connections for live event streaming."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast event to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ==============================================================================
# REST Endpoints (Historical Data)
# ==============================================================================

# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/api/stats")
async def get_stats():
    """
    Get system stats for LiveStatusHeader component.
    Returns basic system health and symbol information.
    """
    collector_stats = read_collector_stats()
    
    stats = {
        "mode": "LIVE_PEAK_PRESSURE",
        "symbols": list(TOP_10_SYMBOLS) if not collector_stats.get('stats_unavailable') else [],
        "symbol_count": len(TOP_10_SYMBOLS),
        "ingestion_health": "OK"
    }
    
    # Add collector stats if available
    if not collector_stats.get('stats_unavailable'):
        stats["events_ingested"] = collector_stats.get('events_ingested', {})
        stats["events_dropped"] = collector_stats.get('events_dropped', {})
        
        # Calculate health
        total_dropped = sum(collector_stats.get('events_dropped', {}).values())
        total_ingested = sum(collector_stats.get('events_ingested', {}).values())
        
        if total_ingested > 0:
            drop_rate = total_dropped / (total_ingested + total_dropped)
            stats["ingestion_health"] = 'DEGRADED' if drop_rate > 0.1 else 'OK'
        else:
            stats["ingestion_health"] = 'STARTING'
    else:
        stats["ingestion_health"] = "UNKNOWN"
        stats["stats_unavailable_reason"] = collector_stats.get('reason', 'Unknown')
    
    return stats

@app.get("/api/status")
async def get_system_status():
    """Get current system status."""
    # Read latest metrics
    if METRICS_FILE.exists():
        df = pd.read_parquet(METRICS_FILE)
        latest = df.iloc[-1].to_dict() if len(df) > 0 else {}
        
        return {
            "mode": "LIVE_GHOST",
            "symbols": df["symbol"].unique().tolist() if "symbol" in df.columns else [],
            "last_activity": latest.get("timestamp", 0),
            "event_count": len(df),
            "event_rate": _calculate_event_rate(df)
        }
    
    return {
        "mode": "LIVE_GHOST",
        "symbols": [],
        "last_activity": 0,
        "event_count": 0,
        "event_rate": 0
    }


@app.get("/api/events")
async def get_audit_events(
    symbol: Optional[str] = None,
    strategy_id: Optional[str] = None,
    limit: int = 100
):
    """Get historical audit events with filters."""
    if not METRICS_FILE.exists():
        return []
    
    df = pd.read_parquet(METRICS_FILE)
    
    # Apply filters
    if symbol:
        df = df[df["symbol"] == symbol]
    if strategy_id:
        df = df[df.get("strategy_id") == strategy_id]
    
    # Get latest N events
    df = df.tail(limit)
    
    return df.to_dict(orient="records")


@app.get("/api/metrics")
async def get_aggregated_metrics():
    """Get aggregated metrics for metrics panel."""
    if not METRICS_FILE.exists():
        return {}
    
    df = pd.read_parquet(METRICS_FILE)
    
    metrics = {
        "total_events": len(df),
        "symbols": df["symbol"].unique().tolist() if "symbol" in df.columns else [],
        "spread_stats": {
            "mean": df["spread"].mean() if "spread" in df.columns else 0,
            "min": df["spread"].min() if "spread" in df.columns else 0,
            "max": df["spread"].max() if "spread" in df.columns else 0,
        },
        "spread_bps_stats": {
            "mean": df["spread_bps"].mean() if "spread_bps" in df.columns else 0,
            "median": df["spread_bps"].median() if "spread_bps" in df.columns else 0,
        }
    }
    
    return metrics


@app.get("/api/snapshots")
async def get_snapshots(symbol: str, date: Optional[str] = None):
    """Get available snapshots for a symbol."""
    symbol_dir = SNAPSHOTS_DIR / symbol
    
    if not symbol_dir.exists():
        return []
    
    snapshots = []
    
    if date:
        # Get snapshots for specific date
        date_dir = symbol_dir / date
        if date_dir.exists():
            for snapshot_file in sorted(date_dir.glob("snapshot_*.json")):
                with open(snapshot_file) as f:
                    snapshots.append(json.load(f))
    else:
        # Get all snapshots
        for date_dir in sorted(symbol_dir.iterdir()):
            if date_dir.is_dir():
                for snapshot_file in sorted(date_dir.glob("snapshot_*.json")):
                    with open(snapshot_file) as f:
                        snapshots.append(json.load(f))
    
    return snapshots


# ==============================================================================
# Market Event Endpoints (NEW)
# ==============================================================================

MARKET_EVENTS_DIR = DATA_DIR / "market_events"

# CRITICAL: Symbol scope lockdown
import sys
sys.path.append(str(Path(__file__).parent.parent.parent / "scripts"))
from symbol_config import TOP_10_SYMBOLS

# Per-Symbol Peak Pressure Detectors (STRICT ISOLATION + SCOPE LOCKDOWN)
# CRITICAL INVARIANT: Each symbol has exactly one detector instance.
# CRITICAL SCOPE: Only TOP_10_SYMBOLS are initialized.
peak_pressure_detectors: Dict[str, PeakPressureDetector] = {}

def initialize_detectors():
    """Pre-initialize detectors for TOP_10_SYMBOLS only.
    
    Called once at startup. NO dynamic expansion allowed.
    """
    global peak_pressure_detectors
    peak_pressure_detectors = {
        symbol: PeakPressureDetector(symbol)
        for symbol in TOP_10_SYMBOLS
    }
    print(f"[PEAK PRESSURE] Initialized {len(peak_pressure_detectors)} detectors for TOP_10_SYMBOLS")

# Initialize at module load
initialize_detectors()

def get_detector(symbol: str) -> Optional[PeakPressureDetector]:
    """Get detector for symbol (if allowed).
    
    Returns:
        Detector if symbol in TOP_10_SYMBOLS, None otherwise.
    """
    return peak_pressure_detectors.get(symbol)

def read_collector_stats() -> Dict:
    """Read runtime stats from collector (IPC via JSON file).
    
    Returns:
        Stats dict if available, or stats_unavailable flag if missing/stale.
    """
    stats_file = DATA_DIR / "runtime_stats" / "collector_stats.json"
    
    try:
        if not stats_file.exists():
            return {"stats_unavailable": True, "reason": "File not found"}
        
        import time
        with open(stats_file, 'r') as f:
            stats = json.load(f)
        
        # Check if stats are stale (> 2 minutes old)
        age = time.time() - stats.get('timestamp', 0)
        if age > 120:
            return {"stats_unavailable": True, "reason": f"Stale data ({age:.0f}s old)"}
        
        return stats
        
    except Exception as e:
        return {"stats_unavailable": True, "reason": str(e)}

# Track last processed event to avoid reprocessing
last_processed_event_id = None

async def process_market_events_background():
    """
    Background task: Read all market events and feed to Peak Pressure detector.
    
    Processes trades, liquidations, klines, OI from parquet.
    Runs continuously, processing only new events since last check.
    """
    global last_processed_event_id
    
    events_file = MARKET_EVENTS_DIR / "market_events.parquet"
    
    while True:
        try:
            if events_file.exists():
                df = pd.read_parquet(events_file)
                
                if len(df) > 0:
                    # Process only new events
                    if last_processed_event_id is not None:
                        try:
                            last_idx = df[df["event_id"] == last_processed_event_id].index[0]
                            df = df.iloc[last_idx + 1:]
                        except (IndexError, KeyError):
                            # Last ID not found, process all
                            pass
                    
                    # Feed each event to correct detector by symbol
                    for _, event in df.iterrows():
                        event_type = event["type"]
                        timestamp = event["timestamp"]
                        symbol = event["symbol"]
                        
                        # CRITICAL: Route to per-symbol detector (prevents mixing)
                        # Returns None if symbol not in TOP_10_SYMBOLS
                        detector = get_detector(symbol)
                        if not detector:
                            continue  # DROP non-TOP_10 symbols
                        
                        if event_type == "TRADE":
                            detector.process_trade(
                                timestamp=timestamp,
                                symbol=symbol,
                                price=event["price"],
                                quantity=event["quantity"],
                                side=event["side"]
                            )
                        
                        elif event_type == "LIQUIDATION":
                            detector.process_liquidation(
                                timestamp=timestamp,
                                symbol=symbol,
                                price=event["price"],
                                quantity=event["quantity"],
                                side=event["side"]
                            )
                        
                        elif event_type == "KLINE":
                            # Extract kline data from raw JSON
                            raw = json.loads(event["raw"])
                            kline = raw["k"]
                            detector.process_kline(
                                timestamp=timestamp,
                                symbol=symbol,
                                open_price=float(kline["o"]),
                                high=float(kline["h"]),
                                low=float(kline["l"]),
                                close=float(kline["c"])
                            )
                        
                        elif event_type == "OPEN_INTEREST":
                            detector.process_oi(
                                symbol=symbol,
                                oi=event["quantity"],  # Stored as quantity
                                timestamp=timestamp
                            )
                    
                    # Update last processed
                    if len(df) > 0:
                        last_processed_event_id = df.iloc[-1]["event_id"]
            
            await asyncio.sleep(0.5)  # Check for new events every 500ms
            
        except Exception as e:
            print(f"[PEAK PRESSURE] Error in event processor: {e}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    """Start background Peak Pressure processor on API startup."""
    asyncio.create_task(process_market_events_background())
    print("[PEAK PRESSURE] Background processor started")


def read_parquet_with_retry(filepath: Path, retries: int = 3) -> pd.DataFrame:
    """Robust read with retry for Windows file locking."""
    import time
    last_err = None
    
    for i in range(retries):
        try:
            if not filepath.exists():
                # If missing, wait briefly in case it's being renamed
                time.sleep(0.1)
                if not filepath.exists():
                    return pd.DataFrame()
            
            return pd.read_parquet(filepath)
        except Exception as e:
            last_err = e
            time.sleep(0.1 * (i + 1))
            
    print(f"[WARN] Read failed for {filepath}: {last_err}")
    return pd.DataFrame()

@app.get("/api/market/events")
async def get_market_events(
    event_type: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 100
):
    """Get normalized market events (unified schema)."""
    events_file = MARKET_EVENTS_DIR / "market_events.parquet"
    
    df = read_parquet_with_retry(events_file)
    if len(df) == 0:
        return []
    
    # Apply filters
    if event_type:
        df = df[df["type"] == event_type]
    if symbol:
        df = df[df["symbol"] == symbol]
    
    df = df.tail(limit)
    
    # Sanitize non-JSON-compliant values (NaN, inf, -inf)
    df = df.replace([np.inf, -np.inf], np.nan)  # Convert inf to NaN
    df = df.astype(object).where(pd.notnull(df), None)  # Convert NaN to None
    
    return df.to_dict(orient="records")


@app.get("/api/market/trades")
async def get_trades(
    symbol: Optional[str] = None,
    limit: int = 100
):
    """Get trade events (filtered from unified schema)."""
    return await get_market_events(event_type="TRADE", symbol=symbol, limit=limit)


@app.get("/api/market/liquidations")
async def get_liquidations(
    symbol: Optional[str] = None,
    limit: int = 100
):
    """Get liquidation events (filtered from unified schema)."""
    return await get_market_events(event_type="LIQUIDATION", symbol=symbol, limit=limit)


@app.get("/api/market/book_updates")
async def get_book_updates(
    symbol: Optional[str] = None,
    limit: int = 100
):
    """Get recent order book update events."""
    book_file = MARKET_EVENTS_DIR / "book_updates.parquet"
    
    if not book_file.exists():
        return []
    
    df = pd.read_parquet(book_file)
    
    if symbol:
        df = df[df["symbol"] == symbol.upper()]
    
    df = df.tail(limit)
    return df.to_dict(orient="records")


@app.get("/api/events/peak_pressure")
async def get_peak_pressure_events(limit: int = 50):
    """
    Get Peak Pressure events (multi-stream structural stress coincidence).
    
    Returns only events where ALL 4 conditions met:
    - Trade flow surge (abs_flow >= P90)
    - Large trade participation (count >= 1)
    - Compression OR expansion
    - External stress (liquidations OR OI change)
    
    Empty result is valid and common during stable market periods.
    """
    # Aggregate events from all detectors
    all_events = []
    for detector in peak_pressure_detectors.values():
        all_events.extend(detector.get_events(limit=limit))
    
    # Sort by timestamp desc and limit
    all_events.sort(key=lambda e: e['timestamp'], reverse=True)
    return all_events[:limit]


@app.get("/api/market/stats")
async def get_market_stats():
    """
    Get aggregated Peak Pressure detector statistics across all symbols.
    
    MANDATORY COUNTERS:
    - total_windows_processed: 1s windows closed
    - peak_pressure_count: Events promoted
    - condition_failures: Breakdown by which condition failed
    
    Returns exact reason for zero events if applicable.
    """
    # Aggregate stats from all detectors
    if not peak_pressure_detectors:
        return {
            'counters': {'total_windows_processed': 0, 'peak_pressure_count': 0},
            'windows_processed': 0,
            'peak_pressure_count': 0,
            'condition_failures': {},
            'baselines_active': 0,
            'baselines_warm': 0,
            'zero_reason': 'No detectors created yet (no events processed)'
        }
    
    # Sum counters across all detectors
    aggregated = {
        'total_windows_processed': 0,
        'peak_pressure_count': 0,
        'flow_surge_failed': 0,
        'large_trade_failed': 0,
        'compression_failed': 0,
        'stress_failed': 0,
        'baseline_not_warm': 0
    }
    
    total_baselines = 0
    warm_baselines = 0
    liquidation_buffers = {}
    
    for symbol, detector in peak_pressure_detectors.items():
        stats = detector.get_stats()
        
        # Sum counters
        for key in aggregated.keys():
            aggregated[key] += stats['counters'].get(key, 0)
        
        # Sum baselines
        total_baselines += stats.get('baselines_active', 0)
        warm_baselines += stats.get('baselines_warm', 0)
        
        # Collect liquidation buffers
        liq_size = stats.get('liquidation_buffer_size', 0)
        if liq_size > 0:
            liquidation_buffers[symbol] = liq_size
    
    stats = {
        'counters': aggregated.copy(),
        'windows_processed': aggregated['total_windows_processed'],
        'peak_pressure_count': aggregated['peak_pressure_count'],
        'condition_failures': {
            'baseline_not_warm': aggregated['baseline_not_warm'],
            'flow_surge': aggregated['flow_surge_failed'],
            'large_trade': aggregated['large_trade_failed'],
            'compression': aggregated['compression_failed'],
            'stress': aggregated['stress_failed']
        },
        'baselines_active': len(peak_pressure_detectors),  # Number of symbols
        'baselines_warm': sum(1 for d in peak_pressure_detectors.values() if d.get_stats()['baselines_warm'] > 0),
        'liquidation_buffers': liquidation_buffers
    }
    
    # Add collector stats from IPC
    collector_stats = read_collector_stats()
    
    if collector_stats.get('stats_unavailable'):
        stats['dropped_events'] = {
            'stats_unavailable': True,
            'reason': collector_stats.get('reason', 'Unknown')
        }
        stats['ingestion_health'] = 'UNKNOWN'
    else:
        stats['dropped_events'] = collector_stats.get('events_dropped', {})
        stats['ingested_events'] = collector_stats.get('events_ingested', {})
        
        # Calculate ingestion health
        total_dropped = sum(collector_stats.get('events_dropped', {}).values())
        total_ingested = sum(collector_stats.get('events_ingested', {}).values())
        
        if total_ingested > 0:
            drop_rate = total_dropped / (total_ingested + total_dropped)
            stats['ingestion_health'] = 'DEGRADED' if drop_rate > 0.1 else 'OK'
        else:
            stats['ingestion_health'] = 'STARTING'
    
    # Add baseline readiness indicator
    warm_count = stats['baselines_warm']
    total_count = stats['baselines_active']
    stats['baselines_ready'] = f"{warm_count} / {total_count}"
    
    # Add explanation for zero peak pressure events
    if stats["peak_pressure_count"] == 0:
        failure_counts = stats["condition_failures"]
        
        if failure_counts["baseline_not_warm"] > 0:
            stats["zero_reason"] = f"Baseline warming up ({stats['baselines_warm']}/{stats['baselines_active']} symbols ready)"
        else:
            # Find most common failure
            top_failure = max(failure_counts.items(), key=lambda x: x[1] if x[0] != 'baseline_not_warm' else 0)
            stats["zero_reason"] = f"All {stats['windows_processed']} windows failed promotion. Most common: {top_failure[0]} ({top_failure[1]} failures)"
    
    return stats


@app.get("/api/market/promoted_events")
async def get_promoted_events_legacy(limit: int = 100):
    """
    DEPRECATED: Legacy endpoint for simple trade promotion.
    Use /api/events/peak_pressure instead.
    """
    return []


@app.get("/api/market/correlation")
async def get_correlation_window(
    timestamp: float,
    window_seconds: float = 5.0
):
    """
    Get event counts within time window.
    NO RATIOS. NO THRESHOLDS. Counts only.
    """
    start_time = timestamp - window_seconds
    end_time = timestamp + window_seconds
    
    # Count trades
    trades_file = MARKET_EVENTS_DIR / "trades.parquet"
    trade_count = 0
    total_volume = 0.0
    if trades_file.exists():
        df = pd.read_parquet(trades_file)
        window_trades = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)]
        trade_count = len(window_trades)
        total_volume = window_trades["quantity"].sum() if len(window_trades) > 0 else 0.0
    
    # Count liquidations
    liq_file = MARKET_EVENTS_DIR / "liquidations.parquet"
    liq_count = 0
    if liq_file.exists():
        df = pd.read_parquet(liq_file)
        window_liq = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)]
        liq_count = len(window_liq)
    
    # Count book updates
    book_file = MARKET_EVENTS_DIR / "book_updates.parquet"
    book_count = 0
    if book_file.exists():
        df = pd.read_parquet(book_file)
        window_book = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)]
        book_count = len(window_book)
    
    # Count system events (from existing metrics)
    proposal_count = 0
    ghost_count = 0
    
    return {
        "center_timestamp": timestamp,
        "window_seconds": window_seconds,
        "trade_count": int(trade_count),
        "total_volume": float(total_volume),
        "book_update_count": int(book_count),
        "liquidation_count": int(liq_count),
        "proposal_count": int(proposal_count),
        "ghost_execution_count": int(ghost_count)
}


    return {"error": "Snapshot not found"}


@app.get("/api/debug/streams")
async def get_stream_health():
    """
    Get health metrics for all data streams.
    Step 5 of Strict Correction Protocol.
    """
    now = datetime.now().timestamp()
    
    def get_stream_stats(filename: str):
        filepath = MARKET_EVENTS_DIR / filename
        if not filepath.exists():
            return {"last_ts": None, "rate_per_sec": 0, "status": "OFFLINE"}
            
        try:
            # Read last 60 seconds of data only for speed
            # But parquet doesn't support partial read easily without dataset API (pyarrow)
            # We'll read the whole dataframe but only tail if it's huge?
            # Ideally we keep these stats in memory in background task, but for now verify file
            df = pd.read_parquet(filepath)
            if len(df) == 0:
                 return {"last_ts": None, "rate_per_sec": 0, "status": "EMPTY"}
                 
            if "timestamp" in df.columns:
                last_ts = df["timestamp"].max()
                # Count events in last 60s
                recent = df[df["timestamp"] > (now - 60)]
                count = len(recent)
                rate = count / 60.0
                
                lag = now - last_ts
                status = "OK" if lag < 30 else "STALE"
                if lag > 300: status = "DEAD"
                
                return {
                    "last_ts": last_ts,
                    "last_ts_human": datetime.fromtimestamp(last_ts).strftime('%H:%M:%S'),
                    "lag_seconds": round(lag, 1),
                    "count_last_min": count,
                    "rate_per_sec": round(rate, 2),
                    "status": status
                }
            return {"last_ts": None, "error": "No timestamp col"}
        except Exception as e:
            return {"error": str(e)}

    return {
        "trades": get_stream_stats("trades.parquet"),
        "liquidations": get_stream_stats("liquidations.parquet"),
        "klines": get_stream_stats("klines.parquet"), # Assuming klines stored here? Or in market_events?
        # Actually klines might be in a different file or just unified market_events
        # Check unified file for types
        "unified_events": get_stream_stats("market_events.parquet")
    }


# ==============================================================================
# WebSocket Endpoints (Live Streaming)
# ==============================================================================

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for live system event streaming."""
    await manager.connect(websocket)
    
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/market_events")
async def websocket_market_events(websocket: WebSocket):
    """WebSocket endpoint for live market event streaming (SPECIFICATION REQUIRED)."""
    from websocket_broadcaster import broadcaster
    
    await broadcaster.connect(websocket)
    
    try:
        while True:
            # Keep connection alive
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)


# ==============================================================================
# Event Broadcasting (Called by Live Monitor)
# ==============================================================================

async def broadcast_event(event: Dict):
    """
    Broadcast event to all connected WebSocket clients.
    
    Called by live monitor when new events occur.
    """
    await manager.broadcast(event)


# ==============================================================================
# Helper Functions
# ==============================================================================

def _calculate_event_rate(df: pd.DataFrame) -> float:
    """Calculate events per minute from recent history."""
    if len(df) < 2:
        return 0.0
    
    # Get last 10 minutes of data
    if "timestamp" not in df.columns:
        return 0.0
    
    recent = df[df["timestamp"] > (df["timestamp"].max() - 600)]
    
    if len(recent) < 2:
        return 0.0
    
    duration_minutes = (recent["timestamp"].max() - recent["timestamp"].min()) / 60
    
    if duration_minutes == 0:
        return 0.0
    
    return len(recent) / duration_minutes


# ==============================================================================
# Main Entry Point
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print("OBSERVABILITY API SERVER - Phase V1-LIVE")
    print("=" * 80)
    print("Starting server on http://localhost:8000")
    print("WebSocket endpoint: ws://localhost:8000/ws/events")
    print("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

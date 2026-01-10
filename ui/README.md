# Live-Run Observability UI - Setup Guide

## Overview

Strictly read-only interface for Phase V1-LIVE empirical validation.
Renders system truth without controlling behavior.

---

## Prerequisites

- Node.js 18+ 
- Python 3.9+
- System v1.0 (frozen)

---

## Installation

### 1. Install Frontend Dependencies

```bash
cd ui
npm install
```

### 2. Install Backend Dependencies

```bash
pip install fastapi uvicorn pandas pyarrow websockets
```

---

## Running the System

### Terminal 1: Start API Server

```bash
cd ui/backend
python api_server.py
```

API will be available at: `http://localhost:8000`

### Terminal 2: Start UI

```bash
cd ui
npm run dev
```

UI will be available at: `http://localhost:3000`

### Terminal 3: Start Live Monitor (Optional)

```bash
cd scripts
python live_ghost_monitor.py
```

This will start collecting real market data and feeding the UI.

---

## What You'll See

### Live Status Header
- System mode (LIVE GHOST / SNAPSHOT REPLAY)
- Monitored symbols
- Event throughput
- Last activity timestamp

### Decision Timeline
- Scrollable event history
- Color-coded outcomes (gray/yellow/red/blue)
- Click for ghost execution details

### Ghost Execution Drawer
- Market state (bid/ask/spread)
- Would execute? (yes/no)
- Fill estimate (FULL/PARTIAL/NONE)
- Reject reason (if any)

---

## Design Philosophy

> **This UI exists to reveal pressure, not success.**

- Silence is a valid outcome
- Abstention is information  
- Reality is allowed to disagree
- No controls, no semantics, no interpretation

---

## File Structure

```
ui/
├── src/
│   ├── components/
│   │   ├── LiveStatusHeader.tsx      # System status display
│   │   ├── DecisionTimeline.tsx      # Event history
│   │   └── GhostExecutionDrawer.tsx  # Execution details
│   ├── types/
│   │   └── events.ts                 # TypeScript types
│   ├── App.tsx                       # Main orchestrator
│   ├── main.tsx                      # React entry
│   └── index.css                     # Global styles
├── backend/
│   └── api_server.py                 # FastAPI server
├── package.json
├── vite.config.ts
└── tsconfig.json
```

---

## API Endpoints

### REST (Historical)
- `GET /api/status` - System status
- `GET /api/events?symbol=BTCUSDT&limit=100` - Audit events
- `GET /api/metrics` - Aggregated metrics
- `GET /api/snapshots?symbol=BTCUSDT` - Available snapshots
- `GET /api/snapshot/{snapshot_id}` - Specific snapshot

### WebSocket (Live)
- `ws://localhost:8000/ws/events` - Live event stream

---

## Expected Behavior

**High abstention rate (50-99%):**
- System is working correctly
- Most moments don't warrant action
- This is success, not failure

**Long periods of silence:**
- No proposals generated
- No executions attempted
- Display: "Silence is a valid outcome"

**Ghost execution failures:**
- Spread too wide
- Liquidity insufficient
- Risk gates failed
- This reveals market reality

---

## Troubleshooting

**No events showing:**
- Check API server is running (`http://localhost:8000/api/status`)
- Check live monitor is running
- System may be correctly abstaining (not broken)

**UI not updating:**
- Check browser console for errors
- Verify WebSocket connection
- Check Vite dev server logs

**Empty snapshots:**
- Binance API may be rate-limited
- Check API key (optional)
- Wait for next snapshot interval

---

## Remember

✓ This UI does NOT control the system  
✓ It renders truth, not success  
✓ Silence is information  
✓ Reality is allowed to disagree  

**Code is frozen. UI is observational only.**

#!/bin/bash
# Watch system internals for debugging

echo "=== SYSTEM INTERNALS MONITOR ==="
echo ""

# 1. HL Node - recent fills
echo "--- HL NODE FILLS (last 5 min) ---"
FILLS_DIR=~/hl/data/node_fills/hourly/$(date +%Y%m%d)
CURRENT_HOUR=$(date +%-H)
if [ -f "$FILLS_DIR/$CURRENT_HOUR" ]; then
    FILL_SIZE=$(stat -c%s "$FILLS_DIR/$CURRENT_HOUR" 2>/dev/null || echo 0)
    echo "Current hour file: $FILL_SIZE bytes"
fi

# 2. Bridge metrics from API
echo ""
echo "--- BRIDGE METRICS ---"
curl -s http://localhost:8080/api/health/ 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    b = d.get('components', {}).get('bridge', {})
    print(f\"  Prices forwarded: {b.get('prices_forwarded', 'N/A')}\")
    print(f\"  Liquidations forwarded: {b.get('liquidations_forwarded', 'N/A')}\")
    print(f\"  Errors: {b.get('errors', 'N/A')}\")
except: print('  API not available')
"

# 3. Recent liquidations from API
echo ""
echo "--- RECENT LIQUIDATIONS ---"
curl -s "http://localhost:8080/api/liquidations/recent?minutes=5" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    events = d.get('events', [])[:5]
    print(f\"  Count (5min): {d.get('count', 0)}\")
    for e in events:
        print(f\"    {e.get('symbol','?')}: {e.get('side','?')} \${e.get('volume',0):,.0f}\")
except: print('  API not available')
"

# 4. Database recent activity (PostgreSQL)
echo ""
echo "--- DATABASE (PostgreSQL) ---"
PGPASSWORD=liqtrade psql -U liqtrade -d liquidation_trading -t -A -c "
    SELECT 'Cycles: ' || COUNT(*) FROM execution_cycles;
    SELECT 'Mandates: ' || COUNT(*) FROM mandates;
    SELECT 'M2 Nodes: ' || COUNT(*) FROM m2_nodes;
    SELECT 'Last cycle: ' || to_char(to_timestamp(timestamp) AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD HH24:MI:SS') FROM execution_cycles ORDER BY id DESC LIMIT 1;
" 2>/dev/null || echo "  PostgreSQL not available"

# 5. Paper trade log tail
echo ""
echo "--- PAPER TRADE LOG (last 5 lines) ---"
tail -5 /home/ksiaz/liquidation-trading/paper_trade.log 2>/dev/null | grep -v "^\s*$"

# 6. WebSocket connections
echo ""
echo "--- WEBSOCKET CONNECTIONS ---"
ss -tn 2>/dev/null | grep -E ":8080|:3000" | wc -l | xargs echo "Active connections:"

echo ""
echo "=== $(date) ==="

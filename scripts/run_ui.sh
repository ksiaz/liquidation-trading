#!/bin/bash
# Unified UI Startup Script
# Handles NTFS permission issues automatically

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
UI_DIR="$PROJECT_ROOT/observatory-ui"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  Liquidation Trading UI"
echo "=============================================="

# Parse arguments
BACKEND_PORT=${BACKEND_PORT:-8080}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
DB_PATH=${DB_PATH:-"$PROJECT_ROOT/logs/execution.db"}

while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-port) BACKEND_PORT="$2"; shift 2 ;;
        --frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
        --db) DB_PATH="$2"; shift 2 ;;
        --backend-only) BACKEND_ONLY=1; shift ;;
        --frontend-only) FRONTEND_ONLY=1; shift ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --backend-port PORT   Backend API port (default: 8080)"
            echo "  --frontend-port PORT  Frontend dev server port (default: 3000)"
            echo "  --db PATH             Path to execution.db"
            echo "  --backend-only        Start only the backend"
            echo "  --frontend-only       Start only the frontend"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Function to fix NTFS permission issues for esbuild
fix_esbuild_permissions() {
    local ESBUILD_SRC="$UI_DIR/node_modules/@esbuild/linux-x64/bin/esbuild"
    local ESBUILD_TMP="/tmp/liquidation-ui-esbuild"

    # Check if esbuild exists and is executable
    if [[ -x "$ESBUILD_SRC" ]]; then
        return 0  # Already executable, no fix needed
    fi

    # Check if it's a symlink to our tmp location
    if [[ -L "$ESBUILD_SRC" ]] && [[ -x "$ESBUILD_TMP/esbuild" ]]; then
        return 0  # Symlink exists and target is executable
    fi

    echo -e "${YELLOW}Fixing esbuild permissions (NTFS workaround)...${NC}"

    # Create tmp directory
    mkdir -p "$ESBUILD_TMP"

    # Copy binary if needed (handle both file and broken symlink)
    if [[ -f "$ESBUILD_SRC" ]] && [[ ! -L "$ESBUILD_SRC" ]]; then
        cp "$ESBUILD_SRC" "$ESBUILD_TMP/esbuild"
    elif [[ ! -f "$ESBUILD_TMP/esbuild" ]]; then
        # Try to find esbuild in package cache or reinstall
        echo -e "${RED}esbuild binary not found. Run: cd ui && npm install${NC}"
        exit 1
    fi

    chmod +x "$ESBUILD_TMP/esbuild"

    # Replace with symlink
    rm -f "$ESBUILD_SRC" 2>/dev/null || true
    ln -sf "$ESBUILD_TMP/esbuild" "$ESBUILD_SRC"

    echo -e "${GREEN}esbuild permissions fixed${NC}"
}

# Function to start backend
start_backend() {
    echo -e "${GREEN}Starting backend on port $BACKEND_PORT...${NC}"
    python "$PROJECT_ROOT/scripts/run_observatory.py" --port "$BACKEND_PORT" --db "$DB_PATH" &
    BACKEND_PID=$!
    echo "Backend PID: $BACKEND_PID"

    # Wait for backend to be ready
    for i in {1..30}; do
        if curl -s "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
            echo -e "${GREEN}Backend ready${NC}"
            return 0
        fi
        sleep 0.5
    done
    echo -e "${RED}Backend failed to start${NC}"
    return 1
}

# Function to start frontend
start_frontend() {
    cd "$UI_DIR"

    # Fix esbuild if needed
    fix_esbuild_permissions

    echo -e "${GREEN}Starting frontend on port $FRONTEND_PORT...${NC}"
    node node_modules/vite/bin/vite.js --host 0.0.0.0 --port "$FRONTEND_PORT" &
    FRONTEND_PID=$!
    echo "Frontend PID: $FRONTEND_PID"

    # Wait for frontend to be ready
    for i in {1..30}; do
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo -e "${GREEN}Frontend ready${NC}"
            return 0
        fi
        sleep 0.5
    done
    echo -e "${RED}Frontend failed to start${NC}"
    return 1
}

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."
    [[ -n "$BACKEND_PID" ]] && kill $BACKEND_PID 2>/dev/null
    [[ -n "$FRONTEND_PID" ]] && kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start services
if [[ -z "$FRONTEND_ONLY" ]]; then
    start_backend
fi

if [[ -z "$BACKEND_ONLY" ]]; then
    start_frontend
fi

echo ""
echo "=============================================="
echo -e "  ${GREEN}UI is running${NC}"
echo "=============================================="
[[ -z "$FRONTEND_ONLY" ]] && echo "  Backend:  http://localhost:$BACKEND_PORT"
[[ -z "$BACKEND_ONLY" ]] && echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo ""
echo "  Press Ctrl+C to stop"
echo "=============================================="

# Wait for processes
wait

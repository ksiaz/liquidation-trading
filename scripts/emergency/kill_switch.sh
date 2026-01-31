#!/bin/bash
#
# EMERGENCY KILL SWITCH
#
# Immediately halts all trading activity:
# 1. Sends SIGUSR1 to trading processes (graceful shutdown signal)
# 2. Closes all open positions at market
# 3. Cancels all pending orders
# 4. Logs emergency activation
#
# Usage:
#   ./kill_switch.sh              # Full emergency shutdown
#   ./kill_switch.sh --positions  # Only close positions
#   ./kill_switch.sh --orders     # Only cancel orders
#   ./kill_switch.sh --signal     # Only signal processes
#   ./kill_switch.sh --dry-run    # Show what would happen
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_FILE="${PROJECT_ROOT}/logs/emergency.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Colors for terminal output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=false
SIGNAL_ONLY=false
POSITIONS_ONLY=false
ORDERS_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --signal)
            SIGNAL_ONLY=true
            shift
            ;;
        --positions)
            POSITIONS_ONLY=true
            shift
            ;;
        --orders)
            ORDERS_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--signal] [--positions] [--orders]"
            exit 1
            ;;
    esac
done

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log_message() {
    local message="$1"
    echo -e "$message"
    echo "[$TIMESTAMP] $message" >> "$LOG_FILE" 2>/dev/null || true
}

log_message ""
log_message "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
log_message "${RED}║              EMERGENCY KILL SWITCH ACTIVATED             ║${NC}"
log_message "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
log_message ""
log_message "Time: $TIMESTAMP"
log_message "Mode: $(if $DRY_RUN; then echo 'DRY RUN'; else echo 'LIVE'; fi)"
log_message ""

if $DRY_RUN; then
    log_message "${YELLOW}[DRY RUN] No actual changes will be made${NC}"
    log_message ""
fi

#
# Step 1: Signal trading processes to stop
#
if ! $POSITIONS_ONLY && ! $ORDERS_ONLY; then
    log_message "${YELLOW}Step 1: Signaling trading processes...${NC}"

    TRADING_PIDS=$(pgrep -f "run_paper_trade.py|run_live_trade.py|trading_service" 2>/dev/null || true)

    if [ -n "$TRADING_PIDS" ]; then
        for pid in $TRADING_PIDS; do
            if $DRY_RUN; then
                log_message "  [DRY RUN] Would send SIGUSR1 to PID $pid"
            else
                log_message "  Sending SIGUSR1 to PID $pid"
                kill -USR1 "$pid" 2>/dev/null || log_message "  ${RED}Failed to signal $pid${NC}"
            fi
        done
    else
        log_message "  No trading processes found"
    fi

    log_message ""
fi

if $SIGNAL_ONLY; then
    log_message "${GREEN}Signal-only mode complete${NC}"
    exit 0
fi

#
# Step 2: Close all positions
#
if ! $ORDERS_ONLY; then
    log_message "${YELLOW}Step 2: Closing all positions...${NC}"

    if $DRY_RUN; then
        python3 "$SCRIPT_DIR/close_positions.py" --force --dry-run
    else
        python3 "$SCRIPT_DIR/close_positions.py" --force
    fi

    log_message ""
fi

if $POSITIONS_ONLY; then
    log_message "${GREEN}Position closure complete${NC}"
    exit 0
fi

#
# Step 3: Cancel all orders
#
if ! $POSITIONS_ONLY; then
    log_message "${YELLOW}Step 3: Cancelling all orders...${NC}"

    if $DRY_RUN; then
        python3 "$SCRIPT_DIR/cancel_orders.py" --all --dry-run
    else
        python3 "$SCRIPT_DIR/cancel_orders.py" --all
    fi

    log_message ""
fi

if $ORDERS_ONLY; then
    log_message "${GREEN}Order cancellation complete${NC}"
    exit 0
fi

#
# Step 4: Final verification
#
log_message "${YELLOW}Step 4: Verification...${NC}"

if $DRY_RUN; then
    log_message "  [DRY RUN] Would verify positions and orders are cleared"
else
    # Check if any trading processes still running
    REMAINING_PIDS=$(pgrep -f "run_paper_trade.py|run_live_trade.py|trading_service" 2>/dev/null || true)
    if [ -n "$REMAINING_PIDS" ]; then
        log_message "  ${YELLOW}Warning: Trading processes still running: $REMAINING_PIDS${NC}"
        log_message "  You may need to kill them manually: kill -9 $REMAINING_PIDS"
    else
        log_message "  ${GREEN}✓${NC} No trading processes running"
    fi
fi

log_message ""
log_message "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
log_message "${RED}║                   KILL SWITCH COMPLETE                   ║${NC}"
log_message "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
log_message ""

# Log to emergency log
echo "[$TIMESTAMP] KILL SWITCH COMPLETED" >> "$LOG_FILE" 2>/dev/null || true

exit 0

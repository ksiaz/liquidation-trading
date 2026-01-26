#!/usr/bin/env python3
"""
Hyperliquid Node Manager

Manages the Hyperliquid node running in WSL via SSH.

Usage:
    python scripts/node_manager.py status
    python scripts/node_manager.py start
    python scripts/node_manager.py stop
    python scripts/node_manager.py logs [--follow]
    python scripts/node_manager.py sync
"""

import subprocess
import sys
import json
import argparse
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


def wsl_run(cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
    """Run command in WSL via subprocess (more reliable than SSH)."""
    try:
        result = subprocess.run(
            ['wsl', 'bash', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)


def wsl(cmd: str, timeout: int = 30) -> str:
    """Run command, return stdout, raise on error."""
    code, stdout, stderr = wsl_run(cmd, timeout)
    if code != 0:
        raise RuntimeError(f"Command failed: {stderr}")
    return stdout


def check_wsl() -> bool:
    """Check WSL connection."""
    code, out, _ = wsl_run('echo OK', timeout=5)
    return code == 0 and 'OK' in out


# Aliases for compatibility
ssh_run = wsl_run
ssh = wsl
check_ssh = check_wsl


def get_node_process() -> Optional[Dict[str, Any]]:
    """Get node process info if running."""
    code, out, _ = ssh_run('ps aux | grep -E "hl-visor|hl-node" | grep -v grep', timeout=10)
    if code == 0 and out.strip():
        lines = out.strip().split('\n')
        for line in lines:
            if 'hl-visor' in line or 'hl-node' in line:
                parts = line.split()
                return {
                    'user': parts[0],
                    'pid': parts[1],
                    'cpu': parts[2],
                    'mem': parts[3],
                    'command': ' '.join(parts[10:]),
                }
    return None


def get_sync_state() -> Optional[Dict[str, Any]]:
    """Get node sync state."""
    code, out, _ = ssh_run('cat ~/hl/hyperliquid_data/visor_abci_state.json 2>/dev/null', timeout=10)
    if code == 0 and out.strip():
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
    return None


def get_replica_info() -> Optional[Dict[str, Any]]:
    """Get info about replica files."""
    code, out, _ = ssh_run('''
        latest=$(ls -t ~/hl/data/replica_cmds/*/* 2>/dev/null | head -1)
        if [ -n "$latest" ]; then
            size=$(stat -c%s "$latest" 2>/dev/null || echo 0)
            mtime=$(stat -c%Y "$latest" 2>/dev/null || echo 0)
            echo "$latest|$size|$mtime"
        fi
    ''', timeout=10)

    if code == 0 and out.strip():
        parts = out.strip().split('|')
        if len(parts) == 3:
            return {
                'path': parts[0],
                'size_bytes': int(parts[1]),
                'mtime': int(parts[2]),
            }
    return None


def cmd_status(args):
    """Show node status."""
    print("=" * 60)
    print("HYPERLIQUID NODE STATUS")
    print("=" * 60)

    # Check SSH
    print("\n[SSH Connection]")
    if not check_ssh():
        print("  ERROR: Cannot connect via SSH")
        print("  Run: python scripts/wsl_ssh.py --update-ip")
        return 1
    print("  OK")

    # Process status
    print("\n[Node Process]")
    proc = get_node_process()
    if proc:
        print(f"  Status:  RUNNING")
        print(f"  PID:     {proc['pid']}")
        print(f"  CPU:     {proc['cpu']}%")
        print(f"  Memory:  {proc['mem']}%")
        print(f"  Command: {proc['command'][:50]}...")
    else:
        print("  Status:  NOT RUNNING")

    # Sync state
    print("\n[Sync State]")
    state = get_sync_state()
    if state:
        height = state.get('height', 0)
        cons_time = state.get('consensus_time', '')
        wall_time = state.get('wall_clock_time', '')

        print(f"  Block Height:    {height:,}")
        print(f"  Consensus Time:  {cons_time}")
        print(f"  Wall Clock:      {wall_time}")

        # Calculate lag
        if cons_time and wall_time:
            try:
                ct = datetime.fromisoformat(cons_time[:26])
                wt = datetime.fromisoformat(wall_time[:26])
                lag = (wt - ct).total_seconds()
                print(f"  Processing Lag:  {lag:.2f}s")
            except:
                pass
    else:
        print("  No state file found")

    # Replica files
    print("\n[Replica Data]")
    replica = get_replica_info()
    if replica:
        age = time.time() - replica['mtime']
        print(f"  Latest File: {replica['path'].split('/')[-1]}")
        print(f"  Size:        {replica['size_bytes'] / 1024 / 1024:.1f} MB")
        print(f"  Age:         {age:.0f}s ago")

        if age > 60:
            print(f"  WARNING: Data is {age:.0f}s old!")
    else:
        print("  No replica files found")

    print("\n" + "=" * 60)
    return 0


def cmd_start(args):
    """Start the node."""
    print("Starting Hyperliquid node...")

    # Check if already running
    proc = get_node_process()
    if proc:
        print(f"Node is already running (PID: {proc['pid']})")
        return 0

    # Start node using hl-node from /root
    code, out, err = ssh_run(
        '''
        pkill -9 hl-node 2>/dev/null || true
        cd /root/hl
        nohup /root/hl-node --chain Mainnet run-non-validator > /tmp/hl-node.log 2>&1 &
        sleep 2
        pgrep -a hl-node
        ''',
        timeout=15
    )

    # Wait and verify
    print("Waiting for node to start...")
    time.sleep(3)

    proc = get_node_process()
    if proc:
        print(f"Node started successfully (PID: {proc['pid']})")
        print("Log file: /tmp/hl-node.log")
        return 0
    else:
        print("Node failed to start. Check /tmp/hl-node.log")
        # Show last few lines of log
        code, log, _ = ssh_run('tail -10 /tmp/hl-node.log 2>/dev/null', timeout=5)
        if log.strip():
            print(f"\nRecent log output:\n{log}")
        return 1


def cmd_stop(args):
    """Stop the node."""
    print("Stopping Hyperliquid node...")

    proc = get_node_process()
    if not proc:
        print("Node is not running")
        return 0

    # Stop gracefully first
    ssh_run('pkill -f hl-visor; pkill -f hl-node', timeout=10)
    time.sleep(2)

    # Check if stopped
    proc = get_node_process()
    if proc:
        print("Node still running, force killing...")
        ssh_run('pkill -9 -f hl-visor; pkill -9 -f hl-node', timeout=10)
        time.sleep(1)

    proc = get_node_process()
    if proc:
        print(f"Warning: Node still running (PID: {proc['pid']})")
        return 1
    else:
        print("Node stopped")
        return 0


def cmd_restart(args):
    """Restart the node."""
    cmd_stop(args)
    time.sleep(2)
    return cmd_start(args)


def cmd_logs(args):
    """Show node logs."""
    # Try both log locations
    log_file = '/tmp/hl-node.log'

    if args.follow:
        print("Following logs (Ctrl+C to stop)...")
        try:
            subprocess.run(
                ['wsl', 'bash', '-c', f'tail -f {log_file}'],
                timeout=None,
            )
        except KeyboardInterrupt:
            print("\nStopped following logs")
    else:
        lines = args.lines or 50
        code, out, _ = ssh_run(f'tail -{lines} {log_file}', timeout=10)
        if code == 0 and out.strip():
            print(out)
        else:
            # Try alternate location
            code, out, _ = ssh_run(f'tail -{lines} ~/hl/node.log', timeout=10)
            if code == 0 and out.strip():
                print(out)
            else:
                print("Could not read log file")
                return 1
    return 0


def cmd_sync(args):
    """Show sync progress."""
    print("Monitoring sync progress (Ctrl+C to stop)...")
    print()

    last_height = 0
    last_time = time.time()

    try:
        while True:
            state = get_sync_state()
            if state:
                height = state.get('height', 0)
                now = time.time()

                # Calculate blocks/sec
                if last_height > 0:
                    elapsed = now - last_time
                    bps = (height - last_height) / elapsed if elapsed > 0 else 0
                    print(f"\rBlock: {height:,}  |  +{height - last_height:,} blocks  |  {bps:.1f} blocks/sec    ", end="", flush=True)
                else:
                    print(f"\rBlock: {height:,}    ", end="", flush=True)

                last_height = height
                last_time = now

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Hyperliquid Node Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # status
    subparsers.add_parser("status", help="Show node status")

    # start
    subparsers.add_parser("start", help="Start the node")

    # stop
    subparsers.add_parser("stop", help="Stop the node")

    # restart
    subparsers.add_parser("restart", help="Restart the node")

    # logs
    logs_parser = subparsers.add_parser("logs", help="Show node logs")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    logs_parser.add_argument("-n", "--lines", type=int, help="Number of lines to show")

    # sync
    subparsers.add_parser("sync", help="Monitor sync progress")

    args = parser.parse_args()

    if not args.command:
        args.command = "status"

    commands = {
        "status": cmd_status,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "logs": cmd_logs,
        "sync": cmd_sync,
    }

    if args.command in commands:
        sys.exit(commands[args.command](args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

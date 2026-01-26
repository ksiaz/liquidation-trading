#!/usr/bin/env python3
"""
WSL Tools - Unified interface for WSL access

Provides reliable WSL access via subprocess (not SSH, which is flaky).
Can be used as a CLI tool or imported as a module.

CLI Usage:
    python scripts/wsl_tools.py run "ls -la ~/hl"
    python scripts/wsl_tools.py check
    python scripts/wsl_tools.py health
    python scripts/wsl_tools.py restart

Module Usage:
    from scripts.wsl_tools import wsl, wsl_json, check_wsl, ensure_wsl

    output = wsl("cat ~/hl/hyperliquid_data/visor_abci_state.json")
    data = wsl_json("cat ~/hl/hyperliquid_data/visor_abci_state.json")
"""

import subprocess
import sys
import json
import time
import argparse
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class WSLState(Enum):
    HEALTHY = "healthy"
    HUNG = "hung"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class WSLStatus:
    state: WSLState
    distro: Optional[str] = None
    process_count: int = 0
    vmmem_mb: int = 0
    message: str = ""


# ============ Core Functions ============

def wsl_run(cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
    """
    Run a command in WSL.

    Args:
        cmd: Bash command to execute
        timeout: Timeout in seconds

    Returns:
        (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ['wsl', 'bash', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return -2, "", "WSL not found - is it installed?"
    except Exception as e:
        return -3, "", str(e)


def wsl(cmd: str, timeout: int = 30) -> str:
    """
    Run command in WSL, return stdout, raise on error.

    Usage:
        output = wsl("cat ~/hl/hyperliquid_data/visor_abci_state.json")
    """
    code, stdout, stderr = wsl_run(cmd, timeout)
    if code != 0:
        raise RuntimeError(f"WSL command failed (code {code}): {stderr}")
    return stdout


def wsl_json(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    """Run command and parse JSON output."""
    output = wsl(cmd, timeout)
    return json.loads(output)


def check_wsl(timeout: int = 5) -> bool:
    """Quick check if WSL is accessible."""
    code, out, _ = wsl_run('echo OK', timeout)
    return code == 0 and 'OK' in out


def ensure_wsl(timeout: int = 10) -> bool:
    """Ensure WSL is accessible, attempt recovery if not."""
    if check_wsl(timeout):
        return True

    # Try to recover
    print("WSL not responding, attempting recovery...", file=sys.stderr)
    success, _ = recover_wsl()
    return success


# ============ Health Check Functions ============

def count_wsl_processes() -> Tuple[int, int]:
    """Count WSL processes and vmmem memory (MB)."""
    try:
        result = subprocess.run(
            ['tasklist'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 0, 0

        wsl_count = 0
        vmmem_mb = 0

        for line in result.stdout.split('\n'):
            lower = line.lower()
            if 'wsl.exe' in lower or 'wslhost.exe' in lower:
                wsl_count += 1
            if 'vmmem' in lower:
                parts = line.split()
                for part in parts:
                    part = part.replace(',', '').replace('K', '')
                    if part.isdigit():
                        kb = int(part)
                        if kb > 10000:
                            vmmem_mb = kb // 1024
                            break

        return wsl_count, vmmem_mb
    except:
        return 0, 0


def get_wsl_distro() -> Optional[str]:
    """Get the default WSL distribution name."""
    try:
        result = subprocess.run(
            ['wsl', '--list', '--quiet'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = [l.strip().replace('\x00', '') for l in result.stdout.split('\n') if l.strip()]
            return lines[0] if lines else None
    except:
        pass
    return None


def check_health() -> WSLStatus:
    """Full health check of WSL."""
    wsl_count, vmmem_mb = count_wsl_processes()
    distro = get_wsl_distro()

    # No processes = stopped
    if wsl_count == 0 and vmmem_mb == 0:
        return WSLStatus(
            state=WSLState.STOPPED,
            distro=distro,
            message="WSL is not running",
        )

    # Too many processes = likely hung
    if wsl_count > 10:
        return WSLStatus(
            state=WSLState.HUNG,
            distro=distro,
            process_count=wsl_count,
            vmmem_mb=vmmem_mb,
            message=f"Too many WSL processes ({wsl_count}), likely zombie accumulation",
        )

    # Check responsiveness
    if check_wsl():
        return WSLStatus(
            state=WSLState.HEALTHY,
            distro=distro,
            process_count=wsl_count,
            vmmem_mb=vmmem_mb,
            message="WSL is healthy and responsive",
        )
    else:
        return WSLStatus(
            state=WSLState.HUNG,
            distro=distro,
            process_count=wsl_count,
            vmmem_mb=vmmem_mb,
            message="WSL is unresponsive",
        )


# ============ Recovery Functions ============

def kill_wsl_processes() -> int:
    """Force kill WSL processes."""
    killed = 0
    for proc in ['wsl.exe', 'wslhost.exe', 'wslrelay.exe']:
        try:
            result = subprocess.run(
                ['taskkill', '/F', '/IM', proc],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                killed += 1
        except:
            pass
    return killed


def shutdown_wsl() -> bool:
    """Clean shutdown of WSL."""
    try:
        result = subprocess.run(
            ['wsl', '--shutdown'],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except:
        return False


def start_wsl() -> bool:
    """Start WSL by running a command."""
    code, _, _ = wsl_run('echo started', timeout=30)
    return code == 0


def recover_wsl() -> Tuple[bool, str]:
    """Attempt to recover WSL from hung state."""
    steps = []

    steps.append("Killing zombie processes...")
    kill_wsl_processes()
    time.sleep(1)

    steps.append("Shutting down WSL...")
    if not shutdown_wsl():
        steps.append("Shutdown failed, force killing...")
        kill_wsl_processes()
        time.sleep(2)

    steps.append("Waiting for cleanup...")
    time.sleep(3)

    steps.append("Starting WSL...")
    if start_wsl():
        steps.append("WSL recovered successfully!")
        return True, '\n'.join(steps)
    else:
        steps.append("Failed to start WSL")
        return False, '\n'.join(steps)


# ============ CLI Interface ============

def print_status(status: WSLStatus):
    """Print health status."""
    icons = {
        WSLState.HEALTHY: "[OK]",
        WSLState.HUNG: "[!!]",
        WSLState.STOPPED: "[--]",
        WSLState.UNKNOWN: "[??]",
    }

    print(f"\n{'='*50}")
    print("WSL Health Check")
    print(f"{'='*50}")
    print(f"Status:     {icons[status.state]} {status.state.value.upper()}")
    print(f"Distro:     {status.distro or 'N/A'}")
    print(f"Processes:  {status.process_count}")
    print(f"vmmem:      {status.vmmem_mb} MB")
    print(f"Message:    {status.message}")
    print(f"{'='*50}\n")


def cmd_run(args):
    """Run a command in WSL."""
    if not args.command:
        print("Error: No command specified", file=sys.stderr)
        return 1

    code, stdout, stderr = wsl_run(args.command, timeout=args.timeout)

    if args.json and code == 0:
        try:
            data = json.loads(stdout)
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(stdout, end='')
    else:
        if stdout:
            print(stdout, end='')
        if stderr and not args.quiet:
            print(stderr, end='', file=sys.stderr)

    return code if code >= 0 else 1


def cmd_check(args):
    """Check if WSL is accessible."""
    if check_wsl():
        print("WSL: OK")
        return 0
    else:
        print("WSL: NOT ACCESSIBLE")
        return 1


def cmd_health(args):
    """Full health check."""
    status = check_health()

    if args.json:
        print(json.dumps({
            'state': status.state.value,
            'distro': status.distro,
            'process_count': status.process_count,
            'vmmem_mb': status.vmmem_mb,
            'message': status.message,
        }))
    else:
        print_status(status)

    return 0 if status.state == WSLState.HEALTHY else 1


def cmd_restart(args):
    """Restart WSL."""
    print("Restarting WSL...")
    success, log = recover_wsl()
    print(log)

    status = check_health()
    print_status(status)

    return 0 if status.state == WSLState.HEALTHY else 1


def main():
    parser = argparse.ArgumentParser(
        description="WSL Tools - Unified interface for WSL access",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest='cmd', help='Command')

    # run
    run_parser = subparsers.add_parser('run', help='Run a command in WSL')
    run_parser.add_argument('command', nargs='?', help='Command to run')
    run_parser.add_argument('-t', '--timeout', type=int, default=30, help='Timeout in seconds')
    run_parser.add_argument('-j', '--json', action='store_true', help='Parse output as JSON')
    run_parser.add_argument('-q', '--quiet', action='store_true', help='Suppress stderr')

    # check
    subparsers.add_parser('check', help='Quick accessibility check')

    # health
    health_parser = subparsers.add_parser('health', help='Full health check')
    health_parser.add_argument('-j', '--json', action='store_true', help='JSON output')

    # restart
    subparsers.add_parser('restart', help='Restart WSL')

    args = parser.parse_args()

    commands = {
        'run': cmd_run,
        'check': cmd_check,
        'health': cmd_health,
        'restart': cmd_restart,
    }

    if args.cmd in commands:
        sys.exit(commands[args.cmd](args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

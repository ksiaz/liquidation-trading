#!/usr/bin/env python3
"""
WSL Health Check and Recovery Tool

Checks WSL accessibility and recovers from hung states.

Usage:
    python scripts/wsl_health.py          # Check health
    python scripts/wsl_health.py --fix    # Check and fix if unhealthy
    python scripts/wsl_health.py --restart # Force restart WSL
"""

import subprocess
import sys
import time
import argparse
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


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


def run_cmd(cmd: str, timeout: int = 10) -> Tuple[int, str, str]:
    """Run a command with timeout, returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)


def count_wsl_processes() -> Tuple[int, int]:
    """Count WSL processes and vmmem memory (MB)."""
    code, out, _ = run_cmd("tasklist", timeout=5)
    if code != 0:
        return 0, 0

    wsl_count = 0
    vmmem_mb = 0

    for line in out.split("\n"):
        lower = line.lower()
        if "wsl.exe" in lower or "wslhost.exe" in lower:
            wsl_count += 1
        if "vmmem" in lower:
            parts = line.split()
            for part in parts:
                part = part.replace(",", "").replace("K", "")
                if part.isdigit():
                    kb = int(part)
                    if kb > 10000:  # Likely the memory column
                        vmmem_mb = kb // 1024
                        break

    return wsl_count, vmmem_mb


def check_wsl_responsive() -> bool:
    """Check if WSL responds to commands."""
    code, out, err = run_cmd('wsl bash -c "echo OK"', timeout=5)
    return code == 0 and "OK" in out


def get_wsl_distro() -> Optional[str]:
    """Get the default WSL distribution name."""
    code, out, _ = run_cmd("wsl --list --quiet", timeout=5)
    if code == 0 and out.strip():
        # First line is default distro
        lines = [l.strip() for l in out.split("\n") if l.strip()]
        if lines:
            # Remove null bytes from output
            return lines[0].replace("\x00", "")
    return None


def check_health() -> WSLStatus:
    """Full health check."""
    wsl_count, vmmem_mb = count_wsl_processes()
    distro = get_wsl_distro()

    # No WSL processes = stopped
    if wsl_count == 0 and vmmem_mb == 0:
        return WSLStatus(
            state=WSLState.STOPPED,
            distro=distro,
            process_count=0,
            vmmem_mb=0,
            message="WSL is not running",
        )

    # Too many WSL processes = likely hung
    if wsl_count > 10:
        return WSLStatus(
            state=WSLState.HUNG,
            distro=distro,
            process_count=wsl_count,
            vmmem_mb=vmmem_mb,
            message=f"Too many WSL processes ({wsl_count}), likely zombie accumulation",
        )

    # Check if responsive
    if check_wsl_responsive():
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
            message="WSL is unresponsive (command timeout)",
        )


def kill_wsl_processes() -> int:
    """Force kill all WSL processes. Returns count killed."""
    killed = 0
    for proc in ["wsl.exe", "wslhost.exe", "wslrelay.exe"]:
        code, _, _ = run_cmd(f'cmd.exe /c "taskkill /F /IM {proc}"', timeout=30)
        if code == 0:
            killed += 1
    return killed


def shutdown_wsl() -> bool:
    """Clean shutdown of WSL."""
    code, _, _ = run_cmd("wsl --shutdown", timeout=30)
    return code == 0


def start_wsl() -> bool:
    """Start WSL by running a simple command."""
    code, _, _ = run_cmd('wsl bash -c "echo started"', timeout=30)
    return code == 0


def recover_wsl() -> Tuple[bool, str]:
    """Attempt to recover WSL from hung state."""
    steps = []

    # Step 1: Kill zombie processes
    steps.append("Killing zombie WSL processes...")
    kill_wsl_processes()
    time.sleep(1)

    # Step 2: Shutdown
    steps.append("Shutting down WSL...")
    if not shutdown_wsl():
        # Force kill if shutdown fails
        steps.append("Shutdown failed, force killing...")
        kill_wsl_processes()
        time.sleep(2)

    # Step 3: Wait for cleanup
    steps.append("Waiting for cleanup...")
    time.sleep(3)

    # Step 4: Start
    steps.append("Starting WSL...")
    if start_wsl():
        steps.append("WSL started successfully!")
        return True, "\n".join(steps)
    else:
        steps.append("Failed to start WSL")
        return False, "\n".join(steps)


def print_status(status: WSLStatus) -> None:
    """Print status in a readable format."""
    icons = {
        WSLState.HEALTHY: "[OK]",
        WSLState.HUNG: "[!!]",
        WSLState.STOPPED: "[--]",
        WSLState.UNKNOWN: "[??]",
    }

    print(f"\n{'='*50}")
    print(f"WSL Health Check")
    print(f"{'='*50}")
    print(f"Status:     {icons[status.state]} {status.state.value.upper()}")
    print(f"Distro:     {status.distro or 'N/A'}")
    print(f"Processes:  {status.process_count}")
    print(f"vmmem:      {status.vmmem_mb} MB")
    print(f"Message:    {status.message}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="WSL Health Check and Recovery")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix if unhealthy")
    parser.add_argument("--restart", action="store_true", help="Force restart WSL")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Force restart requested
    if args.restart:
        print("Force restarting WSL...")
        success, log = recover_wsl()
        print(log)
        status = check_health()
        print_status(status)
        sys.exit(0 if status.state == WSLState.HEALTHY else 1)

    # Check health
    status = check_health()

    if args.json:
        import json
        print(json.dumps({
            "state": status.state.value,
            "distro": status.distro,
            "process_count": status.process_count,
            "vmmem_mb": status.vmmem_mb,
            "message": status.message,
        }))
    else:
        print_status(status)

    # Fix if requested and unhealthy
    if args.fix and status.state in (WSLState.HUNG, WSLState.STOPPED):
        print("Attempting recovery...")
        success, log = recover_wsl()
        print(log)

        # Recheck
        status = check_health()
        print_status(status)

    # Exit code based on health
    sys.exit(0 if status.state == WSLState.HEALTHY else 1)


if __name__ == "__main__":
    main()

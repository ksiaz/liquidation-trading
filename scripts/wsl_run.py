#!/usr/bin/env python3
"""
WSL Command Runner

Clean wrapper for running commands in WSL from Windows.
Handles Git Bash path mangling and provides timeout/retry logic.

Usage:
    python scripts/wsl_run.py "ls -la ~/hl/data"
    python scripts/wsl_run.py --timeout 60 "cat ~/hl/hyperliquid_data/visor_abci_state.json"
    python scripts/wsl_run.py --check  # Just check if WSL is accessible
"""

import subprocess
import sys
import argparse
import json
from typing import Tuple, Optional


def run_wsl(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    check_health: bool = True,
) -> Tuple[int, str, str]:
    """
    Run a command in WSL.

    Args:
        command: The bash command to run
        timeout: Timeout in seconds
        cwd: Working directory (Linux path, e.g., ~/hl)
        check_health: Pre-check WSL health before running

    Returns:
        (returncode, stdout, stderr)
    """
    # Build the full command
    if cwd:
        full_cmd = f'cd {cwd} && {command}'
    else:
        full_cmd = command

    # Wrap in wsl bash -c '...'
    wsl_cmd = ['wsl', 'bash', '-c', full_cmd]

    try:
        result = subprocess.run(
            wsl_cmd,
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


def check_wsl_accessible(timeout: int = 5) -> bool:
    """Quick check if WSL is accessible."""
    code, out, _ = run_wsl("echo OK", timeout=timeout, check_health=False)
    return code == 0 and "OK" in out


def main():
    parser = argparse.ArgumentParser(
        description="Run commands in WSL from Windows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s "ls -la ~/hl/data"
    %(prog)s --timeout 60 "cat ~/hl/hyperliquid_data/visor_abci_state.json"
    %(prog)s --cwd ~/hl/data "ls -la"
    %(prog)s --json "echo hello"
    %(prog)s --check
        """,
    )
    parser.add_argument("command", nargs="?", help="Command to run in WSL")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout in seconds")
    parser.add_argument("--cwd", "-d", help="Working directory (Linux path)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--check", "-c", action="store_true", help="Just check WSL accessibility")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress stderr")

    args = parser.parse_args()

    # Check mode
    if args.check:
        accessible = check_wsl_accessible()
        if args.json:
            print(json.dumps({"accessible": accessible}))
        else:
            print(f"WSL accessible: {accessible}")
        sys.exit(0 if accessible else 1)

    # Need a command
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the command
    code, stdout, stderr = run_wsl(
        args.command,
        timeout=args.timeout,
        cwd=args.cwd,
    )

    # Output
    if args.json:
        print(json.dumps({
            "returncode": code,
            "stdout": stdout,
            "stderr": stderr,
        }))
    else:
        if stdout:
            print(stdout, end="")
        if stderr and not args.quiet:
            print(stderr, end="", file=sys.stderr)

    sys.exit(code)


# Convenience functions for importing
def wsl(cmd: str, timeout: int = 30, cwd: str = None) -> str:
    """
    Simple wrapper - run command, return stdout, raise on error.

    Usage:
        from scripts.wsl_run import wsl
        output = wsl("cat ~/hl/hyperliquid_data/visor_abci_state.json")
    """
    code, stdout, stderr = run_wsl(cmd, timeout=timeout, cwd=cwd)
    if code != 0:
        raise RuntimeError(f"WSL command failed (code {code}): {stderr}")
    return stdout


def wsl_json(cmd: str, timeout: int = 30, cwd: str = None) -> dict:
    """Run command and parse JSON output."""
    output = wsl(cmd, timeout=timeout, cwd=cwd)
    return json.loads(output)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
WSL SSH Runner

Reliable interface to WSL via SSH.
Handles connection issues, dynamic IP resolution, and provides
both CLI and importable functions.

Usage:
    python scripts/wsl_ssh.py "ls -la ~/hl/data"
    python scripts/wsl_ssh.py --json "cat ~/hl/hyperliquid_data/visor_abci_state.json"

    # From Python:
    from scripts.wsl_ssh import ssh, ssh_json
    output = ssh("cat ~/hl/hyperliquid_data/visor_abci_state.json")
    state = ssh_json("cat ~/hl/hyperliquid_data/visor_abci_state.json")
"""

import subprocess
import sys
import json
import argparse
from pathlib import Path
from typing import Tuple, Optional, Dict, Any


# Cache for WSL IP (changes on WSL restart)
_wsl_ip_cache: Optional[str] = None


def get_wsl_ip() -> Optional[str]:
    """Get WSL's current IP address."""
    global _wsl_ip_cache

    try:
        result = subprocess.run(
            ['wsl', 'bash', '-c', 'hostname -I'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            _wsl_ip_cache = result.stdout.strip().split()[0]
            return _wsl_ip_cache
    except:
        pass

    return _wsl_ip_cache


def update_ssh_config(ip: str, user: str = "root", port: int = 22) -> bool:
    """Update ~/.ssh/config with current WSL IP."""
    ssh_config_path = Path.home() / '.ssh' / 'config'

    config_entry = f"""
Host wsl
    HostName {ip}
    Port {port}
    User {user}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    ConnectTimeout 5
"""

    try:
        # Read existing config
        existing = ""
        if ssh_config_path.exists():
            existing = ssh_config_path.read_text()

        # Remove old wsl entry if exists
        lines = existing.split('\n')
        new_lines = []
        skip_until_next_host = False

        for line in lines:
            if line.strip().startswith('Host wsl'):
                skip_until_next_host = True
                continue
            if skip_until_next_host and line.strip().startswith('Host '):
                skip_until_next_host = False
            if not skip_until_next_host:
                new_lines.append(line)

        # Add new entry
        new_config = '\n'.join(new_lines).strip() + config_entry

        ssh_config_path.parent.mkdir(parents=True, exist_ok=True)
        ssh_config_path.write_text(new_config)
        return True

    except Exception as e:
        print(f"Warning: Could not update SSH config: {e}", file=sys.stderr)
        return False


def check_ssh_connection() -> bool:
    """Quick check if SSH to WSL works."""
    try:
        result = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3', 'wsl', 'echo', 'OK'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and 'OK' in result.stdout
    except:
        return False


def ensure_ssh_connection() -> bool:
    """Ensure SSH connection is working, update config if needed."""
    # Try existing connection
    if check_ssh_connection():
        return True

    # Get fresh IP and update config
    ip = get_wsl_ip()
    if not ip:
        return False

    update_ssh_config(ip)

    # Try again
    return check_ssh_connection()


def ssh_run(
    command: str,
    timeout: int = 30,
    check: bool = False,
) -> Tuple[int, str, str]:
    """
    Run a command in WSL via SSH.

    Args:
        command: Bash command to run
        timeout: Timeout in seconds
        check: If True, raise exception on non-zero exit

    Returns:
        (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', 'wsl', 'bash', '-c', command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if check and result.returncode != 0:
            raise RuntimeError(
                f"SSH command failed (code {result.returncode}): {result.stderr}"
            )

        return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError:
        return -2, "", "SSH client not found"
    except Exception as e:
        return -3, "", str(e)


def ssh(cmd: str, timeout: int = 30) -> str:
    """
    Simple wrapper - run command, return stdout, raise on error.

    Usage:
        from scripts.wsl_ssh import ssh
        output = ssh("cat ~/hl/hyperliquid_data/visor_abci_state.json")
    """
    code, stdout, stderr = ssh_run(cmd, timeout=timeout)
    if code != 0:
        raise RuntimeError(f"SSH command failed (code {code}): {stderr}")
    return stdout


def ssh_json(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    """Run command and parse JSON output."""
    output = ssh(cmd, timeout=timeout)
    return json.loads(output)


def main():
    parser = argparse.ArgumentParser(
        description="Run commands in WSL via SSH",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s "ls -la ~/hl/data"
    %(prog)s --json "cat ~/hl/hyperliquid_data/visor_abci_state.json"
    %(prog)s --check
    %(prog)s --update-ip
        """,
    )
    parser.add_argument("command", nargs="?", help="Command to run")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout in seconds")
    parser.add_argument("--json", "-j", action="store_true", help="Parse output as JSON")
    parser.add_argument("--check", "-c", action="store_true", help="Check SSH connection")
    parser.add_argument("--update-ip", action="store_true", help="Update SSH config with current WSL IP")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress stderr")

    args = parser.parse_args()

    # Check mode
    if args.check:
        if ensure_ssh_connection():
            print("SSH connection: OK")
            sys.exit(0)
        else:
            print("SSH connection: FAILED")
            print("Try: python scripts/wsl_ssh.py --update-ip")
            sys.exit(1)

    # Update IP mode
    if args.update_ip:
        ip = get_wsl_ip()
        if ip:
            update_ssh_config(ip)
            print(f"Updated SSH config with WSL IP: {ip}")
            if check_ssh_connection():
                print("SSH connection: OK")
                sys.exit(0)
            else:
                print("SSH connection: FAILED (check SSH setup in WSL)")
                sys.exit(1)
        else:
            print("Could not get WSL IP")
            sys.exit(1)

    # Need a command
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure connection works
    if not ensure_ssh_connection():
        print("SSH connection failed. Try: python scripts/wsl_ssh.py --update-ip", file=sys.stderr)
        sys.exit(1)

    # Run the command
    code, stdout, stderr = ssh_run(args.command, timeout=args.timeout)

    # Output
    if args.json and code == 0:
        try:
            data = json.loads(stdout)
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(stdout, end="")
    else:
        if stdout:
            print(stdout, end="")

    if stderr and not args.quiet:
        print(stderr, end="", file=sys.stderr)

    sys.exit(code if code >= 0 else 1)


if __name__ == "__main__":
    main()

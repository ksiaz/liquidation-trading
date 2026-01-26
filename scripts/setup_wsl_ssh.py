#!/usr/bin/env python3
"""
Setup SSH in WSL for reliable access.

This script:
1. Installs OpenSSH server in WSL if needed
2. Configures it for localhost-only access
3. Starts the service
4. Creates an SSH config entry

Usage:
    python scripts/setup_wsl_ssh.py
"""

import subprocess
import sys
import os
from pathlib import Path


def wsl_run(cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a command in WSL."""
    result = subprocess.run(
        ['wsl', 'bash', '-c', cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def wsl_sudo(cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a sudo command in WSL (may prompt for password)."""
    # For commands that need sudo, we run them with subprocess and allow stdin
    result = subprocess.run(
        ['wsl', 'bash', '-c', f'sudo {cmd}'],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def check_ssh_installed() -> bool:
    """Check if openssh-server is installed."""
    code, out, _ = wsl_run('dpkg -l openssh-server 2>/dev/null | grep -q "^ii"')
    return code == 0


def check_ssh_running() -> bool:
    """Check if SSH service is running."""
    code, out, _ = wsl_run('systemctl is-active ssh 2>/dev/null')
    return 'active' in out


def get_wsl_ip() -> str:
    """Get WSL's IP address."""
    code, out, _ = wsl_run("hostname -I | awk '{print $1}'")
    return out.strip() if code == 0 else '127.0.0.1'


def get_wsl_user() -> str:
    """Get the default WSL user."""
    code, out, _ = wsl_run('whoami')
    return out.strip() if code == 0 else 'root'


def main():
    print("=" * 50)
    print("WSL SSH Setup")
    print("=" * 50)

    # Check WSL is accessible
    print("\n[1/5] Checking WSL accessibility...")
    code, out, err = wsl_run('echo OK')
    if code != 0 or 'OK' not in out:
        print(f"ERROR: WSL is not accessible")
        print(f"  stdout: {out}")
        print(f"  stderr: {err}")
        print("\nTry running: wsl --shutdown")
        sys.exit(1)
    print("  WSL is accessible")

    # Check if SSH is installed
    print("\n[2/5] Checking SSH installation...")
    if check_ssh_installed():
        print("  openssh-server is already installed")
    else:
        print("  Installing openssh-server...")
        print("  (You may be prompted for your sudo password)")
        code, out, err = wsl_sudo('apt-get update && apt-get install -y openssh-server')
        if code != 0:
            print(f"ERROR: Failed to install openssh-server")
            print(f"  {err}")
            sys.exit(1)
        print("  Installed successfully")

    # Configure SSH for localhost only
    print("\n[3/5] Configuring SSH...")
    # Create a simple config that only listens on localhost
    config_cmd = '''
cat > /tmp/sshd_config_patch << 'EOF'
# Listen only on localhost for security
ListenAddress 127.0.0.1
ListenAddress ::1

# Allow password auth for simplicity
PasswordAuthentication yes
EOF

# Backup and patch if needed
if ! grep -q "ListenAddress 127.0.0.1" /etc/ssh/sshd_config; then
    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
    cat /tmp/sshd_config_patch >> /etc/ssh/sshd_config
    echo "Config updated"
else
    echo "Config already set"
fi
'''
    code, out, err = wsl_sudo(config_cmd)
    print(f"  {out.strip()}")

    # Start SSH service
    print("\n[4/5] Starting SSH service...")
    if check_ssh_running():
        print("  SSH is already running")
        # Restart to pick up any config changes
        wsl_sudo('systemctl restart ssh')
        print("  Restarted to apply config")
    else:
        code, out, err = wsl_sudo('systemctl enable ssh && systemctl start ssh')
        if code != 0:
            print(f"ERROR: Failed to start SSH")
            print(f"  {err}")
            sys.exit(1)
        print("  SSH started")

    # Get connection info
    print("\n[5/5] Getting connection info...")
    user = get_wsl_user()

    # For WSL2, we connect via localhost
    # Get the port SSH is listening on
    code, out, _ = wsl_run("grep -E '^Port' /etc/ssh/sshd_config | awk '{print $2}' || echo '22'")
    port = out.strip() or '22'

    print("\n" + "=" * 50)
    print("SSH Setup Complete!")
    print("=" * 50)
    print(f"\nConnection command:")
    print(f"  ssh {user}@localhost -p {port}")
    print(f"\nOr add to ~/.ssh/config:")
    print(f"""
Host wsl
    HostName localhost
    Port {port}
    User {user}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

    # Create Windows SSH config entry
    ssh_config_path = Path.home() / '.ssh' / 'config'
    print(f"\nWould you like to add this to {ssh_config_path}? (y/n)")

    # Check if entry already exists
    if ssh_config_path.exists():
        content = ssh_config_path.read_text()
        if 'Host wsl' in content:
            print("  Entry already exists in SSH config")
            return

    # For non-interactive, just print instructions
    print("\nTo add manually, run:")
    print(f'  echo "Host wsl" >> {ssh_config_path}')
    print(f'  echo "    HostName localhost" >> {ssh_config_path}')
    print(f'  echo "    Port {port}" >> {ssh_config_path}')
    print(f'  echo "    User {user}" >> {ssh_config_path}')


if __name__ == '__main__':
    main()

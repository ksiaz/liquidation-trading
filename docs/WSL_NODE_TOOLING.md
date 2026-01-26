# WSL Node Tooling & Ubuntu Migration Guide

**Date:** 2026-01-26
**Status:** Working (WSL), migrating to native Ubuntu

---

## Executive Summary

This document covers the tooling built to access a Hyperliquid node running in WSL2 from Windows, and the decision to migrate to native Ubuntu for simplicity.

### Current Architecture (WSL)

```
┌─────────────────────────────────────────────────────────────┐
│ WSL2 (Ubuntu 24.04)                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ hl-node --chain Mainnet run-non-validator           │   │
│  │  → writes to ~/hl/data/replica_cmds/                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
              ↓ (ext4 mounted as E: on Windows)
┌─────────────────────────────────────────────────────────────┐
│ Windows                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ windows_node_adapter.py                              │   │
│  │  → reads E:\hl\data\replica_cmds\                   │   │
│  │  → TCP server on 127.0.0.1:8090                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ WindowsNodeConnector (Python)                        │   │
│  │  → TCP client                                        │   │
│  │  → feeds events to M1 ingestion                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Future Architecture (Native Ubuntu)

```
┌─────────────────────────────────────────────────────────────┐
│ Ubuntu (native)                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ hl-node (systemd service)                            │   │
│  │  → writes to ~/hl/data/replica_cmds/                │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Python (direct file read)                            │   │
│  │  → reads ~/hl/data/replica_cmds/ directly           │   │
│  │  → no adapter, no TCP, no bridges                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## WSL Problems Encountered

| Problem | Description | Impact |
|---------|-------------|--------|
| Zombie processes | wsl.exe/wslhost.exe accumulate over time | WSL becomes unresponsive |
| SSH networking | WSL2 VM networking doesn't forward ports reliably | Can't use SSH from Windows |
| Path mangling | Git Bash converts `/root/...` to `C:/Program Files/Git/root/...` | Commands fail |
| Connection timeout | `HCS_E_CONNECTION_TIMEOUT` after prolonged use | Need WSL restart |
| State drift | WSL shows "Running" but commands hang | False positive health checks |

### Solution: Python subprocess with `wsl bash -c`

Direct `subprocess.run(['wsl', 'bash', '-c', cmd])` is the most reliable method. Avoids:
- Git Bash path mangling
- SSH networking issues
- Direct wsl.exe CLI quirks

---

## Tooling Created

### Python Tools

| Tool | Purpose | Usage |
|------|---------|-------|
| `wsl_tools.py` | Unified WSL interface | `python scripts/wsl_tools.py check/health/restart/run` |
| `node_manager.py` | Node lifecycle management | `python scripts/node_manager.py status/start/stop/logs/sync` |
| `windows_node_adapter.py` | TCP bridge for node data | `python scripts/windows_node_adapter.py` |
| `wsl_health.py` | Health check and recovery | `python scripts/wsl_health.py --fix` |

### Batch Scripts (Wrappers)

| Script | Action |
|--------|--------|
| `wsl_health.cmd` | Health check |
| `wsl_restart.cmd` | Force restart WSL |
| `wsl_node_status.cmd` | Node status |
| `wsl_node_start.cmd` | Start node |
| `wsl_node_stop.cmd` | Stop node |
| `wsl.cmd` | Run arbitrary command |

### Usage Examples

```bash
# Check WSL health
python scripts/wsl_tools.py health

# Run command in WSL
python scripts/wsl_tools.py run "cat ~/hl/hyperliquid_data/visor_abci_state.json"

# Node management
python scripts/node_manager.py status
python scripts/node_manager.py start
python scripts/node_manager.py logs -f
python scripts/node_manager.py sync

# Start adapter (Windows reads E:\hl\data directly)
python scripts/windows_node_adapter.py

# Recovery from hung WSL
python scripts/wsl_tools.py restart
```

### Importing in Python

```python
from scripts.wsl_tools import wsl, wsl_json, check_wsl, ensure_wsl

# Run command, get output
output = wsl("cat ~/hl/hyperliquid_data/visor_abci_state.json")

# Get JSON directly
state = wsl_json("cat ~/hl/hyperliquid_data/visor_abci_state.json")
print(f"Block height: {state['height']}")

# Ensure WSL is accessible (auto-recover if not)
if ensure_wsl():
    print("WSL ready")
```

---

## Node Adapter Performance

Tested performance with node synced:

```
Blocks processed: 1200+
Events sent: 1,300,000+
Throughput: ~2,600 events/sec
Price updates: 4,750
Liquidations: 0 (none in test period)
```

---

## Ubuntu Migration Plan

### Why Migrate?

| WSL | Native Ubuntu |
|-----|---------------|
| VM networking quirks | Direct networking |
| Zombie process accumulation | Clean process management |
| SSH forwarding issues | SSH just works |
| Path translation needed | Native paths |
| Periodic WSL hangs | Stable |
| Complex tooling required | Simple direct access |

### Migration Steps

1. **Backup project:**
   ```cmd
   xcopy D:\liquidation-trading E:\liquidation-trading /E /H
   ```

2. **Install Ubuntu 24.04 on D: drive:**
   - Download Ubuntu 24.04 LTS ISO
   - Create bootable USB
   - Install alongside Windows (dual boot)
   - Select D: drive for Ubuntu

3. **After Ubuntu install:**
   ```bash
   # Mount E: drive (node data)
   sudo mkdir /mnt/e
   sudo mount /dev/sdX1 /mnt/e  # Replace sdX1 with actual partition

   # Add to /etc/fstab for auto-mount
   echo "UUID=<uuid> /mnt/e ntfs defaults 0 0" | sudo tee -a /etc/fstab

   # Install node
   cd ~
   curl -sSL https://raw.githubusercontent.com/hyperliquid-dex/hyperliquid/main/install.sh | bash

   # Symlink existing data
   ln -s /mnt/e/hl ~/hl

   # Start node
   ~/hl-node --chain Mainnet run-non-validator

   # Or create systemd service for auto-start
   ```

4. **Access project:**
   ```bash
   cd /mnt/e/liquidation-trading
   pip install -r requirements.txt
   ```

5. **Simplified code (no adapter needed):**
   ```python
   # Direct file access - no TCP bridge needed
   import json
   from pathlib import Path

   def read_replica_blocks(replica_dir: Path):
       for session in sorted(replica_dir.iterdir(), reverse=True):
           for date_dir in sorted(session.iterdir(), reverse=True):
               for block_file in sorted(date_dir.iterdir(), reverse=True):
                   with open(block_file) as f:
                       for line in f:
                           yield json.loads(line)
   ```

---

## Files Reference

```
scripts/
├── wsl_tools.py           # Unified WSL interface (CLI + library)
├── wsl_health.py          # Health check and recovery
├── wsl_run.py             # Command runner (deprecated, use wsl_tools)
├── wsl_ssh.py             # SSH-based runner (deprecated, unreliable)
├── node_manager.py        # Node lifecycle management
├── windows_node_adapter.py # TCP bridge for node data
├── test_adapter_connection.py # Adapter test client
├── setup_wsl_ssh.py       # SSH setup (optional)
├── wsl.cmd                # Batch wrapper
├── wsl_health.cmd         # Batch wrapper
├── wsl_restart.cmd        # Batch wrapper
├── wsl_node_status.cmd    # Batch wrapper
├── wsl_node_start.cmd     # Batch wrapper
└── wsl_node_stop.cmd      # Batch wrapper

runtime/hyperliquid/
├── windows_connector.py   # TCP client for observation system
├── node_adapter/
│   └── config.py          # Adapter configuration
└── ...
```

---

## Conclusion

The WSL tooling works but requires workarounds for reliability. Native Ubuntu eliminates all these issues and simplifies the architecture significantly. The dual-boot approach preserves Windows access while providing a stable Linux environment for running the node and trading system.

**Recommendation:** Complete migration to Ubuntu for production use.

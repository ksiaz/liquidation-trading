@echo off
REM WSL Command Runner - bypasses Git Bash path mangling
REM Usage: wsl.cmd "command to run"
REM Example: wsl.cmd "cat ~/hl/hyperliquid_data/visor_abci_state.json"

if "%~1"=="" (
    echo Usage: wsl.cmd "command"
    exit /b 1
)

wsl bash -c "%~1"

@echo off
REM WSL Health Check - uses Python tools for reliability
python "%~dp0wsl_tools.py" health %*

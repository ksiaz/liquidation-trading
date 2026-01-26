@echo off
REM WSL Restart - uses Python tools for reliability
python "%~dp0wsl_tools.py" restart %*

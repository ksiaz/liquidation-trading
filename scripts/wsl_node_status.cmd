@echo off
REM Node Status - uses Python node_manager for reliability
python "%~dp0node_manager.py" status %*

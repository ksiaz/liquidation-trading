@echo off
REM Stop Node - uses Python node_manager for reliability
python "%~dp0node_manager.py" stop %*

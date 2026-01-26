@echo off
echo Starting Hyperliquid Node...
echo.
wsl -d Ubuntu-24.04 -u root -- bash -c "cd /root/hl && /root/hl-node --chain Mainnet run-non-validator"
pause

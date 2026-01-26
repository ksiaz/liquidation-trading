#!/usr/bin/env python3
"""Super simple WSL test - just write to a file."""
import time
from pathlib import Path

# Write to Windows filesystem from WSL
output_path = Path('/mnt/d/liquidation-trading/wsl_test_output.txt')
output_path.write_text(f'WSL Python works! Time: {time.time()}\n')
print(f'Wrote to {output_path}')

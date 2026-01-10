#!/usr/bin/env python3
"""
Test Runner for CI Enforcement Scripts
Purpose: Run all three CI scripts and report results
"""

import subprocess
import sys
from pathlib import Path

def run_script(script_name: str) -> tuple[int, str]:
    """Run a script and capture output."""
    script_path = Path(__file__).parent / script_name
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=script_path.parent.parent.parent
        )
        return result.returncode, result.stdout + result.stderr
    except Exception as e:
        return 1, f"Error running {script_name}: {e}"

def main():
    """Run all CI scripts."""
    scripts = [
        'semantic_leak_scan.py',
        'import_validator.py',
        'structural_validator.py',
    ]
    
    print("=" * 80)
    print("CI ENFORCEMENT TEST SUITE")
    print("=" * 80)
    
    all_passed = True
    
    for script in scripts:
        print(f"\n Running: {script}")
        print("-" * 80)
        
        exit_code, output = run_script(script)
        
        print(output)
        
        if exit_code != 0:
            all_passed = False
            print(f"❌ {script} FAILED (exit code: {exit_code})")
        else:
            print(f"✅ {script} PASSED")
    
    print("\n" + "=" * 80)
    
    if all_passed:
        print("✅ ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME CHECKS FAILED")
        sys.exit(1)

if __name__ == '__main__':
    main()

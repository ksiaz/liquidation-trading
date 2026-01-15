"""
Environment setup module - configures temp directories to use D drive.

Import this module EARLY in application startup to redirect temp files to D drive.
This prevents C drive from filling up with temporary files.

Usage:
    import runtime.env_setup  # At top of main entry points
"""
import os
import tempfile
from pathlib import Path

# Project root and temp directory
PROJECT_ROOT = Path(__file__).parent.parent
TEMP_DIR = PROJECT_ROOT / "tmp"
LOG_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"

def setup_temp_directories():
    """
    Configure Python and OS to use D drive for temp files.
    Creates directories if they don't exist.
    """
    # Create directories
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    temp_path = str(TEMP_DIR)

    # Set environment variables for this process and child processes
    os.environ['TEMP'] = temp_path
    os.environ['TMP'] = temp_path
    os.environ['TMPDIR'] = temp_path

    # Update Python's tempfile module to use our temp directory
    tempfile.tempdir = temp_path


def get_temp_dir() -> Path:
    """Return the project temp directory path."""
    return TEMP_DIR


def get_log_dir() -> Path:
    """Return the project log directory path."""
    return LOG_DIR


def get_data_dir() -> Path:
    """Return the project data directory path."""
    return DATA_DIR


# Auto-setup on import
setup_temp_directories()

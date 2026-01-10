"""
Data Pipeline Storage Package

Write-only persistence layer.
"""

from .writer import DatabaseWriter

__all__ = [
    'DatabaseWriter',
]

"""
Replay Data Loader - Replay Harness v1.0

Loads historical market data for deterministic replay.
Zero adaptation. Zero interpretation.

Authority: Replay Harness Specification v1.0
"""

from dataclasses import dataclass
from typing import Iterator, Optional
import pandas as pd
from pathlib import Path


# ==============================================================================
# Market Data Types
# ==============================================================================

@dataclass(frozen=True)
class CandleData:
    """
    OHLCV candle data.
    Minimal, structural only.
    """
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str


@dataclass(frozen=True)
class MarketSnapshot:
    """
    Market snapshot at specific timestamp.
    Contains all available data for that moment.
    """
    timestamp: float
    symbol: str
    candle: CandleData
    # Future: order book, trades, etc.


# ==============================================================================
# Data Loader
# ==============================================================================

class HistoricalDataLoader:
    """
    Loads historical market data from files.
    
    Guarantees:
    - Deterministic ordering (by timestamp)
    - Exact timestamp preservation
    - No data modification
    """
    
    def __init__(self, *, data_path: Path, symbol: str):
        """
        Initialize data loader.
        
        Args:
            data_path: Path to data file (CSV/Parquet)
            symbol: Trading symbol
        """
        self._data_path = data_path
        self._symbol = symbol
        self._data: Optional[pd.DataFrame] = None
    
    def load(self) -> None:
        """
        Load data from file.
        
        Raises:
            FileNotFoundError: If data file doesn't exist
            ValueError: If data format invalid
        """
        if not self._data_path.exists():
            raise FileNotFoundError(f"Data file not found: {self._data_path}")
        
        # Load based on file extension
        if self._data_path.suffix == '.csv':
            self._data = pd.read_csv(self._data_path)
        elif self._data_path.suffix == '.parquet':
            self._data = pd.read_parquet(self._data_path)
        else:
            raise ValueError(f"Unsupported file format: {self._data_path.suffix}")
        
        # Validate required columns
        required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing = set(required_columns) - set(self._data.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Sort by timestamp (deterministic ordering)
        self._data = self._data.sort_values('timestamp').reset_index(drop=True)
    
    def iter_snapshots(self) -> Iterator[MarketSnapshot]:
        """
        Iterate over market snapshots in chronological order.
        
        Yields:
            MarketSnapshot for each candle
        
        Raises:
            RuntimeError: If data not loaded
        """
        if self._data is None:
            raise RuntimeError("Data not loaded. Call load() first.")
        
        for _, row in self._data.iterrows():
            candle = CandleData(
                timestamp=float(row['timestamp']),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                symbol=self._symbol
            )
            
            yield MarketSnapshot(
                timestamp=candle.timestamp,
                symbol=self._symbol,
                candle=candle
            )
    
    def get_row_count(self) -> int:
        """Get number of rows loaded."""
        if self._data is None:
            return 0
        return len(self._data)
    
    def get_time_range(self) -> tuple[float, float]:
        """
        Get time range of loaded data.
        
        Returns:
            (start_timestamp, end_timestamp)
        
        Raises:
            RuntimeError: If data not loaded
            ValueError: If data is empty
        """
        if self._data is None:
            raise RuntimeError("Data not loaded. Call load() first.")
        
        if len(self._data) == 0:
            raise ValueError("Data is empty, cannot determine time range")
        
        return (
            float(self._data['timestamp'].iloc[0]),
            float(self._data['timestamp'].iloc[-1])
        )

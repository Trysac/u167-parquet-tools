"""Inspect, validate, and convert Parquet files."""

from __future__ import annotations

import logging

from .core import (
    ColumnInfo,
    ExpectedColumn,
    FileInfo,
    Issue,
    ParquetErrorCode,
    ParquetToolError,
    convert,
    from_csv,
    inspect,
    to_rows,
    validate,
)

logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "0.1.0"
__all__ = [
    "ColumnInfo",
    "ExpectedColumn",
    "FileInfo",
    "Issue",
    "ParquetErrorCode",
    "ParquetToolError",
    "__version__",
    "convert",
    "from_csv",
    "inspect",
    "to_rows",
    "validate",
]

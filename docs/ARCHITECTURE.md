# Architecture

`parquet-tools` is an enterprise-grade Python library and CLI for inspecting, validating, and converting Apache Parquet files.

## Component Overview

- `parquet_tools.core`: Implements the core functional primitives: `inspect`, `validate`, `to_rows`, `convert`, and `from_csv`.
- `parquet_tools.__main__`: CLI wrapper utilizing standard `argparse` returning standard exit status codes (0 = ok, 1 = issues found, 2 = IO/usage error).
- `parquet_tools.ParquetToolError`: Standardized error envelope supporting deterministic, machine-readable error codes (`invalid_parquet`, `file_too_large`, `missing_column`, `too_many_rows`, `invalid_value`, `unsupported_type`, `unsupported_format`).

## Memory & Safety Guarantees

- **Pre-flight File Size Checks**: Every operation checks file size against `max_file_bytes` (default 1 GiB) via `os.stat` before invoking PyArrow's underlying C++ parsers.
- **Bounded Streaming**: Row iterations and conversions are streamed with `iter_batches` and bounded via `max_rows` to prevent unbounded memory consumption or OOM failures on massive files.
- **Data-Driven Nullability Validation**: When column statistics are missing in metadata, validation falls back to targeted single-column reads rather than reading entire tables.

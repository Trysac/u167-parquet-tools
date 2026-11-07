# parquet-tools

Inspect, validate, and convert Parquet files with bounded memory and schema checking.

## The Problem
Data engineers frequently receive Parquet files from external sources and require a rapid way to understand their structure. Verifying that the schema matches pipeline expectations and ensuring column nullability constraints are met usually requires complex manual usage of the `pyarrow` API, while ad-hoc scripts often inadvertently load entire datasets into memory. This library wraps these operations in a typed, bounded API and command-line utility.

## Installation

```bash
pip install trysac-parquet-tools
```

## Usage Example

```python
import pyarrow as pa
import pyarrow.parquet as pq
from parquet_tools import ExpectedColumn, inspect, validate

pq.write_table(pa.table({"id": [1, 2], "name": ["a", None]}), "data.parquet")
info = inspect("data.parquet")
print(f"{info.num_rows} rows, {len(info.columns)} columns")
issues = validate("data.parquet", {"id": "int64", "name": ExpectedColumn("string", nullable=False)})
for issue in issues:
    print(f"[{issue.code}] {issue.column}: {issue.detail}")
```

## Public API Summary

- `inspect(path, *, max_file_bytes=1073741824) -> FileInfo`: Inspect Parquet metadata, row groups, and statistics. Raises `ParquetToolError` if file access fails, the file is too large, or reading fails.
- `validate(path, expected, *, allow_extra=False) -> list[Issue]`: Validates columns, types, and nullability against an expected schema. Raises `ParquetToolError` for IO or invalid file issues.
- `to_rows(path, *, columns=None, max_rows=100000, batch_size=10000) -> Iterator[dict]`: Streams records; raises `ParquetToolError` (code `too_many_rows`) if limit exceeded.
- `convert(path, out_path, *, max_rows=1000000) -> int`: Bounded conversion to CSV or JSONL. Raises `ParquetToolError` (code `unsupported_format`) for invalid output extensions or `unsupported_type` for complex types.
- `from_csv(csv_path, parquet_path, schema, *, max_rows=1000000) -> int`: Imports CSV to Parquet using a specific schema map. Raises `ParquetToolError` (code `invalid_value`, `too_many_rows`) for schema or row errors.

## Why not <best-known alternative>?
Unlike ad-hoc scripts or one-line `pyarrow` calls, `parquet-tools` provides a small, typed, and consistent API designed specifically for pipeline integration, with built-in memory bounds (`max_rows`, `max_file_bytes`) to prevent production OOM failures.

## Security

See [docs/SECURITY.md](docs/SECURITY.md).
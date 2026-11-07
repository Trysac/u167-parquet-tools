# Testing Strategy

Tests are located in `tests/test_parquet_tools.py` and cover the following:

- **`test_acceptance_item_1_inspect`**: Verifies inspection metadata (num_rows, num_row_groups, column-level statistics for `int64` and `string` types, null_count, and compression).
- **`test_acceptance_item_2_validate_schema_and_missing`**: Verifies `validate` behavior with exact schema matches, type mismatches (e.g., `int32` vs `int64`), missing columns, and extra columns.
- **`test_acceptance_item_3_validate_nullability`**: Verifies data-driven nullability checks against nullable/non-nullable columns.
- **`test_to_rows`**: Validates row streaming, column projection, and error handling for missing columns or excessive rows.
- **`test_convert`**: Verifies CSV/JSONL conversion outputs, row counting, and handling of dates/times.
- **`test_from_csv`**: Verifies CSV import with strict typing, boolean case-insensitivity, empty string handling as nulls, and line-specific error reporting.
- **`test_file_guards`**: Verifies `ParquetToolError` code `invalid_parquet` for corrupt files and `file_too_large` for files exceeding the size limit.
"""Core operations for inspecting, validating, and converting Parquet files."""

from __future__ import annotations

import csv
import datetime
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

ParquetErrorCode = Literal[
    "invalid_parquet",
    "file_too_large",
    "missing_column",
    "too_many_rows",
    "invalid_value",
    "unsupported_type",
    "unsupported_format",
]


class ParquetToolError(Exception):
    """Base exception raised by parquet-tools operations."""

    def __init__(self, code: ParquetErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ParquetErrorCode = code
        self.message: str = message

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ColumnInfo:
    """Metadata and statistics for a single column in a Parquet file."""

    name: str
    type: str
    nullable: bool
    compression: str
    null_count: int | None
    min: Any
    max: Any


@dataclass(frozen=True)
class FileInfo:
    """Summary metadata and column statistics for a Parquet file."""

    num_rows: int
    num_row_groups: int
    created_by: str | None
    columns: tuple[ColumnInfo, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return asdict(self)


@dataclass(frozen=True)
class ExpectedColumn:
    """Expected specification for a column schema check."""

    type: str
    nullable: bool = True


@dataclass(frozen=True)
class Issue:
    """An issue discovered during schema validation."""

    code: str
    column: str
    detail: str


DEFAULT_MAX_FILE_BYTES: int = 1_073_741_824  # 1 GiB
DEFAULT_MAX_ROWS: int = 1_000_000
DEFAULT_STREAM_MAX_ROWS: int = 100_000
DEFAULT_BATCH_SIZE: int = 10_000


def _check_file_size(path: str | Path, max_file_bytes: int) -> int:
    p = Path(path)
    try:
        stat_res = os.stat(p)
    except OSError as err:
        raise ParquetToolError("invalid_parquet", f"Cannot access file '{path}': {err}") from err
    if stat_res.st_size > max_file_bytes:
        raise ParquetToolError(
            "file_too_large",
            f"File size {stat_res.st_size} bytes exceeds maximum allowed {max_file_bytes} bytes",
        )
    return stat_res.st_size


def _open_parquet_file(
    path: str | Path, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
) -> pq.ParquetFile:
    _check_file_size(path, max_file_bytes)
    try:
        return pq.ParquetFile(str(path))
    except (pa.ArrowException, OSError) as err:
        raise ParquetToolError(
            "invalid_parquet", f"Failed to read Parquet file '{path}': {err}"
        ) from err


def inspect(path: str | Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> FileInfo:
    """Inspect Parquet file metadata, row groups, and column statistics."""
    pf = _open_parquet_file(path, max_file_bytes=max_file_bytes)
    metadata = pf.metadata
    schema = pf.schema_arrow
    num_rows = metadata.num_rows
    num_row_groups = metadata.num_row_groups
    created_by = metadata.created_by

    columns: list[ColumnInfo] = []
    for i in range(len(schema)):
        field = schema.field(i)
        name = field.name
        type_str = str(field.type)
        nullable = field.nullable

        # Compression from row group 0 (or 'UNCOMPRESSED' if 0 row groups)
        compression = "UNCOMPRESSED"
        if num_row_groups > 0:
            try:
                rg0_col = metadata.row_group(0).column(i)
                compression = rg0_col.compression
            except Exception:
                compression = "UNCOMPRESSED"

        # Compute null_count, min, max across all row groups
        all_have_stats = True
        all_have_min_max = True
        null_count_sum = 0
        min_values: list[Any] = []
        max_values: list[Any] = []

        # Check if type supports min/max (integer, floating point, string, boolean)
        type_supports_min_max = (
            pa.types.is_integer(field.type)
            or pa.types.is_floating(field.type)
            or pa.types.is_string(field.type)
            or pa.types.is_large_string(field.type)
            or pa.types.is_boolean(field.type)
        )

        if num_row_groups == 0:
            null_count_val: int | None = 0
            col_min = None
            col_max = None
        else:
            for rg_idx in range(num_row_groups):
                col_meta = metadata.row_group(rg_idx).column(i)
                stats = col_meta.statistics
                if stats is None:
                    all_have_stats = False
                    all_have_min_max = False
                    break
                if stats.has_null_count:
                    null_count_sum += stats.null_count
                else:
                    all_have_stats = False

                if type_supports_min_max and stats.has_min_max:
                    min_values.append(stats.min)
                    max_values.append(stats.max)
                else:
                    all_have_min_max = False

            null_count_val = null_count_sum if all_have_stats else None
            col_min = min(min_values) if (all_have_min_max and min_values) else None
            col_max = max(max_values) if (all_have_min_max and max_values) else None

        columns.append(
            ColumnInfo(
                name=name,
                type=type_str,
                nullable=nullable,
                compression=compression,
                null_count=null_count_val,
                min=col_min,
                max=col_max,
            )
        )

    return FileInfo(
        num_rows=num_rows,
        num_row_groups=num_row_groups,
        created_by=created_by,
        columns=tuple(columns),
    )


def validate(
    path: str | Path,
    expected: Mapping[str, str | ExpectedColumn],
    *,
    allow_extra: bool = False,
) -> list[Issue]:
    """Validate that a Parquet file matches expected columns, types, and nullability."""
    info = inspect(path)
    file_cols_dict = {col.name: col for col in info.columns}
    issues: list[Issue] = []

    pf: pq.ParquetFile | None = None

    # 1. Process expected columns in mapping order
    for exp_name, exp_spec in expected.items():
        if isinstance(exp_spec, ExpectedColumn):
            expected_type = exp_spec.type
            expected_nullable = exp_spec.nullable
        else:
            expected_type = str(exp_spec)
            expected_nullable = True

        if exp_name not in file_cols_dict:
            issues.append(Issue(code="missing_column", column=exp_name, detail="not in the file"))
            continue

        file_col = file_cols_dict[exp_name]

        if file_col.type != expected_type:
            issues.append(
                Issue(
                    code="type_mismatch",
                    column=exp_name,
                    detail=f"expected '{expected_type}', found '{file_col.type}'",
                )
            )

        # Nullability check
        if not expected_nullable:
            actual_nulls = file_col.null_count
            if actual_nulls is None:
                # Column lacks statistics; count by reading
                if pf is None:
                    pf = _open_parquet_file(path)
                try:
                    table = pf.read(columns=[exp_name])
                    actual_nulls = table.column(exp_name).null_count
                except Exception:
                    actual_nulls = 0
            if actual_nulls > 0:
                issues.append(
                    Issue(
                        code="nullability",
                        column=exp_name,
                        detail=f"{actual_nulls} null values",
                    )
                )

    # 2. Unexpected columns in file order
    if not allow_extra:
        for col in info.columns:
            if col.name not in expected:
                issues.append(
                    Issue(
                        code="unexpected_column",
                        column=col.name,
                        detail="not in the expected schema",
                    )
                )

    return issues


def to_rows(
    path: str | Path,
    *,
    columns: Sequence[str] | None = None,
    max_rows: int = DEFAULT_STREAM_MAX_ROWS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Iterator[dict[str, Any]]:
    """Stream rows from a Parquet file as dictionaries."""
    pf = _open_parquet_file(path)
    file_column_names = set(pf.schema_arrow.names)
    if columns is not None:
        for col in columns:
            if col not in file_column_names:
                raise ParquetToolError("missing_column", f"Column '{col}' not found in file")
        col_list: list[str] | None = list(columns)
    else:
        col_list = None

    yielded = 0
    for batch in pf.iter_batches(batch_size=batch_size, columns=col_list):
        rows = batch.to_pylist()
        for row in rows:
            if yielded >= max_rows:
                raise ParquetToolError(
                    "too_many_rows",
                    f"File row count exceeds maximum requested row limit of {max_rows}",
                )
            yield row
            yielded += 1


def _check_unsupported_types(schema: pa.Schema) -> None:
    for field in schema:
        t = field.type
        if (
            pa.types.is_list(t)
            or pa.types.is_large_list(t)
            or pa.types.is_struct(t)
            or pa.types.is_map(t)
            or pa.types.is_binary(t)
            or pa.types.is_large_binary(t)
            or pa.types.is_fixed_size_binary(t)
        ):
            raise ParquetToolError(
                "unsupported_type",
                f"Column '{field.name}' has unsupported type '{field.type}' for export",
            )


def _serialize_json_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (datetime.date, datetime.datetime, datetime.time)):
        return val.isoformat()
    return val


def convert(path: str | Path, out_path: str | Path, *, max_rows: int = DEFAULT_MAX_ROWS) -> int:
    """Convert Parquet file to CSV or JSONL format."""
    out_p = Path(out_path)
    suffix = out_p.suffix.lower()
    if suffix not in (".csv", ".jsonl"):
        raise ParquetToolError(
            "unsupported_format",
            f"Unsupported output extension '{suffix}'. Expected '.csv' or '.jsonl'",
        )

    pf = _open_parquet_file(path)
    schema = pf.schema_arrow
    _check_unsupported_types(schema)
    col_names = schema.names

    row_count = 0
    if suffix == ".csv":
        with open(out_p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(col_names)
            for row in to_rows(path, max_rows=max_rows):
                writer.writerow(["" if row[c] is None else row[c] for c in col_names])
                row_count += 1
    else:  # .jsonl
        with open(out_p, "w", encoding="utf-8") as f:
            for row in to_rows(path, max_rows=max_rows):
                formatted_row = {c: _serialize_json_value(row[c]) for c in col_names}
                line = json.dumps(
                    formatted_row, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                )
                f.write(line + "\n")
                row_count += 1

    return row_count


def from_csv(
    csv_path: str | Path,
    parquet_path: str | Path,
    schema: Mapping[str, str],
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> int:
    """Convert CSV file to Parquet file according to schema."""
    supported_types = {"int64", "double", "string", "bool"}
    for col_name, col_type in schema.items():
        if col_type not in supported_types:
            raise ParquetToolError(
                "unsupported_type",
                f"Schema column '{col_name}' specifies unsupported type '{col_type}'",
            )

    csv_p = Path(csv_path)
    try:
        with open(csv_p, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                header = []

            expected_header = list(schema.keys())
            if header != expected_header:
                raise ParquetToolError(
                    "invalid_value",
                    f"CSV header {header} does not match expected schema keys {expected_header}",
                )

            parsed_columns: dict[str, list[Any]] = {k: [] for k in schema}
            line_num = 1  # Header was line 1
            for row_vals in reader:
                line_num += 1
                if line_num - 1 > max_rows:
                    raise ParquetToolError(
                        "too_many_rows",
                        f"CSV exceeds maximum allowed rows ({max_rows})",
                    )
                if len(row_vals) != len(expected_header):
                    raise ParquetToolError(
                        "invalid_value",
                        f"line {line_num}: expected {len(expected_header)} "
                        f"columns, found {len(row_vals)}",
                    )

                for col_name, raw_val in zip(expected_header, row_vals, strict=False):
                    target_type = schema[col_name]
                    if raw_val == "":
                        parsed_columns[col_name].append(None)
                        continue

                    if target_type == "int64":
                        try:
                            # Must be strict integer
                            parsed_columns[col_name].append(int(raw_val))
                        except ValueError as err:
                            raise ParquetToolError(
                                "invalid_value",
                                f"line {line_num}, column {col_name}: not an int64",
                            ) from err
                    elif target_type == "double":
                        try:
                            parsed_columns[col_name].append(float(raw_val))
                        except ValueError as err:
                            raise ParquetToolError(
                                "invalid_value",
                                f"line {line_num}, column {col_name}: not a double",
                            ) from err
                    elif target_type == "bool":
                        val_lower = raw_val.strip().lower()
                        if val_lower == "true":
                            parsed_columns[col_name].append(True)
                        elif val_lower == "false":
                            parsed_columns[col_name].append(False)
                        else:
                            raise ParquetToolError(
                                "invalid_value",
                                f"line {line_num}, column {col_name}: not a bool",
                            )
                    else:  # string
                        parsed_columns[col_name].append(raw_val)
    except OSError as err:
        raise ParquetToolError(
            "invalid_parquet", f"Cannot read CSV file '{csv_path}': {err}"
        ) from err

    num_rows = line_num - 1

    # Construct PyArrow Table
    arrow_fields = []
    for col_name, col_type in schema.items():
        if col_type == "int64":
            pa_t = pa.int64()
        elif col_type == "double":
            pa_t = pa.float64()
        elif col_type == "bool":
            pa_t = pa.bool_()
        else:
            pa_t = pa.string()
        arrow_fields.append(pa.field(col_name, pa_t, nullable=True))

    pa_schema = pa.schema(arrow_fields)
    pa_arrays = [
        pa.array(parsed_columns[col_name], type=pa_schema.field(col_name).type)
        for col_name in schema
    ]
    table = pa.Table.from_arrays(pa_arrays, schema=pa_schema)

    pq.write_table(table, str(parquet_path), compression="snappy")
    return num_rows

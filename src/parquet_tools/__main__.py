"""Command line interface for parquet-tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import ExpectedColumn, ParquetToolError, convert, from_csv, inspect, validate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parquet-tools", description="Parquet inspection, validation, and conversion tool."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # inspect
    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect Parquet file schema and statistics"
    )
    inspect_parser.add_argument("path", help="Path to Parquet file")
    inspect_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # validate
    validate_parser = subparsers.add_parser(
        "validate", help="Validate Parquet file against expected schema"
    )
    validate_parser.add_argument("path", help="Path to Parquet file")
    validate_parser.add_argument("--expect", required=True, help="Path to JSON schema file")
    validate_parser.add_argument(
        "--allow-extra", action="store_true", help="Allow unexpected extra columns"
    )

    # convert
    convert_parser = subparsers.add_parser("convert", help="Convert Parquet file to CSV or JSONL")
    convert_parser.add_argument("in_path", help="Path to input Parquet file")
    convert_parser.add_argument("out_path", help="Path to output CSV or JSONL file")

    # from-csv
    from_csv_parser = subparsers.add_parser("from-csv", help="Convert CSV file to Parquet")
    from_csv_parser.add_argument("in_path", help="Path to input CSV file")
    from_csv_parser.add_argument("out_path", help="Path to output Parquet file")
    from_csv_parser.add_argument("--schema", required=True, help="Path to JSON schema file")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI application."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    try:
        if args.command == "inspect":
            info = inspect(args.path)
            if args.format == "json":
                sys.stdout.write(json.dumps(info.to_dict(), indent=2) + "\n")
            else:
                sys.stdout.write(f"Rows: {info.num_rows}\n")
                sys.stdout.write(f"Row Groups: {info.num_row_groups}\n")
                sys.stdout.write(f"Created By: {info.created_by}\n")
                sys.stdout.write("Columns:\n")
                for col in info.columns:
                    sys.stdout.write(
                        f"  - {col.name}: type={col.type}, nullable={col.nullable}, "
                        f"compression={col.compression}, nulls={col.null_count}, "
                        f"min={col.min}, max={col.max}\n"
                    )
            return 0

        if args.command == "validate":
            schema_path = Path(args.expect)
            if not schema_path.is_file():
                sys.stderr.write(f"Schema file not found: {args.expect}\n")
                return 2
            with open(schema_path, encoding="utf-8") as f:
                raw_schema: dict[str, Any] = json.load(f)

            expected: dict[str, str | ExpectedColumn] = {}
            for k, v in raw_schema.items():
                if isinstance(v, dict):
                    expected[k] = ExpectedColumn(
                        type=v.get("type", ""),
                        nullable=v.get("nullable", True),
                    )
                else:
                    expected[k] = str(v)

            issues = validate(args.path, expected, allow_extra=args.allow_extra)
            if issues:
                for issue in issues:
                    sys.stdout.write(f"[{issue.code}] {issue.column}: {issue.detail}\n")
                return 1
            return 0

        if args.command == "convert":
            count = convert(args.in_path, args.out_path)
            sys.stdout.write(f"Converted {count} rows\n")
            return 0

        if args.command == "from-csv":
            schema_path = Path(args.schema)
            if not schema_path.is_file():
                sys.stderr.write(f"Schema file not found: {args.schema}\n")
                return 2
            with open(schema_path, encoding="utf-8") as f:
                schema_data: dict[str, str] = json.load(f)
            count = from_csv(args.in_path, args.out_path, schema_data)
            sys.stdout.write(f"Wrote {count} rows\n")
            return 0

    except ParquetToolError as err:
        sys.stderr.write(f"Error: {err.message}\n")
        return 2
    except Exception as err:
        sys.stderr.write(f"Unexpected error: {err}\n")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

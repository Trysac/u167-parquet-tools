"""Tests for parquet_tools public API and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from parquet_tools import (
    ColumnInfo,
    ExpectedColumn,
    Issue,
    ParquetToolError,
    convert,
    from_csv,
    inspect,
    to_rows,
    validate,
)
from parquet_tools.__main__ import main


def test_acceptance_item_1_inspect(tmp_path: Path) -> None:
    # For a file written in the test with pq.write_table(pa.table({'id': [1, 2, 3], 'name': ['a', None, 'c']}), path, row_group_size=2),
    # inspect(path) returns num_rows 3, num_row_groups 2, columns[0] == ColumnInfo('id', 'int64', True, 'SNAPPY', 0, 1, 3)
    # and columns[1].null_count == 1 with min 'a' and max 'c'
    path = str(tmp_path / "test1.parquet")
    table = pa.table({"id": [1, 2, 3], "name": ["a", None, "c"]})
    pq.write_table(table, path, row_group_size=2)

    info = inspect(path)
    assert info.num_rows == 3
    assert info.num_row_groups == 2
    assert info.columns[0] == ColumnInfo("id", "int64", True, "SNAPPY", 0, 1, 3)
    assert info.columns[1].null_count == 1
    assert info.columns[1].min == "a"
    assert info.columns[1].max == "c"


def test_acceptance_item_2_validate_schema_and_missing(tmp_path: Path) -> None:
    # validate(path, {'id': 'int64', 'name': 'string'}) == [];
    # validate(path, {'id': 'int32'}) returns [Issue('type_mismatch', 'id', "expected 'int32', found 'int64'"), Issue('unexpected_column', 'name', 'not in the expected schema')];
    # with allow_extra=True only the first issue remains;
    # an expected 'email' gives Issue('missing_column', 'email', 'not in the file')
    path = str(tmp_path / "test2.parquet")
    table = pa.table({"id": [1, 2, 3], "name": ["a", None, "c"]})
    pq.write_table(table, path, row_group_size=2)

    assert validate(path, {"id": "int64", "name": "string"}) == []

    issues = validate(path, {"id": "int32"})
    assert issues == [
        Issue("type_mismatch", "id", "expected 'int32', found 'int64'"),
        Issue("unexpected_column", "name", "not in the expected schema"),
    ]

    issues_extra = validate(path, {"id": "int32"}, allow_extra=True)
    assert issues_extra == [Issue("type_mismatch", "id", "expected 'int32', found 'int64'")]

    issues_missing = validate(path, {"id": "int64", "name": "string", "email": "string"})
    assert issues_missing == [Issue("missing_column", "email", "not in the file")]


def test_acceptance_item_3_validate_nullability(tmp_path: Path) -> None:
    # validate(path, {'id': 'int64', 'name': ExpectedColumn('string', nullable=False)}) returns [Issue('nullability', 'name', '1 null values')]
    path = str(tmp_path / "test3.parquet")
    table = pa.table({"id": [1, 2, 3], "name": ["a", None, "c"]})
    pq.write_table(table, path, row_group_size=2)

    issues = validate(path, {"id": "int64", "name": ExpectedColumn("string", nullable=False)})
    assert issues == [Issue("nullability", "name", "1 null values")]


def test_acceptance_item_4_to_rows(tmp_path: Path) -> None:
    # list(to_rows(path)) == [{'id': 1, 'name': 'a'}, {'id': 2, 'name': None}, {'id': 3, 'name': 'c'}],
    # columns=['name'] yields only name,
    # columns=['x'] raises ParquetToolError with code 'missing_column',
    # and max_rows=2 raises code 'too_many_rows' after yielding 2 rows
    path = str(tmp_path / "test4.parquet")
    table = pa.table({"id": [1, 2, 3], "name": ["a", None, "c"]})
    pq.write_table(table, path, row_group_size=2)

    assert list(to_rows(path)) == [
        {"id": 1, "name": "a"},
        {"id": 2, "name": None},
        {"id": 3, "name": "c"},
    ]

    assert list(to_rows(path, columns=["name"])) == [
        {"name": "a"},
        {"name": None},
        {"name": "c"},
    ]

    with pytest.raises(ParquetToolError) as exc_info:
        list(to_rows(path, columns=["x"]))
    assert exc_info.value.code == "missing_column"

    stream = to_rows(path, max_rows=2)
    rows = []
    with pytest.raises(ParquetToolError) as exc_info_too_many:
        for row in stream:
            rows.append(row)
    assert len(rows) == 2
    assert exc_info_too_many.value.code == "too_many_rows"


def test_acceptance_item_5_convert(tmp_path: Path) -> None:
    # convert(path, out_csv) writes exactly 'id,name\n1,a\n2,\n3,c\n' and returns 3,
    # and convert(path, out_jsonl) writes exactly '{"id":1,"name":"a"}\n{"id":2,"name":null}\n{"id":3,"name":"c"}\n'
    path = str(tmp_path / "test5.parquet")
    table = pa.table({"id": [1, 2, 3], "name": ["a", None, "c"]})
    pq.write_table(table, path, row_group_size=2)

    out_csv = tmp_path / "out.csv"
    count_csv = convert(path, out_csv)
    assert count_csv == 3
    assert out_csv.read_text(encoding="utf-8") == "id,name\n1,a\n2,\n3,c\n"

    out_jsonl = tmp_path / "out.jsonl"
    count_jsonl = convert(path, out_jsonl)
    assert count_jsonl == 3
    assert (
        out_jsonl.read_text(encoding="utf-8")
        == '{"id":1,"name":"a"}\n{"id":2,"name":null}\n{"id":3,"name":"c"}\n'
    )


def test_acceptance_item_6_from_csv(tmp_path: Path) -> None:
    # from_csv of 'id,ok,score\n1,true,1.5\n2,,\n' with schema {'id': 'int64', 'ok': 'bool', 'score': 'double'} returns 2
    # and inspect shows types 'int64', 'bool' and 'double' with null_count 1 for ok and score;
    # a cell 'x' in id raises code 'invalid_value' with message 'line 2, column id: not an int64'
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id,ok,score\n1,true,1.5\n2,,\n", encoding="utf-8")
    parquet_out = tmp_path / "out.parquet"

    count = from_csv(csv_file, parquet_out, {"id": "int64", "ok": "bool", "score": "double"})
    assert count == 2

    info = inspect(parquet_out)
    col_dict = {c.name: c for c in info.columns}
    assert col_dict["id"].type == "int64"
    assert col_dict["ok"].type == "bool"
    assert col_dict["score"].type == "double"
    assert col_dict["ok"].null_count == 1
    assert col_dict["score"].null_count == 1

    bad_csv = tmp_path / "bad_int.csv"
    bad_csv.write_text("id,ok,score\nx,true,1.5\n", encoding="utf-8")
    with pytest.raises(ParquetToolError) as exc_info:
        from_csv(
            bad_csv, tmp_path / "out_bad.parquet", {"id": "int64", "ok": "bool", "score": "double"}
        )
    assert exc_info.value.code == "invalid_value"
    assert str(exc_info.value) == "line 2, column id: not an int64"


def test_acceptance_item_7_errors_and_file_too_large(tmp_path: Path) -> None:
    # A text file named bad.parquet raises ParquetToolError with code 'invalid_parquet',
    # and a file larger than max_file_bytes=10 raises 'file_too_large' before pyarrow opens it
    bad_parquet = tmp_path / "bad.parquet"
    bad_parquet.write_text("this is not a valid parquet file", encoding="utf-8")

    with pytest.raises(ParquetToolError) as exc_info:
        inspect(bad_parquet)
    assert exc_info.value.code == "invalid_parquet"

    with pytest.raises(ParquetToolError) as exc_too_large:
        inspect(bad_parquet, max_file_bytes=10)
    assert exc_too_large.value.code == "file_too_large"


def test_acceptance_item_8_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # main(['inspect', path, '--format', 'json']) prints JSON with num_rows 3 and returns 0,
    # main(['validate', path, '--expect', schema_json]) returns 1 when issues exist,
    # and a missing file returns 2
    path = str(tmp_path / "cli_test.parquet")
    table = pa.table({"id": [1, 2, 3], "name": ["a", None, "c"]})
    pq.write_table(table, path, row_group_size=2)

    ret = main(["inspect", path, "--format", "json"])
    captured = capsys.readouterr()
    assert ret == 0
    parsed = json.loads(captured.out)
    assert parsed["num_rows"] == 3

    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({"id": "int32"}), encoding="utf-8")
    ret_val = main(["validate", path, "--expect", str(schema_path)])
    captured_val = capsys.readouterr()
    assert ret_val == 1
    assert "[type_mismatch] id: expected 'int32', found 'int64'" in captured_val.out

    missing_path = str(tmp_path / "non_existent.parquet")
    ret_missing = main(["inspect", missing_path])
    assert ret_missing == 2


def test_cli_inspect_text_and_validate_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(tmp_path / "cli_text.parquet")
    table = pa.table({"id": [1, 2]})
    pq.write_table(table, path)

    ret = main(["inspect", path])
    out = capsys.readouterr().out
    assert ret == 0
    assert "Rows: 2" in out
    assert "Row Groups: 1" in out

    schema_path = tmp_path / "schema_valid.json"
    schema_path.write_text(
        json.dumps({"id": {"type": "int64", "nullable": True}}), encoding="utf-8"
    )
    ret_valid = main(["validate", path, "--expect", str(schema_path)])
    assert ret_valid == 0


def test_cli_convert_and_from_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = str(tmp_path / "input.parquet")
    pq.write_table(pa.table({"a": [10, 20]}), path)
    out_csv = tmp_path / "cli_out.csv"
    ret_conv = main(["convert", path, str(out_csv)])
    assert ret_conv == 0
    assert "Converted 2 rows" in capsys.readouterr().out

    schema_json = tmp_path / "schema_csv.json"
    schema_json.write_text(json.dumps({"a": "int64"}), encoding="utf-8")
    out_pq = tmp_path / "cli_out.parquet"
    ret_from_csv = main(["from-csv", str(out_csv), str(out_pq), "--schema", str(schema_json)])
    assert ret_from_csv == 0
    assert "Wrote 2 rows" in capsys.readouterr().out


def test_cli_errors(tmp_path: Path) -> None:
    # Missing schema file
    ret = main(
        ["validate", str(tmp_path / "foo.parquet"), "--expect", str(tmp_path / "missing.json")]
    )
    assert ret == 2

    ret_from_csv = main(
        [
            "from-csv",
            str(tmp_path / "foo.csv"),
            str(tmp_path / "out.parquet"),
            "--schema",
            str(tmp_path / "missing.json"),
        ]
    )
    assert ret_from_csv == 2

    # Invalid CLI args (SystemExit handling)
    ret_bad_args = main(["inspect"])
    assert ret_bad_args == 2


def test_convert_unsupported_format(tmp_path: Path) -> None:
    p = tmp_path / "test.parquet"
    pq.write_table(pa.table({"x": [1]}), str(p))
    with pytest.raises(ParquetToolError) as exc_info:
        convert(p, tmp_path / "out.parquet")
    assert exc_info.value.code == "unsupported_format"


def test_convert_unsupported_types(tmp_path: Path) -> None:
    p = tmp_path / "complex.parquet"
    # List column
    pq.write_table(pa.table({"arr": [[1, 2], [3]]}), str(p))
    with pytest.raises(ParquetToolError) as exc_info:
        convert(p, tmp_path / "out.csv")
    assert exc_info.value.code == "unsupported_type"


def test_from_csv_invalid_types_and_rows(tmp_path: Path) -> None:
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col\nnot_a_double\n", encoding="utf-8")
    with pytest.raises(ParquetToolError) as exc:
        from_csv(csv_file, tmp_path / "out.parquet", {"col": "double"})
    assert exc.value.code == "invalid_value"
    assert "line 2, column col: not a double" in str(exc.value)

    csv_file_bool = tmp_path / "test_bool.csv"
    csv_file_bool.write_text("flag\nmaybe\n", encoding="utf-8")
    with pytest.raises(ParquetToolError) as exc_bool:
        from_csv(csv_file_bool, tmp_path / "out.parquet", {"flag": "bool"})
    assert exc_bool.value.code == "invalid_value"
    assert "line 2, column flag: not a bool" in str(exc_bool.value)

    # Header mismatch
    with pytest.raises(ParquetToolError) as exc_header:
        from_csv(csv_file_bool, tmp_path / "out.parquet", {"different": "bool"})
    assert exc_header.value.code == "invalid_value"

    # Row length mismatch
    csv_mismatch = tmp_path / "mismatch.csv"
    csv_mismatch.write_text("a,b\n1\n", encoding="utf-8")
    with pytest.raises(ParquetToolError) as exc_len:
        from_csv(csv_mismatch, tmp_path / "out.parquet", {"a": "int64", "b": "int64"})
    assert exc_len.value.code == "invalid_value"

    # Unsupported schema type in from_csv
    with pytest.raises(ParquetToolError) as exc_unsupported:
        from_csv(csv_file, tmp_path / "out.parquet", {"col": "timestamp"})
    assert exc_unsupported.value.code == "unsupported_type"

    # Row limit exceeded in from_csv
    csv_large = tmp_path / "large.csv"
    csv_large.write_text("a\n1\n2\n3\n", encoding="utf-8")
    with pytest.raises(ParquetToolError) as exc_too_many:
        from_csv(csv_large, tmp_path / "out.parquet", {"a": "int64"}, max_rows=1)
    assert exc_too_many.value.code == "too_many_rows"


def test_validate_column_without_stats(tmp_path: Path) -> None:
    path = str(tmp_path / "nostats.parquet")
    table = pa.table({"x": [1, None, 3]})
    # write without statistics
    pq.write_table(table, path, write_statistics=False)

    info = inspect(path)
    assert info.columns[0].null_count is None
    assert info.columns[0].min is None
    assert info.columns[0].max is None

    issues = validate(path, {"x": ExpectedColumn("int64", nullable=False)})
    assert len(issues) == 1
    assert issues[0].code == "nullability"
    assert issues[0].detail == "1 null values"

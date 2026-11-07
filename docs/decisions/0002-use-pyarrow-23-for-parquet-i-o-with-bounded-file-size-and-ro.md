# Use PyArrow 23 for Parquet I/O with Bounded File-Size and Row Limits

Status: accepted (generated, pending human review)

## Context

Parquet files use Thrift metadata, complex encodings, and row group compression that the Python standard library cannot decode natively. Ad-hoc processing often loads full tables into memory, risking out-of-memory crashes on untrusted or large datasets.

## Decision

Adopt PyArrow as the single runtime dependency. Enforce pre-flight file-size validation using os.stat before PyArrow C++ parsing, cap streaming operations via configurable max_rows and batch_size, and wrap all internal C++ or OS errors in a typed ParquetToolError.

## Consequences

Memory consumption is bounded across inspection, validation, conversion, and streaming. Users gain high-performance Parquet handling with strict error codes and type safety.

# Project Record

## Objective
Provide a typed, bounded API and CLI tool to inspect Parquet schemas, validate file structures against business constraints (including data-driven nullability), and perform memory-bounded conversion to and from CSV/JSONL formats.

## Scope
- Metadata inspection (rows, row groups, column statistics).
- Validation of schema types and nullability constraints.
- Bounded streaming of records for processing.
- Conversion between Parquet and CSV/JSONL (with specific type support: `int64`, `double`, `string`, `bool`).
- CLI interface with machine-readable exit codes.

## Out of Scope
- Writing nested types (structs, maps, lists).
- Handling partitioned datasets.
- Support for S3, HDFS, or other cloud filesystems.
- Schema evolution or data repair utilities.

## Factory run u167b (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | gemini-3.8-flash | yes | 4766 | 13323 | 0 | 0 | 0.0268 |
| fix-1 | gemini-3.8-flash | no | 15457 | 193 | 0 | 11163 | 0.0132 |
| fix-2 | gemini-3.8-flash | no | 50636 | 411 | 0 | 280519 | 0.0606 |
| audit | gemini-3.1-flash-lite | no | 51589 | 195 | 0 | 136540 | 0.0166 |
| docs | gemini-3.1-flash-lite | no | 146318 | 1518 | 0 | 0 | 0.0389 |

Total: $0.1559. Prices: Anthropic list prices.

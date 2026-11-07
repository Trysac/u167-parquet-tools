# Technology Stack

- **Language**: Python >= 3.10
- **Core Dependencies**: `pyarrow` (>=23.0.1,<24) for reading Thrift metadata, encodings, and row group statistics.
- **Type Checking**: `mypy --strict` with `py.typed` export.
- **Linting & Formatting**: Ruff.
- **Testing**: pytest & pytest-cov.

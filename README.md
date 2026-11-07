# parquet-tools

[![PyPI version](https://img.shields.io/pypi/v/trysac-parquet-tools)](https://pypi.org/project/trysac-parquet-tools/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-parquet-tools)](LICENSE)
[![CI](https://github.com/Trysac/u167-parquet-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u167-parquet-tools/actions/workflows/ci.yml)

Inspect, validate and convert Parquet files: schema, row groups and column statistics, expected-schema checks with nullability, and bounded conversion to and from CSV or JSONL

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-parquet-tools
# or
uv add trysac-parquet-tools
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import parquet_tools

# normalize() trims surrounding whitespace and lower-cases the text.
print(parquet_tools.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    parquet_tools.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez

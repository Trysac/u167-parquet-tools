# Security

## Threat Model

### Defended
- **Memory Exhaustion**: The tool mitigates OOM failures by enforcing file size limits via `os.stat` before parsing, and by streaming records using batching and configurable `max_rows` thresholds.
- **Invalid Inputs**: Malformed or corrupt files are caught during the `pyarrow` open/read phase and sanitized into standard `ParquetToolError` exceptions with deterministic error codes (e.g., `invalid_parquet`).

### Not Defended
- **Malicious Binary Files**: Parquet files are binary files parsed directly by the underlying `pyarrow` C++ parser. As this parser is complex, we assume users only process files from trusted sources. No exploit-prevention for vulnerabilities within the C++ parser is provided.
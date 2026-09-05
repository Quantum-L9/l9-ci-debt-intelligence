from __future__ import annotations

from pathlib import Path

import duckdb

from .verify import verify_snapshot


def create_projection(
    *,
    snapshot_path: Path,
    database_path: Path,
) -> Path:
    verification = verify_snapshot(snapshot_path)
    if verification["status"] != "valid":
        raise RuntimeError("snapshot verification failed")
    parquet_glob = snapshot_path.resolve() / "partitions" / "**" / "*.parquet"
    database_path = database_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    try:
        # The glob has to be embedded as a literal rather than bound as a
        # parameter. This VIEW is persisted into database_path and read back by
        # later connections; DuckDB stores `getvariable('...')` unresolved, so a
        # SET VARIABLE / getvariable() form creates a view that works on this
        # connection and then fails on reopen with "read_parquet cannot take
        # NULL list as parameter". Doubling `'` is the complete escape for a
        # DuckDB single-quoted string literal (there is no backslash escape to
        # break out through), so the path cannot terminate the literal.
        parquet_literal = parquet_glob.as_posix().replace("'", "''")
        # nosemgrep: l9.baseline.python.sql-string-format
        connection.execute(
            f"""
            CREATE OR REPLACE VIEW corpus_records AS
            SELECT *
            FROM read_parquet('{parquet_literal}', union_by_name = true)
            ORDER BY record_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE snapshot_metadata AS
            SELECT
                ?::VARCHAR AS snapshot_id,
                ?::BIGINT AS record_count,
                ?::BIGINT AS partition_count
            """,
            [
                verification["snapshot_id"],
                verification["record_count"],
                verification["partition_count"],
            ],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return database_path

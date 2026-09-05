from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from l9_debt_intelligence.contracts.learning_columns import (
    INTEGER_COLUMNS,
    LEARNING_COLUMNS,
)

from .models import PartitionPlan, SnapshotRecord

_RECORD_COLUMNS: tuple[tuple[str, pa.DataType, bool], ...] = (
    ("record_id", pa.string(), False),
    ("source_event_id", pa.string(), False),
    ("producer_id", pa.string(), False),
    ("event_class", pa.string(), False),
    ("lifecycle_state", pa.string(), False),
    ("redaction_status", pa.string(), False),
    ("producer_contract", pa.string(), False),
    ("payload_content_hash", pa.string(), False),
    ("limitations_json", pa.string(), False),
    ("superseded_by", pa.string(), True),
    ("source_record_hash", pa.string(), False),
)

# A partition holds one row per stored row a record contributes, not one row per
# record. The record's own provenance columns come first and repeat across them;
# the rest are the column contract in `contracts.learning_columns`, appended in
# its declared order and written here without being interpreted -- this phase
# excludes the metrics derived from them.
#
# Analytics has always read those columns off these rows. This schema never
# carried them, so every fallback in that reader fired for every record from
# every producer and a record describing many findings collapsed to one opaque
# row.
#
# All of them are nullable by design. A static finding knows its rule and its
# file and nothing about repair effort or false-positive disposition; those
# arrive from other producers. An explicit null is the honest representation and
# the analytical rules forbid converting a missing value to zero.
SCHEMA = pa.schema(
    [
        pa.field(name, kind, nullable=nullable)
        for name, kind, nullable in _RECORD_COLUMNS
    ]
    + [
        pa.field(
            name,
            pa.int64() if name in INTEGER_COLUMNS else pa.string(),
            nullable=True,
        )
        for name in LEARNING_COLUMNS
    ]
)


def partition_row_count(plan: PartitionPlan) -> int:
    """Parquet rows this plan will write.

    One per stored row, and one for a record that has none, so a record never
    disappears from a snapshot because its derived rows are missing.
    """
    return sum(max(1, len(record.observations)) for record in plan.records)


def _rows(record: SnapshotRecord) -> list[Mapping[str, Any] | None]:
    return list(record.observations) if record.observations else [None]


def write_partition(
    destination: Path,
    plan: PartitionPlan,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns: dict[str, list[object]] = {name: [] for name in SCHEMA.names}
    for record in plan.records:
        for row in _rows(record):
            for name, _kind, _nullable in _RECORD_COLUMNS:
                columns[name].append(getattr(record, name))
            for name in LEARNING_COLUMNS:
                columns[name].append(row.get(name) if row is not None else None)
    table = pa.Table.from_pydict(columns, schema=SCHEMA)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
        version="2.6",
        row_group_size=max(1, table.num_rows),
        store_schema=True,
    )

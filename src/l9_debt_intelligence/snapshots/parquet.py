from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .models import PartitionPlan

SCHEMA = pa.schema(
    [
        pa.field("record_id", pa.string(), nullable=False),
        pa.field("source_event_id", pa.string(), nullable=False),
        pa.field("producer_id", pa.string(), nullable=False),
        pa.field("event_class", pa.string(), nullable=False),
        pa.field("lifecycle_state", pa.string(), nullable=False),
        pa.field("redaction_status", pa.string(), nullable=False),
        pa.field("producer_contract", pa.string(), nullable=False),
        pa.field("payload_content_hash", pa.string(), nullable=False),
        pa.field("limitations_json", pa.string(), nullable=False),
        pa.field("superseded_by", pa.string(), nullable=True),
        pa.field("source_record_hash", pa.string(), nullable=False),
    ]
)


def write_partition(
    destination: Path,
    plan: PartitionPlan,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns: dict[str, list[str | None]] = {
        "record_id": [],
        "source_event_id": [],
        "producer_id": [],
        "event_class": [],
        "lifecycle_state": [],
        "redaction_status": [],
        "producer_contract": [],
        "payload_content_hash": [],
        "limitations_json": [],
        "superseded_by": [],
        "source_record_hash": [],
    }
    for record in plan.records:
        columns["record_id"].append(record.record_id)
        columns["source_event_id"].append(record.source_event_id)
        columns["producer_id"].append(record.producer_id)
        columns["event_class"].append(record.event_class)
        columns["lifecycle_state"].append(record.lifecycle_state)
        columns["redaction_status"].append(record.redaction_status)
        columns["producer_contract"].append(record.producer_contract)
        columns["payload_content_hash"].append(record.payload_content_hash)
        columns["limitations_json"].append(record.limitations_json)
        columns["superseded_by"].append(record.superseded_by)
        columns["source_record_hash"].append(record.source_record_hash)
    table = pa.Table.from_pydict(columns, schema=SCHEMA)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
        version="2.6",
        row_group_size=max(1, len(plan.records)),
        store_schema=True,
    )

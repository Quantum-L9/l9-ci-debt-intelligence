"""The learning-observation column contract, owned by neither phase.

`schemas/intelligence/learning-observation.schema.json` names the dimensions
Phase 3 derives metrics from. Two phases have to agree on those names without
either owning the other: ingestion writes them, the snapshot carries them, and
analytics reads them.

The snapshot layer must carry them *without interpreting them*. The snapshot
contract (`.l9/snapshot-contract.yaml`) excludes recurrence metrics,
co-occurrence metrics and effort modelling from that phase, and
`tests/architecture/test_snapshot_boundary.py` enforces the exclusion by
substring. Naming these columns inside `snapshots/` would breach that boundary
for real and not merely by string match: the phase would then encode what the
values mean. So the names live here, the snapshot iterates them as opaque
columns, and the boundary keeps its teeth.

`tests/contracts/` pins this tuple against both the JSON schema and the Phase 3
dataclass, so the three cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "l9.learning-observation/v1"

#: Column order for any tabular projection of an observation. Fixed, because a
#: reordering would change every partition hash without changing any fact.
LEARNING_COLUMNS: tuple[str, ...] = (
    "occurrence_scope",
    "recurrence_fingerprint",
    "canonical_rule_id",
    "repository_identity",
    "component",
    "remediation_class",
    "effort_minutes",
    "validation_outcome",
    "false_positive_disposition",
    "pack_version",
)

#: Columns carrying an integer rather than a string. Missing stays null: the
#: analytical rules forbid converting an unknown effort to zero.
INTEGER_COLUMNS: frozenset[str] = frozenset({"effort_minutes"})

#: Without these an observation cannot be grouped or scoped, so it is not an
#: observation. Everything else is legitimately unknown.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "occurrence_scope",
    "recurrence_fingerprint",
)

#: Length of the grouping key, which is a sha256 digest.
FINGERPRINT_LENGTH = 64


class LearningColumnError(ValueError):
    """A stored observation does not satisfy the column contract."""


def coerce_row(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return one observation reduced to the column contract.

    Unknown keys are dropped rather than carried: a tabular partition has a
    fixed schema, and silently widening it on a producer's extra field would
    change every partition hash. Absent optional columns become null.
    """
    scope = document.get("occurrence_scope")
    if not isinstance(scope, str) or not scope:
        raise LearningColumnError("observation has no occurrence_scope")
    fingerprint = document.get("recurrence_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != FINGERPRINT_LENGTH:
        raise LearningColumnError("observation has no valid grouping key")

    row: dict[str, Any] = {}
    for column in LEARNING_COLUMNS:
        value = document.get(column)
        if column in INTEGER_COLUMNS:
            row[column] = value if isinstance(value, int) and value >= 0 else None
        else:
            row[column] = value if isinstance(value, str) and value else None
    return row


def sort_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Deterministic order for the rows belonging to one record.

    Row order must be a function of content, never of the order observations
    happened to be derived in, or two runs over the same corpus would write
    different partition bytes.
    """
    return tuple(str(row.get(column) or "") for column in LEARNING_COLUMNS)

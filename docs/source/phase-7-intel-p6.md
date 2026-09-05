The next phase is INTEL-P6: closed-loop effectiveness.

It adds the final feedback loop defined by the repository specification:

Core CI outcomes ─┐
LSP outcomes ─────┼→ validated outcome ingestion
repair outcomes ──┘
                         ↓
              pack/rule effectiveness
                         ↓
          drift and regression detection
                         ↓
       retain / investigate / rollback /
              retirement recommendation

Intelligence owns effectiveness measurement and recommendations, but it still cannot mutate Core governance, activate LSP packs, uninstall releases, or automatically retire artifacts. repo-spec.yaml The constellation contract also requires LSP telemetry to preserve canonical rule identity, active pack version, corpus snapshot, and finding semantics. repo-spec.yaml

Save this as build-phase-7.sh.

#!/usr/bin/env bash
set -euo pipefail
require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    printf 'INTEL-P6 requires INTEL-P5 file: %s\n' "$path" >&2
    exit 1
  fi
}
require_file ".l9/architecture.yaml"
require_file ".l9/publication-contract.yaml"
require_file "schemas/intelligence/defense-pack.schema.json"
require_file "src/l9_debt_intelligence/publication/verify.py"
require_file "src/l9_debt_intelligence/ingestion/storage.py"
mkdir -p \
  .github/workflows \
  docs/architecture/ADRs \
  schemas/intelligence \
  src/l9_debt_intelligence/effectiveness \
  tests/effectiveness \
  tests/fixtures/effectiveness
cat > .l9/effectiveness-contract.yaml <<'EOF'
schema: l9.intelligence-effectiveness-contract/v1
metadata:
  repository: Quantum-L9/l9-ci-debt-intelligence
  phase: INTEL-P6
  status: authoritative
purpose: >
  Measure the post-publication effectiveness, safety, and operational value of
  immutable defense packs using canonical CI, LSP, and repair outcome events.
sources:
  allowed:
    - l9-ci-core
    - l9-ci-debt-lsp
    - l9-ci-debt-resolver
    - l9-pr-repair
  required_identity:
    - event_id
    - producer_id
    - producer_contract
    - pack_id
    - pack_version
    - canonical_rule_id
    - outcome_class
    - observation_scope
    - observed_at
  optional_identity:
    - finding_id
    - repository_pseudonym
    - snapshot_identity
    - document_identity
    - policy_mode
    - latency_ms
    - effort_minutes
privacy:
  repository_identity: pseudonymous
  source_content: prohibited
  raw_logs: prohibited
  absolute_paths: prohibited
  secret_values: prohibited
  developer_identity: prohibited
outcome_classes:
  CI:
    - prevented_before_merge
    - detected_in_CI
    - escaped_detection
    - rule_not_evaluated
    - evaluation_incomplete
  LSP:
    - diagnostic_shown
    - diagnostic_accepted
    - diagnostic_dismissed
    - confirmed_false_positive
    - quick_fix_applied
    - quick_fix_reverted
    - rule_not_evaluated
    - evaluation_incomplete
  repair:
    - repair_succeeded
    - repair_failed
    - repair_partial
    - repair_rolled_back
    - outcome_unknown
unknown_semantics:
  rules:
    - Missing outcomes remain unknown.
    - Incomplete evaluation is not PASS.
    - Rule not evaluated is not rule success.
    - Missing latency is not zero latency.
    - Missing effort is not zero effort.
deduplication:
  identity:
    algorithm: SHA-256
    inputs:
      - producer_id
      - producer_contract
      - event_id
      - pack_id
      - canonical_rule_id
      - observation_scope
  duplicate_behavior: one canonical observation
measurement:
  minimum_sample_sizes:
    rule_recommendation: 20
    pack_recommendation: 100
  rule_metrics:
    - evaluation_count
    - known_outcome_count
    - unknown_outcome_count
    - prevention_count
    - detection_count
    - escape_count
    - false_positive_count
    - accepted_diagnostic_count
    - dismissed_diagnostic_count
    - quick_fix_applied_count
    - quick_fix_reverted_count
    - repair_success_count
    - repair_failure_count
    - prevention_ratio
    - escape_ratio
    - false_positive_ratio
    - quick_fix_revert_ratio
    - repair_success_ratio
    - p95_latency_ms
  pack_metrics:
    - active_rule_count
    - observed_rule_count
    - evaluation_count
    - prevention_ratio
    - escape_ratio
    - false_positive_ratio
    - unknown_ratio
    - p95_latency_ms
    - coverage_ratio
recommendations:
  states:
    - insufficient_evidence
    - retain
    - investigate
    - rollback_recommended
    - retirement_recommended
  default_thresholds:
    false_positive_ratio:
      investigate: 0.05
      rollback: 0.10
      retirement: 0.20
    escape_ratio:
      investigate: 0.10
      rollback: 0.20
    quick_fix_revert_ratio:
      investigate: 0.10
      rollback: 0.25
    unknown_ratio:
      investigate: 0.25
    p95_latency_ms:
      LSP_investigate: 200
      LSP_rollback: 1000
  authority:
    intelligence:
      - calculate metrics
      - detect drift
      - recommend retention
      - recommend investigation
      - recommend rollback
      - recommend retirement
    core:
      - select pack
      - change policy mode
      - perform CI rollback
    LSP:
      - activate explicit pack
      - perform editor rollback
    publication_maintainers:
      - retire published pack
drift:
  comparisons:
    - current pack against previous pack
    - current period against baseline period
  outputs:
    - absolute_delta
    - relative_delta
    - regression_state
  prohibition:
    - comparing incompatible rule identities
    - comparing different outcome definitions
    - treating missing baseline as zero
immutability:
  - outcome observations are append-only
  - corrections use correction events
  - effectiveness reports are content-addressed
  - recommendations identify exact evidence snapshots
  - recommendation changes create new reports
phase_7:
  includes:
    - canonical outcome events
    - CI outcome ingestion
    - LSP outcome ingestion
    - repair outcome ingestion
    - deterministic deduplication
    - rule effectiveness measurement
    - pack effectiveness measurement
    - drift comparison
    - rollback recommendations
    - retirement recommendations
    - effectiveness manifests
  excludes:
    - Core policy mutation
    - LSP activation
    - automatic rollback
    - automatic retirement
    - release deletion
    - source repository mutation
EOF
cat > schemas/intelligence/effectiveness-outcome.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/effectiveness-outcome/v1",
  "title": "L9 Defense Effectiveness Outcome",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "event_id",
    "producer_id",
    "producer_contract",
    "pack_id",
    "pack_version",
    "canonical_rule_id",
    "surface",
    "outcome_class",
    "observation_scope",
    "observed_at",
    "limitations"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.effectiveness-outcome/v1"
    },
    "event_id": {
      "type": "string",
      "minLength": 1
    },
    "producer_id": {
      "enum": [
        "Quantum-L9/l9-ci-core",
        "Quantum-L9/l9-ci-debt-lsp",
        "Quantum-L9/l9-ci-debt-resolver",
        "Quantum-L9/l9-pr-repair"
      ]
    },
    "producer_contract": {
      "type": "string",
      "minLength": 1
    },
    "pack_id": {
      "type": "string",
      "pattern": "^pack_[0-9a-f]{64}$"
    },
    "pack_version": {
      "type": "string",
      "minLength": 1
    },
    "canonical_rule_id": {
      "type": "string",
      "minLength": 1
    },
    "surface": {
      "enum": [
        "CI",
        "LSP",
        "repair"
      ]
    },
    "outcome_class": {
      "enum": [
        "prevented_before_merge",
        "detected_in_CI",
        "escaped_detection",
        "diagnostic_shown",
        "diagnostic_accepted",
        "diagnostic_dismissed",
        "confirmed_false_positive",
        "quick_fix_applied",
        "quick_fix_reverted",
        "repair_succeeded",
        "repair_failed",
        "repair_partial",
        "repair_rolled_back",
        "rule_not_evaluated",
        "evaluation_incomplete",
        "outcome_unknown"
      ]
    },
    "observation_scope": {
      "type": "string",
      "minLength": 1
    },
    "observed_at": {
      "type": "string",
      "format": "date-time"
    },
    "finding_id": {
      "type": ["string", "null"]
    },
    "repository_pseudonym": {
      "type": ["string", "null"],
      "pattern": "^(repo_[0-9a-f]{32}|null)$"
    },
    "snapshot_identity": {
      "type": ["string", "null"]
    },
    "document_identity": {
      "type": ["string", "null"]
    },
    "policy_mode": {
      "type": ["string", "null"],
      "enum": [
        "blocking",
        "advisory",
        "shadow",
        "disabled",
        null
      ]
    },
    "latency_ms": {
      "type": ["integer", "null"],
      "minimum": 0
    },
    "effort_minutes": {
      "type": ["integer", "null"],
      "minimum": 0
    },
    "limitations": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "uniqueItems": true
    }
  }
}
EOF
cat > schemas/intelligence/effectiveness-report.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/effectiveness-report/v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "report_id",
    "outcome_snapshot_hash",
    "pack_id",
    "pack_version",
    "observation_count",
    "rule_metrics",
    "pack_metrics",
    "recommendations",
    "limitations"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.effectiveness-report/v1"
    },
    "report_id": {
      "type": "string",
      "pattern": "^effect_[0-9a-f]{64}$"
    },
    "outcome_snapshot_hash": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$"
    },
    "pack_id": {
      "type": "string",
      "pattern": "^pack_[0-9a-f]{64}$"
    },
    "pack_version": {
      "type": "string"
    },
    "observation_count": {
      "type": "integer",
      "minimum": 0
    },
    "rule_metrics": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/ruleMetric"
      }
    },
    "pack_metrics": {
      "type": "object"
    },
    "recommendations": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/recommendation"
      }
    },
    "limitations": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "$defs": {
    "ruleMetric": {
      "type": "object",
      "required": [
        "canonical_rule_id",
        "evaluation_count",
        "known_outcome_count",
        "unknown_outcome_count",
        "prevention_count",
        "detection_count",
        "escape_count",
        "false_positive_count",
        "quick_fix_applied_count",
        "quick_fix_reverted_count",
        "repair_success_count",
        "repair_failure_count",
        "prevention_ratio",
        "escape_ratio",
        "false_positive_ratio",
        "quick_fix_revert_ratio",
        "repair_success_ratio",
        "p95_latency_ms"
      ]
    },
    "recommendation": {
      "type": "object",
      "required": [
        "scope",
        "identity",
        "state",
        "reasons",
        "evidence"
      ],
      "properties": {
        "scope": {
          "enum": [
            "rule",
            "pack"
          ]
        },
        "identity": {
          "type": "string"
        },
        "state": {
          "enum": [
            "insufficient_evidence",
            "retain",
            "investigate",
            "rollback_recommended",
            "retirement_recommended"
          ]
        },
        "reasons": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "evidence": {
          "type": "object"
        }
      }
    }
  }
}
EOF
cat > schemas/intelligence/effectiveness-drift.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/effectiveness-drift/v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "comparison_id",
    "baseline_report_id",
    "current_report_id",
    "pack_identity_compatible",
    "metric_deltas",
    "regression_state",
    "limitations"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.effectiveness-drift/v1"
    },
    "comparison_id": {
      "type": "string",
      "pattern": "^drift_[0-9a-f]{64}$"
    },
    "baseline_report_id": {
      "type": "string"
    },
    "current_report_id": {
      "type": "string"
    },
    "pack_identity_compatible": {
      "type": "boolean"
    },
    "metric_deltas": {
      "type": "object"
    },
    "regression_state": {
      "enum": [
        "insufficient_evidence",
        "stable",
        "improved",
        "degraded",
        "critical_regression"
      ]
    },
    "limitations": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  }
}
EOF
cat > src/l9_debt_intelligence/effectiveness/__init__.py <<'EOF'
"""Closed-loop effectiveness measurement for published defense packs."""
EOF
cat > src/l9_debt_intelligence/effectiveness/errors.py <<'EOF'
class EffectivenessError(RuntimeError):
    """Base effectiveness measurement failure."""
class OutcomeValidationError(EffectivenessError):
    """An outcome event violates the effectiveness contract."""
class EffectivenessVerificationError(EffectivenessError):
    """An effectiveness artifact failed integrity verification."""
EOF
cat > src/l9_debt_intelligence/effectiveness/models.py <<'EOF'
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
@dataclass(frozen=True)
class Outcome:
    event_id: str
    producer_id: str
    producer_contract: str
    pack_id: str
    pack_version: str
    canonical_rule_id: str
    surface: str
    outcome_class: str
    observation_scope: str
    observed_at: str
    finding_id: str | None
    repository_pseudonym: str | None
    snapshot_identity: str | None
    document_identity: str | None
    policy_mode: str | None
    latency_ms: int | None
    effort_minutes: int | None
    limitations: tuple[str, ...]
    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "l9.effectiveness-outcome/v1",
            "event_id": self.event_id,
            "producer_id": self.producer_id,
            "producer_contract": self.producer_contract,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "canonical_rule_id": self.canonical_rule_id,
            "surface": self.surface,
            "outcome_class": self.outcome_class,
            "observation_scope": self.observation_scope,
            "observed_at": self.observed_at,
            "finding_id": self.finding_id,
            "repository_pseudonym": self.repository_pseudonym,
            "snapshot_identity": self.snapshot_identity,
            "document_identity": self.document_identity,
            "policy_mode": self.policy_mode,
            "latency_ms": self.latency_ms,
            "effort_minutes": self.effort_minutes,
            "limitations": list(self.limitations),
        }
EOF
cat > src/l9_debt_intelligence/effectiveness/validation.py <<'EOF'
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from .errors import OutcomeValidationError
from .models import Outcome
SURFACE_OUTCOMES = {
    "CI": {
        "prevented_before_merge",
        "detected_in_CI",
        "escaped_detection",
        "rule_not_evaluated",
        "evaluation_incomplete",
    },
    "LSP": {
        "diagnostic_shown",
        "diagnostic_accepted",
        "diagnostic_dismissed",
        "confirmed_false_positive",
        "quick_fix_applied",
        "quick_fix_reverted",
        "rule_not_evaluated",
        "evaluation_incomplete",
    },
    "repair": {
        "repair_succeeded",
        "repair_failed",
        "repair_partial",
        "repair_rolled_back",
        "outcome_unknown",
    },
}
class OutcomeValidator:
    def __init__(self, schema_path: Path) -> None:
        schema = json.loads(
            schema_path.read_text(encoding="utf-8")
        )
        self.validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
    def validate(self, event: dict[str, Any]) -> Outcome:
        errors = sorted(
            self.validator.iter_errors(event),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            message = "; ".join(
                f"{'/'.join(map(str, error.absolute_path))}: "
                f"{error.message}"
                for error in errors
            )
            raise OutcomeValidationError(message)
        surface = event["surface"]
        outcome_class = event["outcome_class"]
        if outcome_class not in SURFACE_OUTCOMES[surface]:
            raise OutcomeValidationError(
                f"{outcome_class} is not valid for surface {surface}"
            )
        return Outcome(
            event_id=event["event_id"],
            producer_id=event["producer_id"],
            producer_contract=event["producer_contract"],
            pack_id=event["pack_id"],
            pack_version=event["pack_version"],
            canonical_rule_id=event["canonical_rule_id"],
            surface=surface,
            outcome_class=outcome_class,
            observation_scope=event["observation_scope"],
            observed_at=event["observed_at"],
            finding_id=event.get("finding_id"),
            repository_pseudonym=event.get(
                "repository_pseudonym"
            ),
            snapshot_identity=event.get("snapshot_identity"),
            document_identity=event.get("document_identity"),
            policy_mode=event.get("policy_mode"),
            latency_ms=event.get("latency_ms"),
            effort_minutes=event.get("effort_minutes"),
            limitations=tuple(
                sorted(set(event.get("limitations", [])))
            ),
        )
EOF
cat > src/l9_debt_intelligence/effectiveness/storage.py <<'EOF'
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
from l9_debt_intelligence.contracts.canonical import canonical_json
from l9_debt_intelligence.snapshots.hashing import (
    namespaced_document_hash,
    sha256_bytes,
)
from .models import Outcome
def outcome_identity(outcome: Outcome) -> str:
    return namespaced_document_hash(
        "outcome_",
        {
            "producer_id": outcome.producer_id,
            "producer_contract": outcome.producer_contract,
            "event_id": outcome.event_id,
            "pack_id": outcome.pack_id,
            "canonical_rule_id": outcome.canonical_rule_id,
            "observation_scope": outcome.observation_scope,
        },
    )
class OutcomeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.records = self.root / "records"
        self.ledger = self.root / "ledger/outcomes.jsonl"
    def initialize(self) -> None:
        self.records.mkdir(parents=True, exist_ok=True)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.ledger.touch(exist_ok=True)
    def ingest(self, outcome: Outcome) -> dict[str, Any]:
        self.initialize()
        identity = outcome_identity(outcome)
        destination = self.records / f"{identity}.json"
        document = {
            "outcome_id": identity,
            **outcome.as_dict(),
        }
        encoded = canonical_json(document) + b"\n"
        status = "accepted"
        if destination.exists():
            if destination.read_bytes() != encoded:
                raise RuntimeError(
                    f"outcome identity collision: {identity}"
                )
            status = "duplicate"
        else:
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        observation = {
            "schema_version": "l9.effectiveness-ledger-entry/v1",
            "outcome_id": identity,
            "status": status,
            "event_id": outcome.event_id,
            "pack_id": outcome.pack_id,
            "canonical_rule_id": outcome.canonical_rule_id,
            "observed_at": outcome.observed_at,
            "document_sha256": sha256_bytes(
                canonical_json(document)
            ),
        }
        with self.ledger.open("ab") as stream:
            stream.write(canonical_json(observation) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return {
            "schema_version": "l9.effectiveness-ingestion-result/v1",
            "status": status,
            "outcome_id": identity,
            "pack_id": outcome.pack_id,
            "canonical_rule_id": outcome.canonical_rule_id,
        }
    def load(
        self,
        *,
        pack_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        self.initialize()
        records: list[dict[str, Any]] = []
        for path in sorted(self.records.glob("outcome_*.json")):
            value = json.loads(
                path.read_text(encoding="utf-8")
            )
            if pack_id and value.get("pack_id") != pack_id:
                continue
            records.append(value)
        return tuple(
            sorted(
                records,
                key=lambda item: item["outcome_id"],
            )
        )
EOF
cat > src/l9_debt_intelligence/effectiveness/metrics.py <<'EOF'
from __future__ import annotations
import math
from collections import defaultdict
from typing import Any, Iterable
UNKNOWN_OUTCOMES = {
    "rule_not_evaluated",
    "evaluation_incomplete",
    "outcome_unknown",
}
PREVENTION_OUTCOMES = {
    "prevented_before_merge",
    "diagnostic_accepted",
}
DETECTION_OUTCOMES = {
    "detected_in_CI",
    "diagnostic_shown",
}
ESCAPE_OUTCOMES = {
    "escaped_detection",
}
FALSE_POSITIVE_OUTCOMES = {
    "confirmed_false_positive",
}
REPAIR_SUCCESS = {
    "repair_succeeded",
}
REPAIR_FAILURE = {
    "repair_failed",
    "repair_rolled_back",
}
def ratio(
    numerator: int,
    denominator: int,
) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 12)
def p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(
        0,
        math.ceil(len(ordered) * 0.95) - 1,
    )
    return ordered[index]
def rule_metrics(
    outcomes: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome["canonical_rule_id"]].append(outcome)
    rows: list[dict[str, Any]] = []
    for rule_id in sorted(grouped):
        items = grouped[rule_id]
        classes = [
            item["outcome_class"]
            for item in items
        ]
        unknown_count = sum(
            value in UNKNOWN_OUTCOMES
            for value in classes
        )
        known_count = len(classes) - unknown_count
        prevention = sum(
            value in PREVENTION_OUTCOMES
            for value in classes
        )
        detection = sum(
            value in DETECTION_OUTCOMES
            for value in classes
        )
        escape = sum(
            value in ESCAPE_OUTCOMES
            for value in classes
        )
        false_positive = sum(
            value in FALSE_POSITIVE_OUTCOMES
            for value in classes
        )
        accepted = classes.count("diagnostic_accepted")
        dismissed = classes.count("diagnostic_dismissed")
        quick_fix_applied = classes.count(
            "quick_fix_applied"
        )
        quick_fix_reverted = classes.count(
            "quick_fix_reverted"
        )
        repair_success = sum(
            value in REPAIR_SUCCESS
            for value in classes
        )
        repair_failure = sum(
            value in REPAIR_FAILURE
            for value in classes
        )
        evaluated_for_prevention = (
            prevention + detection + escape
        )
        diagnostic_classified = (
            accepted + dismissed + false_positive
        )
        quick_fix_classified = (
            quick_fix_applied + quick_fix_reverted
        )
        repair_classified = repair_success + repair_failure
        latencies = [
            item["latency_ms"]
            for item in items
            if isinstance(item.get("latency_ms"), int)
        ]
        rows.append(
            {
                "canonical_rule_id": rule_id,
                "evaluation_count": len(items),
                "known_outcome_count": known_count,
                "unknown_outcome_count": unknown_count,
                "prevention_count": prevention,
                "detection_count": detection,
                "escape_count": escape,
                "false_positive_count": false_positive,
                "accepted_diagnostic_count": accepted,
                "dismissed_diagnostic_count": dismissed,
                "quick_fix_applied_count": quick_fix_applied,
                "quick_fix_reverted_count": quick_fix_reverted,
                "repair_success_count": repair_success,
                "repair_failure_count": repair_failure,
                "prevention_ratio": ratio(
                    prevention,
                    evaluated_for_prevention,
                ),
                "escape_ratio": ratio(
                    escape,
                    evaluated_for_prevention,
                ),
                "false_positive_ratio": ratio(
                    false_positive,
                    diagnostic_classified,
                ),
                "quick_fix_revert_ratio": ratio(
                    quick_fix_reverted,
                    quick_fix_classified,
                ),
                "repair_success_ratio": ratio(
                    repair_success,
                    repair_classified,
                ),
                "p95_latency_ms": p95(latencies),
            }
        )
    return rows
def weighted_ratio(
    rows: list[dict[str, Any]],
    numerator: str,
    denominator_fields: tuple[str, ...],
) -> float | None:
    numerator_total = sum(
        int(row[numerator])
        for row in rows
    )
    denominator_total = sum(
        sum(int(row[field]) for field in denominator_fields)
        for row in rows
    )
    return ratio(numerator_total, denominator_total)
def pack_metrics(
    *,
    rows: list[dict[str, Any]],
    active_rule_count: int,
) -> dict[str, Any]:
    evaluation_count = sum(
        int(row["evaluation_count"])
        for row in rows
    )
    unknown_count = sum(
        int(row["unknown_outcome_count"])
        for row in rows
    )
    latencies = [
        int(row["p95_latency_ms"])
        for row in rows
        if isinstance(row["p95_latency_ms"], int)
    ]
    return {
        "active_rule_count": active_rule_count,
        "observed_rule_count": len(rows),
        "evaluation_count": evaluation_count,
        "prevention_ratio": weighted_ratio(
            rows,
            "prevention_count",
            (
                "prevention_count",
                "detection_count",
                "escape_count",
            ),
        ),
        "escape_ratio": weighted_ratio(
            rows,
            "escape_count",
            (
                "prevention_count",
                "detection_count",
                "escape_count",
            ),
        ),
        "false_positive_ratio": weighted_ratio(
            rows,
            "false_positive_count",
            (
                "accepted_diagnostic_count",
                "dismissed_diagnostic_count",
                "false_positive_count",
            ),
        ),
        "unknown_ratio": ratio(
            unknown_count,
            evaluation_count,
        ),
        "p95_latency_ms": p95(latencies),
        "coverage_ratio": ratio(
            len(rows),
            active_rule_count,
        ),
    }
EOF
cat > src/l9_debt_intelligence/effectiveness/recommendations.py <<'EOF'
from __future__ import annotations
from typing import Any
MINIMUM_RULE_SAMPLE = 20
MINIMUM_PACK_SAMPLE = 100
def rule_recommendation(
    row: dict[str, Any],
) -> dict[str, Any]:
    count = int(row["evaluation_count"])
    reasons: list[str] = []
    state = "retain"
    if count < MINIMUM_RULE_SAMPLE:
        state = "insufficient_evidence"
        reasons.append(
            f"requires at least {MINIMUM_RULE_SAMPLE} observations"
        )
    else:
        false_positive = row["false_positive_ratio"]
        escape = row["escape_ratio"]
        revert = row["quick_fix_revert_ratio"]
        latency = row["p95_latency_ms"]
        if (
            false_positive is not None
            and false_positive >= 0.20
        ):
            state = "retirement_recommended"
            reasons.append(
                "false-positive ratio exceeds retirement threshold"
            )
        elif (
            false_positive is not None
            and false_positive >= 0.10
        ):
            state = "rollback_recommended"
            reasons.append(
                "false-positive ratio exceeds rollback threshold"
            )
        elif escape is not None and escape >= 0.20:
            state = "rollback_recommended"
            reasons.append(
                "escape ratio exceeds rollback threshold"
            )
        elif revert is not None and revert >= 0.25:
            state = "rollback_recommended"
            reasons.append(
                "quick-fix revert ratio exceeds rollback threshold"
            )
        elif (
            (false_positive is not None and false_positive >= 0.05)
            or (escape is not None and escape >= 0.10)
            or (revert is not None and revert >= 0.10)
            or (latency is not None and latency > 200)
        ):
            state = "investigate"
            reasons.append(
                "one or more effectiveness thresholds require review"
            )
        else:
            reasons.append(
                "observed effectiveness remains within thresholds"
            )
    return {
        "scope": "rule",
        "identity": row["canonical_rule_id"],
        "state": state,
        "reasons": reasons,
        "evidence": {
            "evaluation_count": count,
            "false_positive_ratio": row[
                "false_positive_ratio"
            ],
            "escape_ratio": row["escape_ratio"],
            "quick_fix_revert_ratio": row[
                "quick_fix_revert_ratio"
            ],
            "p95_latency_ms": row["p95_latency_ms"],
        },
    }
def pack_recommendation(
    *,
    pack_id: str,
    metrics: dict[str, Any],
    rule_recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    evaluation_count = int(metrics["evaluation_count"])
    reasons: list[str] = []
    if evaluation_count < MINIMUM_PACK_SAMPLE:
        state = "insufficient_evidence"
        reasons.append(
            f"requires at least {MINIMUM_PACK_SAMPLE} observations"
        )
    else:
        states = {
            recommendation["state"]
            for recommendation in rule_recommendations
        }
        if "retirement_recommended" in states:
            state = "rollback_recommended"
            reasons.append(
                "one or more active rules have retirement recommendations"
            )
        elif "rollback_recommended" in states:
            state = "rollback_recommended"
            reasons.append(
                "one or more active rules exceed rollback thresholds"
            )
        elif (
            "investigate" in states
            or (
                metrics["unknown_ratio"] is not None
                and metrics["unknown_ratio"] >= 0.25
            )
        ):
            state = "investigate"
            reasons.append(
                "pack effectiveness or coverage requires investigation"
            )
        else:
            state = "retain"
            reasons.append(
                "pack effectiveness remains within configured thresholds"
            )
    return {
        "scope": "pack",
        "identity": pack_id,
        "state": state,
        "reasons": reasons,
        "evidence": metrics,
    }
EOF
cat > src/l9_debt_intelligence/effectiveness/builder.py <<'EOF'
from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from l9_debt_intelligence.contracts.canonical import canonical_json
from l9_debt_intelligence.snapshots.hashing import (
    namespaced_document_hash,
    sha256_bytes,
)
from .metrics import pack_metrics, rule_metrics
from .recommendations import (
    pack_recommendation,
    rule_recommendation,
)
from .storage import OutcomeStore
def load_pack(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "l9.debt-defense/v1":
        raise ValueError("unsupported defense-pack schema")
    return value
def build_effectiveness_report(
    *,
    store_root: Path,
    defense_pack_path: Path,
    reports_root: Path,
) -> dict[str, Any]:
    pack = load_pack(defense_pack_path)
    store = OutcomeStore(store_root)
    outcomes = store.load(pack_id=pack["pack_id"])
    outcome_documents = [
        {
            key: value
            for key, value in outcome.items()
            if key != "observed_at"
        }
        for outcome in outcomes
    ]
    outcome_snapshot_hash = sha256_bytes(
        canonical_json(outcome_documents)
    )
    rows = rule_metrics(outcomes)
    metrics = pack_metrics(
        rows=rows,
        active_rule_count=len(pack["rules"]),
    )
    rule_recommendations = [
        rule_recommendation(row)
        for row in rows
    ]
    recommendation_rows = [
        *rule_recommendations,
        pack_recommendation(
            pack_id=pack["pack_id"],
            metrics=metrics,
            rule_recommendations=rule_recommendations,
        ),
    ]
    limitations: list[str] = []
    if not outcomes:
        limitations.append(
            "no effectiveness outcomes were available"
        )
    if metrics["coverage_ratio"] != 1.0:
        limitations.append(
            "not all active rules have effectiveness observations"
        )
    identity = {
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "outcome_snapshot_hash": outcome_snapshot_hash,
        "rule_metrics": rows,
        "pack_metrics": metrics,
        "recommendations": recommendation_rows,
    }
    report_id = namespaced_document_hash(
        "effect_",
        identity,
    )
    report = {
        "schema_version": "l9.effectiveness-report/v1",
        "report_id": report_id,
        "outcome_snapshot_hash": outcome_snapshot_hash,
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "observation_count": len(outcomes),
        "rule_metrics": rows,
        "pack_metrics": metrics,
        "recommendations": recommendation_rows,
        "limitations": limitations,
    }
    reports_root = reports_root.resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    destination = reports_root / report_id
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{report_id}.",
            dir=reports_root,
        )
    )
    try:
        report_path = temporary / "effectiveness-report.json"
        report_path.write_bytes(
            canonical_json(report) + b"\n"
        )
        manifest_document = {
            "schema_version": "l9.effectiveness-manifest/v1",
            "report_id": report_id,
            "pack_id": pack["pack_id"],
            "pack_version": pack["version"],
            "outcome_snapshot_hash": outcome_snapshot_hash,
            "report_sha256": sha256_bytes(
                canonical_json(report)
            ),
            "observation_count": len(outcomes),
        }
        (temporary / "manifest.json").write_bytes(
            canonical_json(manifest_document) + b"\n"
        )
        if destination.exists():
            existing = json.loads(
                (
                    destination / "effectiveness-report.json"
                ).read_text(encoding="utf-8")
            )
            if existing != report:
                raise RuntimeError(
                    "effectiveness report identity collision"
                )
            shutil.rmtree(temporary)
        else:
            os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "schema_version": "l9.effectiveness-build-result/v1",
        "report_id": report_id,
        "report_path": (
            destination / "effectiveness-report.json"
        ).as_posix(),
        "manifest_path": (
            destination / "manifest.json"
        ).as_posix(),
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "observation_count": len(outcomes),
    }
EOF
cat > src/l9_debt_intelligence/effectiveness/drift.py <<'EOF'
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from l9_debt_intelligence.snapshots.hashing import (
    namespaced_document_hash,
)
METRICS = (
    "prevention_ratio",
    "escape_ratio",
    "false_positive_ratio",
    "unknown_ratio",
    "coverage_ratio",
    "p95_latency_ms",
)
def delta(
    baseline: float | int | None,
    current: float | int | None,
) -> dict[str, float | None]:
    if baseline is None or current is None:
        return {
            "absolute_delta": None,
            "relative_delta": None,
        }
    absolute = float(current) - float(baseline)
    relative = (
        absolute / float(baseline)
        if float(baseline) != 0
        else None
    )
    return {
        "absolute_delta": round(absolute, 12),
        "relative_delta": (
            round(relative, 12)
            if relative is not None
            else None
        ),
    }
def compare_reports(
    *,
    baseline_path: Path,
    current_path: Path,
) -> dict[str, Any]:
    baseline = json.loads(
        baseline_path.read_text(encoding="utf-8")
    )
    current = json.loads(
        current_path.read_text(encoding="utf-8")
    )
    compatible = (
        baseline["pack_id"] == current["pack_id"]
    )
    limitations: list[str] = []
    if not compatible:
        limitations.append(
            "pack identities differ; comparison is informational only"
        )
    metric_deltas = {
        metric: delta(
            baseline["pack_metrics"].get(metric),
            current["pack_metrics"].get(metric),
        )
        for metric in METRICS
    }
    if (
        baseline["observation_count"] == 0
        or current["observation_count"] == 0
    ):
        state = "insufficient_evidence"
    else:
        false_positive_delta = metric_deltas[
            "false_positive_ratio"
        ]["absolute_delta"]
        escape_delta = metric_deltas[
            "escape_ratio"
        ]["absolute_delta"]
        latency_delta = metric_deltas[
            "p95_latency_ms"
        ]["absolute_delta"]
        prevention_delta = metric_deltas[
            "prevention_ratio"
        ]["absolute_delta"]
        if (
            (false_positive_delta is not None
             and false_positive_delta >= 0.10)
            or (escape_delta is not None
                and escape_delta >= 0.15)
            or (latency_delta is not None
                and latency_delta >= 800)
        ):
            state = "critical_regression"
        elif (
            (false_positive_delta is not None
             and false_positive_delta >= 0.03)
            or (escape_delta is not None
                and escape_delta >= 0.05)
            or (latency_delta is not None
                and latency_delta >= 100)
        ):
            state = "degraded"
        elif (
            prevention_delta is not None
            and prevention_delta >= 0.05
        ):
            state = "improved"
        else:
            state = "stable"
    identity = {
        "baseline_report_id": baseline["report_id"],
        "current_report_id": current["report_id"],
        "metric_deltas": metric_deltas,
    }
    return {
        "schema_version": "l9.effectiveness-drift/v1",
        "comparison_id": namespaced_document_hash(
            "drift_",
            identity,
        ),
        "baseline_report_id": baseline["report_id"],
        "current_report_id": current["report_id"],
        "pack_identity_compatible": compatible,
        "metric_deltas": metric_deltas,
        "regression_state": state,
        "limitations": limitations,
    }
EOF
cat > src/l9_debt_intelligence/effectiveness/verify.py <<'EOF'
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from l9_debt_intelligence.contracts.canonical import canonical_json
from l9_debt_intelligence.snapshots.hashing import sha256_bytes
from .errors import EffectivenessVerificationError
def verify_effectiveness_report(
    report_directory: Path,
) -> dict[str, Any]:
    report_directory = report_directory.resolve()
    report_path = (
        report_directory / "effectiveness-report.json"
    )
    manifest_path = report_directory / "manifest.json"
    if not report_path.is_file() or not manifest_path.is_file():
        raise EffectivenessVerificationError(
            "effectiveness report or manifest is missing"
        )
    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    if report["report_id"] != report_directory.name:
        raise EffectivenessVerificationError(
            "report directory identity mismatch"
        )
    if manifest["report_id"] != report["report_id"]:
        raise EffectivenessVerificationError(
            "manifest report identity mismatch"
        )
    actual_hash = sha256_bytes(canonical_json(report))
    if actual_hash != manifest["report_sha256"]:
        raise EffectivenessVerificationError(
            "effectiveness report hash mismatch"
        )
    if (
        manifest["outcome_snapshot_hash"]
        != report["outcome_snapshot_hash"]
    ):
        raise EffectivenessVerificationError(
            "outcome snapshot lineage mismatch"
        )
    return {
        "schema_version": "l9.effectiveness-verification/v1",
        "status": "valid",
        "report_id": report["report_id"],
        "pack_id": report["pack_id"],
        "pack_version": report["pack_version"],
        "observation_count": report["observation_count"],
        "report_sha256": actual_hash,
    }
EOF
python3 - <<'PY'
from pathlib import Path
path = Path("src/l9_debt_intelligence/cli.py")
text = path.read_text(encoding="utf-8")
anchor = (
    "from .publication.verify import verify_publication\n"
)
replacement = """from .publication.verify import verify_publication
from .effectiveness.builder import build_effectiveness_report
from .effectiveness.drift import compare_reports
from .effectiveness.storage import OutcomeStore
from .effectiveness.validation import OutcomeValidator
from .effectiveness.verify import verify_effectiveness_report
"""
if replacement not in text:
    if anchor not in text:
        raise SystemExit("unexpected CLI imports")
    text = text.replace(anchor, replacement)
parser_anchor = """    retire.add_argument("--output", type=Path)
    return parser
"""
parser_replacement = """    retire.add_argument("--output", type=Path)
    ingest_outcome = commands.add_parser(
        "ingest-effectiveness-outcome",
        help="Validate and ingest one CI, LSP, or repair outcome.",
    )
    ingest_outcome.add_argument("event", type=Path)
    ingest_outcome.add_argument(
        "--store-root",
        type=Path,
        required=True,
    )
    ingest_outcome.add_argument(
        "--schema",
        type=Path,
        default=repository_root()
        / "schemas/intelligence/effectiveness-outcome.schema.json",
    )
    ingest_outcome.add_argument("--output", type=Path)
    build_effectiveness = commands.add_parser(
        "build-effectiveness-report",
        help="Build closed-loop effectiveness metrics.",
    )
    build_effectiveness.add_argument(
        "--store-root",
        type=Path,
        required=True,
    )
    build_effectiveness.add_argument(
        "--defense-pack",
        type=Path,
        required=True,
    )
    build_effectiveness.add_argument(
        "--reports-root",
        type=Path,
        required=True,
    )
    build_effectiveness.add_argument("--output", type=Path)
    verify_effectiveness = commands.add_parser(
        "verify-effectiveness-report",
        help="Verify an effectiveness report.",
    )
    verify_effectiveness.add_argument(
        "report_directory",
        type=Path,
    )
    verify_effectiveness.add_argument("--output", type=Path)
    compare_effectiveness = commands.add_parser(
        "compare-effectiveness",
        help="Compare baseline and current effectiveness reports.",
    )
    compare_effectiveness.add_argument(
        "--baseline",
        type=Path,
        required=True,
    )
    compare_effectiveness.add_argument(
        "--current",
        type=Path,
        required=True,
    )
    compare_effectiveness.add_argument("--output", type=Path)
    return parser
"""
if parser_replacement not in text:
    if parser_anchor not in text:
        raise SystemExit("unexpected CLI parser")
    text = text.replace(parser_anchor, parser_replacement)
dispatcher_anchor = """        elif arguments.command == "retire-defense-pack":
            import datetime as dt
            document = retire_pack(
                publication_manifest_path=(
                    arguments.publication_manifest
                ),
                reason=arguments.reason,
                issuer=arguments.issuer,
                replacement_version=(
                    arguments.replacement_version
                ),
                retired_at=dt.datetime.now(
                    dt.timezone.utc
                ),
                ledger_path=arguments.ledger,
            )
            exit_code = 0
        else:
            return 2
"""
dispatcher_replacement = """        elif arguments.command == "retire-defense-pack":
            import datetime as dt
            document = retire_pack(
                publication_manifest_path=(
                    arguments.publication_manifest
                ),
                reason=arguments.reason,
                issuer=arguments.issuer,
                replacement_version=(
                    arguments.replacement_version
                ),
                retired_at=dt.datetime.now(
                    dt.timezone.utc
                ),
                ledger_path=arguments.ledger,
            )
            exit_code = 0
        elif arguments.command == "ingest-effectiveness-outcome":
            event = json.loads(
                arguments.event.read_text(encoding="utf-8")
            )
            if not isinstance(event, dict):
                raise ValueError(
                    "effectiveness event must be an object"
                )
            validator = OutcomeValidator(arguments.schema)
            outcome = validator.validate(event)
            store = OutcomeStore(arguments.store_root)
            document = store.ingest(outcome)
            exit_code = 0
        elif arguments.command == "build-effectiveness-report":
            document = build_effectiveness_report(
                store_root=arguments.store_root,
                defense_pack_path=arguments.defense_pack,
                reports_root=arguments.reports_root,
            )
            exit_code = 0
        elif arguments.command == "verify-effectiveness-report":
            document = verify_effectiveness_report(
                arguments.report_directory
            )
            exit_code = 0
        elif arguments.command == "compare-effectiveness":
            document = compare_reports(
                baseline_path=arguments.baseline,
                current_path=arguments.current,
            )
            exit_code = 0
        else:
            return 2
"""
if dispatcher_replacement not in text:
    if dispatcher_anchor not in text:
        raise SystemExit("unexpected CLI dispatcher")
    text = text.replace(
        dispatcher_anchor,
        dispatcher_replacement,
    )
path.write_text(text, encoding="utf-8")
PY
cat > tests/fixtures/effectiveness/lsp-outcome.json <<'EOF'
{
  "schema_version": "l9.effectiveness-outcome/v1",
  "event_id": "lsp-observation-100",
  "producer_id": "Quantum-L9/l9-ci-debt-lsp",
  "producer_contract": "l9.lsp-diagnostic-outcome/v1",
  "pack_id": "pack_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "pack_version": "1.0.0",
  "canonical_rule_id": "l9.debt.example-rule",
  "surface": "LSP",
  "outcome_class": "diagnostic_accepted",
  "observation_scope": "document-session-100",
  "observed_at": "2026-07-17T12:00:00Z",
  "finding_id": "finding-example-100",
  "repository_pseudonym": "repo_0123456789abcdef0123456789abcdef",
  "snapshot_identity": null,
  "document_identity": "document-sha256-example",
  "policy_mode": "advisory",
  "latency_ms": 42,
  "effort_minutes": null,
  "limitations": []
}
EOF
cat > tests/fixtures/effectiveness/ci-outcome.json <<'EOF'
{
  "schema_version": "l9.effectiveness-outcome/v1",
  "event_id": "ci-observation-100",
  "producer_id": "Quantum-L9/l9-ci-core",
  "producer_contract": "l9.core-rule-outcome/v1",
  "pack_id": "pack_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "pack_version": "1.0.0",
  "canonical_rule_id": "l9.debt.example-rule",
  "surface": "CI",
  "outcome_class": "prevented_before_merge",
  "observation_scope": "run-100",
  "observed_at": "2026-07-17T12:01:00Z",
  "finding_id": "finding-example-100",
  "repository_pseudonym": "repo_0123456789abcdef0123456789abcdef",
  "snapshot_identity": "snapshot-example",
  "document_identity": null,
  "policy_mode": "blocking",
  "latency_ms": 800,
  "effort_minutes": null,
  "limitations": []
}
EOF
cat > tests/effectiveness/test_validation.py <<'EOF'
from __future__ import annotations
import json
import unittest
from pathlib import Path
from l9_debt_intelligence.effectiveness.errors import (
    OutcomeValidationError,
)
from l9_debt_intelligence.effectiveness.validation import (
    OutcomeValidator,
)
ROOT = Path(__file__).resolve().parents[2]
class OutcomeValidationTests(unittest.TestCase):
    def validator(self) -> OutcomeValidator:
        return OutcomeValidator(
            ROOT
            / "schemas/intelligence/effectiveness-outcome.schema.json"
        )
    def test_valid_lsp_outcome(self) -> None:
        event = json.loads(
            (
                ROOT
                / "tests/fixtures/effectiveness/lsp-outcome.json"
            ).read_text(encoding="utf-8")
        )
        outcome = self.validator().validate(event)
        self.assertEqual("LSP", outcome.surface)
        self.assertEqual(
            "diagnostic_accepted",
            outcome.outcome_class,
        )
    def test_surface_mismatch_is_rejected(self) -> None:
        event = json.loads(
            (
                ROOT
                / "tests/fixtures/effectiveness/lsp-outcome.json"
            ).read_text(encoding="utf-8")
        )
        event["outcome_class"] = "repair_succeeded"
        with self.assertRaises(OutcomeValidationError):
            self.validator().validate(event)
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/effectiveness/test_storage.py <<'EOF'
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from l9_debt_intelligence.effectiveness.storage import OutcomeStore
from l9_debt_intelligence.effectiveness.validation import (
    OutcomeValidator,
)
ROOT = Path(__file__).resolve().parents[2]
class OutcomeStorageTests(unittest.TestCase):
    def test_duplicate_delivery_is_idempotent(self) -> None:
        validator = OutcomeValidator(
            ROOT
            / "schemas/intelligence/effectiveness-outcome.schema.json"
        )
        event = json.loads(
            (
                ROOT
                / "tests/fixtures/effectiveness/lsp-outcome.json"
            ).read_text(encoding="utf-8")
        )
        outcome = validator.validate(event)
        with tempfile.TemporaryDirectory() as directory:
            store = OutcomeStore(Path(directory))
            first = store.ingest(outcome)
            second = store.ingest(outcome)
            self.assertEqual("accepted", first["status"])
            self.assertEqual("duplicate", second["status"])
            self.assertEqual(
                first["outcome_id"],
                second["outcome_id"],
            )
            self.assertEqual(1, len(store.load()))
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/effectiveness/test_metrics.py <<'EOF'
from __future__ import annotations
import unittest
from l9_debt_intelligence.effectiveness.metrics import (
    pack_metrics,
    rule_metrics,
)
def outcome(
    outcome_class: str,
    *,
    latency: int | None = None,
) -> dict:
    return {
        "canonical_rule_id": "l9.debt.rule-1",
        "outcome_class": outcome_class,
        "latency_ms": latency,
    }
class EffectivenessMetricTests(unittest.TestCase):
    def test_unknown_is_not_success(self) -> None:
        rows = rule_metrics(
            [
                outcome("prevented_before_merge"),
                outcome("evaluation_incomplete"),
            ]
        )
        row = rows[0]
        self.assertEqual(1, row["prevention_count"])
        self.assertEqual(1, row["unknown_outcome_count"])
        self.assertEqual(1.0, row["prevention_ratio"])
    def test_false_positive_ratio_uses_classified_diagnostics(self) -> None:
        rows = rule_metrics(
            [
                outcome("diagnostic_accepted"),
                outcome("confirmed_false_positive"),
                outcome("evaluation_incomplete"),
            ]
        )
        self.assertEqual(
            0.5,
            rows[0]["false_positive_ratio"],
        )
    def test_pack_coverage_is_explicit(self) -> None:
        rows = rule_metrics(
            [outcome("diagnostic_accepted")]
        )
        metrics = pack_metrics(
            rows=rows,
            active_rule_count=4,
        )
        self.assertEqual(0.25, metrics["coverage_ratio"])
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/effectiveness/test_recommendations.py <<'EOF'
from __future__ import annotations
import unittest
from l9_debt_intelligence.effectiveness.recommendations import (
    rule_recommendation,
)
def row(
    *,
    count: int = 20,
    false_positive: float | None = 0.0,
    escape: float | None = 0.0,
    revert: float | None = 0.0,
    latency: int | None = 50,
) -> dict:
    return {
        "canonical_rule_id": "l9.debt.rule-1",
        "evaluation_count": count,
        "false_positive_ratio": false_positive,
        "escape_ratio": escape,
        "quick_fix_revert_ratio": revert,
        "p95_latency_ms": latency,
    }
class RecommendationTests(unittest.TestCase):
    def test_insufficient_sample_is_not_retirement(self) -> None:
        recommendation = rule_recommendation(
            row(
                count=3,
                false_positive=1.0,
            )
        )
        self.assertEqual(
            "insufficient_evidence",
            recommendation["state"],
        )
    def test_high_false_positive_rate_recommends_retirement(self) -> None:
        recommendation = rule_recommendation(
            row(false_positive=0.25)
        )
        self.assertEqual(
            "retirement_recommended",
            recommendation["state"],
        )
    def test_moderate_regression_recommends_investigation(self) -> None:
        recommendation = rule_recommendation(
            row(false_positive=0.06)
        )
        self.assertEqual(
            "investigate",
            recommendation["state"],
        )
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/effectiveness/test_drift.py <<'EOF'
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from l9_debt_intelligence.effectiveness.drift import (
    compare_reports,
)
def report(
    report_id: str,
    *,
    false_positive: float,
    escape: float,
    prevention: float,
    latency: int,
) -> dict:
    return {
        "report_id": report_id,
        "pack_id": "pack_" + ("a" * 64),
        "observation_count": 100,
        "pack_metrics": {
            "prevention_ratio": prevention,
            "escape_ratio": escape,
            "false_positive_ratio": false_positive,
            "unknown_ratio": 0.0,
            "coverage_ratio": 1.0,
            "p95_latency_ms": latency,
        },
    }
class DriftTests(unittest.TestCase):
    def test_critical_false_positive_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            current = root / "current.json"
            baseline.write_text(
                json.dumps(
                    report(
                        "effect_" + ("b" * 64),
                        false_positive=0.01,
                        escape=0.01,
                        prevention=0.80,
                        latency=100,
                    )
                )
            )
            current.write_text(
                json.dumps(
                    report(
                        "effect_" + ("c" * 64),
                        false_positive=0.15,
                        escape=0.02,
                        prevention=0.75,
                        latency=110,
                    )
                )
            )
            comparison = compare_reports(
                baseline_path=baseline,
                current_path=current,
            )
            self.assertEqual(
                "critical_regression",
                comparison["regression_state"],
            )
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/architecture/test_effectiveness_boundary.py <<'EOF'
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/l9_debt_intelligence/effectiveness"
class EffectivenessBoundaryTests(unittest.TestCase):
    def test_effectiveness_cannot_activate_or_retire(self) -> None:
        prohibited = (
            "git push",
            "merge_pull_request",
            "rule-modes.yaml",
            "quality-thresholds.yaml",
            "activate_pack",
            "uninstall_pack",
            "delete_release",
            "gh release delete",
            "automatic_rollback",
        )
        violations: list[str] = []
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for token in prohibited:
                if token.lower() in text:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{token}"
                    )
        self.assertEqual([], violations)
    def test_contract_preserves_unknown_semantics(self) -> None:
        contract = (
            ROOT / ".l9/effectiveness-contract.yaml"
        ).read_text(encoding="utf-8")
        required = (
            "Incomplete evaluation is not PASS.",
            "Rule not evaluated is not rule success.",
            "automatic rollback",
            "automatic retirement",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, contract)
if __name__ == "__main__":
    unittest.main()
EOF
cat > .github/workflows/phase-7-effectiveness.yml <<'EOF'
name: Intelligence Phase 7 effectiveness
on:
  pull_request:
    paths:
      - ".l9/effectiveness-contract.yaml"
      - "schemas/intelligence/**"
      - "src/l9_debt_intelligence/effectiveness/**"
      - "src/l9_debt_intelligence/cli.py"
      - "tests/effectiveness/**"
      - "tests/architecture/**"
  push:
    branches:
      - main
    paths:
      - ".l9/effectiveness-contract.yaml"
      - "schemas/intelligence/**"
      - "src/l9_debt_intelligence/effectiveness/**"
      - "src/l9_debt_intelligence/cli.py"
      - "tests/effectiveness/**"
      - "tests/architecture/**"
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: intelligence-phase-7-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
jobs:
  effectiveness:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Checkout immutable revision
        uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Install project
        run: |
          python -m pip install \
            --disable-pip-version-check \
            --no-input \
            -e ".[dev]"
          python -m pip install \
            --disable-pip-version-check \
            --no-input \
            -r requirements/snapshot.txt \
            -r requirements/publication.txt
      - name: Run complete Phase 1–7 suite
        run: |
          python -m pytest \
            tests/architecture \
            tests/contracts \
            tests/ingestion \
            tests/snapshots \
            tests/analytics \
            tests/compilation \
            tests/publication \
            tests/effectiveness
      - name: Exercise outcome ingestion
        run: |
          set -euo pipefail
          store="$(mktemp -d)"
          l9-intelligence ingest-effectiveness-outcome \
            tests/fixtures/effectiveness/lsp-outcome.json \
            --store-root "${store}" \
            --output "${store}/lsp-result.json"
          l9-intelligence ingest-effectiveness-outcome \
            tests/fixtures/effectiveness/ci-outcome.json \
            --store-root "${store}" \
            --output "${store}/ci-result.json"
          l9-intelligence ingest-effectiveness-outcome \
            tests/fixtures/effectiveness/lsp-outcome.json \
            --store-root "${store}" \
            --output "${store}/duplicate-result.json"
          python - "${store}" <<'PY'
          import json
          import sys
          from pathlib import Path
          root = Path(sys.argv[1])
          lsp = json.loads(
              (root / "lsp-result.json").read_text()
          )
          ci = json.loads(
              (root / "ci-result.json").read_text()
          )
          duplicate = json.loads(
              (root / "duplicate-result.json").read_text()
          )
          assert lsp["status"] == "accepted", lsp
          assert ci["status"] == "accepted", ci
          assert duplicate["status"] == "duplicate", duplicate
          PY
EOF
cat > docs/architecture/ADRs/ADR-INTEL-022-canonical-outcome-events.md <<'EOF'
# ADR-INTEL-022: Closed-loop learning consumes canonical outcome events
- Status: Accepted
- Phase: INTEL-P6
## Decision
Core, LSP, Resolver, and PR Repair emit versioned effectiveness outcome events.
Every event identifies the active defense pack and canonical rule. Producer
implementations remain outside Intelligence.
## Consequences
Intelligence can measure CI, editor, and repair effectiveness without depending
on producer internals.
EOF
cat > docs/architecture/ADRs/ADR-INTEL-023-unknown-outcomes-are-not-success.md <<'EOF'
# ADR-INTEL-023: Unknown or incomplete outcomes are not successful outcomes
- Status: Accepted
- Phase: INTEL-P6
## Decision
`rule_not_evaluated`, `evaluation_incomplete`, and `outcome_unknown` remain
explicit unknown observations.
They cannot increase prevention, repair-success, or quality scores.
## Consequences
Incomplete telemetry lowers evidence coverage rather than producing false
success.
EOF
cat > docs/architecture/ADRs/ADR-INTEL-024-effectiveness-recommendations-are-advisory.md <<'EOF'
# ADR-INTEL-024: Effectiveness recommendations are advisory
- Status: Accepted
- Phase: INTEL-P6
## Decision
Intelligence may recommend retention, investigation, rollback, or retirement.
It cannot change Core policy, activate an LSP pack, delete a release, or append
a retirement record without an explicit maintainer action.
## Consequences
Fleet learning remains separated from operational governance.
EOF
cat > docs/architecture/ADRs/ADR-INTEL-025-minimum-sample-gates.md <<'EOF'
# ADR-INTEL-025: Rollback and retirement recommendations require minimum samples
- Status: Accepted
- Phase: INTEL-P6
## Decision
Rule-level recommendations require at least 20 observations. Pack-level
recommendations require at least 100 observations.
Below those thresholds the state is `insufficient_evidence`, even when the
observed ratio appears poor.
## Consequences
Small-sample noise cannot automatically escalate to rollback or retirement.
EOF
python3 - <<'PY'
from pathlib import Path
path = Path(".l9/architecture.yaml")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "phase: INTEL-P5",
    "phase: INTEL-P6",
    1,
)
old = """phase_6:
  name: signed-publication
  status: implemented
  includes:
    - immutable defense-pack assembly
    - promotion-eligible rule selection
    - compatibility matrices
    - deterministic tar-gzip archives
    - Ed25519 detached signatures
    - publication manifests
    - experimental, shadow, and stable channels
    - rollback metadata
    - append-only retirement records
    - immutable GitHub Release workflow
  excludes:
    - Core governance mutation
    - automatic blocking promotion
    - LSP activation
    - OCI registry push
    - closed-loop outcome ingestion
    - effectiveness-based retirement recommendations
"""
new = """phase_6:
  name: signed-publication
  status: implemented
phase_7:
  name: closed-loop-effectiveness
  status: implemented
  includes:
    - canonical CI outcome ingestion
    - canonical LSP outcome ingestion
    - canonical repair outcome ingestion
    - deterministic outcome deduplication
    - rule effectiveness metrics
    - pack effectiveness metrics
    - coverage and unknown accounting
    - drift comparison
    - rollback recommendations
    - retirement recommendations
    - immutable effectiveness manifests
  excludes:
    - Core governance mutation
    - LSP pack activation
    - automatic rollback
    - automatic retirement
    - release deletion
    - source repository mutation
"""
if old not in text:
    raise SystemExit("unexpected INTEL-P5 architecture block")
path.write_text(
    text.replace(old, new),
    encoding="utf-8",
)
PY
python3 - <<'PY'
from pathlib import Path
path = Path("ROADMAP.md")
text = path.read_text(encoding="utf-8")
old = """## INTEL-P6 — Closed-loop effectiveness
Not authorized.
"""
new = """## INTEL-P6 — Closed-loop effectiveness
Implemented:
- canonical Core CI outcome ingestion;
- canonical LSP outcome ingestion;
- canonical repair outcome ingestion;
- deterministic outcome identities and deduplication;
- rule-level effectiveness measurement;
- pack-level effectiveness measurement;
- explicit unknown and coverage accounting;
- baseline-versus-current drift comparison;
- retain, investigate, rollback, and retirement recommendations;
- minimum-sample recommendation gates;
- immutable effectiveness reports and manifests.
Recommendations remain advisory. Intelligence cannot activate, roll back, or
retire a pack without an explicit action by the responsible authority.
"""
if old not in text:
    raise SystemExit("unexpected ROADMAP INTEL-P6 block")
path.write_text(
    text.replace(old, new),
    encoding="utf-8",
)
PY
cat >> AGENTS.md <<'EOF'
## INTEL-P6 effectiveness rules
- Accept only versioned canonical producer outcome events.
- Preserve pack, rule, finding, and producer lineage.
- Deduplicate repeated event delivery deterministically.
- Keep source content, raw logs, developer identities, and absolute paths out
  of effectiveness events.
- Treat missing and incomplete outcomes as unknown.
- Never infer PASS from `rule_not_evaluated`.
- Measure rule and pack coverage explicitly.
- Require minimum sample sizes before rollback or retirement recommendations.
- Compare compatible identities and metric definitions only.
- Keep recommendations advisory.
- Never mutate Core governance, activate LSP packs, delete releases, or execute
  automatic retirement.
EOF
python -m pip install \
  --disable-pip-version-check \
  --no-input \
  -e ".[dev]"
python -m pip install \
  --disable-pip-version-check \
  --no-input \
  -r requirements/snapshot.txt \
  -r requirements/publication.txt
python -m pytest \
  tests/architecture \
  tests/contracts \
  tests/ingestion \
  tests/snapshots \
  tests/analytics \
  tests/compilation \
  tests/publication \
  tests/effectiveness
temporary_store="$(mktemp -d)"
trap 'rm -rf "$temporary_store"' EXIT
l9-intelligence ingest-effectiveness-outcome \
  tests/fixtures/effectiveness/lsp-outcome.json \
  --store-root "$temporary_store" \
  --output "$temporary_store/lsp.json"
l9-intelligence ingest-effectiveness-outcome \
  tests/fixtures/effectiveness/ci-outcome.json \
  --store-root "$temporary_store" \
  --output "$temporary_store/ci.json"
l9-intelligence ingest-effectiveness-outcome \
  tests/fixtures/effectiveness/lsp-outcome.json \
  --store-root "$temporary_store" \
  --output "$temporary_store/duplicate.json"
python - "$temporary_store" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
lsp = json.loads(
    (root / "lsp.json").read_text(encoding="utf-8")
)
ci = json.loads(
    (root / "ci.json").read_text(encoding="utf-8")
)
duplicate = json.loads(
    (root / "duplicate.json").read_text(encoding="utf-8")
)
assert lsp["status"] == "accepted", lsp
assert ci["status"] == "accepted", ci
assert duplicate["status"] == "duplicate", duplicate
assert lsp["outcome_id"] == duplicate["outcome_id"]
PY
printf '\nINTEL-P6 closed-loop effectiveness built and validated.\n'
printf 'The l9-ci-debt-intelligence roadmap is now complete through INTEL-P6.\n'

Execute:

chmod +x build-phase-7.sh
./build-phase-7.sh

Commit:

git status --short
git diff --check
git add \
  .l9 \
  .github/workflows/phase-7-effectiveness.yml \
  schemas/intelligence \
  src/l9_debt_intelligence \
  tests/architecture \
  tests/effectiveness \
  tests/fixtures/effectiveness \
  docs/architecture/ADRs \
  AGENTS.md \
  ROADMAP.md
git commit -m "feat!: implement Intelligence INTEL-P6 closed-loop effectiveness"

The completed Intelligence lifecycle is now:

canonical producer events
        ↓
validated historical corpus
        ↓
immutable snapshots
        ↓
learning metrics
        ↓
candidate rule compilation
        ↓
signed defense packs
        ↓
CI and LSP execution
        ↓
canonical outcome events
        ↓
effectiveness and drift reports
        ↓
advisory rollback or retirement recommendations

The most important next repository is l9-ci-debt-lsp, beginning with immutable defense-pack installation, signature verification, explicit version activation, and previous-known-good rollback.
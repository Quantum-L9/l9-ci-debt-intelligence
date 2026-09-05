Phase 1 should implement INTEL-P0: schema federation and producer compatibility. It must not begin corpus analytics, rule generation, or defense-pack compilation.

The repository currently contains legacy corpus/offense/defense tools and generated-output conventions. The build below introduces the new authoritative package and contracts without deleting those paths; they are explicitly marked transitional already targets Python 3.11 and includes jsonschema, Pydantic, PyYAML, and pytest, so Phase 1 can add contract validation without introducing another schema framework.

The implementation follows the uploaded repository specification: Intelligence owns fleet corpus extensions and correction/retraction events, references SDK base schemas instead of duplicating them, preserves producer lineage, represents unknowns explicitly, and contains no source-repository mutation behavior. repo-spec.yaml

Save this as build-phase-1.sh in the repository root.

#!/usr/bin/env bash
set -euo pipefail
SDK_REVISION="c78486ea9b7d596d0b6db755b5780e5289878d35"
test -f pyproject.toml || {
  echo "Run this script from the l9-ci-debt-intelligence repository root." >&2
  exit 1
}
mkdir -p \
  .l9 \
  .github/workflows \
  docs/architecture/ADRs \
  schemas/intelligence \
  src/l9_debt_intelligence/contracts \
  tests/architecture \
  tests/contracts \
  tests/fixtures/producers
cat > .l9/architecture.yaml <<EOF
schema: l9.architecture-spec/v1
metadata:
  repository: Quantum-L9/l9-ci-debt-intelligence
  phase: INTEL-P0
  status: authoritative
identity:
  role: fleet-learning-and-prevention-compiler
  plane: corpus-learning-and-artifact-compilation
  operating_model:
    - historical
    - cross-repository
    - append-and-correction-oriented
mission: >
  Ingest compatible, redacted producer events; preserve immutable lineage;
  maintain the canonical fleet corpus; and later compile deterministic,
  immutable prevention artifacts.
dependency_direction:
  required:
    - l9-ci-debt-intelligence -> l9-ci-sdk public contracts
  event_inputs:
    - l9-ci-core -> l9-ci-debt-intelligence
    - l9-ci-debt-resolver -> l9-ci-debt-intelligence
    - l9-pr-repair -> l9-ci-debt-intelligence
    - l9-ci-debt-lsp -> l9-ci-debt-intelligence
  prohibited:
    - l9-ci-debt-intelligence -> producer runtime internals
    - l9-ci-debt-intelligence -> l9-ci-sdk private internals
    - l9-ci-debt-intelligence -> source repository mutation
owns:
  - corpus event envelope
  - corpus schema extensions
  - producer compatibility registry
  - ingestion validation
  - redaction state
  - quarantine classification
  - correction events
  - retraction events
  - producer lineage
  - explicit unknown representation
does_not_own:
  - SDK evidence schema
  - SDK finding schema
  - SDK source-location schema
  - SDK validation-result schema
  - scanner output parsing
  - repository source parsing
  - CI orchestration
  - editor protocol
  - repository patching
  - branch operations
  - repair execution
phase_1:
  name: schema-federation
  status: implemented
  includes:
    - SDK schema reference registry
    - producer compatibility registry
    - corpus event envelope
    - corpus record extension
    - correction and retraction contracts
    - deterministic contract validation
    - architecture boundary tests
  excludes:
    - persistent corpus ingestion
    - deduplication engine
    - corpus snapshots
    - analytics
    - candidate-rule generation
    - defense-pack compilation
    - artifact publication
legacy:
  status: transitional
  paths:
    - tools
    - adapters
    - outputs
    - references
    - schemas/corpus.schema.json
    - schemas/cooccurrence.schema.json
    - schemas/effort_atlas.schema.json
    - schemas/invariant.schema.json
  rule: >
    Legacy paths may be read for migration analysis but must not be imported
    by the authoritative src/l9_debt_intelligence package.
EOF
cat > .l9/ownership.yaml <<'EOF'
schema: l9.ownership-spec/v1
repository: Quantum-L9/l9-ci-debt-intelligence
intelligence_owns:
  corpus:
    - record extensions
    - ingestion lifecycle
    - redaction disposition
    - quarantine disposition
    - correction chain
    - retraction chain
    - producer lineage
  compatibility:
    - accepted producer event classes
    - accepted producer contract versions
    - minimum SDK contract requirements
  future_compilation:
    - corpus snapshots
    - candidate prevention rules
    - immutable defense packs
    - publication manifests
federated_from_sdk:
  - source-location
  - evidence
  - finding
  - snapshot
  - validation-result
  - coverage
prohibited:
  - copying SDK base schemas into this repository
  - redefining SDK finding identity
  - parsing scanner-native reports
  - patching producer repositories
  - pushing branches
  - weakening Core policy
  - importing producer implementation packages
  - fabricating unavailable producer fields
EOF
cat > .l9/sdk-schema-registry.json <<EOF
{
  "schema": "l9.sdk-schema-registry/v1",
  "sdk": {
    "repository": "Quantum-L9/l9-ci-sdk",
    "revision": "${SDK_REVISION}",
    "integration_contract": "l9.integration-contract/v1"
  },
  "references": {
    "source-location": {
      "uri": "l9://sdk/source-location/v1",
      "owner": "Quantum-L9/l9-ci-sdk"
    },
    "evidence": {
      "uri": "l9://sdk/evidence/v1",
      "owner": "Quantum-L9/l9-ci-sdk"
    },
    "finding": {
      "uri": "l9://sdk/finding/v1",
      "owner": "Quantum-L9/l9-ci-sdk"
    },
    "snapshot": {
      "uri": "l9://sdk/snapshot/v1",
      "owner": "Quantum-L9/l9-ci-sdk"
    },
    "validation-result": {
      "uri": "l9://sdk/validation-result/v1",
      "owner": "Quantum-L9/l9-ci-sdk"
    },
    "coverage": {
      "uri": "l9://sdk/coverage/v1",
      "owner": "Quantum-L9/l9-ci-sdk"
    }
  },
  "policy": {
    "local_schema_copies_allowed": false,
    "private_sdk_imports_allowed": false,
    "unknown_sdk_contract_behavior": "reject"
  }
}
EOF
cat > .l9/producer-compatibility.json <<'EOF'
{
  "schema": "l9.producer-compatibility/v1",
  "producers": {
    "Quantum-L9/l9-ci-core": {
      "event_classes": ["gate_outcome"],
      "contract_versions": ["l9.core-gate-event/v1"],
      "required_sdk_contract": "l9.integration-contract/v1"
    },
    "Quantum-L9/l9-ci-debt-resolver": {
      "event_classes": [
        "CI_failure_classification",
        "repair_attempt",
        "verification_outcome"
      ],
      "contract_versions": ["l9.resolver-corpus-event/v1"],
      "required_sdk_contract": "l9.integration-contract/v1"
    },
    "Quantum-L9/l9-pr-repair": {
      "event_classes": [
        "repair_attempt",
        "verification_outcome"
      ],
      "contract_versions": ["l9.repair-learning-packet/v1"],
      "required_sdk_contract": "l9.integration-contract/v1"
    },
    "Quantum-L9/l9-ci-debt-lsp": {
      "event_classes": [
        "editor_diagnostic_outcome",
        "false_positive_disposition"
      ],
      "contract_versions": ["l9.editor-outcome-event/v1"],
      "required_sdk_contract": "l9.integration-contract/v1"
    },
    "Quantum-L9/l9-ci-sdk": {
      "event_classes": ["static_finding"],
      "contract_versions": ["l9.finding-bundle/v1"],
      "required_sdk_contract": "l9.integration-contract/v1"
    }
  },
  "unknown_producer_behavior": "quarantine",
  "unknown_contract_behavior": "quarantine",
  "incompatible_sdk_behavior": "quarantine"
}
EOF
cat > schemas/intelligence/corpus-event.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/corpus-event/v1",
  "title": "L9 Intelligence Corpus Event",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "producer_id",
    "producer_contract",
    "event_id",
    "event_class",
    "event_time",
    "snapshot_or_run_id",
    "redaction_status",
    "limitations",
    "payload"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.corpus-event/v1"
    },
    "producer_id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 255
    },
    "producer_contract": {
      "type": "string",
      "minLength": 1,
      "maxLength": 255
    },
    "sdk_contract": {
      "type": ["string", "null"]
    },
    "event_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
    },
    "event_class": {
      "enum": [
        "static_finding",
        "CI_failure_classification",
        "repair_attempt",
        "verification_outcome",
        "editor_diagnostic_outcome",
        "false_positive_disposition",
        "gate_outcome"
      ]
    },
    "event_time": {
      "type": "string",
      "format": "date-time"
    },
    "snapshot_or_run_id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 512
    },
    "redaction_status": {
      "enum": [
        "producer_redacted",
        "intelligence_redacted",
        "quarantine_required"
      ]
    },
    "limitations": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "uniqueItems": true
    },
    "unknowns": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/unknown"
      },
      "default": []
    },
    "lineage": {
      "$ref": "#/$defs/lineage"
    },
    "payload": {
      "type": "object",
      "description": "Producer-owned payload validated by its public contract."
    }
  },
  "$defs": {
    "unknown": {
      "type": "object",
      "additionalProperties": false,
      "required": ["field", "reason"],
      "properties": {
        "field": {
          "type": "string",
          "minLength": 1
        },
        "reason": {
          "enum": [
            "not_observed",
            "not_applicable",
            "producer_did_not_emit",
            "redacted",
            "incompatible_version",
            "unavailable"
          ]
        }
      }
    },
    "lineage": {
      "type": "object",
      "additionalProperties": false,
      "required": ["producer_event_hash"],
      "properties": {
        "producer_event_hash": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$"
        },
        "parent_event_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "uniqueItems": true,
          "default": []
        }
      }
    }
  }
}
EOF
cat > schemas/intelligence/corpus-record.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/corpus-record/v1",
  "title": "L9 Intelligence Corpus Record",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "record_id",
    "source_event_id",
    "producer_id",
    "event_class",
    "lifecycle_state",
    "redaction_status",
    "payload_reference",
    "limitations"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.corpus-record/v1"
    },
    "record_id": {
      "type": "string",
      "pattern": "^cr_[0-9a-f]{64}$"
    },
    "source_event_id": {
      "type": "string",
      "minLength": 1
    },
    "producer_id": {
      "type": "string",
      "minLength": 1
    },
    "event_class": {
      "type": "string",
      "minLength": 1
    },
    "lifecycle_state": {
      "enum": [
        "RECEIVED",
        "SCHEMA_VALIDATED",
        "REDACTED",
        "NORMALIZED",
        "DEDUPLICATED",
        "CURATED",
        "QUARANTINED",
        "REJECTED",
        "CORRECTED",
        "RETRACTED"
      ]
    },
    "redaction_status": {
      "type": "string",
      "minLength": 1
    },
    "payload_reference": {
      "type": "object",
      "additionalProperties": false,
      "required": ["producer_contract", "content_hash"],
      "properties": {
        "producer_contract": {
          "type": "string",
          "minLength": 1
        },
        "sdk_schema_references": {
          "type": "array",
          "items": {
            "enum": [
              "l9://sdk/source-location/v1",
              "l9://sdk/evidence/v1",
              "l9://sdk/finding/v1",
              "l9://sdk/snapshot/v1",
              "l9://sdk/validation-result/v1",
              "l9://sdk/coverage/v1"
            ]
          },
          "uniqueItems": true
        },
        "content_hash": {
          "type": "string",
          "pattern": "^[0-9a-f]{64}$"
        }
      }
    },
    "limitations": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "uniqueItems": true
    },
    "superseded_by": {
      "type": ["string", "null"]
    }
  }
}
EOF
cat > schemas/intelligence/corpus-correction.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/corpus-correction/v1",
  "title": "L9 Intelligence Corpus Correction",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "correction_id",
    "target_record_id",
    "replacement_event_id",
    "reason",
    "issued_at",
    "issuer"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.corpus-correction/v1"
    },
    "correction_id": {
      "type": "string",
      "pattern": "^cc_[0-9a-f]{64}$"
    },
    "target_record_id": {
      "type": "string",
      "pattern": "^cr_[0-9a-f]{64}$"
    },
    "replacement_event_id": {
      "type": "string",
      "minLength": 1
    },
    "reason": {
      "type": "string",
      "minLength": 1
    },
    "issued_at": {
      "type": "string",
      "format": "date-time"
    },
    "issuer": {
      "type": "string",
      "minLength": 1
    }
  }
}
EOF
cat > schemas/intelligence/corpus-retraction.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/corpus-retraction/v1",
  "title": "L9 Intelligence Corpus Retraction",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "retraction_id",
    "target_record_id",
    "reason",
    "issued_at",
    "issuer"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.corpus-retraction/v1"
    },
    "retraction_id": {
      "type": "string",
      "pattern": "^rt_[0-9a-f]{64}$"
    },
    "target_record_id": {
      "type": "string",
      "pattern": "^cr_[0-9a-f]{64}$"
    },
    "reason": {
      "type": "string",
      "minLength": 1
    },
    "issued_at": {
      "type": "string",
      "format": "date-time"
    },
    "issuer": {
      "type": "string",
      "minLength": 1
    }
  }
}
EOF
cat > schemas/intelligence/validation-result.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "l9://intelligence/validation-result/v1",
  "title": "L9 Intelligence Validation Result",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "status",
    "event_id",
    "producer_id",
    "event_class",
    "event_hash",
    "limitations"
  ],
  "properties": {
    "schema_version": {
      "const": "l9.intelligence-validation-result/v1"
    },
    "status": {
      "enum": ["accepted", "quarantined", "rejected"]
    },
    "event_id": {
      "type": "string"
    },
    "producer_id": {
      "type": "string"
    },
    "event_class": {
      "type": "string"
    },
    "event_hash": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$"
    },
    "quarantine_reason": {
      "type": ["string", "null"]
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
cat > src/l9_debt_intelligence/__init__.py <<'EOF'
"""L9 Debt Intelligence authoritative corpus contracts."""
__version__ = "0.2.0"
EOF
cat > src/l9_debt_intelligence/contracts/__init__.py <<'EOF'
"""Schema federation and producer contract validation."""
EOF
cat > src/l9_debt_intelligence/contracts/errors.py <<'EOF'
from __future__ import annotations
class ContractError(ValueError):
    """Base error for corpus contract failures."""
class SchemaValidationError(ContractError):
    """The event does not satisfy the corpus event schema."""
class ProducerCompatibilityError(ContractError):
    """The producer or producer contract is not supported."""
class SDKCompatibilityError(ContractError):
    """The event references an incompatible SDK contract."""
EOF
cat > src/l9_debt_intelligence/contracts/canonical.py <<'EOF'
from __future__ import annotations
import hashlib
import json
from typing import Any
def canonical_json(document: Any) -> bytes:
    """Serialize a JSON-compatible value deterministically."""
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
def sha256_document(document: Any) -> str:
    return hashlib.sha256(canonical_json(document)).hexdigest()
EOF
cat > src/l9_debt_intelligence/contracts/registry.py <<'EOF'
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .errors import ProducerCompatibilityError, SDKCompatibilityError
@dataclass(frozen=True)
class ProducerContract:
    producer_id: str
    event_classes: frozenset[str]
    contract_versions: frozenset[str]
    required_sdk_contract: str
class CompatibilityRegistry:
    def __init__(
        self,
        producers: dict[str, ProducerContract],
        *,
        unknown_producer_behavior: str,
        unknown_contract_behavior: str,
        incompatible_sdk_behavior: str,
    ) -> None:
        self._producers = producers
        self.unknown_producer_behavior = unknown_producer_behavior
        self.unknown_contract_behavior = unknown_contract_behavior
        self.incompatible_sdk_behavior = incompatible_sdk_behavior
    @classmethod
    def load(cls, path: Path) -> "CompatibilityRegistry":
        document: dict[str, Any] = json.loads(
            path.read_text(encoding="utf-8")
        )
        if document.get("schema") != "l9.producer-compatibility/v1":
            raise ProducerCompatibilityError(
                "unsupported producer compatibility registry schema"
            )
        raw_producers = document.get("producers")
        if not isinstance(raw_producers, dict):
            raise ProducerCompatibilityError(
                "producer registry must contain a producers object"
            )
        producers: dict[str, ProducerContract] = {}
        for producer_id, value in raw_producers.items():
            if not isinstance(value, dict):
                raise ProducerCompatibilityError(
                    f"producer {producer_id!r} must be an object"
                )
            event_classes = value.get("event_classes")
            contract_versions = value.get("contract_versions")
            sdk_contract = value.get("required_sdk_contract")
            if not isinstance(event_classes, list) or not all(
                isinstance(item, str) for item in event_classes
            ):
                raise ProducerCompatibilityError(
                    f"producer {producer_id!r} has invalid event classes"
                )
            if not isinstance(contract_versions, list) or not all(
                isinstance(item, str) for item in contract_versions
            ):
                raise ProducerCompatibilityError(
                    f"producer {producer_id!r} has invalid contracts"
                )
            if not isinstance(sdk_contract, str) or not sdk_contract:
                raise ProducerCompatibilityError(
                    f"producer {producer_id!r} has no SDK contract"
                )
            producers[producer_id] = ProducerContract(
                producer_id=producer_id,
                event_classes=frozenset(event_classes),
                contract_versions=frozenset(contract_versions),
                required_sdk_contract=sdk_contract,
            )
        return cls(
            producers,
            unknown_producer_behavior=str(
                document.get("unknown_producer_behavior", "quarantine")
            ),
            unknown_contract_behavior=str(
                document.get("unknown_contract_behavior", "quarantine")
            ),
            incompatible_sdk_behavior=str(
                document.get("incompatible_sdk_behavior", "quarantine")
            ),
        )
    def validate(
        self,
        *,
        producer_id: str,
        event_class: str,
        producer_contract: str,
        sdk_contract: str | None,
    ) -> ProducerContract:
        producer = self._producers.get(producer_id)
        if producer is None:
            raise ProducerCompatibilityError(
                f"unknown producer: {producer_id}"
            )
        if event_class not in producer.event_classes:
            raise ProducerCompatibilityError(
                f"producer {producer_id!r} cannot emit "
                f"event class {event_class!r}"
            )
        if producer_contract not in producer.contract_versions:
            raise ProducerCompatibilityError(
                f"unsupported producer contract: {producer_contract}"
            )
        if sdk_contract != producer.required_sdk_contract:
            raise SDKCompatibilityError(
                f"producer requires SDK contract "
                f"{producer.required_sdk_contract!r}, "
                f"received {sdk_contract!r}"
            )
        return producer
EOF
cat > src/l9_debt_intelligence/contracts/validator.py <<'EOF'
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from .canonical import sha256_document
from .errors import (
    ContractError,
    ProducerCompatibilityError,
    SDKCompatibilityError,
    SchemaValidationError,
)
from .registry import CompatibilityRegistry
@dataclass(frozen=True)
class ValidationResult:
    schema_version: str
    status: str
    event_id: str
    producer_id: str
    event_class: str
    event_hash: str
    quarantine_reason: str | None
    limitations: tuple[str, ...]
    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "event_id": self.event_id,
            "producer_id": self.producer_id,
            "event_class": self.event_class,
            "event_hash": self.event_hash,
            "quarantine_reason": self.quarantine_reason,
            "limitations": list(self.limitations),
        }
class EventValidator:
    def __init__(
        self,
        *,
        event_schema: Path,
        compatibility_registry: Path,
    ) -> None:
        schema = json.loads(event_schema.read_text(encoding="utf-8"))
        self._validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
        self._registry = CompatibilityRegistry.load(
            compatibility_registry
        )
    def validate(self, event: dict[str, Any]) -> ValidationResult:
        errors = sorted(
            self._validator.iter_errors(event),
            key=lambda error: tuple(str(part) for part in error.path),
        )
        event_hash = sha256_document(event)
        event_id = str(event.get("event_id", "unknown"))
        producer_id = str(event.get("producer_id", "unknown"))
        event_class = str(event.get("event_class", "unknown"))
        limitations = tuple(event.get("limitations", []))
        if errors:
            message = "; ".join(
                f"{'/'.join(str(part) for part in error.path) or '<root>'}: "
                f"{error.message}"
                for error in errors
            )
            raise SchemaValidationError(message)
        try:
            self._registry.validate(
                producer_id=event["producer_id"],
                event_class=event["event_class"],
                producer_contract=event["producer_contract"],
                sdk_contract=event.get("sdk_contract"),
            )
        except (ProducerCompatibilityError, SDKCompatibilityError) as error:
            return ValidationResult(
                schema_version="l9.intelligence-validation-result/v1",
                status="quarantined",
                event_id=event_id,
                producer_id=producer_id,
                event_class=event_class,
                event_hash=event_hash,
                quarantine_reason=type(error).__name__,
                limitations=limitations + (str(error),),
            )
        if event["redaction_status"] == "quarantine_required":
            return ValidationResult(
                schema_version="l9.intelligence-validation-result/v1",
                status="quarantined",
                event_id=event_id,
                producer_id=producer_id,
                event_class=event_class,
                event_hash=event_hash,
                quarantine_reason="redaction_required",
                limitations=limitations,
            )
        return ValidationResult(
            schema_version="l9.intelligence-validation-result/v1",
            status="accepted",
            event_id=event_id,
            producer_id=producer_id,
            event_class=event_class,
            event_hash=event_hash,
            quarantine_reason=None,
            limitations=limitations,
        )
EOF
cat > src/l9_debt_intelligence/cli.py <<'EOF'
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Sequence
from .contracts.errors import ContractError
from .contracts.validator import EventValidator
def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="l9-intelligence")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser(
        "validate-event",
        help="Validate one producer event against Phase 1 contracts.",
    )
    validate.add_argument("event", type=Path)
    validate.add_argument(
        "--schema",
        type=Path,
        default=repository_root()
        / "schemas/intelligence/corpus-event.schema.json",
    )
    validate.add_argument(
        "--registry",
        type=Path,
        default=repository_root()
        / ".l9/producer-compatibility.json",
    )
    validate.add_argument("--output", type=Path)
    return parser
def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command != "validate-event":
        return 2
    try:
        event = json.loads(arguments.event.read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("event must contain a JSON object")
        validator = EventValidator(
            event_schema=arguments.schema,
            compatibility_registry=arguments.registry,
        )
        result = validator.validate(event)
        serialized = (
            json.dumps(
                result.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        if arguments.output:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(serialized, encoding="utf-8")
        else:
            sys.stdout.write(serialized)
        return 0 if result.status == "accepted" else 3
    except (OSError, ValueError, ContractError) as error:
        print(f"l9-intelligence: {error}", file=sys.stderr)
        return 2
if __name__ == "__main__":
    raise SystemExit(main())
EOF
cat > tests/fixtures/producers/valid-core-gate.json <<'EOF'
{
  "schema_version": "l9.corpus-event/v1",
  "producer_id": "Quantum-L9/l9-ci-core",
  "producer_contract": "l9.core-gate-event/v1",
  "sdk_contract": "l9.integration-contract/v1",
  "event_id": "gate-run-100",
  "event_class": "gate_outcome",
  "event_time": "2026-07-17T12:00:00Z",
  "snapshot_or_run_id": "run-100",
  "redaction_status": "producer_redacted",
  "limitations": [],
  "unknowns": [],
  "lineage": {
    "producer_event_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "parent_event_ids": []
  },
  "payload": {
    "artifact_reference": "artifact://gate-run-100"
  }
}
EOF
cat > tests/contracts/test_event_validation.py <<'EOF'
from __future__ import annotations
import json
import unittest
from pathlib import Path
from l9_debt_intelligence.contracts.validator import EventValidator
ROOT = Path(__file__).resolve().parents[2]
class EventValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = EventValidator(
            event_schema=(
                ROOT / "schemas/intelligence/corpus-event.schema.json"
            ),
            compatibility_registry=(
                ROOT / ".l9/producer-compatibility.json"
            ),
        )
        self.valid_event = json.loads(
            (
                ROOT
                / "tests/fixtures/producers/valid-core-gate.json"
            ).read_text(encoding="utf-8")
        )
    def test_known_compatible_event_is_accepted(self) -> None:
        result = self.validator.validate(self.valid_event)
        self.assertEqual("accepted", result.status)
        self.assertIsNone(result.quarantine_reason)
    def test_unknown_producer_is_quarantined(self) -> None:
        event = dict(self.valid_event)
        event["producer_id"] = "Unknown/example"
        result = self.validator.validate(event)
        self.assertEqual("quarantined", result.status)
        self.assertEqual(
            "ProducerCompatibilityError",
            result.quarantine_reason,
        )
    def test_incompatible_sdk_contract_is_quarantined(self) -> None:
        event = dict(self.valid_event)
        event["sdk_contract"] = "l9.integration-contract/v999"
        result = self.validator.validate(event)
        self.assertEqual("quarantined", result.status)
        self.assertEqual(
            "SDKCompatibilityError",
            result.quarantine_reason,
        )
    def test_event_hash_is_deterministic(self) -> None:
        first = self.validator.validate(self.valid_event)
        second = self.validator.validate(self.valid_event)
        self.assertEqual(first.event_hash, second.event_hash)
        self.assertEqual(64, len(first.event_hash))
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/contracts/test_schema_federation.py <<'EOF'
from __future__ import annotations
import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
class SchemaFederationTests(unittest.TestCase):
    def test_sdk_registry_is_pinned(self) -> None:
        registry = json.loads(
            (
                ROOT / ".l9/sdk-schema-registry.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "c78486ea9b7d596d0b6db755b5780e5289878d35",
            registry["sdk"]["revision"],
        )
        self.assertFalse(
            registry["policy"]["local_schema_copies_allowed"]
        )
    def test_intelligence_schemas_do_not_define_sdk_findings(self) -> None:
        prohibited = {
            "canonical_rule_id",
            "provider_rule_id",
            "finding_id",
            "evidence_id",
            "source_location",
        }
        for schema in (
            ROOT / "schemas/intelligence"
        ).glob("*.schema.json"):
            with self.subTest(schema=schema.name):
                document = json.loads(
                    schema.read_text(encoding="utf-8")
                )
                properties = set(document.get("properties", {}))
                self.assertTrue(prohibited.isdisjoint(properties))
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/architecture/test_intelligence_boundary.py <<'EOF'
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/l9_debt_intelligence"
PROHIBITED_TEXT = (
    "git push",
    "git commit",
    "create_pull_request",
    "merge_pull_request",
    "checkout -b",
    "subprocess.run([\"git\"",
    "import semgrep",
    "from semgrep",
    "import l9_ci._",
    "from l9_ci._",
)
PROHIBITED_PATH_PARTS = {
    "repair",
    "mutation",
    "branch",
    "scanner_parser",
    "repository_parser",
}
class IntelligenceBoundaryTests(unittest.TestCase):
    def test_authoritative_package_contains_no_mutation_behavior(self) -> None:
        violations: list[str] = []
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for prohibited in PROHIBITED_TEXT:
                if prohibited.lower() in text:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{prohibited}"
                    )
        self.assertEqual([], violations)
    def test_authoritative_package_has_no_prohibited_modules(self) -> None:
        violations = [
            path.relative_to(ROOT).as_posix()
            for path in SOURCE.rglob("*")
            if any(
                part.lower() in PROHIBITED_PATH_PARTS
                for part in path.parts
            )
        ]
        self.assertEqual([], violations)
    def test_authoritative_package_does_not_import_legacy_tools(self) -> None:
        violations: list[str] = []
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "from tools" in text or "import tools" in text:
                violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], violations)
if __name__ == "__main__":
    unittest.main()
EOF
cat > tests/architecture/test_contract_inventory.py <<'EOF'
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
class ContractInventoryTests(unittest.TestCase):
    def test_phase_1_contracts_exist(self) -> None:
        expected = [
            ".l9/architecture.yaml",
            ".l9/ownership.yaml",
            ".l9/sdk-schema-registry.json",
            ".l9/producer-compatibility.json",
            "schemas/intelligence/corpus-event.schema.json",
            "schemas/intelligence/corpus-record.schema.json",
            "schemas/intelligence/corpus-correction.schema.json",
            "schemas/intelligence/corpus-retraction.schema.json",
            "schemas/intelligence/validation-result.schema.json",
        ]
        for relative in expected:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
if __name__ == "__main__":
    unittest.main()
EOF
cat > .github/workflows/phase-1-contracts.yml <<'EOF'
name: Intelligence Phase 1 contracts
on:
  pull_request:
    paths:
      - ".l9/**"
      - "schemas/intelligence/**"
      - "src/l9_debt_intelligence/**"
      - "tests/architecture/**"
      - "tests/contracts/**"
      - "pyproject.toml"
  push:
    branches:
      - main
    paths:
      - ".l9/**"
      - "schemas/intelligence/**"
      - "src/l9_debt_intelligence/**"
      - "tests/architecture/**"
      - "tests/contracts/**"
      - "pyproject.toml"
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: intelligence-phase-1-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
jobs:
  contracts:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout immutable event revision
        env:
          REPOSITORY: ${{ github.repository }}
          REVISION: ${{ github.sha }}
          TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          git init .
          git remote add origin \
            "https://x-access-token:${TOKEN}@github.com/${REPOSITORY}.git"
          git -c protocol.version=2 fetch --depth=1 origin "${REVISION}"
          git checkout --detach FETCH_HEAD
          git remote set-url origin \
            "https://github.com/${REPOSITORY}.git"
      - name: Install project
        run: |
          python -m pip install --disable-pip-version-check \
            --no-input -e ".[dev]"
      - name: Run Phase 1 tests
        run: |
          python -m pytest \
            tests/architecture \
            tests/contracts
EOF
cat > docs/architecture/ADRs/ADR-INTEL-001-canonical-corpus.md <<'EOF'
# ADR-INTEL-001: Intelligence owns the canonical fleet corpus
- Status: Accepted
- Phase: INTEL-P0
## Decision
`l9-ci-debt-intelligence` owns historical fleet corpus records and
Intelligence-specific schema extensions.
SDK evidence, findings, source locations, snapshots, validation results, and
coverage remain SDK-owned contracts. Intelligence references those contracts;
it does not duplicate them.
## Consequences
Producer payloads retain their public contract identity. Intelligence records
lineage, lifecycle, redaction state, limitations, and correction history
around those payloads.
EOF
cat > docs/architecture/ADRs/ADR-INTEL-003-immutable-defense-packs.md <<'EOF'
# ADR-INTEL-003: Prevention artifacts are immutable and versioned
- Status: Accepted
- Phase: INTEL-P0
## Decision
Future defense packs will be derived from pinned corpus snapshots and compiler
versions. Phase 1 defines no compiler and publishes no pack.
Unversioned working-tree output is not an authoritative distribution channel.
EOF
cat > docs/architecture/ADRs/ADR-INTEL-005-correction-events.md <<'EOF'
# ADR-INTEL-005: Corpus history uses correction and retraction events
- Status: Accepted
- Phase: INTEL-P0
## Decision
Historical records are never silently overwritten.
Corrections identify the target record and replacement event. Retractions
identify the target record, issuer, timestamp, and reason. Consumers reconstruct
the current logical view from the append-only event history.
EOF
cat > AGENTS.md <<'EOF'
# Agent Instructions
This repository owns historical corpus learning and prevention-artifact
compilation.
Before modifying the authoritative implementation:
1. Read `.l9/architecture.yaml`.
2. Read `.l9/ownership.yaml`.
3. Read `.l9/sdk-schema-registry.json`.
4. Read `.l9/producer-compatibility.json`.
5. Preserve producer lineage.
6. Represent missing data explicitly as unknown.
7. Reference SDK schemas; never reproduce them.
8. Use correction or retraction events; never silently rewrite history.
9. Keep source repository mutation out of this repository.
10. Run the complete Phase 1 contract suite.
The following are prohibited:
- repository patching;
- branch pushing;
- scanner-native parsing;
- SDK private imports;
- producer implementation imports;
- fabricated corpus fields;
- publishing unversioned prevention artifacts.
Legacy `tools/`, `adapters/`, `outputs/`, and root legacy schemas are
transitional and are not authoritative Phase 1 implementation packages.
EOF
cat > ROADMAP.md <<'EOF'
# Roadmap
## INTEL-P0 — Schema federation
Implemented:
- repository ownership boundary;
- immutable SDK schema registry;
- producer compatibility registry;
- corpus event envelope;
- corpus record extension;
- correction and retraction contracts;
- deterministic event hashing;
- quarantine behavior for incompatible producers and contracts;
- architecture tests.
## INTEL-P1 — Reproducible ingestion
Not authorized:
- ingestion ledger;
- redaction engine;
- quarantine persistence;
- deterministic deduplication;
- producer payload validation adapters.
## INTEL-P2 — Immutable snapshots
Not authorized.
## INTEL-P3 — Learning metrics
Not authorized.
## INTEL-P4 — Rule compilation
Not authorized.
## INTEL-P5 — Signed publication
Not authorized.
## INTEL-P6 — Closed-loop effectiveness
Not authorized.
EOF
python3 - <<'PY'
from pathlib import Path
path = Path("pyproject.toml")
text = path.read_text(encoding="utf-8")
text = text.replace(
    'version = "0.1.0"',
    'version = "0.2.0"',
    1,
)
if "[project.scripts]" not in text:
    text += """
[project.scripts]
l9-intelligence = "l9_debt_intelligence.cli:main"
"""
if "[tool.hatch.build.targets.wheel]" not in text:
    text += """
[tool.hatch.build.targets.wheel]
packages = ["src/l9_debt_intelligence"]
"""
path.write_text(text, encoding="utf-8")
PY
python -m pip install --disable-pip-version-check --no-input -e ".[dev]"
python -m pytest \
  tests/architecture \
  tests/contracts
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
l9-intelligence validate-event \
  tests/fixtures/producers/valid-core-gate.json \
  --output "$tmpdir/validation-result.json"
python - <<PY
import json
from pathlib import Path
result = json.loads(
    Path("$tmpdir/validation-result.json").read_text(encoding="utf-8")
)
assert result["status"] == "accepted", result
assert len(result["event_hash"]) == 64, result
PY
printf '\nINTEL-P0 successfully built and validated.\n'
printf 'SDK revision: %s\n' "$SDK_REVISION"

Execute it:

chmod +x build-phase-1.sh
./build-phase-1.sh

Then review and commit:

git status --short
git diff --check
git add \
  .l9 \
  .github/workflows/phase-1-contracts.yml \
  schemas/intelligence \
  src/l9_debt_intelligence \
  tests/architecture \
  tests/contracts \
  tests/fixtures \
  docs/architecture/ADRs \
  AGENTS.md \
  ROADMAP.md \
  pyproject.toml
git commit -m "feat!: implement Intelligence INTEL-P0 schema federation"

Phase 1 acceptance boundary

After this commit:

producer event
    ↓
corpus envelope validation
    ↓
producer compatibility validation
    ↓
SDK contract compatibility validation
    ↓
accepted or quarantined

The implementation does not persist a corpus, normalize producer payload semantics, deduplicate records, compile rules, or publish defense packs. Those begin in INTEL-P1 and later phases.
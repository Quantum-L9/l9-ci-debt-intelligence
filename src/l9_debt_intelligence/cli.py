from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .analytics.builder import build_analytics
from .analytics.verify import verify_analytics
from .compilation.builder import build_compilation
from .compilation.verify import verify_compilation
from .contracts.errors import ContractError
from .contracts.validator import EventValidator
from .effectiveness.builder import build_effectiveness_report
from .effectiveness.drift import compare_reports
from .effectiveness.storage import OutcomeStore
from .effectiveness.validation import OutcomeValidator
from .effectiveness.verify import verify_effectiveness_report
from .ingestion.http_ingress import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_PATH,
    FeedbackIngress,
    build_server,
)
from .ingestion.resolver_feedback import ResolverFeedbackAdapter
from .ingestion.service import IngestionService
from .ingestion.verify import verify_store
from .publication.assembler import assemble_pack
from .publication.channels import update_channel
from .publication.crypto import generate_keypair
from .publication.publisher import sign_publication
from .publication.retirement import retire_pack
from .publication.verify import verify_publication
from .snapshots.builder import build_snapshot
from .snapshots.duckdb_projection import create_projection
from .snapshots.verify import verify_snapshot


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
        default=repository_root() / "schemas/intelligence/corpus-event.schema.json",
    )
    validate.add_argument(
        "--registry",
        type=Path,
        default=repository_root() / ".l9/producer-compatibility.json",
    )
    validate.add_argument("--output", type=Path)
    ingest = commands.add_parser(
        "ingest-event",
        help="Validate and ingest one producer event.",
    )
    ingest.add_argument("event", type=Path)
    ingest.add_argument(
        "--schema",
        type=Path,
        default=repository_root() / "schemas/intelligence/corpus-event.schema.json",
    )
    ingest.add_argument(
        "--registry",
        type=Path,
        default=repository_root() / ".l9/producer-compatibility.json",
    )
    ingest.add_argument(
        "--storage-root",
        type=Path,
        required=True,
    )
    ingest.add_argument("--output", type=Path)
    resolver_feedback = commands.add_parser(
        "ingest-resolver-feedback",
        help=(
            "Project one native l9.intelligence-feedback-event/v1 document "
            "onto the corpus envelope and ingest it."
        ),
    )
    resolver_feedback.add_argument("event", type=Path)
    resolver_feedback.add_argument(
        "--consumer-schema",
        type=Path,
        default=(
            repository_root()
            / "schemas/intelligence/consumers/resolver-feedback.schema.json"
        ),
    )
    resolver_feedback.add_argument(
        "--schema",
        type=Path,
        default=repository_root() / "schemas/intelligence/corpus-event.schema.json",
    )
    resolver_feedback.add_argument(
        "--registry",
        type=Path,
        default=repository_root() / ".l9/producer-compatibility.json",
    )
    resolver_feedback.add_argument(
        "--storage-root",
        type=Path,
        required=True,
    )
    resolver_feedback.add_argument("--output", type=Path)
    ingress = commands.add_parser(
        "serve-feedback-ingress",
        help=(
            "Serve the producer feedback ingress. Terminate TLS in front of "
            "it; the bearer token is read from L9_INTELLIGENCE_INGRESS_TOKEN."
        ),
    )
    ingress.add_argument("--host", default="127.0.0.1")
    ingress.add_argument("--port", type=int, default=8080)
    ingress.add_argument("--path", default=DEFAULT_PATH)
    ingress.add_argument(
        "--max-body-bytes",
        type=int,
        default=DEFAULT_MAX_BODY_BYTES,
    )
    ingress.add_argument(
        "--consumer-schema",
        type=Path,
        default=(
            repository_root()
            / "schemas/intelligence/consumers/resolver-feedback.schema.json"
        ),
    )
    ingress.add_argument(
        "--schema",
        type=Path,
        default=repository_root() / "schemas/intelligence/corpus-event.schema.json",
    )
    ingress.add_argument(
        "--registry",
        type=Path,
        default=repository_root() / ".l9/producer-compatibility.json",
    )
    ingress.add_argument(
        "--storage-root",
        type=Path,
        required=True,
    )
    verify = commands.add_parser(
        "verify-store",
        help="Verify the append-only ingestion store.",
    )
    verify.add_argument(
        "--storage-root",
        type=Path,
        required=True,
    )
    verify.add_argument("--output", type=Path)
    snapshot = commands.add_parser(
        "build-snapshot",
        help="Build an immutable corpus snapshot.",
    )
    snapshot.add_argument(
        "--storage-root",
        type=Path,
        required=True,
    )
    snapshot.add_argument(
        "--snapshots-root",
        type=Path,
        required=True,
    )
    snapshot.add_argument("--output", type=Path)
    verify_snapshot_parser = commands.add_parser(
        "verify-snapshot",
        help="Verify an immutable corpus snapshot.",
    )
    verify_snapshot_parser.add_argument(
        "snapshot",
        type=Path,
    )
    verify_snapshot_parser.add_argument("--output", type=Path)
    projection = commands.add_parser(
        "create-duckdb-projection",
        help="Create a derived DuckDB projection.",
    )
    projection.add_argument(
        "snapshot",
        type=Path,
    )
    projection.add_argument(
        "--database",
        type=Path,
        required=True,
    )
    projection.add_argument("--output", type=Path)
    analytics = commands.add_parser(
        "build-analytics",
        help="Build deterministic learning metrics.",
    )
    analytics.add_argument(
        "snapshot",
        type=Path,
    )
    analytics.add_argument(
        "--analytics-root",
        type=Path,
        required=True,
    )
    analytics.add_argument("--output", type=Path)
    verify_analytics_parser = commands.add_parser(
        "verify-analytics",
        help="Verify deterministic analytical reports.",
    )
    verify_analytics_parser.add_argument(
        "analysis",
        type=Path,
    )
    verify_analytics_parser.add_argument("--output", type=Path)
    compile_parser = commands.add_parser(
        "compile-candidates",
        help="Compile deterministic prevention candidates.",
    )
    compile_parser.add_argument("analysis", type=Path)
    compile_parser.add_argument(
        "--compilation-root",
        type=Path,
        required=True,
    )
    compile_parser.add_argument("--output", type=Path)
    verify_compile_parser = commands.add_parser(
        "verify-compilation",
        help="Verify candidate compiler outputs.",
    )
    verify_compile_parser.add_argument(
        "compilation",
        type=Path,
    )
    verify_compile_parser.add_argument("--output", type=Path)
    keygen = commands.add_parser(
        "generate-publication-key",
        help="Generate an Ed25519 defense-pack signing key.",
    )
    keygen.add_argument(
        "--private-key",
        type=Path,
        required=True,
    )
    keygen.add_argument(
        "--public-key",
        type=Path,
        required=True,
    )
    assemble = commands.add_parser(
        "assemble-defense-pack",
        help="Assemble an immutable defense pack.",
    )
    assemble.add_argument("compilation", type=Path)
    assemble.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )
    assemble.add_argument(
        "--version",
        required=True,
    )
    assemble.add_argument(
        "--taxonomy-version",
        required=True,
    )
    assemble.add_argument(
        "--sdk-contract-version",
        default="l9.integration-contract/v1",
    )
    assemble.add_argument(
        "--compatibility",
        type=Path,
        default=repository_root() / ".l9/default-compatibility.json",
    )
    assemble.add_argument("--output", type=Path)
    sign = commands.add_parser(
        "sign-defense-pack",
        help="Sign an assembled defense-pack archive.",
    )
    sign.add_argument(
        "build_result",
        type=Path,
    )
    sign.add_argument(
        "--private-key",
        type=Path,
        required=True,
    )
    sign.add_argument(
        "--channel",
        choices=["experimental", "shadow", "stable"],
        required=True,
    )
    sign.add_argument(
        "--previous-manifest",
        type=Path,
    )
    sign.add_argument(
        "--publication-manifest",
        type=Path,
        required=True,
    )
    sign.add_argument("--output", type=Path)
    verify_pack = commands.add_parser(
        "verify-defense-pack",
        help="Verify archive integrity and detached signature.",
    )
    verify_pack.add_argument(
        "publication_manifest",
        type=Path,
    )
    verify_pack.add_argument(
        "archive",
        type=Path,
    )
    verify_pack.add_argument("--output", type=Path)
    channel = commands.add_parser(
        "update-defense-channel",
        help="Atomically update a defense-pack channel index.",
    )
    channel.add_argument(
        "publication_manifest",
        type=Path,
    )
    channel.add_argument(
        "--channel",
        choices=["experimental", "shadow", "stable"],
        required=True,
    )
    channel.add_argument(
        "--channel-index",
        type=Path,
        required=True,
    )
    channel.add_argument("--output", type=Path)
    retire = commands.add_parser(
        "retire-defense-pack",
        help="Append a defense-pack retirement record.",
    )
    retire.add_argument(
        "publication_manifest",
        type=Path,
    )
    retire.add_argument("--reason", required=True)
    retire.add_argument("--issuer", required=True)
    retire.add_argument("--replacement-version")
    retire.add_argument(
        "--ledger",
        type=Path,
        required=True,
    )
    retire.add_argument("--output", type=Path)
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


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "validate-event":
            event = json.loads(arguments.event.read_text(encoding="utf-8"))
            if not isinstance(event, dict):
                raise ValueError("event must contain a JSON object")
            validator = EventValidator(
                event_schema=arguments.schema,
                compatibility_registry=arguments.registry,
            )
            result = validator.validate(event)
            document = result.as_dict()
            exit_code = 0 if result.status == "accepted" else 3
        elif arguments.command == "ingest-event":
            event = json.loads(arguments.event.read_text(encoding="utf-8"))
            if not isinstance(event, dict):
                raise ValueError("event must contain a JSON object")
            service = IngestionService(
                event_schema=arguments.schema,
                compatibility_registry=arguments.registry,
                storage_root=arguments.storage_root,
            )
            ingestion_result = service.ingest(event)
            document = ingestion_result.as_dict()
            exit_code = 0 if ingestion_result.status in {"accepted", "duplicate"} else 3
        elif arguments.command == "ingest-resolver-feedback":
            native = json.loads(arguments.event.read_text(encoding="utf-8"))
            if not isinstance(native, dict):
                raise ValueError("resolver feedback event must be a JSON object")
            adapter = ResolverFeedbackAdapter(
                consumer_schema=arguments.consumer_schema,
            )
            service = IngestionService(
                event_schema=arguments.schema,
                compatibility_registry=arguments.registry,
                storage_root=arguments.storage_root,
            )
            ingestion_result = service.ingest(adapter.project(native))
            document = ingestion_result.as_dict()
            exit_code = 0 if ingestion_result.status in {"accepted", "duplicate"} else 3
        elif arguments.command == "serve-feedback-ingress":
            # Never a flag: a token on the command line lands in shell history
            # and in every process listing on the host.
            token = os.environ.get("L9_INTELLIGENCE_INGRESS_TOKEN", "")
            if not token:
                raise ValueError(
                    "L9_INTELLIGENCE_INGRESS_TOKEN must be set to serve the "
                    "feedback ingress"
                )
            server = build_server(
                ingress=FeedbackIngress(
                    service=IngestionService(
                        event_schema=arguments.schema,
                        compatibility_registry=arguments.registry,
                        storage_root=arguments.storage_root,
                    ),
                    adapter=ResolverFeedbackAdapter(
                        consumer_schema=arguments.consumer_schema,
                    ),
                    bearer_token=token,
                    path=arguments.path,
                    max_body_bytes=arguments.max_body_bytes,
                ),
                host=arguments.host,
                port=arguments.port,
            )
            host, port = server.server_address[:2]
            print(
                json.dumps(
                    {
                        "schema_version": "l9.ingestion-ingress-start/v1",
                        "status": "listening",
                        "host": str(host),
                        "port": int(port),
                        "path": arguments.path,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                file=sys.stderr,
                flush=True,
            )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("feedback ingress shutting down", file=sys.stderr, flush=True)
            finally:
                server.server_close()
            return 0
        elif arguments.command == "verify-store":
            document = verify_store(arguments.storage_root)
            exit_code = 0
        elif arguments.command == "build-snapshot":
            snapshot_result = build_snapshot(
                storage_root=arguments.storage_root,
                snapshots_root=arguments.snapshots_root,
            )
            document = snapshot_result.as_dict()
            exit_code = 0
        elif arguments.command == "verify-snapshot":
            document = verify_snapshot(arguments.snapshot)
            exit_code = 0
        elif arguments.command == "create-duckdb-projection":
            database = create_projection(
                snapshot_path=arguments.snapshot,
                database_path=arguments.database,
            )
            document = {
                "schema_version": "l9.duckdb-projection-result/v1",
                "status": "created",
                "database": database.as_posix(),
            }
            exit_code = 0
        elif arguments.command == "build-analytics":
            document = build_analytics(
                snapshot_path=arguments.snapshot,
                analytics_root=arguments.analytics_root,
            )
            exit_code = 0
        elif arguments.command == "verify-analytics":
            document = verify_analytics(arguments.analysis)
            exit_code = 0
        elif arguments.command == "compile-candidates":
            document = build_compilation(
                analysis_path=arguments.analysis,
                compilation_root=arguments.compilation_root,
            )
            exit_code = 0
        elif arguments.command == "verify-compilation":
            document = verify_compilation(arguments.compilation)
            exit_code = 0
        elif arguments.command == "generate-publication-key":
            generate_keypair(
                private_key_path=arguments.private_key,
                public_key_path=arguments.public_key,
            )
            document = {
                "schema_version": "l9.publication-key-result/v1",
                "status": "created",
                "private_key": arguments.private_key.as_posix(),
                "public_key": arguments.public_key.as_posix(),
            }
            exit_code = 0
        elif arguments.command == "assemble-defense-pack":
            document = assemble_pack(
                compilation_path=arguments.compilation,
                output_root=arguments.output_root,
                version=arguments.version,
                taxonomy_version=arguments.taxonomy_version,
                sdk_contract_version=(arguments.sdk_contract_version),
                compatibility_path=arguments.compatibility,
            )
            exit_code = 0
        elif arguments.command == "sign-defense-pack":
            document = sign_publication(
                build_result_path=arguments.build_result,
                private_key_path=arguments.private_key,
                channel=arguments.channel,
                output_path=arguments.publication_manifest,
                previous_manifest_path=(arguments.previous_manifest),
            )
            exit_code = 0
        elif arguments.command == "verify-defense-pack":
            document = verify_publication(
                publication_manifest_path=(arguments.publication_manifest),
                archive_path=arguments.archive,
            )
            exit_code = 0
        elif arguments.command == "update-defense-channel":
            document = update_channel(
                channel=arguments.channel,
                publication_manifest_path=(arguments.publication_manifest),
                channel_index_path=arguments.channel_index,
            )
            exit_code = 0
        elif arguments.command == "retire-defense-pack":
            import datetime as dt

            document = retire_pack(
                publication_manifest_path=(arguments.publication_manifest),
                reason=arguments.reason,
                issuer=arguments.issuer,
                replacement_version=(arguments.replacement_version),
                retired_at=dt.datetime.now(dt.UTC),
                ledger_path=arguments.ledger,
            )
            exit_code = 0
        elif arguments.command == "ingest-effectiveness-outcome":
            event = json.loads(arguments.event.read_text(encoding="utf-8"))
            if not isinstance(event, dict):
                raise ValueError("effectiveness event must be an object")
            outcome_validator = OutcomeValidator(arguments.schema)
            outcome = outcome_validator.validate(event)
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
            document = verify_effectiveness_report(arguments.report_directory)
            exit_code = 0
        elif arguments.command == "compare-effectiveness":
            document = compare_reports(
                baseline_path=arguments.baseline,
                current_path=arguments.current,
            )
            exit_code = 0
        else:
            return 2
        serialized = (
            json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        if arguments.output:
            arguments.output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            arguments.output.write_text(
                serialized,
                encoding="utf-8",
            )
        else:
            sys.stdout.write(serialized)
        return exit_code
    except (OSError, ValueError, ContractError) as error:
        print(f"l9-intelligence: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from l9_debt_intelligence.contracts.canonical import sha256_document

from .attribution import AttributionAssessment, assess_attribution
from .contracts import (
    RECONSTRUCTION_ALGORITHM_VERSION,
    RECONSTRUCTION_CONTRACT_VERSION,
    NormalizedObservation,
    ResolutionEpisode,
)
from .equivalence import evaluate_validation_equivalence
from .flakiness import classify_flakiness


class ReconstructionError(ValueError):
    pass


@dataclass(frozen=True)
class TemporalEvidenceGraph:
    nodes: tuple[tuple[str, str], ...]
    edges: tuple[tuple[str, str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "l9.historical-temporal-evidence-graph/v1",
            "nodes": [
                {"id": node_id, "type": node_type} for node_id, node_type in self.nodes
            ],
            "edges": [
                {"type": edge_type, "source": source, "target": target}
                for edge_type, source, target in self.edges
            ],
        }


def build_temporal_graph(
    observations: tuple[NormalizedObservation, ...],
) -> TemporalEvidenceGraph:
    nodes: set[tuple[str, str]] = set()
    edges: set[tuple[str, str, str]] = set()
    for observation in observations:
        if observation.kind == "commit":
            revision = _string(observation.data.get("revision"))
            if revision is None:
                continue
            nodes.add((f"revision:{revision}", "revision"))
            parents = observation.data.get("parent_revisions")
            if isinstance(parents, list):
                for parent in parents:
                    if not isinstance(parent, str):
                        continue
                    nodes.add((f"revision:{parent}", "revision"))
                    edges.add(
                        (
                            "revision_parent",
                            f"revision:{parent}",
                            f"revision:{revision}",
                        )
                    )
        elif observation.kind == "ci_execution":
            execution = _string(observation.data.get("execution_ref"))
            revision = _string(observation.data.get("revision"))
            if execution is None:
                continue
            nodes.add((f"execution:{execution}", "ci_execution"))
            if revision is not None:
                nodes.add((f"revision:{revision}", "revision"))
                edges.add(
                    (
                        "execution_for_revision",
                        f"revision:{revision}",
                        f"execution:{execution}",
                    )
                )
        elif observation.kind == "ci_job":
            job = _string(observation.data.get("job_ref"))
            execution = _string(observation.data.get("execution_ref"))
            if job is not None:
                nodes.add((f"job:{job}", "ci_job"))
                if execution is not None:
                    edges.add(
                        (
                            "job_part_of_execution",
                            f"execution:{execution}",
                            f"job:{job}",
                        )
                    )
        elif observation.kind == "failure":
            occurrence = _string(observation.data.get("occurrence_identity"))
            execution = _string(observation.data.get("execution_ref"))
            if occurrence is not None:
                nodes.add((f"failure:{occurrence}", "failure_occurrence"))
                if execution is not None:
                    edges.add(
                        (
                            "failure_observed_in",
                            f"execution:{execution}",
                            f"failure:{occurrence}",
                        )
                    )
        elif observation.kind == "change":
            nodes.add((f"change:{observation.observation_id}", "change"))
        elif observation.kind == "validation":
            nodes.add((f"validation:{observation.observation_id}", "validation"))
        elif observation.kind in {"review_signal", "textual_hint"}:
            nodes.add((f"human:{observation.observation_id}", "human_signal"))
    return TemporalEvidenceGraph(tuple(sorted(nodes)), tuple(sorted(edges)))


def reconstruct_episodes(
    observations: tuple[NormalizedObservation, ...],
    *,
    closed_loop_lineage: dict[str, Any] | None = None,
) -> tuple[ResolutionEpisode, ...]:
    pulls = [item for item in observations if item.kind == "pull_request"]
    if not pulls:
        raise ReconstructionError("pull request context is required")
    pull = sorted(pulls, key=lambda item: item.observation_id)[0]
    runs = [item for item in observations if item.kind == "ci_execution"]
    jobs = [item for item in observations if item.kind == "ci_job"]
    failures = [item for item in observations if item.kind == "failure"]
    changes = [item for item in observations if item.kind == "change"]
    signals = [item for item in observations if item.kind == "review_signal"]

    parent: dict[str, tuple[str, ...]] = {}
    base_revision = _string(pull.data.get("base_revision"))
    if base_revision is not None:
        parent[base_revision] = ()
    for commit in (item for item in observations if item.kind == "commit"):
        revision = _string(commit.data.get("revision"))
        parents = commit.data.get("parent_revisions")
        if revision is None or not isinstance(parents, list):
            continue
        parent[revision] = tuple(
            parent_revision
            for parent_revision in parents
            if isinstance(parent_revision, str)
        )

    jobs_by_run = _many(jobs, "execution_ref")
    failures_by_run = _many(failures, "execution_ref")
    runs_by_id = _one(runs, "execution_ref")
    changes_by_after = _one(changes, "after_revision")
    graph = build_temporal_graph(observations)
    episodes: list[ResolutionEpisode] = []

    pr_confounders: set[str] = set()
    for signal in signals:
        if signal.data.get("signal") == "base_ref_changed":
            pr_confounders.add("base_branch_update")
        if signal.data.get("signal") == "head_ref_force_pushed":
            pr_confounders.add("force_updated_pr_branch")
    if pull.data.get("merge_method_hint") == "squash":
        pr_confounders.add("squash_merge")

    for failure in failures:
        before_execution = _string(failure.data.get("execution_ref"))
        before_job_ref = _string(failure.data.get("job_ref"))
        job_name = _string(failure.data.get("job_name"))
        semantic_identity = _string(failure.data.get("semantic_failure_identity"))
        if None in {
            before_execution,
            before_job_ref,
            job_name,
            semantic_identity,
        }:
            continue
        assert before_execution is not None
        assert before_job_ref is not None
        assert job_name is not None
        assert semantic_identity is not None

        before = runs_by_id.get(before_execution)
        before_job = _find(
            jobs_by_run.get(before_execution, ()),
            "job_ref",
            before_job_ref,
        )
        if before is None or before_job is None:
            continue
        after = _next_run(before, runs, parent)
        if after is None:
            continue

        after_execution = _string(after.data.get("execution_ref"))
        before_revision = _string(before.data.get("revision"))
        after_revision = _string(after.data.get("revision"))
        if after_execution is None or before_revision is None or after_revision is None:
            continue

        after_jobs = jobs_by_run.get(after_execution, ())
        after_job = _find(after_jobs, "name", job_name)
        path = _path(before_revision, after_revision, parent)
        transition = tuple(
            changes_by_after[revision]
            for revision in (path or ())
            if revision in changes_by_after
        )
        intervention_missing = path is not None and len(transition) != len(path)
        equivalence = evaluate_validation_equivalence(
            before_run=before,
            after_run=after,
            before_job=before_job,
            after_job=after_job,
            changes=transition,
        )

        after_identities = tuple(
            identity
            for item in failures_by_run.get(after_execution, ())
            if (identity := _string(item.data.get("semantic_failure_identity")))
            is not None
        )
        before_identities = {
            identity
            for item in failures_by_run.get(before_execution, ())
            if (identity := _string(item.data.get("semantic_failure_identity")))
            is not None
        }
        extra_confounders = set(pr_confounders)
        if intervention_missing:
            extra_confounders.add("intervention_evidence_missing")

        assessment = assess_attribution(
            before_run=before,
            after_run=after,
            target_after_job=after_job,
            all_after_jobs=after_jobs,
            changes=transition,
            equivalence=equivalence,
            same_revision=before_revision == after_revision,
            target_failure_present=semantic_identity in after_identities,
            new_failure_count=sum(
                identity != semantic_identity for identity in after_identities
            ),
            before_failure_count=len(before_identities),
            extra_confounders=tuple(sorted(extra_confounders)),
        )
        flake = classify_flakiness(failure_run=before, runs=tuple(runs))
        if not flake.repair_credit_allowed and assessment.outcome == "clean_verified":
            assessment = AttributionAssessment(
                "U",
                "unresolved",
                tuple(
                    sorted(set(assessment.confounders + ("verified_flaky_failure",)))
                ),
                min(assessment.evidence_completeness, 50),
                tuple(
                    sorted(
                        set(
                            assessment.limitations
                            + ("verified flaky failure cannot receive repair credit",)
                        )
                    )
                ),
                "outcome_unknown",
                True,
            )
        source_refs = sorted(
            {
                ref
                for item in (
                    failure,
                    before,
                    before_job,
                    after,
                    *after_jobs,
                    *transition,
                    *failures_by_run.get(after_execution, ()),
                )
                for ref in item.provenance_refs
            }
        )
        failure_time = _historical_time(before_job, before)
        validation_time = _historical_time(after_job, after)
        intervention_time = _intervention_time(transition, after)

        episode = ResolutionEpisode.build(
            context={
                "repository_ref": pull.repository_ref,
                "pull_request_ref": pull.data.get("number"),
                "base_revision": pull.data.get("base_revision"),
                "head_revision": pull.data.get("head_revision"),
            },
            failure_state={
                "failure_refs": [failure.observation_id],
                "semantic_failure_identity": semantic_identity,
                "identity_authority": failure.data.get("identity_authority"),
                "occurrence_identities": [failure.data.get("occurrence_identity")],
                "evidence_availability": failure.evidence_availability,
                "execution_ref": before_execution,
                "provider_time": failure_time,
            },
            intervention={
                "before_revision": before_revision,
                "after_revision": after_revision,
                "change_refs": [item.observation_id for item in transition],
                "change_fingerprint": sha256_document(
                    [item.data.get("change_fingerprint") for item in transition]
                ),
                "remediation_class_optional": None,
                "provider_time": intervention_time,
            },
            validation={
                "validation_refs": [after.observation_id]
                + ([after_job.observation_id] if after_job else []),
                "execution_ref": after_execution,
                "equivalent_check_relationship": equivalence.status,
                "equivalence_reasons": list(equivalence.reasons),
                "failure_after_state": (
                    "present"
                    if semantic_identity in after_identities
                    else "absent"
                    if after_job
                    else "unknown"
                ),
                "newly_observed_failures": sorted(
                    identity
                    for identity in after_identities
                    if identity != semantic_identity
                ),
                "validation_completeness": equivalence.completeness,
                "provider_time": validation_time,
            },
            outcome=assessment.outcome,
            attribution={
                **assessment.as_dict(),
                "flake_classification": flake.classification,
                "flake_indicators": list(flake.indicators),
                "prevention_learning": (
                    "separate_from_repair_learning"
                    if flake.classification == "verified"
                    else "normal"
                ),
            },
            provenance={
                "source_observation_refs": source_refs,
                "algorithm_version": RECONSTRUCTION_ALGORITHM_VERSION,
                "schema_version": RECONSTRUCTION_CONTRACT_VERSION,
                "temporal_graph_digest": sha256_document(graph.as_dict()),
                "closed_loop_lineage": _lineage(closed_loop_lineage),
            },
        )
        episodes.append(episode)

    unique = {episode.episode_id: episode for episode in episodes}
    return tuple(unique[key] for key in sorted(unique))


def _lineage(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    allowed = {
        "active_defense_pack",
        "active_rule_ids",
        "resolver_strategy_source",
        "lsp_intervention",
        "pr_repair_intervention",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ReconstructionError(
            "unsupported closed-loop lineage fields: " + ", ".join(sorted(unknown))
        )
    return {key: value[key] for key in sorted(value)}


def _one(
    items: Iterable[NormalizedObservation], key: str
) -> dict[str, NormalizedObservation]:
    result: dict[str, NormalizedObservation] = {}
    for item in items:
        value = _string(item.data.get(key))
        if value is not None:
            result[value] = item
    return result


def _many(
    items: Iterable[NormalizedObservation], key: str
) -> dict[str, tuple[NormalizedObservation, ...]]:
    grouped: defaultdict[str, list[NormalizedObservation]] = defaultdict(list)
    for item in items:
        value = _string(item.data.get(key))
        if value is not None:
            grouped[value].append(item)
    return {
        key_value: tuple(
            sorted(group, key=lambda observation: observation.observation_id)
        )
        for key_value, group in grouped.items()
    }


def _find(
    items: tuple[NormalizedObservation, ...], key: str, value: str
) -> NormalizedObservation | None:
    return next((item for item in items if item.data.get(key) == value), None)


def _path(
    before: str,
    after: str,
    parent: dict[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    if before == after:
        return ()
    paths: list[tuple[str, ...]] = []

    def walk(current: str, seen: set[str], trail: tuple[str, ...]) -> None:
        if len(paths) > 1:
            return
        if current == before:
            paths.append(tuple(reversed(trail)))
            return
        if current in seen:
            return
        for parent_revision in parent.get(current, ()):
            walk(parent_revision, seen | {current}, trail + (current,))

    walk(after, set(), ())
    return paths[0] if len(paths) == 1 else None


def _next_run(
    before: NormalizedObservation,
    runs: list[NormalizedObservation],
    parent: dict[str, tuple[str, ...]],
) -> NormalizedObservation | None:
    before_revision = _string(before.data.get("revision"))
    workflow = before.data.get("workflow_identity")
    before_attempt = _positive_int(before.data.get("attempt"))
    same_revision: list[NormalizedObservation] = []
    later: list[tuple[int, NormalizedObservation]] = []

    for run in runs:
        if run.observation_id == before.observation_id:
            continue
        if run.data.get("workflow_identity") != workflow:
            continue
        run_revision = _string(run.data.get("revision"))
        run_attempt = _positive_int(run.data.get("attempt"))
        if run_revision == before_revision and (
            before_attempt is None
            or run_attempt is None
            or run_attempt > before_attempt
        ):
            same_revision.append(run)
        elif before_revision is not None and run_revision is not None:
            path = _path(before_revision, run_revision, parent)
            if path:
                later.append((len(path), run))

    if same_revision:
        return sorted(
            same_revision,
            key=lambda item: (
                _positive_int(item.data.get("attempt")) or 0,
                item.observation_id,
            ),
        )[0]
    if later:
        return sorted(later, key=lambda item: (item[0], item[1].observation_id))[0][1]
    return None


def _historical_time(
    job: NormalizedObservation | None,
    run: NormalizedObservation,
) -> str | None:
    if job is not None:
        completed = _string(job.data.get("completed_at"))
        if completed is not None:
            return completed
        started = _string(job.data.get("started_at"))
        if started is not None:
            return started
    return _string(run.data.get("updated_at")) or _string(run.data.get("created_at"))


def _intervention_time(
    changes: tuple[NormalizedObservation, ...],
    validation_run: NormalizedObservation,
) -> str | None:
    for change in reversed(changes):
        committed_at = _string(change.data.get("committed_at"))
        if committed_at is not None:
            return committed_at
    return _string(validation_run.data.get("created_at"))


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None

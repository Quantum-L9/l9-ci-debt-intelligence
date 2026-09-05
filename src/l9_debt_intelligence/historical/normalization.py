from __future__ import annotations

from typing import Any, cast

from l9_debt_intelligence.contracts.canonical import sha256_document

from .contracts import (
    AcquisitionObservation,
    NormalizedKind,
    NormalizedObservation,
    deterministic_id,
)

_ENVIRONMENT_BASENAMES = {
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "dockerfile",
}
_SKIP_MARKERS = (
    "pytest.mark.skip",
    "pytest.mark.xfail",
    "pytest.skip(",
    "unittest.skip",
    "skiptests(",
    "if: false",
    "if: ${{ false }}",
)


def normalize_observations(
    observations: tuple[AcquisitionObservation, ...],
) -> tuple[NormalizedObservation, ...]:
    normalized: list[NormalizedObservation] = []
    for observation in observations:
        normalized.extend(normalize_observation(observation))
    return tuple(sorted(normalized, key=lambda item: item.observation_id))


def normalize_observation(
    observation: AcquisitionObservation,
) -> tuple[NormalizedObservation, ...]:
    kind = observation.object_kind
    payload = _object_payload(observation) if kind != "job_log" else None

    if kind == "pull_request":
        assert payload is not None
        base = _nested(payload, "base", "sha")
        head = _nested(payload, "head", "sha")
        auto_merge = payload.get("auto_merge")
        merge_method = (
            _string(auto_merge.get("merge_method"))
            if isinstance(auto_merge, dict)
            else None
        )
        return (
            _build(
                observation,
                "pull_request",
                {
                    "number": (
                        payload.get("number")
                        if isinstance(payload.get("number"), int)
                        and not isinstance(payload.get("number"), bool)
                        else None
                    ),
                    "base_revision": base,
                    "head_revision": head,
                    "merge_commit_revision": _string(payload.get("merge_commit_sha")),
                    "merge_method_hint": merge_method,
                    "merged": (
                        bool(payload.get("merged")) if "merged" in payload else None
                    ),
                    "updated_at": _string(payload.get("updated_at")),
                },
                "complete" if base and head else "partial",
            ),
        )

    if kind == "timeline_event":
        assert payload is not None
        event = _string(payload.get("event"))
        if event not in {"base_ref_changed", "head_ref_force_pushed"}:
            return ()
        return (
            _build(
                observation,
                "review_signal",
                {
                    "signal": event,
                    "created_at": _string(payload.get("created_at")),
                    "commit_id": _string(payload.get("commit_id")),
                    "before_commit": _string(payload.get("before_commit")),
                    "after_commit": _string(payload.get("after_commit")),
                },
                "direct_provider_event",
            ),
        )

    if kind == "commit":
        assert payload is not None
        revision = _string(payload.get("sha"))
        parents = _parents(payload.get("parents"))
        files = _files(payload.get("files"))
        committed_at = _committed_at(payload)
        commit = _build(
            observation,
            "commit",
            {
                "revision": revision,
                "parent_revisions": parents,
                "committed_at": committed_at,
                "is_merge": len(parents) > 1,
            },
            "complete" if revision else "partial",
        )
        if not revision or not parents:
            return (commit,)
        change = _build(
            observation,
            "change",
            {
                "before_revision": parents[0],
                "after_revision": revision,
                "parent_revisions": parents,
                "committed_at": committed_at,
                "change_fingerprint": sha256_document(files),
                "file_count": len(files),
                "workflow_changed": any(
                    str(item["path"]).startswith(".github/workflows/") for item in files
                ),
                "test_changed": any(_is_test(str(item["path"])) for item in files),
                "environment_changed": any(
                    _is_env(str(item["path"])) for item in files
                ),
                "dependency_lockfile_change": any(
                    _is_lock(str(item["path"])) for item in files
                ),
                "validation_weakening_signals": _weakening(files),
                "is_merge": len(parents) > 1,
                "changed_paths": [str(item["path"]) for item in files],
            },
            "complete" if files else "partial",
        )
        return commit, change

    if kind in {"workflow_run", "workflow_attempt"}:
        assert payload is not None
        run_ref = _strint(payload.get("id"))
        revision = _string(payload.get("head_sha"))
        attempt = _attempt(observation, payload)
        execution_ref = _execution_ref(run_ref, attempt)
        return (
            _build(
                observation,
                "ci_execution",
                {
                    "provider_run_ref": run_ref,
                    "execution_ref": execution_ref,
                    "revision": revision,
                    "workflow_identity": _workflow(payload),
                    "attempt": attempt,
                    "status": _string(payload.get("status")),
                    "conclusion": _string(payload.get("conclusion")),
                    "event": _string(payload.get("event")),
                    "created_at": _string(payload.get("created_at")),
                    "updated_at": _string(payload.get("updated_at")),
                },
                "complete" if execution_ref and revision else "partial",
            ),
        )

    if kind == "ci_job":
        assert payload is not None
        run_ref = _strint(payload.get("run_id"))
        attempt = _attempt(observation, payload)
        execution_ref = _execution_ref(run_ref, attempt)
        job_ref = _strint(payload.get("id"))
        revision = _string(payload.get("head_sha"))
        name = _string(payload.get("name"))
        steps = _steps(payload.get("steps"))
        job = _build(
            observation,
            "ci_job",
            {
                "job_ref": job_ref,
                "provider_run_ref": run_ref,
                "execution_ref": execution_ref,
                "attempt": attempt,
                "revision": revision,
                "name": name,
                "workflow_name": _string(payload.get("workflow_name")),
                "status": _string(payload.get("status")),
                "conclusion": _string(payload.get("conclusion")),
                "started_at": _string(payload.get("started_at")),
                "completed_at": _string(payload.get("completed_at")),
                "steps": steps,
            },
            "complete" if job_ref and execution_ref and name else "partial",
        )
        normalized_jobs: list[NormalizedObservation] = [job]
        if _string(payload.get("conclusion")) == "failure":
            failed_steps = [
                str(step["name"])
                for step in steps
                if step.get("conclusion") == "failure"
            ]
            semantic_identity = deterministic_id(
                "historical:",
                {
                    "producer_family": "github_actions",
                    "finding_kind": "ci_job_failure",
                    "job_name": name or "unknown",
                    "failed_steps": failed_steps,
                },
            )
            occurrence_identity = deterministic_id(
                "hfo_",
                {
                    "repository_ref": observation.repository_ref,
                    "revision": revision,
                    "execution_ref": execution_ref,
                    "attempt_ref": attempt,
                    "job_ref": job_ref,
                },
            )
            normalized_jobs.append(
                _build(
                    observation,
                    "failure",
                    {
                        "semantic_failure_identity": semantic_identity,
                        "identity_authority": "historical_noncanonical",
                        "occurrence_identity": occurrence_identity,
                        "revision": revision,
                        "execution_ref": execution_ref,
                        "job_ref": job_ref,
                        "job_name": name,
                        "failed_steps": failed_steps,
                    },
                    "complete" if failed_steps else "partial",
                    ("failed_step_unavailable",) if not failed_steps else (),
                )
            )
        return tuple(normalized_jobs)

    if kind == "check_run":
        assert payload is not None
        return (
            _build(
                observation,
                "validation",
                {
                    "check_ref": _strint(payload.get("id")),
                    "revision": _string(payload.get("head_sha")),
                    "name": _string(payload.get("name")),
                    "status": _string(payload.get("status")),
                    "conclusion": _string(payload.get("conclusion")),
                    "started_at": _string(payload.get("started_at")),
                    "completed_at": _string(payload.get("completed_at")),
                },
                "complete",
            ),
        )

    if kind == "job_log":
        return (
            _build(
                observation,
                "textual_hint",
                {
                    "source_kind": "job_log",
                    "content_digest": observation.observed_content_digest,
                    "raw_text_retained": False,
                },
                "digest_only",
                ("raw_log_not_normalized_or_projected",),
            ),
        )
    return ()


def _build(
    source: AcquisitionObservation,
    kind: NormalizedKind,
    data: dict[str, Any],
    availability: str,
    limitations: tuple[str, ...] = (),
) -> NormalizedObservation:
    return NormalizedObservation.build(
        kind=kind,
        repository_ref=source.repository_ref,
        provenance_refs=(source.observation_id,),
        evidence_availability=availability,
        limitations=tuple(sorted(set(source.limitations + limitations))),
        data=data,
    )


def _object_payload(observation: AcquisitionObservation) -> dict[str, Any]:
    if not isinstance(observation.payload, dict):
        raise ValueError(f"{observation.object_kind} payload must be an object")
    return cast(dict[str, Any], observation.payload)


def _attempt(
    observation: AcquisitionObservation, payload: dict[str, Any]
) -> int | None:
    value = payload.get("run_attempt")
    if not isinstance(value, int) or isinstance(value, bool):
        value = observation.provenance.get("run_attempt")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _execution_ref(run_ref: str | None, attempt: int | None) -> str | None:
    if run_ref is None:
        return None
    if attempt is None:
        return run_ref
    return f"{run_ref}:attempt:{attempt}"


def _nested(document: dict[str, Any], key: str, child: str) -> str | None:
    value = document.get(key)
    return _string(value.get(child)) if isinstance(value, dict) else None


def _workflow(payload: dict[str, Any]) -> str:
    return (
        _string(payload.get("path"))
        or _strint(payload.get("workflow_id"))
        or _string(payload.get("name"))
        or "unknown"
    )


def _parents(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    parents: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        revision = _string(item.get("sha"))
        if revision:
            parents.append(revision)
    return parents


def _committed_at(payload: dict[str, Any]) -> str | None:
    commit = payload.get("commit")
    if not isinstance(commit, dict):
        return None
    committer = commit.get("committer")
    if not isinstance(committer, dict):
        return None
    return _string(committer.get("date"))


def _files(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    files: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _string(item.get("filename"))
        if not path:
            continue
        files.append(
            {
                "path": path,
                "status": _string(item.get("status")) or "unknown",
                "patch": _string(item.get("patch")),
            }
        )
    return sorted(files, key=lambda item: str(item["path"]))


def _steps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    steps: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _string(item.get("name"))
        if not name:
            continue
        steps.append(
            {
                "name": name,
                "status": _string(item.get("status")),
                "conclusion": _string(item.get("conclusion")),
            }
        )
    return steps


def _weakening(files: list[dict[str, Any]]) -> list[str]:
    signals: set[str] = set()
    for item in files:
        path = str(item["path"])
        patch = item.get("patch")
        if item["status"] == "removed" and (
            _is_test(path) or path.startswith(".github/workflows/")
        ):
            signals.add("validation_file_removed")
        if isinstance(patch, str):
            additions = "\n".join(
                line[1:].lower()
                for line in patch.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
            if any(marker in additions for marker in _SKIP_MARKERS):
                signals.add("validation_skip_added")
    return sorted(signals)


def _is_test(path: str) -> bool:
    lower = path.lower()
    return (
        lower.startswith("tests/")
        or "/tests/" in lower
        or lower.endswith("_test.py")
        or lower.startswith("test_")
    )


def _is_env(path: str) -> bool:
    basename = path.lower().rsplit("/", 1)[-1]
    return basename in _ENVIRONMENT_BASENAMES or basename.startswith("requirements-")


def _is_lock(path: str) -> bool:
    basename = path.lower().rsplit("/", 1)[-1]
    return basename.endswith(".lock") or basename in {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _strint(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)) and str(value):
        return str(value)
    return None

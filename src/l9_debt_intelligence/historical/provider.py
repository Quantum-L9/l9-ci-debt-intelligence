from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib import error, parse, request

from .contracts import AcquisitionObservation


class ProviderError(RuntimeError):
    """Historical provider acquisition failed without inventing missing data."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self, *, method: str, url: str, headers: dict[str, str]
    ) -> HttpResponse: ...


class UrlLibTransport:
    def request(
        self, *, method: str, url: str, headers: dict[str, str]
    ) -> HttpResponse:
        req = request.Request(url=url, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=30) as response:
                return HttpResponse(
                    int(response.status),
                    {
                        str(key).lower(): str(value)
                        for key, value in response.headers.items()
                    },
                    response.read(),
                )
        except error.HTTPError as exc:
            return HttpResponse(
                int(exc.code),
                {
                    str(key).lower(): str(value)
                    for key, value in exc.headers.items()
                },
                exc.read(),
            )
        except error.URLError as exc:
            raise ProviderError(
                f"provider transport unavailable: {exc.reason}"
            ) from exc


class GitHubHistoricalProvider:
    _TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})

    def __init__(
        self,
        *,
        token: str,
        transport: HttpTransport | None = None,
        api_base: str = "https://api.github.com",
        max_pages: int = 10,
        max_retries: int = 2,
    ) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        if max_retries < 0 or max_retries > 5:
            raise ValueError("max_retries must be between zero and five")
        self._token = token
        self._transport = transport or UrlLibTransport()
        self._api_base = api_base.rstrip("/")
        self._max_pages = max_pages
        self._max_retries = max_retries

    def harvest_pull_request(
        self,
        *,
        repository: str,
        pr_number: int,
        include_logs: bool = True,
    ) -> tuple[AcquisitionObservation, ...]:
        owner, name = self._repository_parts(repository)
        repo = f"repos/{parse.quote(owner)}/{parse.quote(name)}"
        observations: list[AcquisitionObservation] = []

        pull_path = f"/{repo}/pulls/{pr_number}"
        pull = self._get_object(pull_path)
        observations.append(
            self._obs(
                repository,
                "pull_request",
                str(pull.get("id", pr_number)),
                pull,
                pull_path,
            )
        )

        timeline_path = f"/{repo}/issues/{pr_number}/timeline"
        for index, event in enumerate(self._get_list(timeline_path)):
            if event.get("event") not in {
                "base_ref_changed",
                "head_ref_force_pushed",
            }:
                continue
            observations.append(
                self._obs(
                    repository,
                    "timeline_event",
                    str(event.get("id", index)),
                    event,
                    timeline_path,
                )
            )

        revisions: list[str] = []
        for summary in self._get_list(f"/{repo}/pulls/{pr_number}/commits"):
            revision = summary.get("sha")
            if not isinstance(revision, str) or not revision:
                continue
            revisions.append(revision)
            path = f"/{repo}/commits/{parse.quote(revision)}"
            observations.append(
                self._obs(
                    repository,
                    "commit",
                    revision,
                    self._get_paginated_commit(path),
                    path,
                )
            )

        seen_runs: set[str] = set()
        seen_jobs: set[str] = set()
        seen_checks: set[str] = set()
        for revision in revisions:
            runs_path = (
                f"/{repo}/actions/runs?event=pull_request"
                f"&head_sha={parse.quote(revision)}"
            )
            runs = self._get_collection(runs_path, field="workflow_runs")
            for run in runs:
                run_id = _provider_id(run.get("id"))
                if run_id is None or run_id in seen_runs:
                    continue
                seen_runs.add(run_id)
                run_attempt = run.get("run_attempt")
                latest_attempt = (
                    run_attempt
                    if isinstance(run_attempt, int)
                    and not isinstance(run_attempt, bool)
                    and run_attempt > 0
                    else 1
                )
                missing_attempt_history = False
                attempts: list[tuple[int, dict[str, Any]]] = []
                for attempt_number in range(1, latest_attempt):
                    attempt_path = (
                        f"/{repo}/actions/runs/{run_id}/attempts/{attempt_number}"
                    )
                    document = self._get_optional_object(attempt_path)
                    if document is None:
                        missing_attempt_history = True
                    else:
                        attempts.append((attempt_number, document))
                attempts.append((latest_attempt, run))

                for attempt_number, document in attempts:
                    attempt_path = (
                        f"/{repo}/actions/runs/{run_id}/attempts/{attempt_number}"
                    )
                    limitations = (
                        ("provider_attempt_history_missing",)
                        if missing_attempt_history
                        else ()
                    )
                    observations.append(
                        self._obs(
                            repository,
                            "workflow_attempt",
                            f"{run_id}:attempt:{attempt_number}",
                            document,
                            attempt_path,
                            limitations,
                            {"run_attempt": attempt_number},
                        )
                    )

                jobs_path = f"/{repo}/actions/runs/{run_id}/jobs?filter=all"
                for job in self._get_collection(jobs_path, field="jobs"):
                    job_id = _provider_id(job.get("id"))
                    if job_id is None or job_id in seen_jobs:
                        continue
                    seen_jobs.add(job_id)
                    limitations_list: list[str] = []
                    log: AcquisitionObservation | None = None
                    attempt = job.get("run_attempt")
                    if include_logs:
                        log_path = f"/{repo}/actions/jobs/{job_id}/logs"
                        response = self._raw_request(log_path, accept="text/plain")
                        if response.status == 200:
                            log = self._obs(
                                repository,
                                "job_log",
                                job_id,
                                response.body.decode("utf-8", errors="replace"),
                                log_path,
                                (),
                                {"run_attempt": attempt},
                            )
                        elif response.status in {404, 410}:
                            limitations_list.append("job_log_unavailable")
                        else:
                            self._raise_status(log_path, response)
                    observations.append(
                        self._obs(
                            repository,
                            "ci_job",
                            job_id,
                            job,
                            f"/{repo}/actions/jobs/{job_id}",
                            tuple(limitations_list),
                            {"run_attempt": attempt},
                        )
                    )
                    if log is not None:
                        observations.append(log)

            checks_path = f"/{repo}/commits/{parse.quote(revision)}/check-runs"
            for check in self._get_collection(checks_path, field="check_runs"):
                check_id = _provider_id(check.get("id"))
                if check_id is None or check_id in seen_checks:
                    continue
                seen_checks.add(check_id)
                observations.append(
                    self._obs(
                        repository,
                        "check_run",
                        check_id,
                        check,
                        f"/{repo}/check-runs/{check_id}",
                    )
                )

        return tuple(
            sorted(
                observations,
                key=lambda item: (item.object_kind, item.observation_id),
            )
        )

    def _obs(
        self,
        repository: str,
        kind: str,
        object_id: str,
        payload: Any,
        path: str,
        limitations: tuple[str, ...] = (),
        extra: dict[str, Any] | None = None,
    ) -> AcquisitionObservation:
        provenance: dict[str, Any] = {
            "provider": "github",
            "resource": path,
            "provider_object_id": object_id,
        }
        provenance.update(extra or {})
        return AcquisitionObservation.build(
            provider="github",
            repository_ref=repository,
            object_kind=kind,
            provider_object_id=object_id,
            payload=payload,
            provenance=provenance,
            limitations=limitations,
        )

    def _raw_request(
        self, path: str, *, accept: str = "application/vnd.github+json"
    ) -> HttpResponse:
        last_response: HttpResponse | None = None
        for attempt in range(self._max_retries + 1):
            response = self._transport.request(
                method="GET",
                url=f"{self._api_base}{path}",
                headers={
                    "accept": accept,
                    "authorization": f"Bearer {self._token}",
                    "x-github-api-version": "2022-11-28",
                    "user-agent": "l9-ci-debt-intelligence-historical-miner",
                },
            )
            last_response = response
            if response.status not in self._TRANSIENT_STATUSES:
                return response
            if attempt < self._max_retries:
                time.sleep(min(2**attempt, 4))
        if last_response is None:
            raise ProviderError("provider retry loop executed zero attempts")
        return last_response

    def _request(
        self, path: str, *, accept: str = "application/vnd.github+json"
    ) -> HttpResponse:
        response = self._raw_request(path, accept=accept)
        if response.status != 200:
            self._raise_status(path, response)
        return response

    def _get_object(self, path: str) -> dict[str, Any]:
        parsed = self._parse_json(self._request(path).body, path)
        if not isinstance(parsed, dict):
            raise ProviderError(f"expected object from GitHub at {path}")
        return cast(dict[str, Any], parsed)

    def _get_optional_object(self, path: str) -> dict[str, Any] | None:
        response = self._raw_request(path)
        if response.status in {404, 410}:
            return None
        if response.status != 200:
            self._raise_status(path, response)
        parsed = self._parse_json(response.body, path)
        if not isinstance(parsed, dict):
            raise ProviderError(f"expected object from GitHub at {path}")
        return cast(dict[str, Any], parsed)

    def _get_paginated_commit(self, path: str) -> dict[str, Any]:
        first: dict[str, Any] | None = None
        files: list[dict[str, Any]] = []
        for page in range(1, self._max_pages + 1):
            document = self._get_object(f"{path}?per_page=100&page={page}")
            page_files = self._objects(document.get("files", []), "files")
            if first is None:
                first = dict(document)
            files.extend(page_files)
            if len(page_files) < 100:
                break
        else:
            raise ProviderError(f"pagination bound reached for commit at {path}")
        if first is None:
            raise ProviderError(f"commit unavailable at {path}")
        first["files"] = files
        return first

    def _get_collection(self, path: str, *, field: str) -> list[dict[str, Any]]:
        items_out: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, self._max_pages + 1):
            page_path = f"{path}{separator}per_page=100&page={page}"
            document = self._get_object(page_path)
            items = self._objects(document.get(field, []), field)
            items_out.extend(items)
            if len(items) < 100:
                break
        else:
            raise ProviderError(f"pagination bound reached for {path}")
        return items_out

    def _get_list(self, path: str) -> list[dict[str, Any]]:
        items_out: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, self._max_pages + 1):
            page_path = f"{path}{separator}per_page=100&page={page}"
            parsed = self._parse_json(self._request(page_path).body, page_path)
            if not isinstance(parsed, list):
                raise ProviderError(f"expected list from GitHub at {page_path}")
            items = self._objects(parsed, "page")
            items_out.extend(items)
            if len(items) < 100:
                break
        else:
            raise ProviderError(f"pagination bound reached for {path}")
        return items_out

    @staticmethod
    def _parse_json(body: bytes, path: str) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"invalid JSON from GitHub at {path}") from exc

    @staticmethod
    def _objects(value: Any, field: str) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ProviderError(f"GitHub field {field} must be a list")
        if not all(isinstance(item, dict) for item in value):
            raise ProviderError(f"GitHub field {field} contains a non-object")
        return cast(list[dict[str, Any]], value)

    @staticmethod
    def _repository_parts(repository: str) -> tuple[str, str]:
        parts = repository.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("repository must be owner/name")
        return parts[0], parts[1]

    @staticmethod
    def _raise_status(path: str, response: HttpResponse) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        detail = ""
        if remaining == "0" or response.status in {403, 429}:
            detail = (
                f"; rate_limit_remaining={remaining or 'unknown'} "
                f"reset={reset or 'unknown'}"
            )
        raise ProviderError(
            f"GitHub acquisition failed at {path}: HTTP {response.status}{detail}"
        )


def _provider_id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)) and str(value):
        return str(value)
    return None

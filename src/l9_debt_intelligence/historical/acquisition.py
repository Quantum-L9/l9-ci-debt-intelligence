from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from l9_debt_intelligence.contracts.canonical import sha256_document

from .contracts import AcquisitionObservation


class HistoricalProvider(Protocol):
    def harvest_pull_request(
        self,
        *,
        repository: str,
        pr_number: int,
        include_logs: bool = True,
    ) -> tuple[AcquisitionObservation, ...]: ...


@dataclass(frozen=True)
class HarvestResult:
    observations: tuple[AcquisitionObservation, ...]
    checkpoint_path: Path | None
    source_set_digest: str


class CheckpointStore:
    """Operational-only resumability state, excluded from logical identity."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(
        self,
        *,
        repository: str,
        pr_number: int,
        observations: tuple[AcquisitionObservation, ...],
    ) -> Path:
        observation_ids = sorted(item.observation_id for item in observations)
        document: dict[str, Any] = {
            "schema_version": "l9.historical-checkpoint/v1",
            "repository_ref": repository,
            "pull_request": pr_number,
            "observation_ids": observation_ids,
            "source_set_digest": sha256_document(observation_ids),
            "identity_authority": "operational_only",
        }
        checkpoint_id = sha256_document(
            {"repository_ref": repository, "pull_request": pr_number}
        )
        self._root.mkdir(parents=True, exist_ok=True)
        destination = self._root / f"{checkpoint_id}.json"
        payload = (
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._root,
            prefix=".checkpoint-",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        os.replace(temporary, destination)
        return destination


class HistoricalHarvester:
    def __init__(
        self,
        *,
        provider: HistoricalProvider,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self._provider = provider
        self._checkpoint_store = checkpoint_store

    def harvest(
        self,
        *,
        repository: str,
        pr_number: int,
        include_logs: bool = True,
    ) -> HarvestResult:
        observations = self._provider.harvest_pull_request(
            repository=repository,
            pr_number=pr_number,
            include_logs=include_logs,
        )
        checkpoint_path = None
        if self._checkpoint_store is not None:
            checkpoint_path = self._checkpoint_store.write(
                repository=repository,
                pr_number=pr_number,
                observations=observations,
            )
        source_set_digest = sha256_document(
            sorted(item.observation_id for item in observations)
        )
        return HarvestResult(
            observations=observations,
            checkpoint_path=checkpoint_path,
            source_set_digest=source_set_digest,
        )

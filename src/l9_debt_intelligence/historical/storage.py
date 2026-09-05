from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import NormalizedObservation, ResolutionEpisode
from .safety import QuarantinedObservation


class HistoricalDerivedStore:
    """Rebuildable historical products outside canonical P1 storage."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write_normalized(self, observation: NormalizedObservation) -> Path:
        return self._write(
            self._root / "normalized" / f"{observation.observation_id}.json",
            observation.as_dict(),
        )

    def write_episode(self, episode: ResolutionEpisode) -> Path:
        algorithm = str(episode.provenance.get("algorithm_version", "unknown"))
        return self._write(
            self._root / "episodes" / algorithm / f"{episode.episode_id}.json",
            episode.as_dict(),
        )

    def write_quarantine(self, item: QuarantinedObservation) -> Path:
        return self._write(
            self._root / "quarantine" / f"{item.observation_id}.json",
            item.as_dict(),
        )

    @staticmethod
    def _write(path: Path, document: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
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
            dir=path.parent,
            prefix=".historical-",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        return path

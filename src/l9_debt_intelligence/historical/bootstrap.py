from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from l9_debt_intelligence.ingestion.models import IngestionResult
from l9_debt_intelligence.ingestion.service import IngestionService
from .acquisition import CheckpointStore, HistoricalHarvester, HistoricalProvider
from .admission import HistoricalAdmissionAdapter, HistoricalProjector
from .normalization import normalize_observations
from .provider import GitHubHistoricalProvider
from .reconstruction import reconstruct_episodes
from .safety import screen_observations
from .storage import HistoricalDerivedStore

@dataclass(frozen=True)
class BootstrapResult:
    repository: str
    pull_request: int
    source_observations: int
    quarantined_observations: int
    normalized_observations: int
    episodes: int
    admission_results: tuple[IngestionResult, ...]
    source_set_digest: str
    def as_dict(self) -> dict[str, Any]:
        return {"schema_version":"l9.historical-bootstrap-result/v1",
                "repository":self.repository,"pull_request":self.pull_request,
                "source_observations":self.source_observations,
                "quarantined_observations":self.quarantined_observations,
                "normalized_observations":self.normalized_observations,
                "episodes":self.episodes,
                "admission_results":[x.as_dict() for x in self.admission_results],
                "source_set_digest":self.source_set_digest}

def run_bootstrap(*, repository: str, pr_number: int, provider: HistoricalProvider,
                  ingress: IngestionService, pseudonym_key: bytes, state_root: Path,
                  include_logs: bool = True,
                  closed_loop_lineage: dict[str, Any] | None = None) -> BootstrapResult:
    _assert_state_root(state_root)
    harvest = HistoricalHarvester(provider=provider,
        checkpoint_store=CheckpointStore(state_root / "checkpoints")).harvest(
        repository=repository, pr_number=pr_number, include_logs=include_logs)
    safety = screen_observations(harvest.observations)
    normalized = normalize_observations(safety.safe)
    episodes = reconstruct_episodes(normalized, closed_loop_lineage=closed_loop_lineage)
    store = HistoricalDerivedStore(state_root / "derived")
    for item in safety.quarantined: store.write_quarantine(item)
    for item in normalized: store.write_normalized(item)
    for item in episodes: store.write_episode(item)
    adapter = HistoricalAdmissionAdapter(ingress=ingress,
        projector=HistoricalProjector(pseudonym_key=pseudonym_key))
    results = tuple(adapter.admit(item) for item in episodes)
    return BootstrapResult(repository, pr_number, len(harvest.observations),
        len(safety.quarantined), len(normalized), len(episodes), results,
        harvest.source_set_digest)

def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]

def build_parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog="python -m l9_debt_intelligence.historical")
    p.add_argument("repository"); p.add_argument("pr_number",type=int)
    p.add_argument("--storage-root",type=Path,required=True)
    p.add_argument("--state-root",type=Path,required=True)
    p.add_argument("--max-pages",type=int,default=10)
    p.add_argument("--without-logs",action="store_true")
    return p

def main(argv: Sequence[str] | None = None) -> int:
    a=build_parser().parse_args(argv)
    token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token: raise ValueError("GITHUB_TOKEN or GH_TOKEN must be set")
    key=os.environ.get("L9_INTELLIGENCE_PSEUDONYM_KEY","").encode()
    if len(key)<32: raise ValueError("L9_INTELLIGENCE_PSEUDONYM_KEY must be at least 32 bytes")
    state=a.state_root.resolve(); corpus=a.storage_root.resolve()
    if _is_relative_to(state,corpus) or _is_relative_to(corpus,state):
        raise ValueError("historical state and canonical corpus storage must be separate")
    _assert_state_root(corpus); root=repository_root()
    ingress=IngestionService(event_schema=root/"schemas/intelligence/corpus-event.schema.json",
        compatibility_registry=root/".l9/producer-compatibility.json",storage_root=corpus)
    lineage_raw=os.environ.get("L9_HISTORICAL_LINEAGE_JSON")
    lineage=json.loads(lineage_raw) if lineage_raw else None
    if lineage is not None and not isinstance(lineage,dict):
        raise ValueError("L9_HISTORICAL_LINEAGE_JSON must contain a JSON object")
    result=run_bootstrap(repository=a.repository,pr_number=a.pr_number,
        provider=GitHubHistoricalProvider(token=token,max_pages=a.max_pages),
        ingress=ingress,pseudonym_key=key,state_root=state,
        include_logs=not a.without_logs,closed_loop_lineage=lineage)
    print(json.dumps(result.as_dict(),sort_keys=True,indent=2))
    statuses={x.status for x in result.admission_results}
    return 0 if result.episodes and statuses.issubset({"accepted","duplicate"}) else 3

def _assert_state_root(path: Path) -> None:
    if _is_relative_to(path.resolve(),repository_root().resolve()):
        raise ValueError("historical runtime state must be outside the source repository")

def _is_relative_to(path: Path,parent: Path) -> bool:
    try: path.relative_to(parent)
    except ValueError: return False
    return True

if __name__ == "__main__": raise SystemExit(main())

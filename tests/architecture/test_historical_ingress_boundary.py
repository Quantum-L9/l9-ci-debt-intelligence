from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL = ROOT / "src/l9_debt_intelligence/historical"


def test_historical_runtime_does_not_own_p1_record_or_storage_identity() -> None:
    forbidden = (
        "FilesystemCorpusStore",
        "record_id(",
        "observation_id(",
        "ledger_sequence",
        "quarantine_id",
    )
    violations: list[str] = []
    for path in HISTORICAL.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append(f"{path.name}:{token}")
    assert violations == []


def test_only_ingestion_adapter_manufactures_corpus_envelope() -> None:
    violations: list[str] = []
    for path in HISTORICAL.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if '"l9.corpus-event/v1"' in text or "'l9.corpus-event/v1'" in text:
            violations.append(path.name)
    assert violations == []

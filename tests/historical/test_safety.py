from __future__ import annotations

from l9_debt_intelligence.historical.contracts import AcquisitionObservation
from l9_debt_intelligence.historical.safety import (
    QuarantinedObservation,
    screen_observation,
    screen_observations,
)
from l9_debt_intelligence.ingestion.redaction import assess_redaction


def _obs(payload: dict, object_id: str = "1") -> AcquisitionObservation:
    return AcquisitionObservation.build(
        provider="github",
        repository_ref="Quantum-L9/l9-ci-core",
        object_kind="pull_request",
        provider_object_id=object_id,
        payload=payload,
        provenance={"provider": "github", "resource": "/repos/x/pulls/1"},
    )


def test_github_pull_request_shas_are_not_quarantined() -> None:
    """GitHub identity is a 40-character object id. Corpus redaction still fires."""
    result = screen_observation(
        _obs(
            {
                "number": 148,
                "head": {"sha": "edeef6dcc316ec79b2f672ec2c827083f4035656"},
                "base": {"sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
                "merge_commit_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        )
    )
    assert isinstance(result, AcquisitionObservation)


def test_historical_safety_still_quarantines_tokens() -> None:
    result = screen_observation(
        _obs({"authorization": "token value", "head": {"sha": "e" * 40}})
    )
    assert isinstance(result, QuarantinedObservation)
    assert result.reason == "sensitive_content"
    assert any(item.startswith("sensitive-key:") for item in result.limitations)


def test_corpus_ingress_still_rejects_a_bare_git_object_id() -> None:
    assessment = assess_redaction(
        {
            "redaction_status": "producer_redacted",
            "payload": {"revision": "edeef6dcc316ec79b2f672ec2c827083f4035656"},
        }
    )
    assert assessment.safe is False
    assert "git-object-id:payload.revision" in assessment.limitations


def test_screen_observations_keeps_sha_bearing_pulls() -> None:
    safe = screen_observations(
        (
            _obs(
                {
                    "number": 1,
                    "head": {"sha": "c" * 40},
                    "base": {"sha": "d" * 40},
                },
                object_id="pr-1",
            ),
        )
    )
    assert len(safe.safe) == 1
    assert safe.quarantined == ()

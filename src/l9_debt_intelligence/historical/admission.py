from __future__ import annotations

import hashlib
from typing import Any, Protocol

from l9_debt_intelligence.contracts.canonical import sha256_document
from l9_debt_intelligence.ingestion.identity import repository_pseudonym
from l9_debt_intelligence.ingestion.models import IngestionResult
from .contracts import EPISODE_SCHEMA, ResolutionEpisode

HISTORICAL_PRODUCER_ID = "Quantum-L9/l9-ci-debt-intelligence"
SDK_CONTRACT = "l9.integration-contract/v1"

class P1Ingress(Protocol):
    def ingest(self,event:dict[str,Any])->IngestionResult: ...

class HistoricalProjector:
    def __init__(self,*,pseudonym_key:bytes)->None:
        if len(pseudonym_key)<32: raise ValueError("pseudonym key must be at least 32 bytes")
        self._key=pseudonym_key
    def project(self,episode:ResolutionEpisode)->dict[str,Any]:
        when=episode.validation.get("provider_time")
        if not isinstance(when,str) or not when: raise ValueError("historical projection requires provider validation time")
        relation=episode.validation.get("equivalent_check_relationship")
        if episode.outcome in {"clean_verified","target_failure_resolved"} and relation!="equivalent":
            raise ValueError("successful historical outcome requires equivalent validation")
        repo=episode.context.get("repository_ref")
        if not isinstance(repo,str) or not repo: raise ValueError("historical episode requires repository provenance")
        run=episode.validation.get("execution_ref")
        if not isinstance(run,str) or not run: raise ValueError("historical episode requires validation execution reference")
        limits=[str(x) for x in episode.attribution.get("limitations",[]) if isinstance(x,str) and x]
        if not limits: limits=["historical evidence is reconstructed and subordinate to live CI"]
        unknowns=[]
        if episode.outcome in {"outcome_unknown","unresolved"}: unknowns.append({"field":"historical_outcome","reason":"unavailable"})
        if relation!="equivalent": unknowns.append({"field":"validation_equivalence","reason":"unavailable"})
        payload={
            "historical_episode_id":episode.episode_id,
            "repository":repository_pseudonym(repository=repo,pseudonym_key=self._key),
            "pull_request_present":episode.context.get("pull_request_ref") is not None,
            "failure":{"semantic_failure_identity":episode.failure_state.get("semantic_failure_identity"),"identity_authority":episode.failure_state.get("identity_authority")},
            "intervention":{"before_revision":_token("revision_",episode.intervention.get("before_revision")),"after_revision":_token("revision_",episode.intervention.get("after_revision")),"change_fingerprint":episode.intervention.get("change_fingerprint"),"change_count":len(episode.intervention.get("change_refs",[]))},
            "validation":{"execution_ref":_token("validation_",run),"equivalent_check_relationship":relation,"failure_after_state":episode.validation.get("failure_after_state"),"new_failure_count":len(episode.validation.get("newly_observed_failures",[])),"validation_completeness":episode.validation.get("validation_completeness")},
            "outcome":episode.outcome,
            "attribution":{"evidence_grade":episode.attribution.get("evidence_grade"),"attribution_class":episode.attribution.get("attribution_class"),"confounders":episode.attribution.get("confounders",[]),"evidence_completeness":episode.attribution.get("evidence_completeness"),"suspected_flake":episode.attribution.get("suspected_flake",False),"flake_classification":episode.attribution.get("flake_classification","none"),"prevention_learning":episode.attribution.get("prevention_learning","normal")},
            "provenance":{"source_observation_refs":episode.provenance.get("source_observation_refs",[]),"algorithm_version":episode.provenance.get("algorithm_version"),"schema_version":episode.provenance.get("schema_version"),"closed_loop_lineage":episode.provenance.get("closed_loop_lineage",{})},
        }
        return {"schema_version":"l9.corpus-event/v1","producer_id":HISTORICAL_PRODUCER_ID,"producer_contract":EPISODE_SCHEMA,"sdk_contract":SDK_CONTRACT,"event_id":f"historical.{episode.episode_id}","event_class":"verification_outcome","event_time":when,"snapshot_or_run_id":_token("historical_run_",run),"redaction_status":"intelligence_redacted","limitations":sorted(set(limits)),"unknowns":unknowns,"lineage":{"producer_event_hash":sha256_document(episode.as_dict()),"parent_event_ids":[]},"payload":payload}

class HistoricalAdmissionAdapter:
    def __init__(self,*,ingress:P1Ingress,projector:HistoricalProjector)->None:
        self._ingress=ingress; self._projector=projector
    def admit(self,episode:ResolutionEpisode)->IngestionResult:
        return self._ingress.ingest(self._projector.project(episode))

def _token(prefix:str,value:Any)->str|None:
    if not isinstance(value,str) or not value: return None
    return f"{prefix}{hashlib.sha256(value.encode('utf-8')).hexdigest()}"

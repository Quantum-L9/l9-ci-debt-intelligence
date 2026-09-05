from __future__ import annotations

from typing import Any, cast
from l9_debt_intelligence.contracts.canonical import sha256_document
from .contracts import AcquisitionObservation, NormalizedKind, NormalizedObservation, deterministic_id

_ENVIRONMENT_BASENAMES={"pyproject.toml","poetry.lock","uv.lock","package-lock.json","pnpm-lock.yaml","yarn.lock","requirements.txt","dockerfile"}
_SKIP_MARKERS=("pytest.mark.skip","pytest.mark.xfail","pytest.skip(","unittest.skip","skiptests(","if: false","if: ${{ false }}")

def normalize_observations(observations:tuple[AcquisitionObservation,...])->tuple[NormalizedObservation,...]:
    out=[]
    for observation in observations:out.extend(normalize_observation(observation))
    return tuple(sorted(out,key=lambda x:x.observation_id))

def normalize_observation(observation:AcquisitionObservation)->tuple[NormalizedObservation,...]:
    kind=observation.object_kind
    if kind=="pull_request":
        p=_object_payload(observation); base=_nested(p,"base","sha"); head=_nested(p,"head","sha"); auto=p.get("auto_merge"); hint=_string(auto.get("merge_method")) if isinstance(auto,dict) else None
        return (_build(observation,"pull_request",{"number":p.get("number") if isinstance(p.get("number"),int) else None,"base_revision":base,"head_revision":head,"merge_commit_revision":_string(p.get("merge_commit_sha")),"merge_method_hint":hint,"merged":bool(p.get("merged")) if "merged" in p else None,"updated_at":_string(p.get("updated_at"))},"complete" if base and head else "partial"),)
    if kind=="timeline_event":
        p=_object_payload(observation); event=_string(p.get("event"))
        if event not in {"base_ref_changed","head_ref_force_pushed"}:return ()
        return (_build(observation,"review_signal",{"signal":event,"created_at":_string(p.get("created_at")),"commit_id":_string(p.get("commit_id")),"before_commit":_string(p.get("before_commit")),"after_commit":_string(p.get("after_commit"))},"direct_provider_event"),)
    if kind=="commit":
        p=_object_payload(observation); sha=_string(p.get("sha")); parents=[x["sha"] for x in p.get("parents",[]) if isinstance(x,dict) and isinstance(x.get("sha"),str)]; files=_files(p.get("files",[])); committed=None; c=p.get("commit")
        if isinstance(c,dict) and isinstance(c.get("committer"),dict):committed=_string(c["committer"].get("date"))
        commit=_build(observation,"commit",{"revision":sha,"parent_revisions":parents,"committed_at":committed,"is_merge":len(parents)>1},"complete" if sha else "partial")
        if not sha or not parents:return (commit,)
        change=_build(observation,"change",{"before_revision":parents[0],"after_revision":sha,"parent_revisions":parents,"change_fingerprint":sha256_document(files),"file_count":len(files),"workflow_changed":any(str(x["path"]).startswith(".github/workflows/") for x in files),"test_changed":any(_is_test(str(x["path"])) for x in files),"environment_changed":any(_is_env(str(x["path"])) for x in files),"dependency_lockfile_change":any(_is_lock(str(x["path"])) for x in files),"validation_weakening_signals":_weakening(files),"is_merge":len(parents)>1,"changed_paths":[str(x["path"]) for x in files]},"complete" if files else "partial")
        return commit,change
    if kind in {"workflow_run","workflow_attempt"}:
        p=_object_payload(observation); rid=_strint(p.get("id")); revision=_string(p.get("head_sha")); attempt=_attempt(observation,p); execution=_exec(rid,attempt)
        return (_build(observation,"ci_execution",{"provider_run_ref":rid,"execution_ref":execution,"revision":revision,"workflow_identity":_workflow(p),"attempt":attempt,"status":_string(p.get("status")),"conclusion":_string(p.get("conclusion")),"event":_string(p.get("event")),"created_at":_string(p.get("created_at")),"updated_at":_string(p.get("updated_at"))},"complete" if execution and revision else "partial"),)
    if kind=="ci_job":
        p=_object_payload(observation); rid=_strint(p.get("run_id")); attempt=_attempt(observation,p); execution=_exec(rid,attempt); jid=_strint(p.get("id")); revision=_string(p.get("head_sha")); name=_string(p.get("name")); steps=_steps(p.get("steps",[]))
        job=_build(observation,"ci_job",{"job_ref":jid,"provider_run_ref":rid,"execution_ref":execution,"attempt":attempt,"revision":revision,"name":name,"workflow_name":_string(p.get("workflow_name")),"status":_string(p.get("status")),"conclusion":_string(p.get("conclusion")),"started_at":_string(p.get("started_at")),"completed_at":_string(p.get("completed_at")),"steps":steps},"complete" if jid and execution and name else "partial")
        out=[job]
        if _string(p.get("conclusion"))=="failure":
            failed=[str(x["name"]) for x in steps if x.get("conclusion")=="failure"]; semantic=deterministic_id("historical:",{"producer_family":"github_actions","finding_kind":"ci_job_failure","job_name":name or "unknown","failed_steps":failed}); occurrence=deterministic_id("hfo_",{"repository_ref":observation.repository_ref,"revision":revision,"execution_ref":execution,"attempt_ref":attempt,"job_ref":jid})
            out.append(_build(observation,"failure",{"semantic_failure_identity":semantic,"identity_authority":"historical_noncanonical","occurrence_identity":occurrence,"revision":revision,"execution_ref":execution,"job_ref":jid,"job_name":name,"failed_steps":failed},"complete" if failed else "partial",("failed_step_unavailable",) if not failed else ()))
        return tuple(out)
    if kind=="check_run":
        p=_object_payload(observation); return (_build(observation,"validation",{"check_ref":_strint(p.get("id")),"revision":_string(p.get("head_sha")),"name":_string(p.get("name")),"status":_string(p.get("status")),"conclusion":_string(p.get("conclusion")),"started_at":_string(p.get("started_at")),"completed_at":_string(p.get("completed_at"))},"complete"),)
    if kind=="job_log":return (_build(observation,"textual_hint",{"source_kind":"job_log","content_digest":observation.observed_content_digest,"raw_text_retained":False},"digest_only",("raw_log_not_normalized_or_projected",)),)
    return ()

def _build(source:AcquisitionObservation,kind:NormalizedKind,data:dict[str,Any],availability:str,limitations:tuple[str,...]=())->NormalizedObservation:
    return NormalizedObservation.build(kind=kind,repository_ref=source.repository_ref,provenance_refs=(source.observation_id,),evidence_availability=availability,limitations=tuple(sorted(set(source.limitations+limitations))),data=data)
def _object_payload(o:AcquisitionObservation)->dict[str,Any]:
    if not isinstance(o.payload,dict):raise ValueError(f"{o.object_kind} payload must be an object")
    return cast(dict[str,Any],o.payload)
def _attempt(o:AcquisitionObservation,p:dict[str,Any])->int|None:
    v=p.get("run_attempt"); v=v if isinstance(v,int) else o.provenance.get("run_attempt"); return v if isinstance(v,int) and v>0 else None
def _exec(r:str|None,a:int|None)->str|None:return None if r is None else r if a is None else f"{r}:attempt:{a}"
def _nested(d:dict[str,Any],k:str,c:str)->str|None:
    v=d.get(k); return _string(v.get(c)) if isinstance(v,dict) else None
def _workflow(p:dict[str,Any])->str:return _string(p.get("path")) or _strint(p.get("workflow_id")) or _string(p.get("name")) or "unknown"
def _files(v:Any)->list[dict[str,Any]]:
    if not isinstance(v,list):return []
    out=[]
    for x in v:
        if isinstance(x,dict) and _string(x.get("filename")):out.append({"path":_string(x.get("filename")),"status":_string(x.get("status")) or "unknown","patch":_string(x.get("patch"))})
    return sorted(out,key=lambda x:str(x["path"]))
def _steps(v:Any)->list[dict[str,Any]]:
    if not isinstance(v,list):return []
    return [{"name":x.get("name"),"status":_string(x.get("status")),"conclusion":_string(x.get("conclusion"))} for x in v if isinstance(x,dict) and isinstance(x.get("name"),str)]
def _weakening(files:list[dict[str,Any]])->list[str]:
    out=set()
    for x in files:
        path=str(x["path"]); patch=x.get("patch")
        if x["status"]=="removed" and (_is_test(path) or path.startswith(".github/workflows/")):out.add("validation_file_removed")
        if isinstance(patch,str):
            additions="\n".join(line[1:].lower() for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
            if any(m in additions for m in _SKIP_MARKERS):out.add("validation_skip_added")
    return sorted(out)
def _is_test(path:str)->bool:
    p=path.lower(); return p.startswith("tests/") or "/tests/" in p or p.endswith("_test.py") or p.startswith("test_")
def _is_env(path:str)->bool:
    b=path.lower().rsplit("/",1)[-1]; return b in _ENVIRONMENT_BASENAMES or b.startswith("requirements-")
def _is_lock(path:str)->bool:
    b=path.lower().rsplit("/",1)[-1]; return b.endswith(".lock") or b in {"package-lock.json","pnpm-lock.yaml","yarn.lock"}
def _string(v:Any)->str|None:return v if isinstance(v,str) and v else None
def _strint(v:Any)->str|None:
    if isinstance(v,bool):return None
    return str(v) if isinstance(v,(str,int)) and str(v) else None

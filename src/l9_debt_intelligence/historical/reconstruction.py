from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from typing import Any,Iterable
from l9_debt_intelligence.contracts.canonical import sha256_document
from .attribution import assess_attribution
from .contracts import RECONSTRUCTION_ALGORITHM_VERSION,RECONSTRUCTION_CONTRACT_VERSION,NormalizedObservation,ResolutionEpisode
from .equivalence import evaluate_validation_equivalence
from .flakiness import classify_flakiness

class ReconstructionError(ValueError):pass
@dataclass(frozen=True)
class TemporalEvidenceGraph:
    nodes:tuple[tuple[str,str],...]; edges:tuple[tuple[str,str,str],...]
    def as_dict(self)->dict[str,Any]:return {"schema_version":"l9.historical-temporal-evidence-graph/v1","nodes":[{"id":i,"type":t} for i,t in self.nodes],"edges":[{"type":t,"source":s,"target":d} for t,s,d in self.edges]}

def build_temporal_graph(obs:tuple[NormalizedObservation,...])->TemporalEvidenceGraph:
    nodes=set();edges=set()
    for o in obs:
        if o.kind=="commit":
            r=o.data.get("revision")
            if isinstance(r,str):
                nodes.add((f"revision:{r}","revision"))
                for p in o.data.get("parent_revisions",[]):
                    if isinstance(p,str):nodes.add((f"revision:{p}","revision"));edges.add(("revision_parent",f"revision:{p}",f"revision:{r}"))
        elif o.kind=="ci_execution":
            e=o.data.get("execution_ref");r=o.data.get("revision")
            if isinstance(e,str):
                nodes.add((f"execution:{e}","ci_execution"))
                if isinstance(r,str):nodes.add((f"revision:{r}","revision"));edges.add(("execution_for_revision",f"revision:{r}",f"execution:{e}"))
        elif o.kind=="ci_job":
            j=o.data.get("job_ref");e=o.data.get("execution_ref")
            if isinstance(j,str):nodes.add((f"job:{j}","ci_job"));edges.add(("job_part_of_execution",f"execution:{e}",f"job:{j}")) if isinstance(e,str) else None
        elif o.kind=="failure":
            f=o.data.get("occurrence_identity");e=o.data.get("execution_ref")
            if isinstance(f,str):nodes.add((f"failure:{f}","failure_occurrence"));edges.add(("failure_observed_in",f"execution:{e}",f"failure:{f}")) if isinstance(e,str) else None
        elif o.kind=="change":nodes.add((f"change:{o.observation_id}","change"))
        elif o.kind=="validation":nodes.add((f"validation:{o.observation_id}","validation"))
        elif o.kind in {"review_signal","textual_hint"}:nodes.add((f"human:{o.observation_id}","human_signal"))
    return TemporalEvidenceGraph(tuple(sorted(nodes)),tuple(sorted(edges)))

def reconstruct_episodes(obs:tuple[NormalizedObservation,...],*,closed_loop_lineage:dict[str,Any]|None=None)->tuple[ResolutionEpisode,...]:
    pulls=[x for x in obs if x.kind=="pull_request"]
    if not pulls:raise ReconstructionError("pull request context is required")
    pull=sorted(pulls,key=lambda x:x.observation_id)[0]; runs=[x for x in obs if x.kind=="ci_execution"]; jobs=[x for x in obs if x.kind=="ci_job"]; failures=[x for x in obs if x.kind=="failure"]; changes=[x for x in obs if x.kind=="change"]; signals=[x for x in obs if x.kind=="review_signal"]
    parent={str(pull.data.get("base_revision")):()}
    for c in [x for x in obs if x.kind=="commit"]:
        r=c.data.get("revision");ps=c.data.get("parent_revisions",[])
        if isinstance(r,str) and isinstance(ps,list):parent[r]=tuple(str(p) for p in ps if isinstance(p,str))
    byrun=_many(jobs,"execution_ref"); failrun=_many(failures,"execution_ref"); runid=_one(runs,"execution_ref"); changeafter=_one(changes,"after_revision"); graph=build_temporal_graph(obs); episodes=[]
    pr_conf=set()
    for s in signals:
        if s.data.get("signal")=="base_ref_changed":pr_conf.add("base_branch_update")
        if s.data.get("signal")=="head_ref_force_pushed":pr_conf.add("force_updated_pr_branch")
    if pull.data.get("merge_method_hint")=="squash":pr_conf.add("squash_merge")
    for f in failures:
        be=f.data.get("execution_ref");bj=f.data.get("job_ref");name=f.data.get("job_name");semantic=f.data.get("semantic_failure_identity")
        if not all(isinstance(x,str) and x for x in (be,bj,name,semantic)):continue
        before=runid.get(be);beforejob=_find(byrun.get(be,()),"job_ref",bj)
        if before is None or beforejob is None:continue
        after=_next_run(before,runs,parent)
        if after is None:continue
        ae=after.data.get("execution_ref");br=before.data.get("revision");ar=after.data.get("revision")
        if not all(isinstance(x,str) and x for x in (ae,br,ar)):continue
        afterjobs=byrun.get(ae,());afterjob=_find(afterjobs,"name",name);path=_path(br,ar,parent);transition=tuple(changeafter[x] for x in (path or ()) if x in changeafter);missing=path is not None and len(transition)!=len(path)
        eq=evaluate_validation_equivalence(before_run=before,after_run=after,before_job=beforejob,after_job=afterjob,changes=transition); afterids=tuple(x.data.get("semantic_failure_identity") for x in failrun.get(ae,())); beforeids=set(x.data.get("semantic_failure_identity") for x in failrun.get(be,())); extra=set(pr_conf)
        if missing:extra.add("intervention_evidence_missing")
        assessment=assess_attribution(before_run=before,after_run=after,target_after_job=afterjob,all_after_jobs=afterjobs,changes=transition,equivalence=eq,same_revision=br==ar,target_failure_present=semantic in afterids,new_failure_count=len([x for x in afterids if x!=semantic]),before_failure_count=len(beforeids),extra_confounders=tuple(sorted(extra))); flake=classify_flakiness(failure_run=before,runs=tuple(runs)); refs=sorted({r for x in (f,before,beforejob,after,*afterjobs,*transition,*failrun.get(ae,())) for r in x.provenance_refs}); when=(afterjob.data.get("completed_at") if afterjob else None) or after.data.get("updated_at") or after.data.get("created_at")
        episode=ResolutionEpisode.build(context={"repository_ref":pull.repository_ref,"pull_request_ref":pull.data.get("number"),"base_revision":pull.data.get("base_revision"),"head_revision":pull.data.get("head_revision")},failure_state={"failure_refs":[f.observation_id],"semantic_failure_identity":semantic,"identity_authority":f.data.get("identity_authority"),"occurrence_identities":[f.data.get("occurrence_identity")],"evidence_availability":f.evidence_availability},intervention={"before_revision":br,"after_revision":ar,"change_refs":[x.observation_id for x in transition],"change_fingerprint":sha256_document([x.data.get("change_fingerprint") for x in transition]),"remediation_class_optional":None},validation={"validation_refs":[after.observation_id]+([afterjob.observation_id] if afterjob else []),"execution_ref":ae,"equivalent_check_relationship":eq.status,"equivalence_reasons":list(eq.reasons),"failure_after_state":"present" if semantic in afterids else "absent" if afterjob else "unknown","newly_observed_failures":sorted(str(x) for x in afterids if x!=semantic),"validation_completeness":eq.completeness,"provider_time":when},outcome=assessment.outcome,attribution={**assessment.as_dict(),"flake_classification":flake.classification,"flake_indicators":list(flake.indicators),"prevention_learning":"separate_from_repair_learning" if flake.classification=="verified" else "normal"},provenance={"source_observation_refs":refs,"algorithm_version":RECONSTRUCTION_ALGORITHM_VERSION,"schema_version":RECONSTRUCTION_CONTRACT_VERSION,"temporal_graph_digest":sha256_document(graph.as_dict()),"closed_loop_lineage":_lineage(closed_loop_lineage)})
        episodes.append(episode)
    return tuple({x.episode_id:x for x in episodes}[k] for k in sorted({x.episode_id:x for x in episodes}))

def _lineage(v:dict[str,Any]|None)->dict[str,Any]:
    if v is None:return {}
    allowed={"active_defense_pack","active_rule_ids","resolver_strategy_source","lsp_intervention","pr_repair_intervention"};unknown=set(v)-allowed
    if unknown:raise ReconstructionError("unsupported closed-loop lineage fields: "+", ".join(sorted(unknown)))
    return {k:v[k] for k in sorted(v)}
def _one(items:Iterable[NormalizedObservation],key:str)->dict[str,NormalizedObservation]:return {str(x.data[key]):x for x in items if isinstance(x.data.get(key),str)}
def _many(items:Iterable[NormalizedObservation],key:str)->dict[str,tuple[NormalizedObservation,...]]:
    d=defaultdict(list)
    for x in items:
        if isinstance(x.data.get(key),str):d[x.data[key]].append(x)
    return {k:tuple(sorted(v,key=lambda x:x.observation_id)) for k,v in d.items()}
def _find(items:tuple[NormalizedObservation,...],key:str,value:str)->NormalizedObservation|None:return next((x for x in items if x.data.get(key)==value),None)
def _path(before:str,after:str,parent:dict[str,tuple[str,...]])->tuple[str,...]|None:
    if before==after:return ()
    paths=[]
    def walk(cur:str,seen:set[str],trail:tuple[str,...])->None:
        if len(paths)>1:return
        if cur==before:paths.append(tuple(reversed(trail)));return
        if cur in seen:return
        for p in parent.get(cur,()):walk(p,seen|{cur},trail+(cur,))
    walk(after,set(),())
    return paths[0] if len(paths)==1 else None
def _next_run(before:NormalizedObservation,runs:list[NormalizedObservation],parent:dict[str,tuple[str,...]])->NormalizedObservation|None:
    br=before.data.get("revision");wf=before.data.get("workflow_identity");attempt=before.data.get("attempt");same=[];later=[]
    for r in runs:
        if r.observation_id==before.observation_id or r.data.get("workflow_identity")!=wf:continue
        if r.data.get("revision")==br and (not isinstance(attempt,int) or not isinstance(r.data.get("attempt"),int) or r.data.get("attempt")>attempt):same.append(r)
        elif isinstance(br,str) and isinstance(r.data.get("revision"),str):
            path=_path(br,r.data["revision"],parent)
            if path:later.append((len(path),r))
    if same:return sorted(same,key=lambda x:(x.data.get("attempt") or 0,x.observation_id))[0]
    if later:return sorted(later,key=lambda x:(x[0],x[1].observation_id))[0][1]
    return None

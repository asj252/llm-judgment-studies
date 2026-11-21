#!/usr/bin/env python3
"""Reproduce descriptive summaries from the eleven formal cohorts, offline.
Numerical routines retain the published sampling algorithms and cell order.
"""
import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path
from types import SimpleNamespace
B=4000
SEED=20261115
EPS_PP=1e-12
FIELDS=['mean','sd','se','median','q25','q75','iqr','min','max','ci95_boot']
KEY_FIELDS=('model','scale','frame','template_id','arm','evidence','ask')
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def index_records(rows, *, expected_stimuli_sha256):
    out={}
    for r in rows:
        if r['stimuli_sha256'] != expected_stimuli_sha256: raise ValueError('Stimuli hash mismatch')
        key=tuple(r[k] for k in KEY_FIELDS)
        if key in out: raise ValueError('Duplicate pairing key')
        out[key]=r
    return out

PRE_REGISTERED_SCALE13_TEMPLATES=['FRM-01', 'FRM-02', 'FRM-03', 'FRM-04', 'FRM-17', 'FRM-18', 'FRM-19', 'FRM-20', 'FRM-33', 'FRM-34', 'FRM-35', 'FRM-36', 'FRM-49', 'FRM-50', 'FRM-51', 'FRM-52', 'FRM-65', 'FRM-66', 'FRM-67', 'FRM-68', 'FRM-81', 'FRM-82', 'FRM-83', 'FRM-84']
EXPECTED_ARMS=[('sf:qwen3-8b', 100, False, 5760, 'sf_qwen3-8b_s100.jsonl'), ('xf:spark-x2.6', 100, False, 5760, 'xf_spark-x2.6_s100.jsonl'), ('nv:nemotron-3.5-super-vl-120b', 100, False, 5760, 'nv_nemotron-3.5-super-vl-120b_s100.jsonl'), ('aistudio:gemini-3.8-flash', 100, False, 5760, 'aistudio_gemini-3.8-flash_s100.jsonl'), ('openai:gpt-4.1-mini', 100, False, 5760, 'openai_gpt-4.1-mini_s100.jsonl'), ('openai:gpt-4.1', 100, False, 5760, 'openai_gpt-4.1_s100.jsonl'), ('openai:gpt-4.1-mini', 100, True, 2880, 'openai_gpt-4.1-mini_s100_lp.jsonl'), ('openai:gpt-4.1', 100, True, 2880, 'openai_gpt-4.1_s100_lp.jsonl'), ('openai:gpt-4.1-mini', 13, False, 1440, 'openai_gpt-4.1-mini_s13.jsonl'), ('aistudio:gemini-3.8-flash', 13, False, 1440, 'aistudio_gemini-3.8-flash_s13.jsonl'), ('nv:nemotron-3.5-super-vl-120b', 13, False, 1440, 'nv_nemotron-3.5-super-vl-120b_s13.jsonl')]
def extract_prob01_variant(record, *, multi_field="m_w", strict_only=True):
    if record is None:
        return None
    parsed = record.get("parsed") or {}
    if not parsed.get("ok"):
        return None
    ask = record.get("ask")
    if ask == "logprob_pct":
        value = parsed.get("p")
        divisor = 1.0
    elif ask.startswith("multi"):
        if strict_only and not parsed.get("weight_sum_in_tolerance"):
            return None
        value = parsed.get(multi_field)
        divisor = 100.0
    else:
        value = parsed.get("p") if ask == "decision_noul" else parsed.get("value")
        divisor = 1.0 if ask == "decision_noul" else 100.0
    if isinstance(value, bool):
        return None
    try:
        p = float(value) / divisor
    except (TypeError, ValueError):
        return None
    return p if math.isfinite(p) and 0.0 <= p <= 1.0 else None

def extract_prob01(record):
    return extract_prob01_variant(record)
def quantile(xs, p):
    if not xs: return None
    xs = sorted(xs)
    i = p * (len(xs)-1)
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi]-xs[lo])*(i-lo)

def absolute(xs):
    if not xs: return dict.fromkeys(['mean','sd','median','q25','q75','iqr','max'])
    q25,q75 = quantile(xs,.25),quantile(xs,.75)
    return dict(mean=statistics.mean(xs),sd=statistics.stdev(xs) if len(xs)>1 else None,
                median=quantile(xs,.5),q25=q25,q75=q75,iqr=q75-q25,max=max(xs))

def signed(xs):
    if not xs: return dict.fromkeys(['mean','sd','se','ci95_boot','n_pos','n_neg','n_zero'])
    n=len(xs); sd=statistics.stdev(xs) if n>1 else None
    ci=None
    if n>1:
        rng=random.Random(SEED)
        # choices uses floor(random()*n), with a fresh generator for every cell.
        means=[sum(rng.choices(xs,k=n))/n for _ in range(B)]
        ci=[quantile(means,.025),quantile(means,.975)]
    return dict(mean=statistics.mean(xs),sd=sd,se=sd/math.sqrt(n) if sd is not None else None,
                ci95_boot=ci,n_pos=sum(x>1e-10 for x in xs),n_neg=sum(x< -1e-10 for x in xs),
                n_zero=sum(abs(x)<=1e-10 for x in xs))

def compute_ties():
    stim=read(PROJECT/'formal_stimuli.json')
    sha=hashlib.sha256((PROJECT/'formal_stimuli.json').read_bytes()).hexdigest()
    templates={t['template_id']:t for t in stim['templates']}
    rows=[]; sources={}
    for model,scale,lp,n,filename in vd.EXPECTED_ARMS:
        p=RAW/filename
        payload=p.read_bytes(); sources[filename]=hashlib.sha256(payload).hexdigest()
        # Keep only the pairing/parser fields; avoid retaining full raw responses.
        count=0
        for line in payload.splitlines():
            if not line.strip():continue
            r=json.loads(line.decode('utf-8'))
            rows.append({k:r[k] for k in ef.KEY_FIELDS+('parsed','plan_version','stimuli_sha256')})
            count+=1
        assert count==n
        del r, payload
    assert len(rows)==44640
    indexed=ef.index_records(rows,expected_stimuli_sha256=sha)
    def get(m,sc,fr,t,arm,ask):
        return ef.extract_prob01(indexed.get((m,sc,fr,t,arm,'P0',ask)))
    result=[]
    for upstream in [{'model': 'aistudio:gemini-3.8-flash', 'frame': 'subjective', 'target': 'MCW-100'}, {'model': 'aistudio:gemini-3.8-flash', 'frame': 'subjective', 'target': 'Direct-13'}, {'model': 'aistudio:gemini-3.8-flash', 'frame': 'observer', 'target': 'MCW-100'}, {'model': 'aistudio:gemini-3.8-flash', 'frame': 'observer', 'target': 'Direct-13'}, {'model': 'nv:nemotron-3.5-super-vl-120b', 'frame': 'subjective', 'target': 'MCW-100'}, {'model': 'nv:nemotron-3.5-super-vl-120b', 'frame': 'subjective', 'target': 'Direct-13'}, {'model': 'nv:nemotron-3.5-super-vl-120b', 'frame': 'observer', 'target': 'MCW-100'}, {'model': 'nv:nemotron-3.5-super-vl-120b', 'frame': 'observer', 'target': 'Direct-13'}, {'model': 'openai:gpt-4.1', 'frame': 'subjective', 'target': 'MCW-100'}, {'model': 'openai:gpt-4.1', 'frame': 'subjective', 'target': 'logprob_pct'}, {'model': 'openai:gpt-4.1', 'frame': 'observer', 'target': 'MCW-100'}, {'model': 'openai:gpt-4.1', 'frame': 'observer', 'target': 'logprob_pct'}, {'model': 'openai:gpt-4.1-mini', 'frame': 'subjective', 'target': 'MCW-100'}, {'model': 'openai:gpt-4.1-mini', 'frame': 'subjective', 'target': 'Direct-13'}, {'model': 'openai:gpt-4.1-mini', 'frame': 'subjective', 'target': 'logprob_pct'}, {'model': 'openai:gpt-4.1-mini', 'frame': 'observer', 'target': 'MCW-100'}, {'model': 'openai:gpt-4.1-mini', 'frame': 'observer', 'target': 'Direct-13'}, {'model': 'openai:gpt-4.1-mini', 'frame': 'observer', 'target': 'logprob_pct'}, {'model': 'sf:qwen3-8b', 'frame': 'subjective', 'target': 'MCW-100'}, {'model': 'sf:qwen3-8b', 'frame': 'observer', 'target': 'MCW-100'}, {'model': 'xf:spark-x2.6', 'frame': 'subjective', 'target': 'MCW-100'}, {'model': 'xf:spark-x2.6', 'frame': 'observer', 'target': 'MCW-100'}]:
        m,fr,target=(upstream[k] for k in ['model','frame','target'])
        sc,ask={'MCW-100':(100,'multi'),'Direct-13':(13,'direct'),'logprob_pct':(100,'logprob_pct')}[target]
        design=sorted(t for t in templates if sc==100 or t in ef.PRE_REGISTERED_SCALE13_TEMPLATES)
        tied=[t for t in design if (a:=get(m,100,fr,t,'A','direct')) is not None and
              (b:=get(m,100,fr,t,'B','direct')) is not None and abs(a-b)<=1e-12]
        valid=[(t,100*(a-b)) for t in tied if (a:=get(m,sc,fr,t,'A',ask)) is not None and
               (b:=get(m,sc,fr,t,'B',ask)) is not None]
        broken=[x for _,x in valid if abs(x)>1e-10]
        r=dict(model=m,frame=fr,target=target,n_templates_design=len(design),n_tied=len(tied),
               n_valid=len(valid),n_broken=len(broken),rate=len(broken)/len(tied) if tied else None)
        r['abs_delta_pp']=dict(broken=absolute([abs(x) for x in broken]),valid=absolute([abs(x) for _,x in valid]))
        r['signed_delta_pp']=dict(valid=signed([x for _,x in valid]),by_dimension={d:signed([x for t,x in valid if templates[t]['dimension']==d]) for d in ['W','C']})
        result.append(r)
    assert len(result)==22
    return dict(n_records=44640,n_files=11,raw_sha256=sources,stimuli_sha256=sha,
                method=dict(unit='percentage points',direction='Arm A - Arm B',ddof=1,
                    quantile='linear',bootstrap_B=B,bootstrap_seed=SEED,bootstrap_sampling='random.Random.choices',
                    bootstrap_order='template_id ascending',tie_tolerance_probability=1e-12),ties=result)
def summarize_values(vals_by_tid, boot_seed=20261115, B=4000):
    xs = [v for _,v in sorted(vals_by_tid.items())]
    n = len(xs)
    if not n: return dict.fromkeys(FIELDS)
    q = upstream.quantile
    sd = statistics.stdev(xs) if n > 1 else None
    ci = None
    if n > 1:
        rng = random.Random(boot_seed)
        means = [sum(xs[rng.randrange(n)] for _ in range(n))/n for _ in range(B)]
        ci = [q(means,.025),q(means,.975)]
    return dict(mean=statistics.mean(xs),sd=sd,se=sd/math.sqrt(n) if sd is not None else None,
                median=q(xs,.5),q25=q(xs,.25),q75=q(xs,.75),iqr=q(xs,.75)-q(xs,.25),
                min=min(xs),max=max(xs),ci95_boot=ci)

def compute_nonties():
    ef = upstream.ef
    by={}; hashes={}; total=0
    for model,scale,lp,n,filename in upstream.vd.EXPECTED_ARMS:
        payload=(upstream.RAW/filename).read_bytes()
        hashes[filename]=hashlib.sha256(payload).hexdigest(); count=0
        for line in payload.decode('utf-8').splitlines():
            if not line.strip():continue
            r=json.loads(line);key=tuple(r[k] for k in ef.KEY_FIELDS)
            if key in by:raise ValueError('duplicate pairing key: '+repr(key))
            by[key]=ef.extract_prob01(r);count+=1
        assert count==n
        total+=count
    sha=hashlib.sha256((upstream.PROJECT/'formal_stimuli.json').read_bytes()).hexdigest()
    assert len(hashes)==11 and total==44640
    tids=sorted(t['template_id'] for t in upstream.read(upstream.PROJECT/'formal_stimuli.json')['templates'])
    def get(m,s,f,t,a,q):return by.get((m,s,f,t,a,'P0',q))
    configs=[]
    for m,s,lp,_,_ in upstream.vd.EXPECTED_ARMS:
        for f in ['subjective','observer']:
            if lp:configs.append((m,f,'logprob_pct',100,'logprob_pct'))
            elif s==13:configs.append((m,f,'Direct-13',13,'direct'))
            else:configs.extend([(m,f,'Direct-100',100,'direct'),(m,f,'MCW-100',100,'multi')])
    p0=[];nt=[]
    for m,f,ch,s,q in configs:
        design=[t for t in tids if s==100 or t in ef.PRE_REGISTERED_SCALE13_TEMPLATES]
        vals={};base_missing=0;eligible=0;missing=0;direct={};target={}
        for t in design:
            a,b=get(m,s,f,t,'A',q),get(m,s,f,t,'B',q)
            if a is not None and b is not None:vals[t]=100*(a-b)
            da,db=get(m,100,f,t,'A','direct'),get(m,100,f,t,'B','direct')
            if da is None or db is None:base_missing+=1;continue
            if abs(da-db)<=1e-12:continue
            eligible+=1
            if a is None or b is None:missing+=1;continue
            direct[t]=100*abs(da-db);target[t]=100*abs(a-b)
        p0.append(dict(model=m,frame=f,channel=ch,n_design=len(design),n_base_missing=len(design)-len(vals),
            n_valid=len(vals),n_pos=sum(v>EPS_PP for v in vals.values()),n_neg=sum(v< -EPS_PP for v in vals.values()),
            n_zero=sum(abs(v)<=EPS_PP for v in vals.values()),signed_delta_pp=summarize_values(vals)))
        if ch!='Direct-100':
            diff={t:target[t]-direct[t] for t in direct}
            nt.append(dict(model=m,frame=f,target=ch,n_design=len(design),n_base_missing=base_missing,
                n_eligible_nontie=eligible,n_target_missing=missing,n_valid=len(diff),
                n_shrunk=sum(v< -EPS_PP for v in diff.values()),n_expanded=sum(v>EPS_PP for v in diff.values()),
                n_equal=sum(abs(v)<=EPS_PP for v in diff.values()),direct_abs_pp=summarize_values(direct),
                target_abs_pp=summarize_values(target),paired_diff_abs_pp=summarize_values(diff)))
    ranges={}
    for name,subjective,all_four in [('subjective_96_three_channels',True,False),('subjective_all_four_channels',True,True),('both_stances_96_three_channels',False,False),('both_stances_all_four_channels',False,True)]:
        xs=[r['signed_delta_pp']['mean'] for r in p0 if (not subjective or r['frame']=='subjective') and (all_four or r['channel']!='Direct-13')]
        ranges[name]=dict(min_mean=min(xs),max_mean=max(xs),n_cells=len(xs))
    mc=[r for r in nt if r['target']=='MCW-100'];valid=[r for r in mc if r['n_valid']]
    mr=dict(n_total_cells=len(mc),n_estimable_cells=len(valid),n_empty_cells=len(mc)-len(valid),n_shrunk_cells=sum(r['paired_diff_abs_pp']['mean']< -EPS_PP for r in valid))
    for label,sub in [('subjective',True),('both_stances',False)]:
        for out,field in [('direct','direct_abs_pp'),('mcw','target_abs_pp')]:
            xs=[r[field]['mean'] for r in valid if not sub or r['frame']=='subjective']
            mr[label+'_'+out+'_abs_range']=[min(xs),max(xs)]
    assert len(p0)==34 and len(nt)==22
    return dict(n_files=11,n_records=total,raw_sha256=hashes,stimuli_sha256=sha,
        method=dict(unit='pp',direction='Arm A - Arm B',B=4000,seed=20261115,EPS_PP=EPS_PP,bootstrap_sampling='randrange',order='template_id ascending',ddof=1),
        p0_signed_all_templates=p0,range_summary=ranges,nontie_smoothing=nt,mcw100_range_summary=mr)
def main():
    global PROJECT, RAW, vd, ef, upstream
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir',type=Path,required=True)
    ap.add_argument('--stimuli',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    a=ap.parse_args()
    PROJECT=a.stimuli.parent
    if a.stimuli.name!='formal_stimuli.json': raise ValueError('Expected formal_stimuli.json')
    RAW=a.data_dir
    vd=SimpleNamespace(EXPECTED_ARMS=EXPECTED_ARMS)
    ef=SimpleNamespace(KEY_FIELDS=KEY_FIELDS,index_records=index_records,extract_prob01=extract_prob01,PRE_REGISTERED_SCALE13_TEMPLATES=PRE_REGISTERED_SCALE13_TEMPLATES)
    upstream=SimpleNamespace(ef=ef,vd=vd,RAW=RAW,PROJECT=PROJECT,read=read,quantile=quantile)
    a.out_dir.mkdir(parents=True,exist_ok=True)
    for name,fn in [('tie_delta_summary.json',compute_ties),('p0_nontie_summary.json',compute_nonties)]:
        (a.out_dir/name).write_text(json.dumps(fn(),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('PASS: 11 files; 44,640 records; 22 tie / 34 P0 / 22 non-tie cells; B=4000 seed=20261115')
if __name__=='__main__': main()

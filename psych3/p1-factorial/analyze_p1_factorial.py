"""Locked two-level cluster analysis, bootstrap-Holm, PP and contrast Manski."""
import argparse, json, math
from collections import defaultdict
from statistics import NormalDist
import numpy as np
from build_banks import ROOT, SEED, dump
B=10000
SESOI={'MAE':1.5,'FrameGap':2.,'Echo_D2':5.,'cand_str_copy_any':5.}
A_CELLS=['A00','A01','A10','A11']
B_CELLS=[f'M{m}_{rep}' for rep in ('pct','freq') for m in (13,15,100)]
A_COEFS={'Delta_P':[-.5,-.5,.5,.5],'Delta_A':[-.5,.5,-.5,.5],'interaction':[1,-1,-1,1]}
def b_coefs():
    out={}
    for rep in ('pct','freq'):
        for m in (13,15): out[f'Delta_{m}_100_{rep}']=[int(c==f'M{m}_{rep}')-int(c==f'M100_{rep}') for c in B_CELLS]
    for m in (13,15): out[f'DiD_{m}']=[a-b for a,b in zip(out[f'Delta_{m}_100_freq'],out[f'Delta_{m}_100_pct'])]
    return out
def frame_bounds(pos,neg):
    def interval(xs): return sum(x for x in xs if x is not None)/len(xs),sum(x if x is not None else 100 for x in xs)/len(xs)
    lp,up=interval(pos); ln,un=interval(neg)
    return max(0,lp-un,ln-up),max(abs(lp-un),abs(up-ln))
def manski(a,l,u):
    return sum(x*(lo if x>0 else hi) for x,lo,hi in zip(a,l,u)),sum(x*(hi if x>0 else lo) for x,lo,hi in zip(a,l,u))
def bootstrap(matrix):
    x=np.asarray(matrix,dtype=float)
    if len(x)==0: return None
    if x.ndim==1: x=x[:,None]
    rng=np.random.default_rng(SEED); samples=x[rng.integers(0,len(x),(B,len(x)))].mean(axis=1)
    k=x.shape[1]; p=np.minimum(1,2*np.minimum((1+(samples<=0).sum(axis=0))/(B+1),(1+(samples>=0).sum(axis=0))/(B+1)))
    order=np.argsort(p,kind='stable'); adj=np.empty(k); adj[order]=np.minimum(1,np.maximum.accumulate(p[order]*(k-np.arange(k))))
    return [dict(estimate=float(x[:,i].mean()),ci95_raw=np.quantile(samples[:,i],[.025,.975]).tolist(),p_raw=float(p[i]),p_holm=float(adj[i]),ci95_simultaneous=np.quantile(samples[:,i],[.05/(2*k),1-.05/(2*k)]).tolist(),cluster_variance=float(x[:,i].var(ddof=1)) if len(x)>1 else None) for i in range(k)]
def score(r,endpoint):
    if endpoint=='MAE':
        truth=r['truth_pct']
        if r['parse_ok']:
            v=abs(r['parsed']['m_w']-truth); return [v,v,v,v,v]
        upper=max(truth,100-truth); return [abs(50-truth),0,upper,upper,abs(50-truth)]
    if r['parse_ok']:
        v=100*float(r['metrics'][endpoint]); return [v,v,v,v,v]
    return [100,0,100,100,0]
def cluster_scores(rows,endpoint,cells):
    grouped=defaultdict(dict)
    for r in rows: grouped[(r['polarity'],r['cell'])][r['rep_idx']]=r
    # PP shares successful repeats across every cell; Framing also across both polarities.
    pp_reps={}
    for pol in ('pos','neg'):
        reps=set.intersection(*(set(grouped[(pol,c)]) for c in cells))
        pp_reps[pol]={idx for idx in reps if all(grouped[(pol,c)][idx]['parse_ok'] for c in cells)}
    if endpoint=='FrameGap': pp_reps['pos']=pp_reps['neg']=pp_reps['pos']&pp_reps['neg']
    available=all(pp_reps.values()); values=[]; pp=[]
    for c in cells:
        if endpoint=='FrameGap':
            predictions={pol:[r['parsed']['m_w'] if r['parse_ok'] else None for _,r in sorted(grouped[(pol,c)].items())] for pol in ('pos','neg')}
            lo,hi=frame_bounds(predictions['pos'],predictions['neg']); values.append([hi,lo,hi,hi,hi])
            if available: pp.append(abs(np.mean([grouped[('pos',c)][i]['parsed']['m_w'] for i in pp_reps['pos']])-np.mean([grouped[('neg',c)][i]['parsed']['m_w'] for i in pp_reps['neg']])))
        else:
            values.append(np.mean([np.mean([score(r,endpoint) for r in grouped[(pol,c)].values()],axis=0) for pol in ('pos','neg')],axis=0).tolist())
            if available: pp.append(float(np.mean([np.mean([score(grouped[(pol,c)][i],endpoint)[0] for i in pp_reps[pol]]) for pol in ('pos','neg')])))
    return np.array(values),np.array(pp) if available else None

def family(rows,endpoint,cells,coefs,formal_n):
    from run_p1_factorial import MODELS
    models=list(MODELS); clusters=sorted({r['cluster_id'] for r in rows}); grouped=defaultdict(list)
    for r in rows: grouped[(r['model'],r['cluster_id'])].append(r)
    data={m:{} for m in models}
    for m in models:
        for s in clusters: data[m][s]=cluster_scores(grouped[(m,s)],endpoint,cells)
    coef=np.array(list(coefs.values())); common=[s for s in clusters if all(data[m][s][1] is not None for m in models)]
    def aggregate(ms,ss,pp=False):
        ans=[]
        for s in ss:
            if pp: ans.append(coef@np.mean([data[m][s][1] for m in ms],axis=0))
            else:
                vals=np.mean([data[m][s][0] for m in ms],axis=0)
                itt=coef@vals[:,0]; bounds=[manski(a,vals[:,1],vals[:,2]) for a in coef]
                ans.append((itt,np.array(bounds)[:,0],np.array(bounds)[:,1],coef@vals[:,3],coef@vals[:,4]))
        return ans
    output={}
    for label,ms in [('four_models_equal',models)]+[(m,[m]) for m in models]:
        ss=common if len(ms)==len(models) else [s for s in clusters if data[ms[0]][s][1] is not None]
        raw=aggregate(ms,clusters); ppr=aggregate(ms,ss,True)
        itt=bootstrap([x[0] for x in raw]); lower=bootstrap([x[1] for x in raw]); upper=bootstrap([x[2] for x in raw]); pen=bootstrap([x[3] for x in raw]); fail0=bootstrap([x[4] for x in raw]); pp=bootstrap(ppr)
        result={}
        for i,name in enumerate(coefs):
            sesoi=SESOI[endpoint]; two_sided=name.startswith(('interaction','DiD'))
            def success(x):
                if x is None: return False
                lo,hi=x['ci95_simultaneous']; return x['p_holm']<.05 and (abs(x['estimate'])>=sesoi and (lo>0 or hi<0) if two_sided else x['estimate']<=-sesoi and hi<0)
            direction=upper[i]['estimate']<0 and upper[i]['ci95_simultaneous'][1]<0
            substantial=upper[i]['estimate']<=-sesoi and upper[i]['ci95_simultaneous'][1]<0
            interaction_robust=direction or (lower[i]['estimate']>0 and lower[i]['ci95_simultaneous'][0]>0)
            ppi=pp[i] if pp else None
            variance=itt[i]['cluster_variance']
            # Normal approximation, family alpha/K, 80% power; not an observed power claim.
            mde=(NormalDist().inv_cdf(1-.05/(2*len(coefs)))+NormalDist().inv_cdf(.8))*math.sqrt(variance/formal_n) if variance is not None else None
            result[name]=dict(ITT=itt[i],Manski_lower=lower[i],Manski_upper=upper[i],PP=ppi,penalty_sensitivity=pen[i],fail_as_0=fail0[i] if endpoint not in ('MAE','FrameGap') else None,**{'Manski-direction-robust':direction,'Manski-SESOI-robust':substantial},Manski_interaction_robust=interaction_robust,confirmatory_success=success(itt[i]) and success(ppi) and (interaction_robust if two_sided and endpoint in ('Echo_D2','cand_str_copy_any') else substantial if endpoint in ('Echo_D2','cand_str_copy_any') else True),pilot_based_MDE_80pct_formal=mde)
        output[label]=dict(contrasts=result,pp_common_clusters=ss,pp_excluded_clusters=sorted(set(clusters)-set(ss)),planned_clusters=clusters)
    return dict(endpoint=endpoint,cells=cells,coefficients=coefs,K_Holm=len(coefs),SESOI=SESOI[endpoint],results=output)
def selftest():
    assert frame_bounds([100,None],[0,100])==(0,50)
    assert frame_bounds([None],[20])==(0,80)
    assert frame_bounds([None,None],[None,None])==(0,100)
    assert manski([1,-1,-1,1],[0]*4,[100]*4)==(-200,200)
    assert score(dict(parse_ok=False,truth_pct=20),'MAE')==[30,0,80,80,30]
    assert score(dict(parse_ok=False),'Echo_D2')==[100,0,100,100,0]
    # One missing polarity invalidates PP; one missing model invalidates pooled PP.
    from build_banks import build
    units=[u for u in build('pilot') if u['cluster_id']=='bayes_A_pilot_01']
    rows=[dict(u,parse_ok=u['polarity']=='pos',parsed={'m_w':20}) for u in units]
    assert cluster_scores(rows,'MAE',A_CELLS)[1] is None
    # Cross-model common set requires every model and both polarities.
    model_pp={'m1':{'s1':True,'s2':True},'m2':{'s1':True,'s2':False},'m3':{'s1':True,'s2':True},'m4':{'s1':True,'s2':False}}
    assert [s for s in ('s1','s2') if all(model_pp[m][s] for m in model_pp)]==['s1']
    for r in rows: r['parse_ok']=True
    complete=cluster_scores(rows,'MAE',A_CELLS)[1]
    assert complete is not None and len(complete)==4
    rows[0]['parse_ok']=False
    assert cluster_scores(rows,'MAE',A_CELLS)[1] is None
    units2=[u for u in build('formal') if u['cluster_id']=='bayes_A_formal_01']
    rows2=[dict(u,parse_ok=True,parsed={'m_w':u['truth_pct']+(10 if u['rep_idx']==1 else 20)}) for u in units2]
    next(r for r in rows2 if r['cell']=='A00' and r['polarity']=='pos' and r['rep_idx']==1)['parse_ok']=False
    _, pp2=cluster_scores(rows2,'MAE',A_CELLS)
    assert np.allclose(pp2,[17.5]*4) # pos shared R2=20, neg shared R1/R2=15; equal polarity weights.
    test=bootstrap([[1,0],[1,0]])
    assert test[0]['p_raw']==2/(B+1) and test[0]['p_holm']==4/(B+1) and test[1]['p_raw']==1
    print('PASS statistics: R=2 FrameGap [0,50], one/both failed, DiD [-200,200], fail_as_1, polarity/model PP, bootstrap-Holm')
def main():
    from run_p1_factorial import MODELS,tag
    ap=argparse.ArgumentParser(); ap.add_argument('--stage',choices=['pilot','formal'],required=True); args=ap.parse_args()
    bank=json.loads((ROOT/f'bank_{args.stage}.json').read_text(encoding='utf-8')); records=[]; gates={}
    for model in MODELS:
        path=ROOT/'results'/f'{args.stage}_{tag(model)}.jsonl'
        rows=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
        indexed={r['unit_id']:r for r in rows}; assert len(indexed)==len(rows),'duplicate units'
        assert set(indexed)<=set(u['unit_id'] for u in bank)
        complete=[]
        for u in bank:
            complete.append(indexed.get(u['unit_id'],dict(u,model=model,parse_ok=False,parsed={'parse_ok':False},metrics=None,attempts_log=[])))
        records+=complete
        gates[model]={}
        for cell in sorted({u['cell'] for u in bank}):
            sub=[r for r in complete if r['cell']==cell]; attempts=[a for r in sub for a in r['attempts_log']]
            first=sum(bool(r['attempts_log']) and r['attempts_log'][0]['attempt_idx']==1 and r['attempts_log'][0]['parse_ok'] for r in sub)/len(sub)
            trunc=sum(a['normalized_stop_reason']=='length_truncated' for a in attempts)/len(attempts) if attempts else None
            unknown=sum(a['normalized_stop_reason']=='unknown_or_other' for a in attempts)/len(attempts) if attempts else None
            missing=sum(not r['parse_ok'] for r in sub)/len(sub)
            gates[model][cell]=dict(planned=len(sub),recorded=sum(bool(r['attempts_log']) for r in sub),first_attempt_parse_rate=first,length_truncated_rate=trunc,unknown_stop_reason_rate=unknown,final_missing_rate=missing,all_attempts=len(attempts),pass_gate=first>=.9 and trunc==0 and unknown==0 and missing<.02)
    families={}
    for name,block,task,ep,cells,coefs,n in [('A_Bayesian','A','bayes','MAE',A_CELLS,A_COEFS,12),('A_Framing','A','framing','FrameGap',A_CELLS,A_COEFS,12)]+[(f'B_{ep}','B','bayes',ep,B_CELLS,b_coefs(),16) for ep in ('MAE','Echo_D2','cand_str_copy_any')]:
        families[name]=family([r for r in records if r['block']==block and r['task']==task],ep,cells,coefs,n)
    diagnostics={}
    for model in MODELS:
        diagnostics[model]={}
        for cell in sorted({r['cell'] for r in records}):
            sub=[r for r in records if r['model']==model and r['cell']==cell and r['parse_ok']]
            diagnostics[model][cell]={'successful_n':len(sub),'ascending_violation_rate':float(np.mean([r['parsed']['ascending_violation'] for r in sub])) if sub else None}
            # Secondary descriptive outcomes are explicitly outside confirmatory families.
            if sub:
                for readout in ('m_w','m_u','top1'):
                    truth=np.array([r['truth_pct'] for r in sub]); pred=np.array([r['parsed'][readout] for r in sub])
                    diagnostics[model][cell][readout]={'MAE_pp':float(np.mean(abs(pred-truth))),'beta1':float(np.cov(truth,pred,ddof=0)[0,1]/np.var(truth)) if np.var(truth)>0 else None,'detectors':{d:float(np.mean([r['metrics'][readout][d] for r in sub])) for d in ('D0','D1','D2','D3','D4','D5a','D5b','D5b_allM')}}
                for key in ('weighted_sd','unweighted_sd','all_candidates_identical'):
                    diagnostics[model][cell][key]=float(np.mean([r['parsed'][key] for r in sub]))
            for metric in ('Echo_D2','cand_str_copy_any','cand_D5a_any','cand_D2_any','non_integer_cand_rate','grid_dist_M'):
                diagnostics[model][cell][metric]=float(np.mean([r['metrics'][metric] for r in sub])) if sub else None
    result=dict(stage=args.stage,planned_units_per_model=len(bank),B=B,seed=SEED,gates=gates,all_gates_pass=all(v['pass_gate'] for m in gates.values() for v in m.values()),families=families,diagnostics=diagnostics,MDE_method='Normal approximation; two-sided alpha/K, 80% power, pilot paired-cluster variance, formal planned S. Pilot estimates are exploratory.',claim_boundary='Only four tested models and sampled scenarios. Operational cue-proximity/string-match changes only; freq minimum cue Pilot 18 / Formal 22 > 15 structurally precludes legal raw matching at M13/M15; no neural mechanism inference.')
    dump(f'summary_p1_{args.stage}.json',result)
    print(json.dumps({'stage':args.stage,'recorded':sum(v['recorded'] for m in gates.values() for v in m.values()),'planned':len(MODELS)*len(bank),'all_gates_pass':result['all_gates_pass'],'families':{k:v['K_Holm'] for k,v in families.items()}},ensure_ascii=False))
if __name__=='__main__': main()

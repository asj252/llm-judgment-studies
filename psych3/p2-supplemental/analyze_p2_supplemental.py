#!/usr/bin/env python3
"""Preregistered paired cluster inference with complete-grid ITT and common-complete PP."""
import argparse, itertools, math
import numpy as np
from build_p2_banks import ROOT,A_MODELS,B_MODELS,A_ARMS,B_ARMS,load,dump,SEED
from run_p2_supplemental import records,result_path
READOUTS=['m_w','m_u','top1']
def avg(x):return float(np.mean(x))
def mde80(values):
    """Normal-approximation, two-sided alpha .05, 80% power; cluster units, no R divisor."""
    values=np.asarray(values,dtype=float)
    n=len(values)
    variance=float(np.var(values,ddof=1)) if n>1 else None
    return dict(cluster_count=n,paired_cluster_difference_variance=variance,
                mde80_pp=(1.959963984540054+0.8416212335729143)*math.sqrt(variance/n) if variance is not None else None,
                method='Normal approximation, unadjusted two-sided alpha=.05; planned cluster count; R=1 not divided by 2')
def frame_interval(values):
    r=len(values);lo=sum(x for x in values if x is not None)/r
    return lo,lo+100*sum(x is None for x in values)/r
def gap_interval(pos,neg):
    lp,up=frame_interval(pos);ln,un=frame_interval(neg)
    return max(0,lp-un,ln-up),max(abs(lp-un),abs(up-ln))
def scalar_score(value,truth):
    return (abs(50-truth),0,max(truth,100-truth)) if value is None else (abs(value-truth),)*3
def b_metrics(vec,truth):
    truth=np.asarray(truth);ok=vec is not None
    y=np.asarray(vec if ok else [100/3]*3,dtype=float);s=float(sum(y));zero=s<=1e-9
    norm=100*y/s if not zero else np.full(3,100/3)
    vals=sorted(norm);tie=abs(vals[-1]-vals[-2])<=1e-9
    mae=float(np.mean(abs(norm-truth)));acc=100. if ok and not tie and int(np.argmax(norm))==int(np.argmax(truth)) else 0.
    return dict(MAE_norm=(mae,mae,mae) if ok else (mae,0,2/3*(100-float(min(truth)))),Acc_argmax=(acc,acc,acc) if ok else (0.,0.,100.),MAE_raw=float(np.mean(abs(y-truth))),S=s,argmax_tie_rate=100.*tie,zero_sum_fallback=zero)
def contrast(t,r):return t[0]-r[0],t[1]-r[2],t[2]-r[1]
def holm(ps):
    order=np.argsort(ps,kind='stable');out=np.ones(len(ps));v=0
    for rank,i in enumerate(order):v=max(v,(len(ps)-rank)*ps[i]);out[i]=min(1,v)
    return out.tolist()
def bootstrap(matrix,k=None):
    x=np.asarray(matrix,dtype=float)
    if len(x)==0:return 'NA_EMPTY_PP'
    if x.ndim==1:x=x[:,None]
    n,cols=x.shape;k=k or cols
    rng=np.random.default_rng(SEED);draw=x[rng.integers(0,n,(10000,n))].mean(axis=1)
    result=[]
    for i in range(cols):
        v=draw[:,i];p=min(1.,2*min((1+sum(v<=0))/10001,(1+sum(v>=0))/10001))
        sd=float(np.std(x[:,i],ddof=1)) if n>1 else 0
        result.append(dict(estimate=float(np.mean(x[:,i])),ci95_raw=np.quantile(v,[.025,.975],method='linear').tolist(),p_raw=p,ci95_simultaneous=np.quantile(v,[.05/(2*k),1-.05/(2*k)],method='linear').tolist(),cluster_sd=sd,MDE_pilot_R1_80=2.801585*sd/math.sqrt(n),clusters=n))
    for r,p in zip(result,holm([r['p_raw'] for r in result])):r['p_holm']=p
    return result
def improved(s,acc=False):
    if not isinstance(s,dict):return False
    return s['p_holm']<.05 and (s['estimate']>0 and s['ci95_simultaneous'][0]>0 if acc else s['estimate']<0 and s['ci95_simultaneous'][1]<0)
def classify_flags(mi,mp,ai,ap,degradation,tie,fragile):
    im=mi and mp;ia=ai and ap
    if im and ia and not tie and not degradation and not fragile:return 1
    elif im or ia or mi or ai:return 2
    else:return 3
def decision(mi,mp,ai,ap,cu,cl,tie_itt,tie_pp,common):
    im,pm,ia,pa=improved(mi),improved(mp),improved(ai,True),improved(ap,True)
    deg=any(improved(dict(s,estimate=-s['estimate'],ci95_simultaneous=[-s['ci95_simultaneous'][1],-s['ci95_simultaneous'][0]]),acc) for s,acc in [(mi,False),(mp,False),(ai,True),(ap,True)] if isinstance(s,dict))
    fragile=common==0 or im!=pm or ia!=pa or (im and cu>=0) or (ia and cl<=0)
    tie=tie_itt>0 or (common>0 and tie_pp>0)
    return dict(category=classify_flags(im,pm,ia,pa,deg,tie,fragile),imp_mae_itt=im,imp_mae_pp=pm,imp_acc_itt=ia,imp_acc_pp=pa,flag_degradation=deg,flag_tie_worsened=tie,flag_missingness_fragile=fragile,flag_exceeds_sesoi=mi['estimate']<=-1 and ai['estimate']>=5)
def final_calls(stage):
    out={};allrows=[]
    for study,models in [('p2a',A_MODELS),('p2b',B_MODELS)]:
        for model in models:
            rows=records(result_path(stage,study,model));allrows.extend(rows)
            for r in rows:
                cid=r['call_id']
                if cid in out and out[cid]['call_parse_ok']:continue
                if cid not in out or r['attempt_idx']>out[cid]['attempt_idx']:out[cid]=r
    return out,allrows
def unit_values(u,calls):
    rows=[calls.get(u['unit_id']+f'/sub{i}') for i in range(len(u['prompts']))]
    if not all(r and r['call_parse_ok'] for r in rows):return None
    if len(rows)==3:return {key:[r['parse'][key] for r in rows] for key in READOUTS}
    p=rows[0]['parse']
    return {key:[p[key][c] for c in 'ABC'] if u['study']=='p2b' else p[key] for key in READOUTS}
def prepare(bank,calls):
    return {(u['cluster_id'],u['model'],u['facet'],u['rep_idx'],u['arm']):(u,unit_values(u,calls)) for u in bank['units']}
def family_data(bank,calls,kind,metric,readout='m_w',models=None):
    b=kind=='scen';models=models or (B_MODELS if b else A_MODELS);arms=B_ARMS if b else A_ARMS
    facets=['ord_abc','ord_cba'] if b else ['pos','neg'];reps=range(1,bank['repeats']+1)
    clusters=sorted({u['cluster_id'] for u in bank['units'] if u['kind']==kind});data=prepare(bank,calls)
    itt=[];pp=[];common=[];lower=[];upper=[]
    for c in clusters:
        bymodel=[];ppmodel=[]
        for m in models:
            complete={f:[r for r in reps if all(data[c,m,f,r,a][1] is not None for a in arms)] for f in facets}
            if metric=='FrameGap':
                rr=[r for r in reps if all(r in complete[f] for f in facets)];eligible=bool(rr)
            else:eligible=all(complete.values())
            vals=[];pv=[]
            for a in arms:
                def value(f,r):
                    u,v=data[c,m,f,r,a];return None if v is None else v[readout]
                if metric=='FrameGap':
                    lo,hi=gap_interval([value('pos',r) for r in reps],[value('neg',r) for r in reps]);score=(hi,lo,hi)
                    pscore=abs(avg([value('pos',r) for r in rr])-avg([value('neg',r) for r in rr])) if eligible else None
                else:
                    def score_one(f,r):
                        u,v=data[c,m,f,r,a]
                        return b_metrics(value(f,r),u['truth'])[metric] if b else scalar_score(value(f,r),u['truth'])
                    scores=[np.mean([score_one(f,r) for r in reps],axis=0) for f in facets];score=np.mean(scores,axis=0)
                    pscore=avg([avg([score_one(f,r)[0] for r in complete[f]]) for f in facets]) if eligible else None
                vals.append(score);pv.append(pscore)
            bymodel.append(vals);ppmodel.append(pv)
        ar=np.mean(bymodel,axis=0);itt.append(ar[:,0]);lower.append(ar[:,1]);upper.append(ar[:,2])
        if all(v is not None for row in ppmodel for v in row):pp.append(np.mean(ppmodel,axis=0));common.append(c)
    return dict(clusters=clusters,itt=np.asarray(itt),lower=np.asarray(lower),upper=np.asarray(upper),pp=np.asarray(pp).reshape(-1,len(arms)),common=common)
def family_report(data,pairs,k):
    ii=np.column_stack([data['itt'][:,t]-data['itt'][:,r] for t,r in pairs]);pp=np.column_stack([data['pp'][:,t]-data['pp'][:,r] for t,r in pairs]);lo=np.column_stack([data['lower'][:,t]-data['upper'][:,r] for t,r in pairs]);hi=np.column_stack([data['upper'][:,t]-data['lower'][:,r] for t,r in pairs])
    return ii,pp,lo,hi

def analyze(stage):
    bank=load(ROOT/f'bank_p2_{stage}.json');calls,rows=final_calls(stage)
    summary=dict(stage=stage,R=bank['repeats'],B=10000,seed=SEED,planned_calls=bank['scheduled_calls'],terminal_calls=sum(r['call_parse_ok'] or r['attempt_idx']==4 for r in calls.values()),confirmatory_readout_p2b='m_w',quality={},P2A={},P2B={})
    for study,models,arms in [('p2a',A_MODELS,A_ARMS),('p2b',B_MODELS,B_ARMS)]:
        for model,a in itertools.product(models,arms):
            planned=[u for u in bank['units'] if u['study']==study and u['model']==model and u['arm']==a]
            n=sum(len(u['prompts']) for u in planned);rr=[r for r in rows if r['model']==model and r['arm']==a];first=[r for r in rr if r['attempt_idx']==1]
            ids=[u['unit_id']+f'/sub{i}' for u in planned for i in range(len(u['prompts']))]
            summary['quality'][study+'/'+model+'/'+a]=dict(planned_calls=n,first_records=len(first),first_parse_rate=sum(r['call_parse_ok'] for r in first)/n,final_missing_rate=sum(not calls.get(cid,{}).get('call_parse_ok',False) for cid in ids)/n,unit_missing_rate=avg([unit_values(u,calls) is None for u in planned]),truncation_rate=avg([r['finish_reason']=='MAX_TOKENS' for r in rr]) if rr else None,unknown_finish_rate=avg([r['finish_reason']=='OTHER' for r in rr]) if rr else None,completion_tokens=avg([r['completion_tokens'] for r in rr]) if rr else None,reasoning_char_len=avg([r['reasoning_char_len'] for r in rr]) if rr else None,latency_ms=avg([r['latency_ms'] for r in rr]) if rr else None,order_violation_rate=avg([r['parse'].get('order_violation',False) for r in rr if r['call_parse_ok']]) if any(r['call_parse_ok'] for r in rr) else None,sum100_violation_rate=avg([r['parse'].get('sum100_violation_rate',0) for r in rr if r['call_parse_ok']]) if any(r['call_parse_ok'] for r in rr) else None)
    for kind,metric in [('bayes','MAE'),('frame','MAE'),('frame','FrameGap')]:
        d=family_data(bank,calls,kind,metric);ii,pp,lo,hi=family_report(d,[(3,2),(3,1),(3,0)],3);it=bootstrap(ii,3);pr=bootstrap(pp,3);boundslo=bootstrap(lo,3);boundshi=bootstrap(hi,3)
        out=dict(pp_common_clusters=len(d['common']),pp_excluded_clusters=len(d['clusters'])-len(d['common']),primary={},arm_means_itt=d['itt'].mean(axis=0).tolist())
        for i,name in enumerate(['delta_elicit','delta_vs_cot','delta_vs_direct']):
            p=pr[i] if isinstance(pr,list) else pr;sesoi=2 if metric=='FrameGap' else 1.5;cu=boundshi[i]['estimate']
            fragile=not d['common'] or improved(it[i])!=improved(p) or (improved(it[i]) and cu>=0)
            passed=isinstance(p,dict) and it[i]['estimate']<=-sesoi and p['estimate']<=-sesoi and improved(it[i]) and improved(p) and cu<0 and not fragile
            out['primary'][name]=dict(ITT=it[i],PP=p,manski=[boundslo[i]['estimate'],cu],manski_ci95_simultaneous=[boundslo[i]['ci95_simultaneous'],boundshi[i]['ci95_simultaneous']],flag_missingness_fragile=fragile,PASS=passed,pilot_mde80=mde80(ii[:,i]) if stage=='pilot' else None)
        du=family_data(bank,calls,kind,metric,'m_u');dt=family_data(bank,calls,kind,metric,'top1')
        out['secondary']=dict(delta_readout=bootstrap(d['itt'][:,3]-du['itt'][:,3],1)[0],top1_E3_mean=avg(dt['itt'][:,3]),elicited_u_minus_posthoc_u=bootstrap(du['itt'][:,2]-du['itt'][:,3],1)[0])
        summary['P2A'][kind+'_'+metric]=out
    pairs=[(1,0),(2,0),(2,1)]
    ds=[family_data(bank,calls,'scen',metric) for metric in ['MAE_norm','Acc_argmax']]
    fd=[family_report(d,pairs,6) for d in ds];it=bootstrap(np.column_stack([x[0] for x in fd]),6);pr=bootstrap(np.column_stack([x[1] for x in fd]),6)
    lows=bootstrap(np.column_stack([x[2] for x in fd]),6);highs=bootstrap(np.column_stack([x[3] for x in fd]),6)
    # Descriptive readouts and exact common-PP tie differences share the same repetition masks.
    table={};data=prepare(bank,calls)
    for readout in READOUTS:
        table[readout]={}
        for a in B_ARMS:
            metrics=[]
            for u in bank['units']:
                if u['study']=='p2b' and u['arm']==a:metrics.append(b_metrics(unit_values(u,calls)[readout] if unit_values(u,calls) else None,u['truth']))
            table[readout][a]={key:avg([v[key][0] if isinstance(v[key],tuple) else v[key] for v in metrics]) for key in ['MAE_norm','MAE_raw','S','Acc_argmax','argmax_tie_rate','zero_sum_fallback']}
    summary['P2B']['readouts']=table;summary['P2B']['contrasts']={}
    def tie_diff(t,r,ppmode):
        scores=[]
        for c in ds[0]['common'] if ppmode else ds[0]['clusters']:
            mm=[]
            for m in B_MODELS:
                ff=[]
                for f in ['ord_abc','ord_cba']:
                    rr=[rep for rep in range(1,bank['repeats']+1) if not ppmode or all(data[c,m,f,rep,a][1] is not None for a in B_ARMS)]
                    aa=[]
                    for ai in [t,r]:
                        vv=[]
                        for rep in rr:
                            u,v=data[c,m,f,rep,B_ARMS[ai]];vv.append(b_metrics(v['m_w'] if v else None,u['truth'])['argmax_tie_rate'])
                        aa.append(avg(vv))
                    ff.append(aa[0]-aa[1])
                mm.append(avg(ff))
            scores.append(avg(mm))
        return avg(scores) if scores else 0.
    for i,(t,r) in enumerate(pairs):
        pm=pr[i] if isinstance(pr,list) else pr;pa=pr[i+3] if isinstance(pr,list) else pr
        out=decision(it[i],pm,it[i+3],pa,highs[i]['estimate'],lows[i+3]['estimate'],tie_diff(t,r,False),tie_diff(t,r,True),len(ds[0]['common']))
        out.update(MAE_norm=dict(ITT=it[i],PP=pm,manski=[lows[i]['estimate'],highs[i]['estimate']]),Acc_argmax=dict(ITT=it[i+3],PP=pa,manski=[lows[i+3]['estimate'],highs[i+3]['estimate']]),pp_common_clusters=len(ds[0]['common']),pp_excluded_clusters=len(ds[0]['clusters'])-len(ds[0]['common']),manski_ci95_simultaneous=[lows[i+3]['ci95_simultaneous'],highs[i]['ci95_simultaneous']],flag_manski_ci_robust=highs[i]['ci95_simultaneous'][1]<0 and lows[i+3]['ci95_simultaneous'][0]>0)
        if stage=='pilot':out['pilot_mde80']={metric:mde80(fd[j][0][:,i]) for j,metric in enumerate(['MAE_norm','Acc_argmax'])}
        summary['P2B']['contrasts'][f'C{t+1}-C{r+1}']=out
    for mode,groups in [('per_model',[[m] for m in B_MODELS]),('leave_one_model_out',[[m for m in B_MODELS if m!=om] for om in B_MODELS])]:
        summary['P2B'][mode]={}
        for models in groups:
            summary['P2B'][mode][','.join(models)]={metric:bootstrap(family_report(family_data(bank,calls,'scen',metric,models=models),pairs,6)[0],6) for metric in ['MAE_norm','Acc_argmax']}
    summary['pilot_gate_pass']=summary['terminal_calls']==bank['scheduled_calls'] and all(q['first_parse_rate']>=.9 and q['final_missing_rate']<.02 and q['unit_missing_rate']<.02 and q['truncation_rate']==0 and q['unknown_finish_rate']==0 for q in summary['quality'].values())
    summary['replicate_variance']={}
    for study,models,arms in [('p2a',A_MODELS,A_ARMS),('p2b',B_MODELS,B_ARMS)]:
        for model,arm in itertools.product(models,arms):
            group={}
            for u in bank['units']:
                if u['study']!=study or u['model']!=model or u['arm']!=arm:continue
                v=unit_values(u,calls)
                if v is not None:group.setdefault((u['cluster_id'],u['facet']),{})[u['rep_idx']]=v['m_w']
            paired=[np.asarray([v[1],v[2]],dtype=float) for v in group.values() if 1 in v and 2 in v]
            cluster={}
            for (cid,facet),v in group.items():cluster.setdefault(cid,[]).append(float(np.mean(list(v.values()))))
            cm=[avg(v) for v in cluster.values()]
            if paired:
                x=np.stack(paired);within=float(np.mean(np.var(x,axis=1,ddof=1)));a=x[:,0].ravel();b=x[:,1].ravel();rho=float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else None
            else:within=None;rho=None
            summary['replicate_variance'][study+'/'+model+'/'+arm]=dict(sigma2_rep=within,sigma2_cluster=float(np.var(cm,ddof=1)) if len(cm)>1 else None,rho_rep=rho,complete_repeat_pairs=len(paired),effective_replications=2/(1+rho) if rho is not None and rho>-1 else None,note='Pilot R=1: no replicate variance or division by 2; R=2 estimates restricted to complete pairs')
    dump(ROOT/f'summary_p2_{stage}.json',summary);return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['pilot','formal'],default='pilot');a=p.parse_args();s=analyze(a.stage);print('Pilot gate:',s['pilot_gate_pass'],'terminal calls:',s['terminal_calls'],'/',s['planned_calls'])

#!/usr/bin/env python3
"""Deterministic Rev 6 banks; no reference-source runtime dependency."""
from pathlib import Path
import sys, json, random, itertools
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
sys.path.insert(0, str(ROOT.parents[1]))
from mcv_standard import ASK_DIRECT, ASK_MULTI, render_joint_multi
SEED = 20261110
A_MODELS = ['sf:qwen3-8b','aistudio:gemma-4-26b-a4b-it','nv:nemotron-3.5-super-vl-120b','xf:spark-x2.6']
B_MODELS = A_MODELS.copy()
A_ARMS = ['E0_direct','E1_generic_cot','E2_unweighted_mcv','E3_weighted_mcv']
B_ARMS = ['C1_joint_constrained','C2_joint_unconstrained','C3_separate_unconstrained']
P3 = [(15,35,50),(20,30,50),(20,50,30),(25,35,40),(30,20,50),(30,45,25),(35,25,40),(40,25,35),(45,30,25),(50,30,20)]
L3 = [(80,45,15),(75,40,20),(85,50,20),(70,35,15),(20,75,35),(25,80,40),(15,70,35),(15,40,85),(20,45,80),(25,35,75)]
EXPECTED_22 = [((15,35,50),l) for l in [(85,50,20),(20,75,35),(15,70,35),(15,40,85),(20,45,80),(25,35,75)]] + [
((20,30,50),(70,35,15)),((20,30,50),(20,45,80)),((20,50,30),(80,45,15)),((20,50,30),(85,50,20)),((25,35,40),(85,50,20)),((25,35,40),(20,75,35)),((25,35,40),(25,80,40)),((25,35,40),(15,40,85)),((25,35,40),(20,45,80)),((30,20,50),(25,80,40)),((30,20,50),(20,45,80)),((30,20,50),(25,35,75)),((30,45,25),(70,35,15)),((30,45,25),(25,80,40)),((35,25,40),(15,40,85)),((35,25,40),(20,45,80))]
def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def posterior(p,l):
    v=[a*b for a,b in zip(p,l)];return [100*x/sum(v) for x in v]
def grids():
    valid=[]
    for p,s,f in itertools.product([4,6,8,12,14,16,18,22,24,28,32,36,42],[65,70,75,80,85,90],[10,15,20,25,30]):
        h=10*p;tp=h*s/100;fp=(1000-h)*f/100
        q=[p,s,f,1000,h,1000-h,tp,h-tp,fp,1000-h-fp]
        truths=[100*tp/(tp+fp),100*(h-tp)/(h-tp+1000-h-fp)]
        if all(min(abs(t-c) for c in q)>2 and all(min(abs(t*m/100-c) for c in q)>.5 for m in [13,15,100]) for t in truths): valid.append((p,s,f))
    v3=[]
    for p in P3:
        for l in L3:
            t=posterior(p,l);sort=sorted(t,reverse=True)
            if sort[0]-sort[1]>8 and min(abs(v-c) for v in t for c in p+l)>2:v3.append((p,l))
    assert len(valid)==310 and len(v3)==30
    selected=[valid[4+16*k] for k in range(18)]
    assert selected[0]==(4,70,30) and selected[-1]==(36,80,30)
    assert v3[:22]==EXPECTED_22
    return selected,v3[:22]
def tail(arm):
    replace='Replace each placeholder with an actual numeric value. Never output literal letters NN or W. Output this format block exactly once, with no second copy, explanations, headings, Markdown, or reasoning before or after it. '
    six='You must output all 6 lines (1 Initial Point line followed by all 5 Estimate lines: Estimate 1 through Estimate 5); even if all 5 candidate rows repeat the exact same numbers, you must still output all 5 Estimate lines. '
    weights='Weights must be nonnegative and sum to one (e.g., 0.2 each); never assign 0 to all five weights. '
    if arm==A_ARMS[0]:return replace+ASK_DIRECT
    if arm==A_ARMS[1]:return "Think step-by-step briefly in plain prose (do NOT write the label 'Probability:' in your reasoning), then on the final line output Probability: <number from 0 to 100>% exactly once."
    if arm==A_ARMS[2]:
        return ('Give an initial probability and five estimates sorted in nondecreasing order; repeats are allowed. '+six+replace+'\nInitial Point: <number from 0 to 100>%\n'+''.join(f'Estimate {i}: <number from 0 to 100>%\n' for i in range(1,6)))
    if arm in [A_ARMS[3],B_ARMS[2]]:
        return ('Give an initial probability and five estimates sorted in nondecreasing order; repeats are allowed. '+six+weights+replace+'\nInitial Point: <number from 0 to 100>%\n'+''.join(f'Estimate {i}: <number from 0 to 100>% | Weight: <number from 0 to 1>\n' for i in range(1,6)))
    values='S1 <number from 0 to 100>% | S2 <number from 0 to 100>% | S3 <number from 0 to 100>%'
    constraint=('Each candidate row must sum to 100% across S1, S2 and S3. ' if arm==B_ARMS[0] else 'Evaluate each option independently; the three probabilities need not sum to 100%. ')
    return (constraint+'Sort ONLY S1 in nondecreasing order; S2 and S3 vary freely; repeats are allowed. '+six+weights+replace+'\nInitial Point: '+values+'\n'+''.join(f'Estimate {i}: {values} | Weight: <number from 0 to 1>\n' for i in range(1,6)))
def banks(stage):
    bayes,opt=grids();pilot=stage=='pilot'; units=[]
    def add(study,kind,idx,facet,truth,params,story,order=None):
        models=A_MODELS if study=='p2a' else B_MODELS
        arms=A_ARMS if study=='p2a' else B_ARMS
        cluster=f'{study}_{kind}_{stage}_{idx:02d}'
        for model,rep,arm in itertools.product(models,range(1,2 if pilot else 3),arms):
            prompts=[story+'\n\n'+tail(arm)]
            if arm==B_ARMS[2]:
                prompts=[story+f'\nTarget statement: The source is option {key}. Estimate only this target, independently.\n\n'+tail(arm) for key in 'ABC']
            units.append(dict(unit_id=f'{cluster}/{facet}/{model}/{rep}/{arm}',study=study,kind=kind,cluster_id=cluster,facet=facet,model=model,rep_idx=rep,arm=arm,truth=truth,params=params,order=order,prompts=prompts))
    for i,(p,s,f) in enumerate(bayes[:6] if pilot else bayes[6:],1):
        for pol in ['pos','neg']:
            ps=p/100;ss=s/100;ff=f/100
            t=100*ps*(ss if pol=='pos' else 1-ss)/(ps*(ss if pol=='pos' else 1-ss)+(1-ps)*(ff if pol=='pos' else 1-ff))
            story=f'In a population, {p}% have condition H. A test is positive for {s}% of those with H and {f}% of those without H. A randomly selected person tests {"positive" if pol=="pos" else "negative"}. Statement: This person has H.'
            add('p2a','bayes',i,pol,t,[p,s,f],story)
    for i,x in enumerate([20,30,40,60,70,80] if pilot else [15,25,35,45,55,65,75,85],1):
        for pol in ['pos','neg']:
            story=(f'A standardized process has a {x}% success rate.' if pol=='pos' else f'A standardized process has a {100-x}% failure rate.')+'\nWhat is the probability that the next independent trial achieves success (the positive target outcome)?'
            add('p2a','frame',i,pol,x,[x],story)
    for i,(p,l) in enumerate(opt[:6] if pilot else opt[6:],1):
        for facet,order in [('ord_abc',list('ABC')),('ord_cba',list('CBA'))]:
            story='Exactly one of sources A, B, C produced a sample. Evidence E is observed.\n'+'\n'.join(f'S{j}: Source {k}; prior {p["ABC".index(k)]}%; P(E | {k}) = {l["ABC".index(k)]}%.' for j,k in enumerate(order,1))+'\nEstimate the posterior probability of each source given E.'
            add('p2b','scen',i,facet,posterior(p,l),[p,l],story,order)
    random.Random(SEED).shuffle(units)
    return dict(stage=stage,seed=SEED,repeats=1 if pilot else 2,units=units,scheduled_calls=sum(len(u['prompts']) for u in units))
def main():
    for stage in ['pilot','formal']:
        b=banks(stage);dump(ROOT/f'bank_p2_{stage}.json',b)
        expected=624 if stage=='pilot' else 2560
        assert b['scheduled_calls']==expected
        print(f'PASS bank_{stage}: {len(b["units"])} units; {expected} calls; R={b["repeats"]}')
    dump(ROOT/'bank_p2_probe.json',dict(seed=SEED,ordered_22=EXPECTED_22,joint_candidates=[[20,50,30],[30,40,30],[40,35,25],[50,30,20],[60,25,15]],cases=['finish_gate_all_7_arms','nonnegative_finite_weights','soft_order_and_sum','canonical_inverse_mapping','top1_same_row_tie','classification_512','R2_framing_intervals','contrast_manski','double_facet_pp_65536','empty_pp']))
    print('PASS grids: 310 Bayesian triples; 30 three-option pairs; locked 22/22 order')
if __name__=='__main__':main()

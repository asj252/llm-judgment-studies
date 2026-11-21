"""Deterministic Rev 5 banks; reference: psych3/p1-narrative-baserate-20261105/prompts_p1.py."""
import json, itertools, sys
from fractions import Fraction
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))
from mcv_standard import ASK_MULTI
SEED = 20261110
ARMS = {"A00": (0,0), "A01": (0,1), "A10": (1,0), "A11": (1,1)}
SCENARIOS = ["ceramic microcracks", "alloy contamination", "optical coating defects", "battery seal faults", "polymer curing defects", "sensor calibration drift", "wafer lattice faults", "filter membrane defects", "catalyst degradation", "turbine blade fatigue", "laser alignment faults", "fiber connector defects", "crystal impurities", "weld porosity", "insulation breakdown", "fluid valve leakage", "mirror surface flaws", "composite delamination", "pump bearing defects", "microfluidic blockage", "thermal interface flaws", "antenna substrate faults", "resin inclusions", "acoustic transducer faults", "electrode coating flaws", "vacuum seal defects", "photonic coupling faults", "solder joint defects", "powder oxidation", "ceramic glaze flaws", "magnet winding faults", "waveguide defects", "spectrometer drift", "adhesive bond faults", "pressure vessel flaws", "nanopore defects", "robot encoder faults", "heat exchanger faults"]
FRAME_SCENARIOS = ["ceramic coating trial", "alloy casting trial", "optical alignment trial", "battery sealing trial", "polymer curing trial", "sensor calibration trial", "wafer fabrication trial", "membrane filtering trial", "catalyst processing trial", "turbine balancing trial", "laser tuning trial", "fiber coupling trial", "crystal growth trial", "weld qualification trial", "insulation testing trial", "valve endurance trial", "mirror polishing trial", "composite bonding trial"]
def dump(name, obj):
    (ROOT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
def counts(t):
    p,s,f=t; h=10*p; n=1000-h
    assert h*s%100==n*f%100==0
    tp=h*s//100; fp=n*f//100
    return [1000,h,n,tp,h-tp,fp,n-fp]
def truth(t, pol):
    p,s,f=(v/100 for v in t)
    if pol=="neg": s,f=1-s,1-f
    return 100*p*s/(p*s+(1-p)*f)
def collision_free(t):
    q=list(t)+counts(t)
    p,s,f=(Fraction(v,100) for v in t)
    ys=[100*p*s/(p*s+(1-p)*f),100*p*(1-s)/(p*(1-s)+(1-p)*(1-f))]
    return all(min(abs(y-c) for c in q)>2 and all(min(abs(y*m/100-c) for c in q)>Fraction(1,2) for m in (13,15,100)) for y in ys)
def triples():
    valid=[t for t in itertools.product([4,6,8,12,14,16,18,22,24,28,32,36,42],[65,70,75,80,85,90],[10,15,20,25,30]) if collision_free(t)]
    assert len(valid)==310
    selected=[valid[8*k] for k in range(38)]
    assert selected[0]==(4,65,10) and selected[-1]==(42,75,25)
    return valid,selected
def instruction(arm,m):
    p,a=ARMS[arm]
    # Reuse the standard elicitation semantics with exactly one factorial format block.
    # Fixed elicitation text avoids importing the standard block a second time.
    suffix="%" if m==100 else ""
    lines=([f"Initial Point: <number from 0 to {m}>{suffix}"] if p else [])
    lines += [f"Estimate {k}: <number from 0 to {m}>{suffix} | Weight: <number from 0 to 1>" for k in range(1,6)]
    return ("Estimate the probability of the target event using five plausible estimates and their relative weights. "
        f"Use output scale 0 to {m}, where {m} denotes certainty. Decimals and repeated values are allowed. "
        "Weights must be nonnegative and sum to one. Use the same posterior probability target for every estimate.\n"+
        ("First give an explicit initial point before the five estimates.\n" if p else "Do not output Initial Point. Every output line must begin with Estimate k:.\n")+
        ("List the five estimates in nondecreasing numerical order.\n" if a else "List estimates freely, without an ordering constraint.\n")+
        f"Replace each placeholder with an actual number in the specified range (values 0 to {m}, weights 0 to 1). "
        "Never output literal letters NN or W. Output this format block exactly once, with no second copy, explanations, headings, Markdown, or reasoning.\n"+
        "\n".join(lines))

def build(stage):
    _,ts=triples(); out=[]
    sections=[("A",0,6),("A",6,18),("B",18,22),("B",22,38)]
    for block,start,end in sections:
        if (stage=="pilot") != (start in (0,18)): continue
        for idx,t in enumerate(ts[start:end],1):
            cluster=f"bayes_{block}_{stage}_{idx:02d}"
            for pol in ("pos","neg"):
                n,h,nh,tp,fn,fp,tn=counts(t)
                truth_freq=100*(tp if pol=="pos" else fn)/((tp+fp) if pol=="pos" else (fn+tn))
                assert abs(truth(t,pol)-truth_freq)<1e-12
                for rep in (["pct"] if block=="A" else ["pct","freq"]):
                    label=SCENARIOS[start+idx-1]
                    if rep=="pct":
                        stem=f"A production population has {label} in {t[0]}% of units. A diagnostic returns positive for {t[1]}% of units with the fault and {t[2]}% of units without the fault."
                        nums=list(t)
                    else:
                        hit,fa=(tp,fp) if pol=="pos" else (fn,tn)
                        stem=f"In a production population of 1,000 units, {h} have {label} and {nh} do not. Among the {h} faulty units, {hit} return {('positive' if pol=='pos' else 'negative')}. Among the {nh} nonfaulty units, {fa} return {('positive' if pol=='pos' else 'negative')}."
                        nums=[1000,h,nh,hit,fa]
                    question=f"A randomly selected unit returns {('positive' if pol=='pos' else 'negative')}. What is the probability that this unit has the fault?"
                    for m,arm in ([(100,a) for a in ARMS] if block=="A" else [(m,"A11") for m in (13,15,100)]):
                        for r in range(1, (2 if stage=="formal" and block=="A" and idx<=6 else 1)+1):
                            cell=arm if block=="A" else f"M{m}_{rep}"
                            out.append(dict(cluster_id=cluster,unit_id=f"{cluster}_{pol}_{cell}_r{r}",block=block,task="bayes",stage=stage,polarity=pol,input_rep=rep,arm=arm,cell=cell,scale_M=m,rep_idx=r,parameters=t,truth_pct=truth(t,pol),question=question,cues_semantic_pct=list(t),cues_literal_num=nums,cues_literal_str=sorted(set(str(v) for v in nums)),prompt_text=stem+"\n"+question+"\n\n"+instruction(arm,m)))
    xs=[18,28,40,60,72,84] if stage=="pilot" else [16,24,36,56,68,80,22,32,44,64,76,88]
    for idx,x in enumerate(xs,1):
        cluster=f"frame_A_{stage}_{idx:02d}"
        label=FRAME_SCENARIOS[idx-1+(0 if stage=="pilot" else 6)]
        question="What is the probability that this scheme succeeds in the next independent trial?"
        for pol in ("pos","neg"):
            cue=x if pol=="pos" else 100-x
            stem=f"For the {label}, historical records show a {cue}% {('success' if pol=='pos' else 'failure')} rate under the same conditions."
            for arm in ARMS:
                for r in range(1,(2 if stage=="formal" and idx<=6 else 1)+1):
                    out.append(dict(cluster_id=cluster,unit_id=f"{cluster}_{pol}_{arm}_r{r}",block="A",task="framing",stage=stage,polarity=pol,input_rep="pct",arm=arm,cell=arm,scale_M=100,rep_idx=r,truth_pct=x,question=question,cues_semantic_pct=[cue],cues_literal_num=[cue],cues_literal_str=[str(cue)],prompt_text=stem+"\n"+question+"\n\n"+instruction(arm,100)))
    assert len(out)==(144 if stage=="pilot" else 480)
    assert len({u['unit_id'] for u in out})==len(out)
    return out
def main():
    pilot,formal=build("pilot"),build("formal")
    assert not {u['cluster_id'] for u in pilot}&{u['cluster_id'] for u in formal}
    assert not {u['unit_id'] for u in pilot}&{u['unit_id'] for u in formal}
    for stage,bank in [("pilot",pilot),("formal",formal)]:
        assert min(min(u['cues_literal_num']) for u in bank if u['block']=="B" and u['input_rep']=="freq")== (18 if stage=="pilot" else 22)
        dump(f"bank_{stage}.json",bank)
    print("PASS banks: VALID_TRIPLES=310 SELECTED_38=38 pilot=144 formal=480; zero shared clusters/units; exact frequencies, posterior equivalence and dual-coordinate constraints")
if __name__=="__main__": main()

"""Pilot runner; formal requires externally audited freeze and Git handoff."""
import argparse, json, math, os, random, re, sys, time, urllib.request, urllib.error, hashlib, socket
from datetime import datetime, timezone
from pathlib import Path
from build_banks import ROOT, SEED, dump, build
sys.path.insert(0,str(ROOT.parents[1]))
from mcv_standard import parse_multi
MODELS={
 "sf:qwen3-8b": ("https://api.siliconflow.cn/v1/chat/completions","SILICONFLOW_API_KEY","Qwen/Qwen3-8B",0.25),
 "aistudio:gemma-4-26b-a4b-it": ("https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent","GEMINI_API_KEY","gemma-4-26b-a4b-it",0.5),
 "nv:nemotron-3.5-super-vl-120b": ("https://integrate.api.nvidia.com/v1/chat/completions","NVIDIA_API_KEY","nvidia/nemotron-3.5-super-vl-120b-a12b",0.3),
 "xf:spark-x2.6": ("https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions","XF_MAAS_API_KEY","spark-x2.6",0.25)}
NUM=r"[+-]?(?:[0-9]+(?:,[0-9]{3})*(?:\.[0-9]*)?|\.[0-9]+)"
EST=re.compile(r"^\s*Estimate\s+(\d+):\s*("+NUM+r")\s*%?\s*\|\s*Weight:\s*("+NUM+r")\s*$",re.M|re.I)
INIT=re.compile(r"^\s*Initial Point:\s*("+NUM+r")\s*%?\s*$",re.M|re.I)
def normalize_stop(raw):
    if raw in {"length","MAX_TOKENS","max_tokens","MODEL_LENGTH"}: return "length_truncated"
    if raw in {"stop","STOP","end_turn"}: return "completed"
    return "unknown_or_other"
def parse(text,u):
    m=u['scale_M']; rows=EST.findall(text); initials=INIT.findall(text)
    failure=lambda reason: dict(parse_ok=False,fail_reason=reason)
    # Count every candidate label, including malformed or duplicated rows.
    if len(rows)!=5 or len(re.findall(r"Estimate\s+\d+\s*:",text,re.I))!=5 or [int(r[0]) for r in rows]!=list(range(1,6)): return failure("five_candidates_incomplete")
    vals=[float(v.replace(',','')) for _,v,_ in rows]; ws=[float(w.replace(',','')) for _,_,w in rows]
    if any(not math.isfinite(v) or not 0<=v<=m for v in vals) or any(not math.isfinite(w) or w<0 for w in ws) or sum(ws)<=0: return failure("range_or_weights")
    init=None
    if u['arm'] in ('A10','A11'):
        if len(initials)!=1: return failure("initial_point_missing_or_duplicate")
        init=float(initials[0].replace(',',''))
        if not 0<=init<=m: return failure("initial_point_range")
        if text.find('Initial Point')>text.find('Estimate'): return failure("initial_point_not_first")
    canonical="\n".join(f"Estimate {k}: {100*v/m:.15g}% | Weight: {w:.15g}" for k,(v,w) in enumerate(zip(vals,[w/sum(ws) for w in ws]),1))
    result=parse_multi(canonical)
    if not result['ok']: return failure(result['error'])
    asc=all(y>=x-1e-9 for x,y in zip(vals,vals[1:]))
    result.update(parse_ok=True,fail_reason=None,raw_values=vals,value_strings=[v.replace(',','') for _,v,_ in rows],initial_value_string=initials[0].replace(',','') if init is not None else None,initial_point_pct=None if init is None else 100*init/m,initial_point_raw=init,weights_norm=result['normalized_weights'],five_candidates_complete=True,has_explicit_initial_point=init is not None,ascending_compliant=asc,ascending_violation=u['arm'] in ('A01','A11') and not asc,all_candidates_identical=max(vals)-min(vals)<=1e-9,non_integer_cand_rate=sum(abs(v-round(v))>1e-9 for v in vals)/5)
    return result
def detectors(p,u):
    sem=u['cues_semantic_pct']; lit=u['cues_literal_num']; m=u['scale_M']; out={}
    for readout in ('m_w','m_u','top1'):
        pct=p[readout]; raw=pct*m/100
        d={f'D{i}': min(abs(pct-c) for c in sem)<=tol for i,tol in enumerate((.5,.75,1.,1.5),1)}
        d.update(D0=min(abs(pct-c) for c in sem)<=.75 or (m!=100 and any(c<=m and abs(raw-c)<=.25 for c in lit)),D5a=any(abs(raw-c)<=1e-6 for c in lit),D5b=m!=100 and any(abs(raw-c)<=.25 for c in lit),D5b_allM=any(abs(raw-c)<=.25 for c in lit))
        out[readout]=d
    vals=p['raw_values']+([] if p['initial_point_raw'] is None else [p['initial_point_raw']])
    strings=p['value_strings']+([] if p['initial_value_string'] is None else [p['initial_value_string']])
    out.update(Echo_D2=out['m_w']['D2'],cand_D5a_any=any(abs(x-c)<=1e-6 for x in vals for c in lit),cand_D2_any=any(abs(x*100/m-c)<=.75 for x in p['raw_values'] for c in sem),cand_str_copy_any=bool(set(strings)&set(u['cues_literal_str'])),grid_dist_M=min(abs(c-100*k/m) for c in sem for k in range(m+1)),non_integer_cand_rate=p['non_integer_cand_rate'])
    return out
def call(model,prompt):
    url,key,api,_=MODELS[model]; token=os.environ.get(key,'')
    if not token: raise RuntimeError('missing_key:'+key)
    headers={'Content-Type':'application/json','User-Agent':'psych3-p1/1'}
    if model.startswith('aistudio:'):
        headers['x-goog-api-key']=token
        payload={'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':{'temperature':.7,'topP':.95,'maxOutputTokens':2048,'thinkingConfig':{'thinkingLevel':'MINIMAL'}}}
    else:
        headers['Authorization']='Bearer '+token
        payload={'model':api,'messages':[{'role':'user','content':prompt}],'temperature':.7,'top_p':.95,'max_tokens':2048}
        if model.startswith(('sf:','xf:')): payload['enable_thinking']=False
        if model.startswith('nv:'): payload['chat_template_kwargs']={'enable_thinking':False}
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=headers,method='POST')
    transport_retries=[]
    delays=(2,4,8,12,18,25)
    for transport_idx in range(7):
        try:
            with urllib.request.urlopen(req,timeout=90) as resp: body=json.loads(resp.read().decode('utf-8'))
            break
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            status=exc.code if isinstance(exc,urllib.error.HTTPError) else None
            retryable=((status==429 or 500<=status<600) if status else True)
            if not retryable or transport_idx==6:
                exc.transport_retries=transport_retries
                raise
            delay=delays[transport_idx]
            transport_retries.append(dict(retry_idx=transport_idx+1,http_status=status,error_type=type(exc).__name__,backoff_seconds=delay))
            time.sleep(delay)
    if model.startswith('aistudio:'):
        c=body.get('candidates',[{}])[0]
        return '\n'.join(p.get('text','') for p in c.get('content',{}).get('parts',[]) if not p.get('thought')),c.get('finishReason'),body.get('usageMetadata',{}),body.get('modelVersion',api),transport_retries
    c=body['choices'][0]
    return c['message'].get('content') or '',c.get('finish_reason'),body.get('usage',{}),body.get('model',api),transport_retries
def tag(model): return re.sub(r'[^a-zA-Z0-9]+','_',model)
def selftest():
    from analyze_p1_factorial import selftest as analyze_test
    probe=[]
    u=dict(build('pilot')[0],arm='A11',cues_semantic_pct=[15],cues_literal_num=[15],cues_literal_str=['15'])
    def text(vals,init='15',weights=None):
        return f"Initial Point: {init}%\n"+'\n'.join(f"Estimate {k}: {v}% | Weight: {(weights or [0.2]*len(vals))[k-1]}" for k,v in enumerate(vals,1))
    def check(name,t,ok,unit=None,**expected):
        un=unit or u; p=parse(t,un); assert p['parse_ok']==ok,(name,p)
        d=detectors(p,un) if ok else {}
        for k,v in expected.items(): assert d.get(k,p.get(k))==v,(name,k,d,p)
        probe.append(dict(name=name,prompt_text=un['prompt_text'],raw_text=t,expected_parse_ok=ok,expected=expected))
    for n in (1,4,6): check(f'candidate_count_{n}',text([10]*n),False)
    check('five_identical',text([15]*5),True,all_candidates_identical=True,cand_str_copy_any=True)
    check('missing_initial',text([15]*5).split('\n',1)[1],False)
    check('nonidentical_zero_weight',text([10,20,30,40,50],weights=[1,0,0,0,0]),True,all_candidates_identical=False)
    check('ascending_violation',text([50,40,30,20,10]),True,ascending_violation=True)
    check('out_of_range',text([101]*5),False)
    check('numerical_not_string',text(['15.0']*5,init='15.00'),True,cand_D5a_any=True,cand_str_copy_any=False)
    check('explanation_only','The cue is 15.\n'+text([10]*5,init='10'),True,cand_str_copy_any=False)
    check('weight_and_index_only',text([10]*5,init='10',weights=[15,0,0,0,0]),True,cand_str_copy_any=False)
    check('mean_only',text([5,10,12,18,25],init='5'),True,unit=dict(u,cues_literal_num=[14],cues_literal_str=['14'],cues_semantic_pct=[14]),cand_D5a_any=False,cand_str_copy_any=False,Echo_D2=True)
    check('M100_D5b_switch',text([15]*5),True)
    assert detectors(parse(text([15]*5),u),u)['m_w']['D5b'] is False
    for raw in ('length','MAX_TOKENS','max_tokens','MODEL_LENGTH'): assert normalize_stop(raw)=='length_truncated'
    for raw in ('stop','STOP','end_turn'): assert normalize_stop(raw)=='completed'
    assert normalize_stop(None)=='unknown_or_other'
    analyze_test()
    probe += [dict(name='Framing_R2_failure',prompt_text='',pos=[100,None],neg=[0,100],expected_bounds=[0,50]),dict(name='DiD_all_missing',prompt_text='',coefficients=[1,-1,-1,1],lower=[0]*4,upper=[100]*4,expected_bounds=[-200,200]),dict(name='stop_mapping',prompt_text='',raw=['length','MAX_TOKENS','max_tokens','MODEL_LENGTH'],expected='length_truncated'),dict(name='PP_polarity_and_model',prompt_text='',rule='Both polarities need nonempty shared repeats across every cell; pooled PP intersects all four models'),dict(name='binary_missing',prompt_text='',ITT_fail_as_1=100,fail_as_0=0,bounds=[0,100])]
    dump('bank_probe.json',probe)
    print('PASS parser/detectors: counts 1/4/5/6, initial point, repeat, weights, ascending, bounds, strings vs numbers, field isolation, mean-only, D5b, MAX_TOKENS')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--self-test',action='store_true'); ap.add_argument('--model',choices=MODELS); ap.add_argument('--stage',choices=['pilot','formal'],default='pilot'); ap.add_argument('--formal-authorized',action='store_true',help='External dispatcher only: c audit passed and a Git handoff completed'); args=ap.parse_args()
    if args.self_test: selftest(); return
    if not args.model: ap.error('--model required')
    if args.stage=='formal':
        if not args.formal_authorized: raise SystemExit('External c Freeze audit and a Git handoff required')
        freeze=json.loads((ROOT/'analysis_freeze.json').read_text(encoding='utf-8'))
        if not freeze['pilot_gates_pass'] or not freeze['drive_archive_complete']: raise SystemExit('Pilot/Drive gate failed')
        for group in ('execution_dependencies','reference_only_provenance','artifacts'):
            for path,digest in freeze[group].items():
                if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest: raise SystemExit('Freeze mismatch: '+path)
    # Fill missing credentials only; never print or overwrite injected values.
    keyfile=Path(os.environ.get("KEYS_ENV_FILE", ""))
    if os.environ.get("KEYS_ENV_FILE") and keyfile.is_file():
        import shlex
        for line in keyfile.read_text(encoding='utf-8').splitlines():
            line=line.strip().removeprefix('export ')
            if not line or line.startswith('#') or '=' not in line: continue
            name,value=line.split('=',1)
            if name.strip() not in {v[1] for v in MODELS.values()}: continue
            parts=shlex.split(value,comments=True)
            if parts: os.environ.setdefault(name.strip(),parts[0])
    execution_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'run_p1_factorial.py',ROOT/'build_banks.py',ROOT/f'bank_{args.stage}.json',ROOT.parents[1]/'mcv_standard.py']}
    units=json.loads((ROOT/f'bank_{args.stage}.json').read_text(encoding='utf-8')); random.Random(SEED).shuffle(units)
    dest=ROOT/'results'/f'{args.stage}_{tag(args.model)}.jsonl'; dest.parent.mkdir(exist_ok=True)
    done=set()
    if dest.exists():
        for line in dest.read_text(encoding='utf-8').splitlines(): done.add(json.loads(line)['unit_id'])
    for u in units:
        if u['unit_id'] in done: continue
        attempts=[]; parsed={'parse_ok':False}; response_model=None
        for idx in range(1,5):
            start=time.monotonic(); raw=''; finish=None; usage={}; error=None; status=None; transport_retries=[]
            try: raw,finish,usage,response_model,transport_retries=call(args.model,u['prompt_text']); status=200
            except urllib.error.HTTPError as e: error=f'HTTP_{e.code}'; status=e.code; transport_retries=getattr(e,'transport_retries',[])
            except Exception as e: error=type(e).__name__; transport_retries=getattr(e,'transport_retries',[])
            stop=normalize_stop(finish); parsed=parse(raw,u)
            if stop!='completed': parsed={'parse_ok':False,'fail_reason':stop}
            attempts.append(dict(attempt_idx=idx,transport_retries=transport_retries,error_type=error,http_status=status,finish_reason_raw=finish,normalized_stop_reason=stop,usage=usage,latency_ms=round((time.monotonic()-start)*1000,3),raw_text=raw,parse_ok=parsed['parse_ok'],fail_reason=parsed.get('fail_reason'),timestamp_utc=datetime.now(timezone.utc).isoformat()))
            if parsed['parse_ok']: break
            time.sleep(min(30,2**idx))
        record=dict(u,execution_sha256=execution_sha256,sampling_config={'max_tokens':2048,'temperature':.7,'top_p':.95,'max_attempts':4},model=args.model,response_model=response_model,timestamp_utc=datetime.now(timezone.utc).isoformat(),job_id=os.environ.get('P1_JOB_ID'),attempts_log=attempts,normalized_stop_reason=attempts[-1]['normalized_stop_reason'],parsed=parsed,parse_ok=parsed['parse_ok'],metrics=detectors(parsed,u) if parsed['parse_ok'] else None)
        with dest.open('a',encoding='utf-8') as f: f.write(json.dumps(record,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
        print(json.dumps({'completed':len(done)+1,'unit_id':u['unit_id'],'parse_ok':parsed['parse_ok']}),flush=True); done.add(u['unit_id'])
        time.sleep(MODELS[args.model][3])
if __name__=='__main__': main()

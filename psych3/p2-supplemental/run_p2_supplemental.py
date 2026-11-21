#!/usr/bin/env python3
"""Patrol worker. Durable attempt records; retries never become independent replicates."""
import argparse, json, os, re, math, sys, time, socket, urllib.request, urllib.error, hashlib, subprocess, shlex
sys.dont_write_bytecode = True
from pathlib import Path
from build_p2_banks import ROOT, REPO, A_ARMS, B_ARMS, load, dump
from mcv_standard import parse_direct, parse_multi, parse_joint_multi, strip_thinking
PARAMS=dict(max_tokens=2048,temperature=.7,top_p=.95,max_attempts=4,B=10000,seed=20261110)
BACKOFF=[2,4,8,12,18,25]
PACE={'sf':0.25,'aistudio':0.35,'nv':0.25,'xf':0.25}
KEYS=Path(os.environ.get("KEYS_ENV_FILE", ""))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def slug(model):return model.replace(':','_').replace('/','_')
def result_path(stage,study,model):return ROOT/'results'/f'{stage}_{study}_{slug(model)}.jsonl'
def records(path):
    if not path.exists():return []
    return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
def finish(raw):
    if raw in ['stop','STOP','end_turn']:return 'STOP'
    if raw in ['length','MAX_TOKENS','max_tokens']:return 'MAX_TOKENS'
    return 'OTHER'
def parse(text,arm,order=None,reason='STOP'):
    out=dict(call_parse_ok=False,finish_reason=reason,is_truncated=reason=='MAX_TOKENS',is_unknown_finish=reason=='OTHER')
    if reason!='STOP':return out
    final,err=strip_thinking(text)
    if err:return dict(out,error=err)
    if arm in A_ARMS[:2]:
        p=parse_direct(final)
        if p['ok']:out.update(call_parse_ok=True,m_w=p['value'],m_u=p['value'],top1=p['value'])
        return dict(out,parsed=p)
    joint=arm in B_ARMS[:2]
    clean=[re.sub(r'[*_]', '',l).strip() for l in final.splitlines()]
    init=[l for l in clean if l.lower().startswith('initial point:')]
    if len(init)!=1:return dict(out,error='initial_point_count')
    num=r'([-+]?(?:\d+(?:\.\d+)?|\.\d+))'
    pat=(rf'Initial Point:\s*S1\s*{num}%\s*\|\s*S2\s*{num}%\s*\|\s*S3\s*{num}%' if joint else rf'Initial Point:\s*{num}%')
    m=re.fullmatch(pat,init[0],re.I)
    if not m or any(not 0<=float(x)<=100 for x in m.groups()):return dict(out,error='invalid_initial_point')
    lines=[l for l in clean if re.match(r'Estimate\s+\d',l,re.I)]
    if len(lines)!=5:return dict(out,error='candidate_count')
    if arm==A_ARMS[2]:
        # Canonical parser supplies readouts; append synthetic equal weights only after strict unweighted validation.
        pp=[re.fullmatch(rf'Estimate\s+(\d):\s*{num}%',l,re.I) for l in lines]
        if any(x is None for x in pp):return dict(out,error='invalid_unweighted_row')
        lines=[l+' | Weight: 0.2' for l in lines]
    else:
        # Canonical v2 uses [0,1]; protocol permits any nonnegative finite weights. Normalize before delegation.
        ws=[]
        for l in lines:
            w=re.search(rf'\|\s*Weight:\s*{num}\s*$',l,re.I)
            if not w:return dict(out,error='invalid_weight')
            ws.append(float(w[1]))
        if any(not math.isfinite(w) or w<0 for w in ws) or sum(ws)<=0:return dict(out,error='weight_sum')
        lines=[re.sub(r'(Weight:\s*).*$',lambda m:m[1]+str(w/sum(ws)),l,flags=re.I) for l,w in zip(lines,ws)]
    p=parse_joint_multi('\n'.join(lines),order) if joint else parse_multi('\n'.join(lines))
    if not p['ok']:return dict(out,parsed=p)
    vals=p['estimates'][order[0]] if joint else p['estimates']
    w=p['weights'];out.update(call_parse_ok=True,parsed=p,initial_point=[float(x) for x in m.groups()],order_violation=any(b<a for a,b in zip(vals,vals[1:])),top1_weight_tie=w.count(max(w))>1)
    for key in ['m_w','m_u','top1','weighted_sd','unweighted_sd']:out[key]=p[key]
    if joint:
        bad=[abs(v-100)>1 for v in p['row_sums']]
        out.update(sum100_violation=any(bad),sum100_violation_rate=sum(bad)/5)
    return out
def load_keys():
    if os.environ.get("KEYS_ENV_FILE") and KEYS.is_file():
        for line in KEYS.read_text(encoding='utf-8').splitlines():
            line=line.strip().removeprefix('export ')
            if not line or line.startswith('#') or '=' not in line:continue
            k,v=line.split('=',1)
            if k in ['SILICONFLOW_API_KEY','GEMINI_API_KEY','NVIDIA_API_KEY','XF_MAAS_API_KEY','GROQ_API_KEY']:
                parts=shlex.split(v,comments=True)
                if parts:os.environ.setdefault(k,parts[0])
def request_spec(model,prompt):
    provider,name=model.split(':',1)
    if provider=='aistudio':
        return ('https://generativelanguage.googleapis.com/v1beta/models/'+name+':generateContent',{'x-goog-api-key':os.environ['GEMINI_API_KEY']},dict(contents=[dict(role='user',parts=[dict(text=prompt)])],generationConfig=dict(temperature=.7,topP=.95,maxOutputTokens=2048,thinkingConfig=dict(thinkingLevel='MINIMAL'))))
    config={
      'sf':('https://api.siliconflow.cn/v1/chat/completions','SILICONFLOW_API_KEY','Qwen/Qwen3-8B'),
      'nv':('https://integrate.api.nvidia.com/v1/chat/completions','NVIDIA_API_KEY','nvidia/nemotron-3.5-super-vl-120b-a12b'),
      'xf':('https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions','XF_MAAS_API_KEY','spark-x2.6'),
      'groq':('https://api.groq.com/openai/v1/chat/completions','GROQ_API_KEY','openai/gpt-oss-120b')}
    url,key,api=config[provider]
    body=dict(model=api,messages=[dict(role='user',content=prompt)],max_tokens=2048,temperature=.7,top_p=.95)
    if provider in ['sf','xf']:body['enable_thinking']=False
    if provider=='nv':body['chat_template_kwargs']=dict(enable_thinking=False)
    if provider=='groq':body['reasoning_effort']='medium'
    return url,{'Authorization':'Bearer '+os.environ[key]},body
def api_call(model,prompt):
    url,headers,body=request_spec(model,prompt);events=[];start=time.monotonic()
    for t in range(7):
        try:
            req=urllib.request.Request(url,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),headers=dict(headers,**{'Content-Type':'application/json','User-Agent':'Mozilla/5.0'}))
            with urllib.request.urlopen(req,timeout=120) as resp:data=json.loads(resp.read().decode('utf-8'))
            if model.startswith('aistudio:'):
                c=data.get('candidates',[{}])[0];parts=c.get('content',{}).get('parts',[])
                text=''.join(p.get('text','') for p in parts if not p.get('thought'));reasoning=''.join(p.get('text','') for p in parts if p.get('thought'))
                raw=c.get('finishReason');tokens=data.get('usageMetadata',{}).get('candidatesTokenCount',0)
            else:
                c=data['choices'][0];msg=c['message'];text=msg.get('content') or '';reasoning=msg.get('reasoning_content') or msg.get('reasoning') or '';raw=c.get('finish_reason');tokens=data.get('usage',{}).get('completion_tokens',0)
            return dict(text=text,reasoning_char_len=len(reasoning)+sum(len(v) for v in re.findall(r'<think>(.*?)</think>',text,re.S)),completion_tokens=tokens,raw_finish_reason=raw,finish_reason=finish(raw),latency_ms=1000*(time.monotonic()-start),transport_events=events)
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,socket.timeout) as e:
            code=getattr(e,'code',None);retry=code==429 or (code is not None and 500<=code<=599) or isinstance(e,(urllib.error.URLError,TimeoutError,socket.timeout)) and code is None
            events.append(dict(transport_idx=t+1,http_status=code,error_type=type(e).__name__))
            if not retry or t==6: return dict(text='',finish_reason='OTHER',raw_finish_reason=None,completion_tokens=0,reasoning_char_len=0,latency_ms=1000*(time.monotonic()-start),transport_events=events,error=type(e).__name__)
            time.sleep(BACKOFF[t])
def verify_freeze():
    f=load(ROOT/'analysis_freeze.json')
    for group in ['execution_dependencies','bank_files','reference_only_provenance','stage1_artifacts']:
        for path,digest in f[group].items():
            if sha(REPO/path)!=digest:raise RuntimeError('freeze hash mismatch: '+path)
    receipt=load(ROOT/'stage2_release_authorization.json')
    if receipt.get('c_freeze_verdict')!='PASS' or receipt.get('analysis_freeze_sha256')!=sha(ROOT/'analysis_freeze.json'):raise RuntimeError('No c Freeze PASS')
    commit=receipt['a_commit']
    actual=subprocess.check_output(['git','show',f'{commit}:connecting-dots/psych3/p2-supplemental-20261110/analysis_freeze.json'])
    if hashlib.sha256(actual).hexdigest()!=sha(ROOT/'analysis_freeze.json'):raise RuntimeError('a commit does not contain this freeze')
def run(stage,study,model):
    if stage=='formal':verify_freeze()
    load_keys();bank=load(ROOT/f'bank_p2_{stage}.json');path=result_path(stage,study,model);path.parent.mkdir(exist_ok=True)
    old=records(path);done={r['call_id'] for r in old if r['call_parse_ok'] or r['attempt_idx']==4}
    latest={r['call_id']:r['attempt_idx'] for r in old}
    pace=PACE[model.split(':',1)[0]]
    for u in bank['units']:
        if u['study']!=study or u['model']!=model:continue
        for sub,prompt in enumerate(u['prompts']):
            cid=u['unit_id']+f'/sub{sub}'
            if cid in done:continue
            for attempt in range(latest.get(cid,0)+1,5):
                raw=api_call(model,prompt);p=parse(raw['text'],u['arm'],u['order'],raw['finish_reason'])
                row=dict(unit_id=u['unit_id'],call_id=cid,sub_idx=sub,attempt_idx=attempt,model=model,arm=u['arm'],**raw,parse=p,call_parse_ok=p['call_parse_ok'])
                with path.open('a',encoding='utf-8') as out:out.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');out.flush();os.fsync(out.fileno())
                print(cid,attempt,p['call_parse_ok'],raw['finish_reason'],flush=True)
                time.sleep(pace)
                if p['call_parse_ok']:break
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['pilot','formal'],default='pilot');ap.add_argument('--study',choices=['p2a','p2b']);ap.add_argument('--model');ap.add_argument('--self-test',action='store_true');args=ap.parse_args()
    if args.self_test:
        from check_p2_stage1 import self_test
        self_test()
    else:
        if not args.study or not args.model:ap.error('--study and --model required')
        run(args.stage,args.study,args.model)

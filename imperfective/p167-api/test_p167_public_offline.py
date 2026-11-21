"""Public offline tests; third-party data is never copied into the release."""
import sys
sys.dont_write_bytecode=True
import hashlib, json, math, shutil, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import stimuli_p167 as s
import addendum_openai_p167 as a
import api_adapter_p167 as api
from configs_p167 import CONFIGS
from run_p167_slice import parse_record, synthetic_response
from analyze_p167 import analyze
ROOT=s.ROOT.parent
def snapshot(root):
    return {str(p.relative_to(root)):(p.is_dir(),p.stat().st_mtime_ns,None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob('*')}
class PublicOffline(unittest.TestCase):
    def test_real_tree_fail_closed(self):
        before=snapshot(ROOT); found=[]; missing=[]
        try:
            for rel,h in s.UPSTREAM.items():
                p=s.resolve_upstream(rel)
                if p.exists():
                    self.assertEqual(s.sha256(p),h); found.append(rel)
                    if p.suffix=='.json': self.assertEqual(s.read_json(rel),json.loads(p.read_text(encoding='utf-8')))
                else: missing.append(Path(rel).name)
            self.assertEqual(len(found),27)
            self.assertEqual(set(missing),{'imperfectiveNLI.json','clusters_100_e3.json','run_inference.py.txt'})
            for fn in [s.verify_upstream,s.upstream_modules,a.ensure_upstream_files]:
                with self.assertRaises((FileNotFoundError,ValueError)): fn()
        finally: self.assertEqual(before,snapshot(ROOT))
    def test_fixture_import_and_synthetic_analysis(self):
        before=snapshot(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); imp=root/'imperfective'; imp.mkdir()
            hashes={}
            for rel in s.UPSTREAM:
                folder=rel.split('/')[0]
                dst=imp/rel if folder=='exp1-en' else root/('imperfective-'+folder)/rel
                dst.parent.mkdir(parents=True,exist_ok=True)
                orig=s.resolve_upstream(rel)
                dst.write_bytes(orig.read_bytes() if orig.exists() else b'[]\n')
                hashes[rel]=s.sha256(dst)
            common=imp/'exp1-en/common.py'; common.write_bytes(s.resolve_upstream('exp1-en/common.py').read_bytes())
            with patch.object(s,'ROOT',imp),patch.object(s,'UPSTREAM',hashes):
                s.upstream_modules.cache_clear()
                mods=s.upstream_modules()
                self.assertTrue({'e1','e2','e3','e4','parse','core_e2','core_e3','core_e4'}<=mods.keys())
                # E2/E4 are author-created banks; E3/E1 synthetic units avoid third-party stimuli.
                units=s.build_slice('slice_e2')+s.build_slice('slice_e4')
                parser=mods['parse']
                for text,prompt in [('True','Z'),('<think>False</think>True','Z'),('{"reasoning":"x","label":"True"}','CoT')]:
                    row=parse_record(dict(task='L',prompt=prompt),'fixture',dict(text=text,truncated=False))
                    self.assertEqual(row['status'],'ok'); self.assertEqual(row['label'],'True')
                row=parse_record(dict(task='L',prompt='Z'),'fixture',dict(text='<think>True',truncated=False))
                self.assertEqual(row['status'],'missing_format')
                for cfg in CONFIGS.values():
                    payload=api.build_request_payload(cfg,[{'role':'user','content':'fixture'}])
                    self.assertTrue(payload)
                cfg=a.ADDENDUM_CONFIGS['openai:gpt-4o-mini']
                self.assertEqual(a.build_addendum_payload(cfg,[])['top_logprobs'],20)
                self.assertEqual(api.parse_api_response('cloudflare',{'result':{'response':'True'}})['text'],'True')
                lp={'content':[{'token':'True','logprob':math.log(.6),'top_logprobs':[{'token':k,'logprob':math.log(v)} for k,v in [('True',.6),('False',.2),('Unknown',.1)]]}]}
                row=parse_record(dict(task='L',prompt='Z'),'fixture',dict(text='True',logprobs=lp))
                self.assertAlmostEqual(row['logprob_metrics']['q_true_lower'],.6)
                self.assertAlmostEqual(row['logprob_metrics']['q_true_upper'],.7)
                rows=[]
                for u in units: rows.append(dict(parse_record(u,'fixture',synthetic_response(u)),dry_run=True))
                self.assertEqual(len(rows),640)
                self.assertTrue(all(x['status']=='ok' for x in rows))
                path=root/'synthetic.jsonl'; path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
                with patch('analyze_p167.build_slice',return_value=units):
                    summary=analyze([path])
                for exp,expected in [('E2',{'E2_H1':20,'E2_H2':20,'E2_H3':30,'E2_H4':1}),('E4',{'E4_H1':60,'E4_H2':40,'E4_H3':40,'E4_H4':1})]:
                    for slot,point in expected.items():
                        self.assertEqual(summary['engines'][exp]['missing_units'][slot],0)
                        self.assertAlmostEqual(summary['engines'][exp]['primary_family']['slots'][slot]['point_lower'],point)
                json.dumps(summary,allow_nan=False)
                s.upstream_modules.cache_clear()
        self.assertEqual(before,snapshot(ROOT))
if __name__=='__main__': unittest.main(verbosity=2)

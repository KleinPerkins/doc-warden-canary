#!/usr/bin/env python3
"""Closed canary source-suite dispatcher and exact-run CI aggregation; no host install."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHARDS = ('engine-positive', 'engine-negative', 'delivery-contracts')
IDENTITY_KEYS = ('repository','repository_id','event','revision','workflow_sha','run_id',
                 'run_attempt','ref','head_sha','base_sha','workflow_ref','workflow')
NAMES = ('KleinPerkins/doc-warden-canary',)
MAX_OUTPUT = 8 * 1024 * 1024
class ContractError(ValueError): pass
def require(ok, reason):
    if not ok: raise ContractError(reason)
def digest(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def closed(value, fields):
    require(isinstance(value,dict) and set(value)==set(fields.split()),'closed schema fields differ')
def parse(raw):
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique)
def policy(root=ROOT):
    raw=(root/'.github/ci-contract.json').read_bytes(); c=parse(raw)
    closed(c,'schema repository_id repository_names workflow workflow_name required_check actions_app_id reviewer_app_id shards commands baseline_tests host_only allowed_skip_reasons nonpassing_runtime_cases owner_source')
    require(c['schema']=='doc-warden-canary-ci-contract/v1' and type(c['repository_id']) is int and c['repository_id']==1324068071,'CI identity')
    require(c['repository_names']==list(NAMES) and c['shards']==list(SHARDS),'CI phases/shards')
    require((c['workflow'],c['workflow_name'],c['required_check'],c['actions_app_id'],c['reviewer_app_id'])==('.github/workflows/ci.yml','CI','ci-required',15368,4217367),'CI producer/workflow')
    require(c['owner_source']=={'repository':'KleinPerkins/dev','revision':'d57009cb004d404adf9daa5a374a1c2b37b8288e'},'owner source drift')
    require(c['commands']=={s:[] for s in SHARDS} and c['allowed_skip_reasons']==[] and c['nonpassing_runtime_cases']==[],'unknown command/skip policy')
    mraw=(root/'.github/test-shards.json').read_bytes();m=parse(mraw)
    closed(m,'schema state aggregate discovery shards')
    require(m['schema']=='doc-warden-canary-test-sharding/v1' and m['state']=='configured' and m['aggregate']=='ci-required','sharding not configured')
    require(m['discovery']=={'include':['tests/test_*.py'],'exclude':[]},'test discovery changed')
    require([s['id'] for s in m['shards']]==list(SHARDS),'shard topology differs')
    members=[]
    for row in m['shards']:
        closed(row,'id tests command timeout_seconds')
        require(row['command']==['python3','-I','-B','scripts/verify.py','local','--shard',row['id']],'shard dispatcher differs')
        require(type(row['timeout_seconds']) is int and 1<=row['timeout_seconds']<=300,'timeout bound')
        require(isinstance(row['tests'],list) and row['tests'] and row['tests']==sorted(set(row['tests'])),'missing/duplicate/unsorted tests')
        members+=row['tests']
    require(len(members)==len(set(members)),'duplicate test ownership')
    discovered={str(p.relative_to(root)) for p in root.glob('tests/test_*.py') if p.is_file()}
    require(set(members)==discovered,'test inventory differs from actual source')
    require(c['baseline_tests']==[{'path':p,'owner_shard':row['id']} for row in m['shards'] for p in row['tests']],'test coverage removed/reassigned')
    for p in members:
        target=root/p
        require(not target.is_symlink() and all(not a.is_symlink() for a in target.parents if a!=root.parent),'symlink test path')
    return c,m,digest(raw+b'\0'+mraw)
def identity(environment):
    names=('GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_EVENT_NAME','GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REF','CI_HEAD_SHA','CI_BASE_SHA','GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW')
    v={k:environment.get(n,'') for k,n in zip(IDENTITY_KEYS,names)}
    require(v['repository'] in NAMES and v['repository_id']=='1324068071','wrong repository phase/ID')
    require(v['event'] in ('push','pull_request','workflow_dispatch'),'unsupported CI event')
    for k in ('revision','workflow_sha'):require(re.fullmatch('[0-9a-f]{40}',v[k]),'invalid '+k)
    for k in ('run_id','run_attempt'):require(re.fullmatch('[1-9][0-9]*',v[k]),'invalid '+k)
    if v['event']=='pull_request':
        require(re.fullmatch(r'refs/pull/[1-9][0-9]*/merge',v['ref']),'expected merge ref')
        for k in ('head_sha','base_sha'):require(re.fullmatch('[0-9a-f]{40}',v[k]),'invalid '+k)
    else:require(v['ref']=='refs/heads/main' and v['head_sha']==v['base_sha']=='','invalid main source tuple')
    require(v['workflow']=='CI' and v['workflow_sha']==v['revision'],'wrong tested workflow')
    require(v['workflow_ref']==v['repository']+'/.github/workflows/ci.yml@'+v['ref'],'workflow phase/path/ref mismatch')
    return v

def check_checkout(expected):
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==expected['revision'],'checkout differs')
    if expected['event']=='pull_request':
        require(subprocess.check_output(['git','show','-s','--format=%P','HEAD'],cwd=ROOT,text=True).split()==[expected['base_sha'],expected['head_sha']],'merge parent ordering differs')

def bounded(argv,timeout,cwd=ROOT):
    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    for k in list(env):
        # Shell startup files/functions can silently displace fixture PATH stubs.
        if k.startswith(('GIT_', 'BASH_FUNC_')) or k in ('BASH_ENV', 'ENV',
                'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
            env.pop(k)
    p=subprocess.Popen(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    out=bytearray();selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ);deadline=time.monotonic()+timeout
    try:
        while selector.get_map():
            require(time.monotonic()<deadline,'command timeout')
            for key,_ in selector.select(min(.25,max(0,deadline-time.monotonic()))):
                data=os.read(key.fileobj.fileno(),65536)
                if not data:selector.unregister(key.fileobj);continue
                out.extend(data);require(len(out)<=MAX_OUTPUT,'command output exceeded bound')
        p.wait(timeout=max(.1,deadline-time.monotonic()))
        require(p.returncode==0,'command failed: '+str(argv)+'\n'+out.decode(errors='replace'))
        return bytes(out)
    finally:
        try:os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait();selector.close();p.stdout.close()

def run_test_module(path, output):
    file=ROOT/path;sys.path.insert(0,str(file.parent));sys.path.insert(0,str(ROOT))
    # This closed source family imports the in-tree package, never an installed copy.
    if file.parent == ROOT/'_ops/doc-warden/v2/tests':
        package=ROOT/'_ops/doc-warden/v2/doc_warden/__init__.py'
        sys.path.insert(0,str(package.parent.parent))
        found=importlib.util.find_spec('doc_warden')
        require(found is not None and isinstance(found.origin,str) and package.is_file()
                and Path(found.origin).resolve()==package.resolve(),'Doc-Warden import must use exact source package')
    spec=importlib.util.spec_from_file_location(file.stem,file);mod=importlib.util.module_from_spec(spec);sys.modules[file.stem]=mod;spec.loader.exec_module(mod)
    suite=unittest.defaultTestLoader.loadTestsFromModule(mod)
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.ids=[]
        def startTest(self,test):self.ids.append(test.id());super().startTest(test)
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    skips={}
    for test,reason in result.skipped:
        # A subTest skip leaves its registered parent only partly exercised.
        # Report that whole parent unqualified; never invent an executed child ID.
        case=getattr(test,'test_case',test).id()
        require(case in result.ids and isinstance(reason,str),'skip lacks registered parent/reason')
        skips[(case,reason)]={'case':case,'reason':reason}
    value={'module':path,'cases':result.ids,'skips':list(skips.values())}
    Path(output).write_bytes(canonical(value))
    require(result.testsRun>0 and result.wasSuccessful(),'module has no tests or failed: '+path)

def measured(shard):
    c,m,hash_=policy();row=next(s for s in m['shards'] if s['id']==shard)
    started=time.monotonic();deadline=started+row['timeout_seconds'];cases=[];skips=[];logs=[]
    for cmd in c['commands'][shard]:
        out=bounded(cmd['argv'],max(1,deadline-time.monotonic()));logs.append({'id':cmd['id'],'sha256':digest(out)})
        require(not re.search(rb'noexec[^\n]*(?:skip|SKIP)|(?:skip|SKIP)[^\n]*noexec',out),'noexec bypass drift must execute')
        print(out.decode(errors='replace'))
    with tempfile.TemporaryDirectory(prefix='dev-ci-results-') as temp:
        for i,path in enumerate(row['tests']):
            target=Path(temp)/str(i)
            out=bounded([sys.executable,'-I','-B',str(Path(__file__)),'module','--module',path,'--output',str(target)],max(1,deadline-time.monotonic()))
            result=parse(target.read_bytes());closed(result,'module cases skips');require(result['module']==path and result['cases'],'empty/wrong case evidence')
            cases.extend(path+'::'+case for case in result['cases'])
            for skip in result['skips']:
                if skip.get('case') in c['nonpassing_runtime_cases']:
                    print(json.dumps({'host_not_qualified':skip,'source_receipt':'refused'},sort_keys=True))
                    raise ContractError('required runtime case remains unqualified: '+skip['case'])
                closed(skip,'case reason');require(skip['case'] in result['cases'] and skip['reason'] in c['allowed_skip_reasons'],'unknown skip: '+str(skip));skips.append(dict(module=path,**skip))
            logs.append({'id':path,'sha256':digest(out)})
    require(len(cases)==len(set(cases)) and len(cases)>len(skips),'duplicate/zero executed cases')
    return {'commands':[x['id'] for x in c['commands'][shard]]+row['tests'],'tests':row['tests'],'case_count':len(cases),'case_ids_sha256':digest(canonical(cases)),'skips':skips,'host_not_qualified':sorted({skip['reason'] for skip in skips}),'logs_sha256':digest(canonical(logs)),'contract_sha256':hash_}

def validate_measurement(value,shard,c,m,hash_):
    closed(value,'commands tests case_count case_ids_sha256 skips host_not_qualified logs_sha256 contract_sha256')
    row=next(s for s in m['shards'] if s['id']==shard)
    require(value['tests']==row['tests'] and value['commands']==[x['id'] for x in c['commands'][shard]]+row['tests'] and value['contract_sha256']==hash_,'stale command/coverage/contract')
    require(type(value['case_count']) is int and value['case_count']>0,'zero cases')
    for k in ('case_ids_sha256','logs_sha256'):require(isinstance(value[k],str) and re.fullmatch('[0-9a-f]{64}',value[k]),'case/log digest missing')
    require(isinstance(value['skips'],list) and len(value['skips'])<value['case_count'],'all tests skipped')
    require(value['host_not_qualified']==sorted({skip['reason'] for skip in value['skips']}),'skip qualification ledger differs')
    seen=set()
    for skip in value['skips']:
        closed(skip,'module case reason');key=(skip['module'],skip['case']);require(key not in seen,'duplicate skip');seen.add(key)
        require(skip['case'] not in c['nonpassing_runtime_cases'],'unqualified required runtime case')
        require(skip['module'] in row['tests'] and isinstance(skip['case'],str) and skip['case'] and skip['reason'] in c['allowed_skip_reasons'],'unknown skip')

def validate_aggregate(needs,expected):
    c,m,hash_=policy()
    require(isinstance(needs,dict) and set(needs)==set(SHARDS),'missing or extra shard')
    for shard in SHARDS:
        row=needs[shard];closed(row,'result outputs');require(row['result']=='success','shard failed/skipped/cancelled')
        closed(row['outputs'],'receipt');receipt=parse(row['outputs']['receipt']);closed(receipt,'schema shard identity result measurement')
        require(receipt['schema']=='doc-warden-canary-ci-shard/v1' and receipt['shard']==shard and receipt['identity']==expected and receipt['result']=='success','stale shard receipt')
        validate_measurement(receipt['measurement'],shard,c,m,hash_)
    return hash_

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('local','shard','aggregate','module'));p.add_argument('--shard',choices=SHARDS);p.add_argument('--module');p.add_argument('--output');a=p.parse_args()
    if a.mode=='module':
        require(a.module in {p for s in parse((ROOT/'.github/test-shards.json').read_bytes())['shards'] for p in s['tests']} and a.output,'unknown module/output');run_test_module(a.module,a.output);return
    require(a.module is None and a.output is None,'unexpected module options')
    if a.mode=='local':
        for shard in (a.shard,) if a.shard else SHARDS:
            result=measured(shard);print(json.dumps({'shard':shard,'measurement':result},sort_keys=True))
        print('Local source checks passed; hosted/account/App/installed-host qualification is separate');return
    expected=identity(dict(os.environ));check_checkout(expected)
    if a.mode=='shard':
        require(a.shard is not None,'shard required');measurement=measured(a.shard)
        output=os.environ.get('GITHUB_OUTPUT');require(output,'GITHUB_OUTPUT required')
        receipt={'schema':'doc-warden-canary-ci-shard/v1','shard':a.shard,'identity':expected,'result':'success','measurement':measurement}
        with open(output,'a') as f:f.write('receipt='+canonical(receipt).decode()+'\n')
    else:
        require(a.shard is None,'aggregate cannot select shard');hash_=validate_aggregate(parse(os.environ.get('CI_NEEDS','null')),expected)
        print('DOC_WARDEN_CANARY_CI_AGGREGATE_V1 '+canonical({'schema':'doc-warden-canary-ci-aggregate/v1','identity':expected,'result':'success','contract_sha256':hash_}).decode())
if __name__=='__main__':
    try:main()
    except (ContractError,ValueError,OSError,subprocess.SubprocessError,KeyError,TypeError) as e:
        print('CI verification refused: '+str(e),file=sys.stderr);sys.exit(1)

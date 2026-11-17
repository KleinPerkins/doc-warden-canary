"""Closed coverage and adversarial exact-run aggregate tests; no hosted claims."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('canary_ci', ROOT / 'scripts/verify.py')
ci = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ci)
ENV = dict(zip(('GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_EVENT_NAME','GITHUB_SHA',
    'GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REF','CI_HEAD_SHA',
    'CI_BASE_SHA','GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW'),
    ('KleinPerkins/doc-warden-canary','1324068071','pull_request','a'*40,'a'*40,'100','1',
     'refs/pull/2/merge','b'*40,'c'*40,'KleinPerkins/doc-warden-canary/.github/workflows/ci.yml@refs/pull/2/merge','CI')))

def evidence():
    c, m, digest = ci.policy(); value = {}
    for row in m['shards']:
        measured = dict(commands=row['tests'], tests=row['tests'], case_count=1,
            case_ids_sha256='d'*64, skips=[], host_not_qualified=[], logs_sha256='e'*64,
            contract_sha256=digest)
        receipt = dict(schema='doc-warden-canary-ci-shard/v1', shard=row['id'],
            identity=ci.identity(ENV), result='success', measurement=measured)
        value[row['id']] = dict(result='success', outputs=dict(receipt=json.dumps(receipt)))
    return value

class Aggregate(unittest.TestCase):
    def test_complete_exact_run_and_every_nonpassing_lane(self):
        ci.validate_aggregate(evidence(), ci.identity(ENV))
        for shard in ci.SHARDS:
            for state in ('failure','cancelled','skipped','neutral','timed_out','',None):
                value = evidence(); value[shard]['result'] = state
                with self.subTest(shard=shard,state=state), self.assertRaises(ci.ContractError):
                    ci.validate_aggregate(value, ci.identity(ENV))

    def test_missing_extra_duplicate_receipts_and_each_identity_drift_refuse(self):
        cases = [None, {}, dict(evidence(), unexpected={})]
        value=evidence();del value['engine-negative'];cases.append(value)
        value=evidence();value['engine-negative']=value['engine-positive'];cases.append(value)
        for field in ci.IDENTITY_KEYS:
            value=evidence();row=json.loads(value['engine-positive']['outputs']['receipt'])
            row['identity'][field] += 'stale';value['engine-positive']['outputs']['receipt']=json.dumps(row);cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ci.ContractError):
                ci.validate_aggregate(value, ci.identity(ENV))

    def test_fabricated_coverage_or_skip_never_qualifies(self):
        for field, value in [('case_count',0),('case_count',True),('tests',[]),('commands',[]),
                ('contract_sha256','f'*64),('logs_sha256','x'),('case_ids_sha256',''),
                ('skips',[dict(module='tests/test_engine_positive.py',case='unrun',reason='skip')])]:
            needs=evidence();row=json.loads(needs['engine-positive']['outputs']['receipt'])
            row['measurement'][field]=value;needs['engine-positive']['outputs']['receipt']=json.dumps(row)
            with self.subTest(field=field), self.assertRaises(ci.ContractError):ci.validate_aggregate(needs,ci.identity(ENV))

    def test_new_or_missing_test_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'.github').mkdir();(root/'tests').mkdir()
            for name in ('ci-contract.json','test-shards.json'):
                (root/'.github'/name).write_bytes((ROOT/'.github'/name).read_bytes())
            for row in ci.policy()[1]['shards']:
                for path in row['tests']:(root/path).touch()
            ci.policy(root)
            (root/'tests/test_unassigned.py').touch()
            with self.assertRaises(ci.ContractError):ci.policy(root)
            (root/'tests/test_unassigned.py').unlink();(root/'tests/test_engine_negative.py').unlink()
            with self.assertRaises(ci.ContractError):ci.policy(root)

class Identity(unittest.TestCase):
    def test_event_repository_and_workflow_matrix(self):
        ci.identity(ENV)
        for key in ENV:
            with self.subTest(key=key),self.assertRaises(ci.ContractError):ci.identity(dict(ENV,**{key:''}))
        for event in ('push','workflow_dispatch'):
            env=dict(ENV,GITHUB_EVENT_NAME=event,GITHUB_REF='refs/heads/main',CI_HEAD_SHA='',CI_BASE_SHA='',
                     GITHUB_WORKFLOW_REF='KleinPerkins/doc-warden-canary/.github/workflows/ci.yml@refs/heads/main')
            ci.identity(env)
            for changes in ({'GITHUB_REF':'refs/heads/topic'},{'CI_HEAD_SHA':'b'*40},
                    {'GITHUB_REPOSITORY_ID':'1'},{'GITHUB_REPOSITORY':'other/repo'},
                    {'GITHUB_WORKFLOW_SHA':'f'*40},{'GITHUB_EVENT_NAME':'pull_request_target'}):
                with self.subTest(event=event,changes=changes),self.assertRaises(ci.ContractError):ci.identity(dict(env,**changes))

    def test_duplicate_json_and_wrong_merge_parent_order_refuse(self):
        with self.assertRaises(ci.ContractError):ci.parse('{"same":1,"same":2}')
        with patch.object(ci.subprocess,'check_output',side_effect=['a'*40,'b'*40+' '+'c'*40]):
            with self.assertRaises(ci.ContractError):ci.check_checkout(ci.identity(ENV))
        with patch.object(ci.subprocess,'check_output',side_effect=['a'*40,'c'*40+' '+'b'*40]):
            ci.check_checkout(ci.identity(ENV))

class Workflow(unittest.TestCase):
    def test_parallel_lanes_and_final_gate_bind_the_immutable_owner(self):
        workflow=ci.parse((ROOT/'.github/workflows/ci.yml').read_bytes())
        contract=ci.policy()[0]
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertEqual(set(workflow['jobs']),set(ci.SHARDS)|{'ci-required'})
        self.assertNotIn('pull_request_target',workflow['on'])
        for shard in ci.SHARDS:
            job=workflow['jobs'][shard]
            self.assertNotIn('needs',job)
            self.assertEqual(job['outputs'],{'receipt':'${{ steps.verify.outputs.receipt }}'})
            self.assertEqual(job['steps'][-1]['run'],'python3 -I -B scripts/verify.py shard --shard '+shard)
            for step in job['steps']:
                if 'uses' in step:
                    self.assertRegex(step['uses'],r'@[a-f0-9]{40}$')
                if step.get('uses','').startswith('actions/checkout@'):
                    self.assertIs(step['with']['persist-credentials'],False)
            owner=[s for s in job['steps'] if s.get('with',{}).get('repository')=='KleinPerkins/dev']
            self.assertEqual(len(owner),1 if shard.startswith('engine-') else 0)
            if owner:self.assertEqual(owner[0]['with']['ref'],contract['owner_source']['revision'])
        gate=workflow['jobs']['ci-required']
        self.assertEqual(gate['needs'],list(ci.SHARDS))
        self.assertEqual(gate['if'],'${{ always() }}')
        self.assertEqual(gate['steps'][-1]['env']['CI_NEEDS'],'${{ toJSON(needs) }}')
        self.assertEqual(gate['steps'][-1]['run'],'python3 -I -B scripts/verify.py aggregate')


class ReadOnlyHarnessSnapshot(unittest.TestCase):
    def test_mutations_to_tree_metadata_links_specials_and_git_are_detected(self):
        from canary_support import snapshot
        def retarget(root):
            (root/'link').unlink();(root/'link').symlink_to('same-bytes')
        changes=[lambda r:(r/'empty').mkdir(),lambda r:(r/'tracked').chmod(0o755),
                 lambda r:(r/'.git/HEAD').write_text('changed'),retarget,
                 lambda r:os.mkfifo(r/'pipe')]
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);(root/'tracked').write_text('same');(root/'tracked').chmod(0o644)
                (root/'same-bytes').write_text('same');(root/'link').symlink_to('tracked')
                (root/'.git').mkdir();(root/'.git/HEAD').write_text('base')
                before=snapshot(root);change(root)
                self.assertNotEqual(snapshot(root),before)

    def test_symlink_targets_are_not_followed_and_fifo_is_not_read(self):
        from canary_support import snapshot
        with tempfile.TemporaryDirectory() as temporary:
            top=Path(temporary);root=top/'repo';root.mkdir();outside=top/'outside';outside.write_text('one')
            (root/'link').symlink_to(outside);os.mkfifo(root/'pipe')
            before=snapshot(root);outside.write_text('two')
            self.assertEqual(snapshot(root),before)
            self.assertIn('pipe',before)


class OwnerCheckoutIdentity(unittest.TestCase):
    def test_exact_public_checkout_transport_forms_and_wrong_origins(self):
        import canary_support as support
        valid=('https://github.com/KleinPerkins/dev.git','https://github.com/KleinPerkins/dev','git@github.com:KleinPerkins/dev.git')
        invalid=('https://github.com/other/dev','https://github.com/KleinPerkins/dev-other','https://github.com.evil.invalid/KleinPerkins/dev','https://credential@github.com/KleinPerkins/dev')
        with tempfile.TemporaryDirectory() as temporary:
            for remote in valid+invalid:
                with self.subTest(remote=remote),patch.dict(os.environ,{'DOC_WARDEN_OWNER_SOURCE':temporary}),patch.object(support.subprocess,'check_output',side_effect=[support.OWNER_REVISION,remote,'']):
                    if remote in valid:self.assertEqual(support.owner_source(),Path(temporary).resolve())
                    else:
                        with self.assertRaisesRegex(AssertionError,'owner origin'):support.owner_source()

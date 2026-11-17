import json
import unittest
from canary_support import fixture, snapshot

class EngineNegative(unittest.TestCase):
    def test_frozen_canary_pending_adr_is_not_product_acceptance(self):
        with fixture() as (repo, run):
            before = snapshot(repo)
            result = run('check', str(repo))
            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn('0001-canary-architecture-choice-v1.md:NEEDS_AUTHORING', result.stdout)
            self.assertIn('Overall: NEEDS_AUTHORING', result.stdout)
            self.assertEqual(snapshot(repo), before)

    def test_owner_drift_and_authority_refusals_do_not_write(self):
        for kind, code, status in [('drifted', 1, 'DRIFTED'),
                                   ('needs_operator', 3, 'NEEDS_OPERATOR'),
                                   ('contradictory', 3, 'CONTRADICTORY')]:
            with self.subTest(kind=kind), fixture(kind) as (repo, run):
                before = snapshot(repo)
                result = run('check', str(repo))
                self.assertEqual(result.returncode, code, result.stderr + result.stdout)
                self.assertIn('Overall: ' + status, result.stdout)
                self.assertEqual(snapshot(repo), before)

    def test_missing_revision_consent_refuses_without_writes(self):
        with fixture('drifted') as (repo, run):
            before = snapshot(repo)
            result = run('repair', str(repo), '--approve')
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            self.assertIn('--approve requires --revision or --greenfield', result.stderr)
            self.assertEqual(snapshot(repo), before)

    def test_invalid_v2_identity_blocks_writes_even_with_zero_exit_view(self):
        with fixture() as (repo, run):
            config = repo / '.planning/doc-warden.json'
            value = json.loads(config.read_text()); value['repository_key'] = 'invalid'
            config.write_text(json.dumps(value))
            before = snapshot(repo)
            result = run('doctor', 'repo', '--repo', str(repo))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            view = json.loads(result.stdout)
            self.assertEqual((view['profile'], view['migration_status']), ('invalid', 'blocked'))
            self.assertFalse(view['write_enabled'])
            self.assertEqual(view['reason'], 'repository_key_unreadable')
            self.assertTrue(view['read_only'])
            self.assertEqual(view['repository_writes'], [])
            self.assertEqual(snapshot(repo), before)

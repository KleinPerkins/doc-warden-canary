import json
import unittest
from canary_support import fixture, snapshot

class EnginePositive(unittest.TestCase):
    def test_frozen_canary_v2_view_is_read_only(self):
        with fixture() as (repo, run):
            before = snapshot(repo)
            result = run('doctor', 'repo', '--repo', str(repo))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            view = json.loads(result.stdout)
            self.assertEqual(view['schema'], 'doc-warden/repo-view/v2')
            self.assertEqual((view['profile'], view['migration_status']), ('v2', 'active'))
            self.assertTrue(view['read_only'])
            self.assertEqual(view['repository_writes'], [])
            self.assertEqual(snapshot(repo), before)

    def test_owner_conformant_fixture_and_empty_preview_do_not_write(self):
        with fixture('conformant') as (repo, run):
            before = snapshot(repo)
            result = run('check', str(repo))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('Overall: CONFORMANT', result.stdout)
            preview = run('repair', str(repo), '--dry-run')
            self.assertEqual(preview.returncode, 0, preview.stderr + preview.stdout)
            self.assertIn('Plan: empty', preview.stdout)
            self.assertEqual(snapshot(repo), before)

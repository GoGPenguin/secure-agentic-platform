#!/usr/bin/env python3
"""Offline regression tests; these are not live authorization evidence."""
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import unittest
from unittest.mock import patch
import yaml

sys.dont_write_bytecode = True

spec = importlib.util.spec_from_file_location('rbac_checks', Path(__file__).with_name('check-rbac.py'))
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class Checks(unittest.TestCase):
    def test_allow_and_deny_mismatches_fail(self):
        rows = [dict(persona='developer', namespace='gitops-apps', verb='get',
                     resource='pods', subresource='', allow=True),
                dict(persona='ci', namespace='monitoring', verb='get',
                     resource='secrets', subresource='', allow=False)]
        for observed in [(True, False), (False, False), (True, True)]:
            with self.subTest(observed=observed), patch.object(checks, 'kubectl') as run:
                values = [True] * 4 + list(observed)
                run.side_effect = [subprocess.CompletedProcess([], 0, 'test-context', '')] + [
                    subprocess.CompletedProcess([], 0 if v else 1, 'yes' if v else 'no', '')
                    for v in values]
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(checks.live(rows), int(observed != (True, False)))

    def test_errors_cannot_pass_as_denials(self):
        for code, out, err in [(1, '', 'Forbidden'), (1, 'no', 'error: connection failed'),
                               (0, '', ''), (1, 'yes', '')]:
            with self.assertRaises(RuntimeError):
                checks.decision(subprocess.CompletedProcess([], code, out, err))

    def test_missing_impersonation_stops_before_assertions(self):
        with patch.object(checks, 'kubectl') as run:
            run.side_effect = [subprocess.CompletedProcess([], 0, 'test-context', ''),
                               subprocess.CompletedProcess([], 1, 'no', '')]
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'BLOCKED'):
                checks.live([])
            self.assertEqual(run.call_count, 2)

    def test_static_rejects_privilege_and_ownership_changes(self):
        mutations = ['wildcard', 'secret', 'binding', 'cluster', 'project']
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for path in ['rbac', 'docs/security', 'bootstrap/argocd/control-plane']:
                    shutil.copytree(checks.ROOT / path, root / path)
                path = root / 'rbac/gitops-apps-developer.yaml'
                docs = list(yaml.safe_load_all(path.read_text()))
                if mutation == 'wildcard':
                    docs[0]['rules'][0]['verbs'] = ['*']
                elif mutation == 'secret':
                    docs[0]['rules'][0]['resources'].append('secrets')
                elif mutation == 'binding':
                    docs[1]['roleRef']['name'] = 'cluster-admin'
                elif mutation == 'cluster':
                    docs[0]['kind'] = 'ClusterRole'
                else:
                    path = root / 'bootstrap/argocd/control-plane/secure-rbac.yaml'
                    docs = [yaml.safe_load(path.read_text())]
                    docs[0]['spec']['clusterResourceWhitelist'] = [{'group': '*', 'kind': '*'}]
                path.write_text(yaml.safe_dump_all(docs))
                with self.assertRaises(AssertionError):
                    checks.validate(root)


if __name__ == '__main__':
    unittest.main()

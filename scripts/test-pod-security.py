#!/usr/bin/env python3
"""Credential-free Helm, schema, inheritance, fixture and regression checks."""

import copy
import importlib.util
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location('checker', ROOT / 'scripts/check-pod-security.py')
checker = importlib.util.module_from_spec(loader)
loader.loader.exec_module(checker)
admission_loader = importlib.util.spec_from_file_location('admission', ROOT / 'scripts/test-psa-admission.py')
admission = importlib.util.module_from_spec(admission_loader)
admission_loader.loader.exec_module(admission)


def helm(command, app='platform-api', hardened=False, extra=(), chart='charts/web-app'):
    args = ['helm', command]
    if command == 'template':
        args += [app]
    args += [str(chart)]
    if command == 'template':
        args += ['-n', 'psa-restricted-test']
    if app != 'defaults':
        args += ['-f', f'environments/{app}-values.yaml']
    if hardened:
        args += ['-f', 'environments/platform-api-restricted-values.yaml']
    return subprocess.run(args + list(extra), cwd=ROOT, text=True, capture_output=True)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.pod = yaml.safe_load((ROOT / 'security/psa-test/pods/compliant.yaml').read_text())

    def test_fixtures_and_cli_exit_codes(self):
        expected = {
            'privileged': 'privileged must be false',
            'missing-allow-privilege-escalation': 'allowPrivilegeEscalation must be false',
            'missing-drop-all': 'capabilities.drop must contain ALL',
            'invalid-seccomp': 'seccomp must be RuntimeDefault or Localhost',
        }
        for path in sorted((ROOT / 'security/psa-test/pods').glob('*.yaml')):
            with self.subTest(fixture=path.stem):
                result = subprocess.run(['python3', '-B', 'scripts/check-pod-security.py', str(path)],
                                        cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0 if path.stem == 'compliant' else 1)
                if path.stem in expected:
                    self.assertIn(expected[path.stem], result.stderr)

    def test_pod_and_container_inheritance(self):
        self.assertEqual(checker.check([self.pod]), [])
        pod = copy.deepcopy(self.pod)
        inherited = pod['spec'].pop('securityContext')
        pod['spec']['containers'][0]['securityContext'].update(inherited)
        self.assertEqual(checker.check([pod]), [])
        for field in ('runAsNonRoot', 'seccompProfile'):
            broken = copy.deepcopy(pod)
            del broken['spec']['containers'][0]['securityContext'][field]
            self.assertTrue(checker.check([broken]))
        for field, value in [('runAsNonRoot', False), ('runAsUser', 0),
                             ('seccompProfile', {'type': 'Unconfined'})]:
            for level in ('pod', 'container'):
                broken = copy.deepcopy(self.pod)
                context = (broken['spec']['securityContext'] if level == 'pod' else
                           broken['spec']['containers'][0]['securityContext'])
                context[field] = value
                self.assertTrue(checker.check([broken]), (field, level))

    def test_live_error_classification_without_requests(self):
        cases = [
            ('Error from server (Forbidden): violates PodSecurity "restricted:v1.37": unrestricted capabilities', 'PSA_REJECTED'),
            ('Error from server (Forbidden): user cannot create resource pods', 'AUTHENTICATION_OR_AUTHORIZATION_FAILURE'),
            ('Error from server (Unauthorized): Unauthorized', 'AUTHENTICATION_OR_AUTHORIZATION_FAILURE'),
            ('Unable to connect to the server: connection refused', 'API_CONNECTIVITY_FAILURE'),
            ('Error from server (Invalid): Pod is invalid', 'INVALID_RESOURCE_SCHEMA'),
            ('error validating data: unknown field', 'INVALID_RESOURCE_SCHEMA'),
            ('Error from server (NotFound): namespace not found', 'UNEXPECTED_FAILURE'),
            ('admission webhook denied the request', 'UNEXPECTED_FAILURE'),
        ]
        for output, category in cases:
            self.assertEqual(admission.classify(1, output), category)
            self.assertFalse(admission.expected_result('privileged', 1, output))
        for name, controls in admission.EXPECTED.items():
            if not controls:
                self.assertTrue(admission.expected_result(name, 0, 'pod/compliant created (server dry run)'))
            else:
                message = 'violates PodSecurity "restricted:v1.37": ' + ', '.join(controls)
                self.assertTrue(admission.expected_result(name, 1, message))
                self.assertFalse(admission.expected_result(name, 0, message))
                self.assertFalse(admission.expected_result(name, 1, message.replace('v1.37', 'v1.36')))
        self.assertFalse(admission.expected_result('privileged', 1,
                         'pods "privileged" is forbidden: violates PodSecurity "restricted:v1.37": allowPrivilegeEscalation'))

    def test_admission_runner_requires_explicit_run_flag(self):
        with patch.object(sys, 'argv', ['test-psa-admission.py', '--context', 'unused']), \
                patch.object(subprocess, 'run') as request, patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                admission.main()
            request.assert_not_called()

    def test_fixture_differences_are_intentional(self):
        for name in admission.EXPECTED:
            pod = yaml.safe_load((ROOT / f'security/psa-test/pods/{name}.yaml').read_text())
            pod['metadata']['name'] = 'compliant'
            context = pod['spec']['containers'][0]['securityContext']
            if name == 'privileged':
                self.assertTrue(context.pop('privileged'))
                self.assertIs(context['allowPrivilegeEscalation'], True)
                context['allowPrivilegeEscalation'] = False
            elif name == 'missing-allow-privilege-escalation':
                self.assertNotIn('allowPrivilegeEscalation', context)
                context['allowPrivilegeEscalation'] = False
            elif name == 'missing-drop-all':
                self.assertNotIn('capabilities', context)
                context['capabilities'] = {'drop': ['ALL']}
            elif name == 'invalid-seccomp':
                self.assertEqual(context.pop('seccompProfile'), {'type': 'Unconfined'})
            self.assertEqual(pod, self.pod, name)

    def test_chart_version_does_not_change_pod_template(self):
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / 'web-app'
            shutil.copytree(ROOT / 'charts/web-app', chart)
            metadata = yaml.safe_load((chart / 'Chart.yaml').read_text())
            metadata['version'] = '0.2.2'
            (chart / 'Chart.yaml').write_text(yaml.safe_dump(metadata))
            for app in ('frontend', 'backend', 'sandbox', 'platform-api'):
                before = list(yaml.safe_load_all(helm('template', app).stdout))
                rendered = helm('template', app, chart=chart)
                self.assertEqual(rendered.returncode, 0, rendered.stderr)
                after = list(yaml.safe_load_all(rendered.stdout))
                for old, new in zip(before, after, strict=True):
                    self.assertIn('helm.sh/chart', new['metadata']['labels'])
                    if old['kind'] == 'Deployment':
                        self.assertEqual(old['spec']['template'], new['spec']['template'])
                        self.assertNotIn('helm.sh/chart', new['spec']['template']['metadata']['labels'])
                        self.assertEqual(old['spec']['selector'], new['spec']['selector'])

    def test_init_ephemeral_and_empty_input(self):
        self.assertTrue(checker.check([]))
        for field in ('initContainers', 'ephemeralContainers'):
            pod = copy.deepcopy(self.pod)
            pod['spec'][field] = [{'name': 'unsafe', 'image': 'unused'}]
            self.assertTrue(checker.check([pod]))

    def test_malformed_security_fields_fail_closed(self):
        # Raw YAML bypasses the Helm values schema: a string containing ALL
        # must not satisfy the drop-array policy by substring membership.
        mutations = [
            ('pod', 'securityContext', []),
            ('container', 'securityContext', False),
            ('container-context', 'capabilities', {'drop': 'ALL'}),
            ('container-context', 'capabilities', {'drop': ['ALL'], 'add': 'NET_BIND_SERVICE'}),
            ('container-context', 'capabilities', {'drop': ['ALL', 123]}),
            ('container-context', 'seccompProfile', 'RuntimeDefault'),
        ]
        for level, field, value in mutations:
            pod = copy.deepcopy(self.pod)
            target = pod['spec'] if level == 'pod' else pod['spec']['containers'][0]
            if level == 'container-context':
                target = target['securityContext']
            target[field] = value
            with self.subTest(level=level, field=field, value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'invalid.yaml'
                path.write_text(yaml.safe_dump(pod))
                result = subprocess.run(['python3', '-B', 'scripts/check-pod-security.py', str(path)],
                                        cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('FAIL: malformed input:', result.stderr)

    def test_null_seccomp_inherits_and_valid_override_works(self):
        context = self.pod['spec']['containers'][0]['securityContext']
        context['seccompProfile'] = None
        self.assertEqual(checker.check([self.pod]), [])
        context['seccompProfile'] = {'type': 'Localhost', 'localhostProfile': 'profiles/app.json'}
        self.assertEqual(checker.check([self.pod]), [])
        context['seccompProfile'] = {'type': 'Localhost'}
        self.assertTrue(checker.check([self.pod]))

    def test_reviewed_lab_artifacts_match_chart_render(self):
        # The lab release identity is part of selectors, not production's name.
        args = ['helm', 'template', 'platform-api-psa', 'charts/web-app', '-n', 'psa-restricted-test',
                '-f', 'environments/platform-api-values.yaml',
                '-f', 'environments/platform-api-restricted-values.yaml',
                '-f', 'security/psa-test/platform-api-lab-values.yaml']
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = list(yaml.safe_load_all(result.stdout))
        for resource in rendered:
            resource['metadata']['namespace'] = 'psa-restricted-test'
        expected = list(yaml.safe_load_all((ROOT / 'security/psa-test/rendered/platform-api-lab.yaml').read_text()))
        expected += list(yaml.safe_load_all((ROOT / 'security/psa-test/rendered/platform-api-hook.yaml').read_text()))
        self.assertEqual(rendered, expected)

    def test_deployment_violations_and_lab_consistency(self):
        deployment = {'kind': 'Deployment', 'metadata': {'name': 'test'},
                      'spec': {'template': {'spec': copy.deepcopy(self.pod['spec'])}}}
        self.assertEqual(checker.check([deployment]), [])
        deployment['spec']['template']['spec']['containers'][0]['securityContext']['privileged'] = True
        self.assertTrue(checker.check([deployment]))
        namespace = yaml.safe_load((ROOT / 'security/psa-test/namespace.yaml').read_text())
        self.assertEqual(namespace['metadata']['name'], 'psa-restricted-test')
        labels = namespace['metadata']['labels']
        for mode in ('enforce', 'warn', 'audit'):
            self.assertEqual(labels[f'pod-security.kubernetes.io/{mode}'], 'restricted')
            self.assertEqual(labels[f'pod-security.kubernetes.io/{mode}-version'], 'v1.37')
        values = yaml.safe_load((ROOT / 'environments/platform-api-values.yaml').read_text())
        reference = values['image']['repository'] + '@' + values['image']['digest']
        for path in (ROOT / 'security/psa-test/pods').glob('*.yaml'):
            pod = yaml.safe_load(path.read_text())
            self.assertEqual(pod['metadata']['namespace'], namespace['metadata']['name'])
            self.assertEqual(pod['spec']['containers'][0]['image'], reference)

    def test_helm_and_opt_in_only(self):
        for app in ('defaults', 'frontend', 'backend', 'sandbox', 'platform-api'):
            with self.subTest(app=app):
                lint = helm('lint', app)
                self.assertEqual(lint.returncode, 0, lint.stderr)
                result = helm('template', app)
                self.assertEqual(result.returncode, 0, result.stderr)
                for resource in yaml.safe_load_all(result.stdout):
                    if resource['kind'] not in ('Deployment', 'Pod'):
                        continue
                    spec = (resource['spec']['template']['spec'] if resource['kind'] == 'Deployment'
                            else resource['spec'])
                    self.assertNotIn('securityContext', spec)
                    for container in spec['containers']:
                        self.assertNotIn('securityContext', container)
        lint = helm('lint', hardened=True)
        self.assertEqual(lint.returncode, 0, lint.stderr)
        result = helm('template', hardened=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        resources = list(yaml.safe_load_all(result.stdout))
        self.assertEqual(checker.check(resources), [])
        baseline = list(yaml.safe_load_all(helm('template').stdout))
        for before, after in zip(baseline, resources, strict=True):
            expected = copy.deepcopy(after)
            if after['kind'] in ('Deployment', 'Pod'):
                spec = (expected['spec']['template']['spec'] if after['kind'] == 'Deployment'
                        else expected['spec'])
                self.assertEqual(spec.pop('securityContext')['runAsUser'], 1000)
                for container in spec['containers']:
                    del container['securityContext']
                if after['kind'] == 'Pod':
                    self.assertIs(spec.pop('automountServiceAccountToken'), False)
            self.assertEqual(before, expected)

    def test_schema_rejects_wrong_types_but_permits_non_restricted_opt_in(self):
        cases = [({'podSecurityContext': {'runAsNonRoot': 'true'}}, False),
                 ({'podSecurityContext': {'runAsUser': -1}}, False),
                 ({'securityContext': {'allowPrivilegeEscalation': 'false'}}, False),
                 ({'securityContext': {'capabilities': {'drop': 'ALL'}}}, False),
                 ({'securityContext': {'seccompProfile': {'type': 'Invalid'}}}, False),
                 ({'podSecurityContext': []}, False),
                 ({'securityContext': {'privileged': True}}, True)]
        for values, valid in cases:
            with self.subTest(values=values), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'values.yaml'
                path.write_text(yaml.safe_dump(values))
                result = helm('template', extra=['-f', str(path)])
                self.assertEqual(result.returncode == 0, valid, result.stderr)


if __name__ == '__main__':
    unittest.main()

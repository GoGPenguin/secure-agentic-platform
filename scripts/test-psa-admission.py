#!/usr/bin/env python3
"""Opt-in live Pod dry-runs. Never creates a namespace or persists a workload.

Do not run until isolated live admission testing is authorized. Error-classifier
unit tests live in test-pod-security.py and require no cluster credentials.
"""

import argparse
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'psa-restricted-test'
POLICY_VERSION = 'v1.37'
EXPECTED = {
    'compliant': (),
    # Both controls are necessarily violated: privileged + no-new-privileges
    # (allowPrivilegeEscalation=false) is an API-invalid combination.
    'privileged': ('privileged', 'allowPrivilegeEscalation'),
    'missing-allow-privilege-escalation': ('allowPrivilegeEscalation',),
    'missing-drop-all': ('unrestricted capabilities',),
    'invalid-seccomp': ('seccompProfile',),
}


def classify(returncode, output):
    if returncode == 0:
        return 'ALLOWED'
    text = output.lower()
    if any(s in text for s in ('unable to connect', 'connection refused', 'i/o timeout',
                               'context deadline exceeded', 'no such host', 'tls handshake',
                               'x509:', 'connection reset', 'unexpected eof',
                               'serviceunavailable', 'gateway timeout')):
        return 'API_CONNECTIVITY_FAILURE'
    if any(s in text for s in ('(invalid)', 'error validating', 'strict decoding error',
                               'unknown field', 'error parsing', 'error converting yaml')):
        return 'INVALID_RESOURCE_SCHEMA'
    # PSA itself returns Forbidden; check its distinctive marker before auth.
    if 'violates PodSecurity ' in output:
        return 'PSA_REJECTED'
    if any(s in text for s in ('(unauthorized)', '(forbidden)', 'must be logged in',
                               'provide credentials', 'getting credentials',
                               'you must be logged', 'cannot create resource')):
        return 'AUTHENTICATION_OR_AUTHORIZATION_FAILURE'
    return 'UNEXPECTED_FAILURE'


def expected_result(name, returncode, output):
    category = classify(returncode, output)
    if not EXPECTED[name]:
        return category == 'ALLOWED'
    marker = f'violates PodSecurity "restricted:{POLICY_VERSION}"'
    if category != 'PSA_REJECTED' or marker not in output:
        return False
    details = output.split(marker, 1)[1]
    return all(control in details for control in EXPECTED[name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='explicitly enable live dry-run requests')
    parser.add_argument('--context', required=True, help='explicit reviewed Kubernetes context')
    args = parser.parse_args()
    if not args.run:
        parser.error('--run is required; no Kubernetes requests have been sent')
    kubectl = ['kubectl', '--context', args.context, '--request-timeout=10s']

    def request(arguments):
        try:
            result = subprocess.run(kubectl + arguments, text=True, capture_output=True, timeout=20)
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return 1, 'Unable to connect: local kubectl timeout'
        except OSError as error:
            return 1, f'kubectl execution failure: {error}'

    code, output = request(['get', 'namespace', NAMESPACE, '-o', 'yaml'])
    if code:
        print(f'FAIL namespace precondition: {classify(code, output)}\n{output}', file=sys.stderr)
        return 1
    try:
        namespace = yaml.safe_load(output)
        labels = namespace['metadata'].get('labels', {})
        if namespace['metadata']['name'] != NAMESPACE:
            raise ValueError('unexpected namespace')
        for mode in ('enforce', 'warn', 'audit'):
            if (labels.get(f'pod-security.kubernetes.io/{mode}') != 'restricted'
                    or labels.get(f'pod-security.kubernetes.io/{mode}-version') != POLICY_VERSION):
                raise ValueError(f'{mode} labels must be restricted/{POLICY_VERSION}')
    except (yaml.YAMLError, KeyError, TypeError, ValueError) as error:
        print(f'FAIL namespace precondition: {error}', file=sys.stderr)
        return 1
    failed = False
    for name in EXPECTED:
        path = ROOT / 'security/psa-test/pods' / f'{name}.yaml'
        # Pin both the fixture namespace and the command namespace.
        pod = yaml.safe_load(path.read_text())
        if pod.get('kind') != 'Pod' or pod['metadata'].get('namespace') != NAMESPACE:
            print(f'FAIL unsafe fixture identity: {path}', file=sys.stderr)
            return 1
        code, output = request(['create', '--dry-run=server', '--validate=strict',
                                '-n', NAMESPACE, '-f', str(path)])
        passed = expected_result(name, code, output)
        print(f'{"PASS" if passed else "FAIL"} {name}: {classify(code, output)} (exit {code})')
        print(output.rstrip())
        failed |= not passed
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())

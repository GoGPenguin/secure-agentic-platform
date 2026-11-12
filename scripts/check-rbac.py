#!/usr/bin/env python3
"""Static policy validation or non-mutating live authorization verification (PyYAML)."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / 'docs/security/authorization-matrix.json'


def load_resources(root):
    return [r for p in sorted((root / 'rbac').glob('*.yaml'))
            for r in yaml.safe_load_all(p.read_text()) if r]


def expected_grants(persona):
    grants = {('', r, v) for r in ['pods', 'services'] for v in ['get', 'list', 'watch']}
    grants |= {('apps', r, v) for r in ['deployments', 'replicasets']
               for v in ['get', 'list', 'watch']}
    if persona == 'developer':
        grants.add(('', 'pods/log', 'get'))
    else:
        grants |= {('', 'serviceaccounts', v) for v in ['get', 'list', 'watch']}
        grants |= {('rbac.authorization.k8s.io', r, v)
                   for r in ['roles', 'rolebindings'] for v in ['get', 'list', 'watch']}
    return grants


def validate(root):
    resources = load_resources(root)
    expected = {(ns, 'w09-' + who) for ns, who in [
        ('gitops-apps', 'developer'), ('gitops-apps', 'auditor'), ('monitoring', 'auditor')]}
    keys = [(r['kind'], r['metadata']['namespace'], r['metadata']['name']) for r in resources]
    assert len(keys) == len(set(keys)) == 6, 'Expected exactly six unique resources'
    assert set(keys) == {(kind, ns, name) for ns, name in expected
                         for kind in ['Role', 'RoleBinding']}, 'Unexpected resource identity'
    for r in resources:
        assert r['apiVersion'] == 'rbac.authorization.k8s.io/v1'
        assert set(r) <= {'apiVersion', 'kind', 'metadata', 'rules', 'subjects', 'roleRef'}
        name, ns = r['metadata']['name'], r['metadata']['namespace']
        persona = name.removeprefix('w09-')
        if r['kind'] == 'Role':
            grants = set()
            for rule in r['rules']:
                assert set(rule) == {'apiGroups', 'resources', 'verbs'}, 'Unexpected rule fields'
                grants |= {(g, res, v) for g in rule['apiGroups']
                           for res in rule['resources'] for v in rule['verbs']}
            assert grants == expected_grants(persona), f'Excess or missing grants: {ns}/{name}'
        else:
            assert r['roleRef'] == {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': name}
            assert r['subjects'] == [{'kind': 'User', 'apiGroup': 'rbac.authorization.k8s.io',
                                      'name': 'w09:' + persona}], 'Unexpected binding subject'
    rows = json.loads((root / 'docs/security/authorization-matrix.json').read_text())
    assert len(rows) == 270
    seen = set()
    for row in rows:
        key = tuple(row[k] for k in ['persona', 'namespace', 'verb', 'resource', 'subresource'])
        assert key not in seen
        seen.add(key)
        who, ns, verb, resource, sub = key
        assert who in ['developer', 'ci', 'auditor'] and ns in ['gitops-apps', 'monitoring', 'argocd']
        base, _, group = resource.partition('.')
        grant = (group, base + ('/' + sub if sub else ''), verb)
        allowed = ((who == 'developer' and ns == 'gitops-apps') or
                   (who == 'auditor' and ns in ['gitops-apps', 'monitoring']))
        allowed = allowed and grant in expected_grants(who)
        assert row['allow'] is bool(allowed), f'Matrix disagrees with least-privilege policy: {key}'
    required_ops = {
        ('list', 'pods', ''), ('get', 'pods', ''), ('get', 'pods', 'log'),
        *((v, 'deployments.apps', '') for v in ['get', 'list', 'watch', 'create', 'update', 'patch', 'delete']),
        ('watch', 'replicasets.apps', ''), ('get', 'services', ''),
        ('get', 'secrets', ''), ('list', 'secrets', ''), ('create', 'pods', ''),
        ('get', 'pods', 'exec'), *(( 'create', 'pods', sub) for sub in ['exec', 'attach', 'portforward']),
        ('create', 'serviceaccounts', 'token'), ('get', 'serviceaccounts', ''),
        *((v, 'roles.rbac.authorization.k8s.io', '') for v in ['get', 'list', 'patch', 'bind', 'escalate']),
        *((v, 'rolebindings.rbac.authorization.k8s.io', '') for v in ['get', 'create', 'update']),
        ('impersonate', 'users', ''),
    }
    for who in ['developer', 'ci', 'auditor']:
        for ns in ['gitops-apps', 'monitoring', 'argocd']:
            assert {(r['verb'], r['resource'], r['subresource']) for r in rows
                    if r['persona'] == who and r['namespace'] == ns} == required_ops, 'Missing operation coverage'
    control = root / 'bootstrap/argocd/control-plane'
    project = yaml.safe_load((control / 'secure-rbac.yaml').read_text())['spec']
    app = yaml.safe_load((control / 'platform-rbac.yaml').read_text())['spec']
    repo = 'https://github.com/GoGPenguin/secure-agentic-platform.git'
    assert project['sourceRepos'] == [repo]
    assert project['clusterResourceWhitelist'] == []
    assert project['namespaceResourceWhitelist'] == [
        {'group': 'rbac.authorization.k8s.io', 'kind': k} for k in ['Role', 'RoleBinding']]
    assert project['destinations'] == [
        {'server': 'https://kubernetes.default.svc', 'namespace': n} for n in ['gitops-apps', 'monitoring']]
    assert app['project'] == 'secure-rbac'
    assert app['source'] == {'repoURL': repo, 'targetRevision': 'main', 'path': 'rbac'}
    assert app['destination'] == {'server': 'https://kubernetes.default.svc', 'namespace': 'gitops-apps'}
    assert app['syncPolicy'] == {'automated': {'enabled': True, 'prune': False, 'selfHeal': True},
                                 'syncOptions': ['CreateNamespace=false', 'FailOnSharedResource=true']}
    print('PASS static: six namespace-scoped resources, exact grants/subjects, project boundaries, 270 expectations')
    return rows


def kubectl(args):
    return subprocess.run(['kubectl', '--request-timeout=10s', *args],
                          text=True, capture_output=True, timeout=20)


def decision(result):
    """Errors must never pass as expected Deny."""
    answer = result.stdout.strip()
    if answer == 'yes' and result.returncode == 0:
        return True
    if answer == 'no' and result.returncode == 1 and 'error:' not in result.stderr.lower():
        return False
    raise RuntimeError(f'Authorization request failed: {result.stdout} {result.stderr}')


def compare(expected, observed):
    return expected is observed


def live(rows):
    print('Context:', kubectl(['config', 'current-context']).stdout.strip(), flush=True)
    # The caller must impersonate only these users and the authenticated group.
    for resource in ['users/w09:developer', 'users/w09:ci', 'users/w09:auditor',
                     'groups/system:authenticated']:
        if not decision(kubectl(['auth', 'can-i', 'impersonate', resource])):
            raise RuntimeError('BLOCKED: caller cannot impersonate ' + resource)
    print('PASS preflight: explicit user and authenticated-group impersonation authority', flush=True)
    passed = failed = 0
    for row in rows:
        args = ['auth', 'can-i', row['verb'], row['resource'], '-n', row['namespace'],
                '--as=w09:' + row['persona'], '--as-group=system:authenticated']
        if row['subresource']:
            args.append('--subresource=' + row['subresource'])
        observed = decision(kubectl(args))
        ok = compare(row['allow'], observed)
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} {row['persona']} {row['namespace']} "
              f"{row['verb']} {row['resource']}/{row['subresource']} "
              f"expected={'Allow' if row['allow'] else 'Deny'} observed={'Allow' if observed else 'Deny'}",
              flush=True)
    print(f'Live assertions: {passed} PASS, {failed} FAIL')
    return int(failed > 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        rows = validate(args.root)
        return live(rows) if args.live else 0
    except (AssertionError, KeyError, ValueError, OSError, RuntimeError,
            subprocess.TimeoutExpired, yaml.YAMLError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

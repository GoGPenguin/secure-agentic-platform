#!/usr/bin/env python3
"""Focused Linux Restricted control checks; NOT a complete PSS/admission engine.

Read rendered YAML files (or stdin). See docs/security/pod-security.md for scope.
Requires only the repository's existing PyYAML dependency.
"""

import argparse
from pathlib import Path
import sys

import yaml


def check(resources):
    errors = []
    checked = 0
    for resource in resources:
        if not resource:
            continue
        kind = resource.get('kind')
        if kind not in ('Pod', 'Deployment'):
            continue
        checked += 1
        name = resource.get('metadata', {}).get('name', '<unnamed>')
        prefix = f'{kind}/{name}'
        spec = resource['spec']
        if kind == 'Deployment':
            spec = spec['template']['spec']
        def security_context(value):
            if value is None:
                return {}
            if not isinstance(value, dict):
                raise ValueError(f'{prefix}: securityContext must be an object')
            return value

        pod = security_context(spec.get('securityContext'))

        def error(message):
            errors.append(f'{prefix}: {message}')

        def identity(context, where):
            if 'runAsNonRoot' in context and context['runAsNonRoot'] is not True:
                error(f'{where}: runAsNonRoot must be true')
            if 'runAsUser' in context:
                uid = context['runAsUser']
                if type(uid) is not int or uid <= 0:
                    error(f'{where}: runAsUser must be a positive integer')

        def seccomp(context, where):
            if 'seccompProfile' not in context:
                return
            profile = context['seccompProfile']
            if profile is None:
                return
            if not isinstance(profile, dict):
                raise ValueError(f'{prefix}/{where}: seccompProfile must be an object')
            if profile.get('type') not in ('RuntimeDefault', 'Localhost'):
                error(f'{where}: seccomp must be RuntimeDefault or Localhost')
            elif profile['type'] == 'Localhost' and not profile.get('localhostProfile'):
                error(f'{where}: Localhost seccomp requires localhostProfile')

        identity(pod, 'pod')
        seccomp(pod, 'pod')
        if spec.get('os', {}).get('name', 'linux') != 'linux':
            error('only Linux workloads are supported by this checker')
        if not spec.get('containers'):
            error('at least one container is required')
        for field in ('containers', 'initContainers', 'ephemeralContainers'):
            for container in spec.get(field, []):
                where = f'{field}/{container["name"]}'
                context = security_context(container.get('securityContext'))
                identity(context, where)
                seccomp(context, where)
                if context.get('runAsNonRoot', pod.get('runAsNonRoot')) is not True:
                    error(f'{where}: missing effective runAsNonRoot: true')
                effective_seccomp = context.get('seccompProfile')
                if effective_seccomp is None:
                    effective_seccomp = pod.get('seccompProfile')
                if not effective_seccomp:
                    error(f'{where}: missing effective seccompProfile')
                if context.get('allowPrivilegeEscalation') is not False:
                    error(f'{where}: allowPrivilegeEscalation must be false')
                if context.get('privileged', False) is not False:
                    error(f'{where}: privileged must be false or absent')
                capabilities = context.get('capabilities')
                if capabilities is None:
                    capabilities = {}
                if not isinstance(capabilities, dict):
                    raise ValueError(f'{prefix}/{where}: capabilities must be an object')
                for action in ('add', 'drop'):
                    values = capabilities.get(action, [])
                    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                        raise ValueError(f'{prefix}/{where}: capabilities.{action} must be a list of strings')
                if 'ALL' not in capabilities.get('drop', []):
                    error(f'{where}: capabilities.drop must contain ALL')
                if set(capabilities.get('add', [])) - {'NET_BIND_SERVICE'}:
                    error(f'{where}: only NET_BIND_SERVICE may be added')
    if checked == 0:
        errors.append('No supported Pod or Deployment found')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path)
    args = parser.parse_args()
    try:
        texts = [p.read_text() for p in args.files] if args.files else [sys.stdin.read()]
        errors = check([r for text in texts for r in yaml.safe_load_all(text)])
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError, ValueError) as exc:
        print(f'FAIL: malformed input: {exc}', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(f'FAIL: {error}' for error in errors), file=sys.stderr)
        return 1
    print('PASS: focused Linux security controls (not full PSS or admission evidence)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

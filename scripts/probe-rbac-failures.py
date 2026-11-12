#!/usr/bin/env python3
"""Live negative probe: healthy deployed policy must produce exit 1 (two intentional failures)."""
import importlib.util, sys
from pathlib import Path
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('checks',Path(__file__).with_name('check-rbac.py'))
checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
print('NEGATIVE HARNESS PROBE: deliberately false expectations; no cluster policy changes.')
print('Developer get Pods is intentionally expected Deny; CI get Secrets intentionally expected Allow.')
rows=[dict(persona='developer',namespace='gitops-apps',verb='get',resource='pods',subresource='',allow=False),dict(persona='ci',namespace='monitoring',verb='get',resource='secrets',subresource='',allow=True)]
sys.exit(checks.live(rows))

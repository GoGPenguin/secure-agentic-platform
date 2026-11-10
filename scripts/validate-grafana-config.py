#!/usr/bin/env python3
"""Render Grafana locally and check its config checksum and project allowlist."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml


def main():
    root = Path(__file__).resolve().parents[1]
    rendered = subprocess.run(
        ["kubectl", "kustomize", str(root / "monitoring/grafana")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = list(yaml.safe_load_all(rendered))
    project = yaml.safe_load(
        (root / "bootstrap/argocd/control-plane/secure-monitoring.yaml").read_text()
    )["spec"]
    allowed = {(r["group"], r["kind"]) for r in project["namespaceResourceWhitelist"]}
    for resource in resources:
        api = resource["apiVersion"]
        group = api.split("/")[0] if "/" in api else ""
        if (group, resource["kind"]) not in allowed:
            raise ValueError(f"Resource outside AppProject allowlist: {resource['kind']}")
        if resource["metadata"].get("namespace") != "monitoring":
            raise ValueError("All Grafana resources must target monitoring")

    # Hash decoded ConfigMap data, independent of YAML formatting or key order.
    config_data = {
        r["metadata"]["name"]: r["data"]
        for r in resources
        if r["kind"] == "ConfigMap"
    }
    canonical = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    deployment = next(r for r in resources if r["kind"] == "Deployment")
    actual = deployment["spec"]["template"]["metadata"]["annotations"]["checksum/config"]
    if actual != expected:
        raise ValueError(f"Stale checksum/config; required value: {expected}")
    print(f"PASS: {len(resources)} rendered resources fit secure-monitoring")
    print(f"PASS: checksum/config = {expected}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)

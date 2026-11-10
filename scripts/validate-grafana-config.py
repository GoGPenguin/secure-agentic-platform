#!/usr/bin/env python3
"""Render Grafana locally and check its config checksum and project allowlist."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml


def validate_dashboard(root, resources, deployment):
    maps = {
        r["metadata"]["name"]: r["data"] for r in resources if r["kind"] == "ConfigMap"
    }
    dashboard_text = (root / "monitoring/grafana/dashboards/platform-api.json").read_text()
    if maps["grafana-dashboards"] != {"platform-api.json": dashboard_text}:
        raise ValueError("Rendered dashboard ConfigMap differs from Git JSON")
    dashboard = json.loads(dashboard_text)
    if dashboard.get("uid") != "platform-api-overview" or dashboard.get("editable") is not False:
        raise ValueError("Dashboard must use stable UID and disable editing")
    panels = dashboard.get("panels", [])
    if len(panels) != 4 or len({p["id"] for p in panels}) != 4:
        raise ValueError("Expected exactly four panels with distinct IDs")
    if {p["fieldConfig"]["defaults"]["unit"] for p in panels} != {"reqps", "percent", "s", "none"}:
        raise ValueError("Expected request rate, percentage, seconds and health units")
    source = {"type": "prometheus", "uid": "prometheus"}
    for panel in panels:
        if not panel.get("title") or panel.get("datasource") != source:
            raise ValueError("Panel needs a title and the provisioned data source UID")
        if "alert" in panel:
            raise ValueError("Alert rules are outside this increment")
        for target in panel["targets"]:
            if target.get("datasource") != source or not target.get("expr"):
                raise ValueError("Panel query needs the provisioned data source and PromQL")

    provider_text = (root / "monitoring/grafana/config/dashboard-provider.yaml").read_text()
    if maps["grafana-dashboard-provider"] != {"dashboard-provider.yaml": provider_text}:
        raise ValueError("Rendered provider ConfigMap differs from Git configuration")
    provider = yaml.safe_load(provider_text)["providers"][0]
    if provider["type"] != "file" or provider["allowUiUpdates"] is not False:
        raise ValueError("Dashboard must use file provisioning with UI saves disabled")
    if provider["updateIntervalSeconds"] <= 10:
        raise ValueError("Use polling for projected dashboard files")

    pod = deployment["spec"]["template"]["spec"]
    volumes = {v["name"]: v for v in pod["volumes"]}
    mounts = {m["name"]: m for m in pod["containers"][0]["volumeMounts"]}
    for name, configmap, path in (
        ("dashboard-provider", "grafana-dashboard-provider", "/etc/grafana/provisioning/dashboards"),
        ("dashboards", "grafana-dashboards", provider["options"]["path"]),
    ):
        mount = mounts[name]
        if volumes[name]["configMap"]["name"] != configmap:
            raise ValueError(f"Wrong ConfigMap volume for {name}")
        if mount["mountPath"] != path or mount.get("readOnly") is not True or "subPath" in mount:
            raise ValueError(f"Expected read-only directory mount at {path}")
    if provider["options"]["path"] != "/var/lib/grafana/dashboards":
        raise ValueError("Dashboard provider must match the JSON mount path")
    print("PASS: dashboard JSON, data source UIDs, provider and read-only mount paths")


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

    # Startup configuration requires a rollout. Dashboard JSON is polled live.
    # Hash decoded data, independent of YAML formatting or key order.
    config_data = {
        r["metadata"]["name"]: r["data"]
        for r in resources
        if r["kind"] == "ConfigMap" and r["metadata"]["name"] != "grafana-dashboards"
    }
    canonical = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    deployment = next(r for r in resources if r["kind"] == "Deployment")
    actual = deployment["spec"]["template"]["metadata"]["annotations"]["checksum/config"]
    if actual != expected:
        raise ValueError(f"Stale checksum/config; required value: {expected}")
    validate_dashboard(root, resources, deployment)
    print(f"PASS: {len(resources)} rendered resources fit secure-monitoring")
    print(f"PASS: checksum/config = {expected}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)

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
    if len(panels) != 6 or {p["id"] for p in panels} != {1, 2, 3, 4, 5, 6}:
        raise ValueError("Expected the existing six panels with distinct IDs")
    if {p["fieldConfig"]["defaults"]["unit"] for p in panels} != {"reqps", "percent", "s", "none"}:
        raise ValueError("Expected request rate, percentage, seconds and health units")
    source = {"type": "prometheus", "uid": "prometheus"}
    for panel in panels:
        if not panel.get("title") or panel.get("datasource") != source:
            raise ValueError("Panel needs a title and the provisioned data source UID")
        if "alert" in panel:
            raise ValueError("Use separate Grafana-managed rules, not dashboard alerts")
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


def validate_alerting(root, resources, deployment):
    text = (root / "monitoring/grafana/config/alerting/platform-api-http.yaml").read_text()
    configmap = next(r for r in resources if r["kind"] == "ConfigMap"
                     and r["metadata"]["name"] == "grafana-alerting")
    if configmap["data"] != {"platform-api-http.yaml": text}:
        raise ValueError("Rendered alert ConfigMap differs from Git configuration")
    config = yaml.safe_load(text)
    if set(config) != {"apiVersion", "groups"} or config["apiVersion"] != 1:
        raise ValueError("Only alert rule provisioning is permitted here")
    if len(config["groups"]) != 1:
        raise ValueError("Expected one alert evaluation group")
    group = config["groups"][0]
    if (group["orgId"], group["folder"], group["name"], group["interval"]) != (
        1, "Platform", "platform-api-http", "30s"
    ) or len(group["rules"]) != 1:
        raise ValueError("Unexpected alert evaluation group")
    rule = group["rules"][0]
    expected = {"uid": "platform-api-http-5xx", "condition": "B", "for": "1m",
                "keepFiringFor": "0s", "noDataState": "NoData",
                "execErrState": "Error", "isPaused": False}
    if any(rule.get(key) != value for key, value in expected.items()):
        raise ValueError("Unexpected rule identity, timing or state handling")
    if [q["refId"] for q in rule["data"]] != ["A", "B"]:
        raise ValueError("Expected query A followed by condition B")
    a, b = rule["data"]
    if (a["datasourceUid"] != "prometheus"
        or a["relativeTimeRange"] != {"from": 300, "to": 0}
        or a["model"]["datasource"] != {"type": "prometheus", "uid": "prometheus"}
        or a["model"]["refId"] != "A"
        or a["model"]["instant"] is not True or a["model"]["range"] is not False):
        raise ValueError("A must be an instant Prometheus query over five minutes")
    if (b["datasourceUid"] != "__expr__"
        or b["relativeTimeRange"] != {"from": 0, "to": 0}
        or b["model"]["datasource"] != {"type": "__expr__", "uid": "__expr__"}
        or b["model"]["refId"] != "B" or b["model"]["type"] != "threshold"
        or b["model"]["expression"] != "A"
        or b["model"]["conditions"] != [{"type": "query", "query": {"params": ["B"]},
            "reducer": {"type": "last", "params": []},
            "evaluator": {"type": "gt", "params": [5]}, "operator": {"type": "and"}}]):
        raise ValueError("B must evaluate the strict A > 5 threshold")
    pod = deployment["spec"]["template"]["spec"]
    volume = next(v for v in pod["volumes"] if v["name"] == "alerting")
    mount = next(m for m in pod["containers"][0]["volumeMounts"] if m["name"] == "alerting")
    if (volume["configMap"]["name"] != "grafana-alerting"
        or mount["mountPath"] != "/etc/grafana/provisioning/alerting"
        or mount.get("readOnly") is not True or "subPath" in mount):
        raise ValueError("Expected read-only alert provisioning directory mount")
    print("PASS: alert provisioning, A/B expression model, timing and state handling")


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
    validate_alerting(root, resources, deployment)
    print(f"PASS: {len(resources)} rendered resources fit secure-monitoring")
    print(f"PASS: checksum/config = {expected}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)

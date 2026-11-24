#!/usr/bin/env python3
"""Validate the W12-A.1 engine render and approved ownership boundaries."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap/argocd/control-plane"
VALUES = ROOT / "security/kyverno/values.yaml"
INVENTORY = ROOT / "docs/security/evidence/week12-engine-inventory.yaml"
REPORTING_ROLE = ROOT / "security/kyverno-reporting-rbac/reports-ephemeralcontainers.yaml"
REPORTING_BOOTSTRAP = BOOTSTRAP.parent / "opt-in/kyverno-reporting-rbac"
REPORTS_AGGREGATE = "kyverno:reports-controller"
CHART_REPO = "https://kyverno.github.io/kyverno/"
PLATFORM_REPO = "https://github.com/GoGPenguin/secure-agentic-platform.git"
DESTINATION = {"server": "https://kubernetes.default.svc", "namespace": "kyverno"}
CHART_SHA256 = "55961392dc0821eb367323f0e9585c061dd4407ef7ada921bd56ea1642c2a301"
CONTROLLERS = {
    "kyverno-admission-controller": 2,
    "kyverno-background-controller": 1,
    "kyverno-cleanup-controller": 1,
    "kyverno-reports-controller": 1,
}
CLUSTER_KINDS = {
    ("apiextensions.k8s.io", "CustomResourceDefinition"),
    ("rbac.authorization.k8s.io", "ClusterRole"),
    ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
}


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def output(*command):
    return subprocess.check_output(command, cwd=ROOT, text=True)


def kind_key(resource):
    api_version = resource["apiVersion"]
    group = api_version.rpartition("/")[0]
    return group, resource["kind"]


def validate_bootstrap():
    namespace, project, application = [
        yaml.safe_load((BOOTSTRAP / name).read_text())
        for name in ("kyverno-namespace.yaml", "secure-kyverno.yaml", "kyverno.yaml")
    ]
    for resource, kind, name, wave in (
        (namespace, "Namespace", "kyverno", "-2"),
        (project, "AppProject", "secure-kyverno", "-1"),
        (application, "Application", "kyverno", "1"),
    ):
        metadata = resource["metadata"]
        require(resource["kind"] == kind and metadata["name"] == name, f"Invalid {kind} identity")
        require(metadata["annotations"]["argocd.argoproj.io/sync-wave"] == wave, f"Invalid {kind} wave")
        require(metadata.get("namespace") == (None if kind == "Namespace" else "argocd"), f"Invalid {kind} namespace")
        require(not metadata.get("finalizers"), f"Unexpected {kind} finalizers")

    require(
        namespace["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false",
        "Namespace deletion protections missing",
    )
    require(not namespace["metadata"].get("labels"), "Unexpected Kyverno namespace labels")
    app = application["spec"]
    require(app["project"] == "secure-kyverno" and app["destination"] == DESTINATION, "Invalid app project or destination")
    require("source" not in app and app["sources"] == [
        {
            "repoURL": CHART_REPO,
            "chart": "kyverno",
            "targetRevision": "3.10.0",
            "helm": {
                "releaseName": "kyverno",
                "valueFiles": ["$platform/security/kyverno/values.yaml"],
                "kubeVersion": "1.37.0",
                "skipTests": True,
            },
        },
        {"repoURL": PLATFORM_REPO, "targetRevision": "main", "ref": "platform"},
    ], "Invalid engine source, chart pin or values reference")
    require(app["syncPolicy"] == {"syncOptions": [
        "CreateNamespace=false", "ServerSideApply=true",
        "FailOnSharedResource=true",
    ]}, "Engine sync must be manual and use the reviewed sync options")

    require("ignoreDifferences" not in app, "Engine must expose RBAC drift")

    root = yaml.safe_load((BOOTSTRAP.parent / "root.yaml").read_text())["spec"]
    require(root["source"]["path"] == "bootstrap/argocd/control-plane", "Root does not discover Kyverno bootstrap")
    project_spec = project["spec"]
    require(set(project_spec) == {
        "sourceRepos", "destinations", "clusterResourceWhitelist", "namespaceResourceWhitelist",
    }, "Unexpected AppProject settings")
    require(project_spec["sourceRepos"] == [CHART_REPO, PLATFORM_REPO], "AppProject repositories changed")
    require(project_spec["destinations"] == [DESTINATION], "AppProject destinations changed")
    return project_spec


def validate_render(resources, project):
    identities = [(kind_key(r), r["metadata"].get("namespace"), r["metadata"]["name"]) for r in resources]
    require(len(identities) == len(set(identities)), "Duplicate rendered resources")
    cluster = {kind for kind, namespace, _ in identities if namespace is None}
    namespaced = {kind for kind, namespace, _ in identities if namespace is not None}
    require(cluster == CLUSTER_KINDS, "Unexpected cluster-scoped kinds in engine render")
    for kinds, field in ((cluster, "clusterResourceWhitelist"), (namespaced, "namespaceResourceWhitelist")):
        allowlist = project[field]
        require(kinds == {(entry["group"], entry["kind"]) for entry in allowlist}
                and len(kinds) == len(allowlist), f"{field} must match the render exactly")
    require(all(namespace in (None, "kyverno") for _, namespace, _ in identities), "Resource escapes Kyverno namespace")

    by_kind = {}
    for resource in resources:
        by_kind.setdefault(resource["kind"], []).append(resource)
    require(set(by_kind) == {
        "CustomResourceDefinition", "ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding",
        "ServiceAccount", "ConfigMap", "Service", "Deployment", "PodDisruptionBudget", "Job",
    }, "Unexpected resource, policy or exception in engine render")

    for crd in by_kind["CustomResourceDefinition"]:
        annotations = crd["metadata"]["annotations"]
        require(annotations["argocd.argoproj.io/sync-wave"] == "-1"
                and annotations["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false",
                f"CRD ordering or protection missing for {crd['metadata']['name']}")
    for role in by_kind["ClusterRole"]:
        labels = role["metadata"].get("labels", {})
        require(not any(key.startswith("rbac.authorization.k8s.io/aggregate-to-") for key in labels),
                "Kyverno must not extend Kubernetes user-facing roles")
        if "aggregationRule" in role:
            require(not role.get("rules"), "The aggregation controller must own generated rules")
    validate_aggregation(by_kind["ClusterRole"], by_kind["ClusterRole"])
    accounts = {r["metadata"]["name"] for r in by_kind["ServiceAccount"]}
    for binding in by_kind["RoleBinding"] + by_kind["ClusterRoleBinding"]:
        require(all(s["kind"] == "ServiceAccount" and s["namespace"] == "kyverno" and s["name"] in accounts
                    for s in binding["subjects"]), f"Unexpected subject in {binding['metadata']['name']}")

    deployments = by_kind["Deployment"]
    require({r["metadata"]["name"]: r["spec"]["replicas"] for r in deployments} == CONTROLLERS,
            "Controller replica counts changed")
    admission = next(r["spec"] for r in deployments if r["metadata"]["name"] == "kyverno-admission-controller")
    affinity = admission["template"]["spec"]["affinity"]
    require(affinity["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"] == [
        {"matchExpressions": [{"key": "node-role.kubernetes.io/control-plane", "operator": "DoesNotExist"}]},
    ], "Admission must avoid the control plane")
    require(affinity["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"] == [{
        "labelSelector": {"matchLabels": admission["selector"]["matchLabels"]},
        "topologyKey": "kubernetes.io/hostname",
    }], "Admission replicas must be on distinct hosts")
    require(admission["strategy"] == {
        "type": "RollingUpdate", "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1},
    }, "Admission rollout requires a two-worker-compatible strategy")
    budgets = by_kind["PodDisruptionBudget"]
    require(len(budgets) == 1 and budgets[0]["spec"]["minAvailable"] == 1
            and budgets[0]["spec"]["selector"] == admission["selector"], "Admission PDB must select one ready replica")

    jobs = by_kind["Job"]
    require(len(jobs) == 1 and jobs[0]["metadata"]["name"] == "kyverno-check-legacy-policies", "Unexpected hook Job")
    for resource in resources:
        annotations = resource["metadata"].get("annotations") or {}
        if "helm.sh/hook" in annotations:
            require(annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
                    and "check-legacy-policies" in resource["metadata"]["name"], "Unexpected Helm hook")
    for resource in deployments + jobs:
        pod = resource["spec"]["template"]["spec"]
        require(pod["serviceAccountName"] in accounts, "Pod uses an unreviewed ServiceAccount")
        for container in pod.get("initContainers", []) + pod["containers"]:
            require(container["image"].startswith("reg.kyverno.io/kyverno/")
                    and container["image"].endswith(":v1.20.0"), f"Unpinned Kyverno image {container['image']}")
            for field in ("requests", "limits"):
                quantities = container["resources"][field]
                require(all(float(str(quantities[key]).removesuffix(unit)) > 0
                            for key, unit in (("cpu", "m"), ("memory", "Mi"))),
                        f"Missing positive {field} on {container['name']}")

    config = next(r["data"] for r in by_kind["ConfigMap"] if r["metadata"]["name"] == "kyverno")
    require(config["enableDefaultRegistryMutation"] == "false", "Default registry mutation must be off")
    require(json.loads(config["webhooks"])["namespaceSelector"]["matchExpressions"] == [
        {"key": "kubernetes.io/metadata.name", "operator": "NotIn", "values": [namespace]}
        for namespace in ("kube-system", "kyverno")
    ], "Unexpected webhook namespace exclusions")


def validate_reporting_rbac(role, project, application):
    require(role == {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {
            "name": "kyverno-reports-ephemeralcontainers",
            "labels": {"rbac.kyverno.io/aggregate-to-reports-controller": "true"},
            "annotations": {"argocd.argoproj.io/sync-options": "Prune=false"},
        },
        "rules": [{"apiGroups": [""], "resources": ["pods/ephemeralcontainers"],
                   "verbs": ["get", "list", "watch"]}],
    }, "Reporting extension must grant only get/list/watch on pods/ephemeralcontainers")
    require(project == {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AppProject",
        "metadata": {"name": "secure-kyverno-reporting-rbac", "namespace": "argocd"},
        "spec": {
            "sourceRepos": [PLATFORM_REPO],
            "destinations": [DESTINATION],
            "clusterResourceWhitelist": [{"group": "rbac.authorization.k8s.io", "kind": "ClusterRole"}],
            "namespaceResourceBlacklist": [{"group": "*", "kind": "*"}],
        },
    }, "Reporting AppProject must permit only ClusterRole from the reviewed repository")
    require(application == {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": "kyverno-reporting-rbac", "namespace": "argocd"},
        "spec": {
            "project": "secure-kyverno-reporting-rbac",
            "source": {"repoURL": PLATFORM_REPO, "targetRevision": "main",
                       "path": str(REPORTING_ROLE.parent.relative_to(ROOT)),
                       "directory": {"recurse": False, "include": REPORTING_ROLE.name}},
            "destination": DESTINATION,
            "syncPolicy": {"syncOptions": [
                "CreateNamespace=false", "ServerSideApply=true", "FailOnSharedResource=true", "Prune=false",
            ]},
        },
    }, "Reporting Application must be manual and limited to the single reviewed ClusterRole")


def validate_aggregation(reviewed_roles, observed_roles, *, live=False, reporting_role=None):
    """Check contributors and their effective rules against the pinned render."""
    reviewed = {r["metadata"]["name"]: r for r in reviewed_roles}
    observed = {r["metadata"]["name"]: r for r in observed_roles}

    def rules(role):
        return {
            json.dumps({key: sorted(values) for key, values in rule.items()}, sort_keys=True)
            for rule in role.get("rules", [])
        }

    for controller in CONTROLLERS:
        name = controller.replace("kyverno-", "kyverno:", 1)
        core = name + ":core"
        aggregation = reviewed[name]["aggregationRule"]
        require(observed.get(name, {}).get("aggregationRule") == aggregation,
                f"{name}: aggregation selectors changed")
        selectors = aggregation["clusterRoleSelectors"]
        require(all(set(selector) == {"matchLabels"} and selector["matchLabels"] for selector in selectors),
                f"{name}: unsupported aggregation selector")
        contributors = set()
        for candidate, role in observed.items():
            labels = role["metadata"].get("labels", {})
            if candidate != name and any(
                selector["matchLabels"].items() <= labels.items() for selector in selectors
            ):
                contributors.add(candidate)
        expected_contributors = {core}
        expected = rules(reviewed[core])
        require(rules(observed[core]) == expected, f"{core}: rules differ from the reviewed render")
        if name == REPORTS_AGGREGATE and reporting_role is not None:
            extension = reporting_role["metadata"]["name"]
            expected_contributors.add(extension)
            require(rules(observed.get(extension, {})) == rules(reporting_role),
                    f"{extension}: rules differ from the reviewed extension")
            expected |= rules(reporting_role)
        require(contributors == expected_contributors,
                f"{name}: unexpected contributors {sorted(contributors)}")
        if live:
            require(rules(observed[name]) == expected, f"{name}: effective rules differ from the reviewed union")


def make_inventory(resources):
    inventory = []
    for resource in resources:
        metadata = resource["metadata"]
        item = {"apiVersion": resource["apiVersion"], "kind": resource["kind"], "name": metadata["name"]}
        for field in ("namespace", "annotations", "labels"):
            if metadata.get(field) and (field != "labels" or resource["kind"] == "ClusterRole"):
                item[field] = metadata[field]
        for field in ("rules", "aggregationRule", "roleRef", "subjects", "automountServiceAccountToken"):
            if field in resource:
                item[field] = resource[field]
        if resource["kind"] in ("Deployment", "Job"):
            spec = resource["spec"]
            pod = spec["template"]["spec"]
            if "replicas" in spec:
                item["replicas"] = spec["replicas"]
            item["serviceAccountName"] = pod["serviceAccountName"]
            for field in ("initContainers", "containers"):
                if field in pod:
                    item[field] = [
                        {key: c[key] for key in ("name", "image", "resources", "args") if key in c} for c in pod[field]
                    ]
        if resource["kind"] == "CustomResourceDefinition":
            item["versions"] = [v["name"] for v in resource["spec"]["versions"] if v["served"]]
            item["storageVersion"] = next(v["name"] for v in resource["spec"]["versions"] if v["storage"])
        inventory.append(item)
    return sorted(inventory, key=lambda item: (item["kind"], item["name"]))


def validate_existing_workloads(base):
    protected = [
        "app-configs", "charts/web-app", "environments", "monitoring", "rbac",
        "bootstrap/argocd/root.yaml", "bootstrap/argocd/control-plane",
    ]
    allowed = {f"bootstrap/argocd/control-plane/{name}" for name in (
        "kyverno-namespace.yaml", "kyverno.yaml", "secure-kyverno.yaml",
    )}
    changed = output("git", "diff", "--no-renames", "--name-only", base, "--", *protected).splitlines()
    untracked = output("git", "ls-files", "--others", "--exclude-standard", "--", *protected).splitlines()
    require(not (set(changed + untracked) - allowed), "Existing workload, digest, RBAC or bootstrap inputs changed")
    print(f"PASS: Existing workload template inputs, image selections and GitOps controls match {base}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chart", type=Path, help="Downloaded official Kyverno Helm archive")
    parser.add_argument("--base", help="Compare protected workload and bootstrap inputs against this Git revision")
    parser.add_argument("--write-inventory", action="store_true", help="Regenerate the inventory for review")
    parser.add_argument("--clusterroles", type=Path,
                        help="Check a post-sync ClusterRoleList JSON export against the reviewed aggregation")
    parser.add_argument("--reporting-rbac-installed", action="store_true",
                        help="Expect the opt-in reporting role in the live aggregation export")
    args = parser.parse_args()
    require(not args.reporting_rbac_installed or args.clusterroles,
            "--reporting-rbac-installed requires --clusterroles")
    chart = args.chart.resolve()
    require(hashlib.sha256(chart.read_bytes()).hexdigest() == CHART_SHA256, "Wrong Kyverno chart archive checksum")
    metadata = yaml.safe_load(output("helm", "show", "chart", str(chart)))
    require((metadata["name"], metadata["version"], metadata["appVersion"]) == ("kyverno", "3.10.0", "v1.20.0"),
            "Wrong chart or application version")
    project = validate_bootstrap()
    reporting_role = yaml.safe_load(REPORTING_ROLE.read_text())
    validate_reporting_rbac(reporting_role, *[
        yaml.safe_load((REPORTING_BOOTSTRAP / name).read_text())
        for name in ("project.yaml", "application.yaml")
    ])
    root_source = yaml.safe_load((BOOTSTRAP.parent / "root.yaml").read_text())["spec"]["source"]
    require(root_source.get("directory", {}).get("recurse") is False
            and REPORTING_BOOTSTRAP.parent.name == "opt-in"
            and not any("kyverno-reporting-rbac" in path.read_text() for path in BOOTSTRAP.glob("*.yaml")),
            "Reporting extension must remain outside the root Application's source")
    rendered = output(
        "helm", "template", "kyverno", str(chart), "--namespace", "kyverno",
        "--kube-version", "1.37.0", "--include-crds", "--skip-tests", "-f", str(VALUES),
    )
    resources = list(filter(None, yaml.safe_load_all(rendered)))
    validate_render(resources, project)
    inventory = make_inventory(resources)
    if args.write_inventory:
        INVENTORY.write_text("# Generated by scripts/validate-kyverno.py --write-inventory.\n"
                             + yaml.safe_dump(inventory, sort_keys=False))
    require(yaml.safe_load(INVENTORY.read_text()) == inventory, "Rendered inventory or RBAC differs from reviewed evidence")
    print(f"PASS: Kyverno chart 3.10.0 / v1.20.0, GitOps boundaries and {len(resources)} rendered resources")
    roles = [r for r in resources if r["kind"] == "ClusterRole"]
    validate_aggregation(roles, [*roles, reporting_role], reporting_role=reporting_role)
    print("PASS: Opt-in reporting role adds only get/list/watch on pods/ephemeralcontainers")
    if args.clusterroles:
        snapshot = json.loads(args.clusterroles.read_text())
        require(snapshot.get("kind") in {"ClusterRoleList", "List"}
                and all(role.get("kind") == "ClusterRole" for role in snapshot["items"]),
                "Expected a complete ClusterRoleList JSON export")
        validate_aggregation(roles, snapshot["items"], live=True,
                             reporting_role=reporting_role if args.reporting_rbac_installed else None)
        print("PASS: Live-export aggregation contributors and effective rules match the reviewed render")
    if args.base:
        validate_existing_workloads(args.base)


if __name__ == "__main__":
    main()

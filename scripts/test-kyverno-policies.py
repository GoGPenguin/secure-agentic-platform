#!/usr/bin/env python3
"""Run the pinned Kyverno CLI against policy fixtures and current Helm renders."""

import argparse
import copy
import json
import os
from pathlib import Path

import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "security/kyverno-policies"
BOOTSTRAP = ROOT / "bootstrap/argocd"
NAMESPACE = "gitops-apps"
REPOSITORY = "https://github.com/GoGPenguin/secure-agentic-platform.git"
EXCLUDED = (
    "default", "kube-system", "kube-public", "kube-node-lease", "argocd",
    "kyverno", "psa-restricted-test", "monitoring", "gitops-apps-extra",
)
NON_ROOT = "require-non-root"
REGISTRY = "restrict-image-registries"
RESOURCES = "require-cpu-memory"
TAG = "disallow-latest-tag"
LABELS = "require-application-labels"
NAMES = (NON_ROOT, REGISTRY, RESOURCES, TAG, LABELS)
CONTROLLERS = ("Deployment", "DaemonSet", "ReplicaSet", "StatefulSet", "Job", "CronJob")
EPHEMERAL_POLICIES = {NON_ROOT, REGISTRY, TAG}
LABEL_KEYS = ("name", "instance", "managed-by")
IMAGE = "ghcr.io/gogpenguin/example:1.2"
DIGEST = "sha256:" + "a" * 64
REQUIREMENTS = {"requests": {"cpu": "10m", "memory": "16Mi"},
                "limits": {"cpu": "20m", "memory": "32Mi"}}


def pod(name, namespace=NAMESPACE):
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {f"app.kubernetes.io/{key}": "example" for key in LABEL_KEYS},
        },
        "spec": {
            "securityContext": {"runAsNonRoot": True, "runAsUser": 1000},
            "containers": [{"name": "app", "image": IMAGE, "resources": copy.deepcopy(REQUIREMENTS)}],
        },
    }


def workload(kind, resource):
    metadata = resource["metadata"]
    template = {"metadata": {"labels": metadata.get("labels", {})}, "spec": resource["spec"]}
    if kind in ("Job", "CronJob"):
        template["spec"]["restartPolicy"] = "Never"
    spec = {"template": template}
    if kind == "CronJob":
        spec = {"schedule": "0 * * * *", "jobTemplate": {"spec": spec}}
    if kind == "StatefulSet":
        spec["serviceName"] = "example"
    if kind not in ("Job", "CronJob"):
        spec["selector"] = {"matchLabels": {"app.kubernetes.io/name": "example"}}
    return {"apiVersion": "batch/v1" if kind in ("Job", "CronJob") else "apps/v1",
            "kind": kind, "metadata": metadata, "spec": spec}


def fixtures():
    yield pod("inherits-non-root"), set()
    for name, security, override, fails in (
        ("container-non-root", {}, {"runAsNonRoot": True}, False),
        ("unset-non-root", {}, {}, True),
        ("false-override", {"runAsNonRoot": True}, {"runAsNonRoot": False}, True),
        ("true-override", {"runAsNonRoot": False}, {"runAsNonRoot": True}, False),
        ("pod-uid-zero", {"runAsNonRoot": True, "runAsUser": 0}, {}, True),
        ("container-uid-zero", {"runAsNonRoot": True}, {"runAsUser": 0}, True),
        ("override-uid-zero", {"runAsNonRoot": True, "runAsUser": 0}, {"runAsUser": 1000}, False),
    ):
        resource = pod(name)
        resource["spec"]["securityContext"] = security
        resource["spec"]["containers"][0]["securityContext"] = override
        yield resource, {NON_ROOT} if fails else set()

    for name, image, failures in (
        ("docker-official", "docker.io/library/nginx:1.27", set()),
        ("registry-suffix", "ghcr.io.example.org/team/app:1.2", {REGISTRY}),
        ("registry-prefix", "example-ghcr.io/team/app:1.2", {REGISTRY}),
        ("docker-namespace-lookalike", "docker.io/library-extra/nginx:1.27", {REGISTRY}),
        ("docker-nested-repository", "docker.io/library/team/nginx:1.27", {REGISTRY}),
        ("docker-registry-alias", "registry-1.docker.io/library/nginx:1.27", {REGISTRY}),
        ("docker-legacy-alias", "index.docker.io/library/nginx:1.27", {REGISTRY}),
        ("docker-implicit-namespace", "docker.io/nginx:1.27", {REGISTRY}),
        ("other-registry-ghcr-path", "evil.example/ghcr.io/team/app:1.2", {REGISTRY}),
        ("ghcr-explicit-port", "ghcr.io:443/team/app:1.2", {REGISTRY}),
        ("mixed-case-registry", "GHCR.IO/team/app:1.2", {REGISTRY}),
        ("short-reference", "nginx:1.27", {REGISTRY}),
        ("implicit-latest-short", "nginx", {REGISTRY, TAG}),
        ("implicit-latest-qualified", "ghcr.io/team/app", {TAG}),
        ("explicit-latest", "ghcr.io/team/app:latest", {TAG}),
        ("digest-only", f"ghcr.io/team/app@{DIGEST}", set()),
        ("tag-and-digest", f"ghcr.io/team/app:1.2@{DIGEST}", set()),
        ("latest-and-digest", f"ghcr.io/team/app:latest@{DIGEST}", {TAG}),
        ("registry-port-is-not-tag", "ghcr.io:443/team/app", {REGISTRY, TAG}),
    ):
        resource = pod(name)
        resource["spec"]["containers"][0]["image"] = image
        yield resource, failures

    resource = pod("no-resources")
    del resource["spec"]["containers"][0]["resources"]
    yield resource, {RESOURCES}
    for section in REQUIREMENTS:
        for key in REQUIREMENTS[section]:
            resource = pod(f"no-{section}-{key}")
            del resource["spec"]["containers"][0]["resources"][section][key]
            yield resource, {RESOURCES}
    for key in LABEL_KEYS:
        resource = pod(f"no-label-{key}")
        del resource["metadata"]["labels"][f"app.kubernetes.io/{key}"]
        yield resource, {LABELS}
    resource = pod("empty-label")
    resource["metadata"]["labels"]["app.kubernetes.io/name"] = ""
    yield resource, {LABELS}
    resource = pod("no-label-map")
    del resource["metadata"]["labels"]
    yield resource, {LABELS}

    for field in ("initContainers", "ephemeralContainers"):
        ephemeral = field == "ephemeralContainers"
        for valid in (True, False):
            resource = pod(f"{field.lower()}-{'valid' if valid else 'invalid'}")
            container = {"name": "secondary", "image": IMAGE if valid else "nginx",
                         "securityContext": {"runAsUser": 1000 if valid else 0}}
            if not ephemeral and valid:
                container["resources"] = copy.deepcopy(REQUIREMENTS)
            resource["spec"][field] = [container]
            failures = {NON_ROOT, REGISTRY, TAG}
            if not ephemeral:
                failures.add(RESOURCES)
            yield resource, set() if valid else failures

    for kind in CONTROLLERS:
        yield workload(kind, pod(f"{kind.lower()}-valid")), set()
        resource = workload(kind, pod(f"{kind.lower()}-invalid"))
        spec = resource["spec"]
        template = (spec["jobTemplate"]["spec"] if kind == "CronJob" else spec)["template"]
        # Keep the controller's labels valid and violate the actual Pod template.
        template["metadata"]["labels"] = {"app.kubernetes.io/name": "example"}
        del template["spec"]["securityContext"]
        template["spec"]["containers"] = [{"name": "app", "image": "nginx"}]
        yield resource, set(NAMES)

    for namespace in EXCLUDED:
        resource = pod(f"excluded-{namespace}", namespace)
        resource["spec"] = {"containers": [{"name": "app", "image": "nginx"}]}
        del resource["metadata"]["labels"]
        yield resource, set()


def run_suite(cli, directory, cases, policy_paths, operation="CREATE", ephemeral_update=False):
    directory.mkdir()
    policy_files = [Path(shutil.copy(path, directory)).name for path in policy_paths]
    names = [Path(path).stem for path in policy_files]
    (directory / "resources.yaml").write_text(yaml.safe_dump_all(resource for resource, _ in cases))
    values = {
        "apiVersion": "cli.kyverno.io/v1alpha1",
        "kind": "Values",
        "metadata": {"name": "offline-values"},
        "globalValues": {"request.operation": operation},
        "namespaceSelector": [
            {"name": namespace, "labels": {"kubernetes.io/metadata.name": namespace}}
            for namespace in (NAMESPACE, *EXCLUDED)
        ],
    }
    if ephemeral_update:
        parent = {"kind": "Pod", "version": "v1", "name": "pods", "namespaced": True}
        values["subresources"] = [{
            "parentResource": parent,
            "subresource": dict(parent, name="pods/ephemeralcontainers"),
        }]
    (directory / "values.yaml").write_text(yaml.safe_dump(values))
    results = []
    for resource, failures in cases:
        for policy in names:
            excluded = resource["metadata"]["namespace"] in EXCLUDED
            if ephemeral_update and (operation != "UPDATE" or policy not in EPHEMERAL_POLICIES):
                excluded = True
            result = "skip" if excluded else "fail" if policy in failures else "pass"
            results.append({"policy": policy, "kind": resource["kind"],
                            "resources": [resource["metadata"]["name"]], "result": result})
    test = {
        "apiVersion": "cli.kyverno.io/v1alpha1",
        "kind": "Test",
        "metadata": {"name": directory.name},
        "policies": policy_files,
        "resources": ["resources.yaml"],
        "variables": "values.yaml",
        "results": results,
    }
    (directory / "kyverno-test.yaml").write_text(yaml.safe_dump(test))
    env = dict(os.environ, KUBECONFIG=os.devnull)
    process = subprocess.run(
        [cli, "test", str(directory), "--require-tests", "--remove-color"],
        env=env, capture_output=True, text=True,
    )
    return process, len(results)


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def check_configuration():
    paths = sorted(POLICIES.glob("*.yaml"))
    require({p.stem for p in paths} == set(NAMES), "Expected exactly the five named policies.")
    for path in paths:
        policy = yaml.safe_load(path.read_text())
        require(policy["apiVersion"] == "policies.kyverno.io/v1"
                and policy["kind"] == "ValidatingPolicy"
                and policy["metadata"]["name"] == path.stem
                and policy["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false"
                and policy["spec"]["validationActions"] == ["Audit"]
                and policy["spec"]["failurePolicy"] == "Ignore", f"Unexpected policy: {path}")
        rules = policy["spec"]["matchConstraints"]["resourceRules"]
        ephemeral_rules = [rule for rule in rules if "pods/ephemeralcontainers" in rule["resources"]]
        expected = [{"apiGroups": [""], "apiVersions": ["v1"], "operations": ["UPDATE"],
                     "resources": ["pods/ephemeralcontainers"]}] if path.stem in EPHEMERAL_POLICIES else []
        require(ephemeral_rules == expected, f"Unexpected ephemeral admission rule: {path}")

    opt_in = BOOTSTRAP / "opt-in/kyverno-policies"
    app = yaml.safe_load((opt_in / "application.yaml").read_text())
    project = yaml.safe_load((opt_in / "project.yaml").read_text())
    spec = app["spec"]
    require(spec["project"] == project["metadata"]["name"]
            and spec["source"]["repoURL"] == REPOSITORY
            and spec["source"]["targetRevision"] == "main"
            and spec["destination"] == {"server": "https://kubernetes.default.svc", "namespace": "kyverno"}
            and spec["source"]["path"] == str(POLICIES.relative_to(ROOT))
            and spec["source"]["directory"] == {"recurse": False}
            and spec["syncPolicy"] == {"syncOptions": [
                "CreateNamespace=false", "ServerSideApply=true", "FailOnSharedResource=true", "Prune=false"]}
            and "finalizers" not in app["metadata"]
            and "operation" not in app, "Policy Application must remain manual and non-pruning.")
    require(project["spec"] == {
        "sourceRepos": [spec["source"]["repoURL"]],
        "destinations": [spec["destination"]],
        "clusterResourceWhitelist": [{"group": "policies.kyverno.io", "kind": "ValidatingPolicy"}],
        "namespaceResourceBlacklist": [{"group": "*", "kind": "*"}],
    }, "Unexpected AppProject permissions.")
    for path in (BOOTSTRAP / "control-plane").glob("*.yaml"):
        require("kyverno-policies" not in path.read_text(), f"Opt-in policy configuration referenced by {path}")
    root = yaml.safe_load((BOOTSTRAP / "root.yaml").read_text())["spec"]["source"]
    require(root["path"] == "bootstrap/argocd/control-plane" and root["directory"]["recurse"] is False,
            "The opt-in Application must stay outside platform-root.")
    return paths


def helm_cases(helm):
    # Expected violations for the checked-in workloads, including manually run Helm test Pods.
    expected = {
        "backend": {NON_ROOT, REGISTRY, TAG},
        "frontend": {NON_ROOT, REGISTRY},
        "platform-api": {NON_ROOT},
        "sandbox": {NON_ROOT, REGISTRY},
    }
    for config_path in sorted((ROOT / "app-configs").glob("*.yaml")):
        config = yaml.safe_load(config_path.read_text())
        name = config["name"]
        rendered = subprocess.check_output(
            [helm, "template", name, "charts/web-app", "-n", config["namespace"],
             "-f", config["valuesFile"]], cwd=ROOT, text=True,
        )
        for resource in yaml.safe_load_all(rendered):
            if resource and resource["kind"] in ("Deployment", "Pod"):
                resource["metadata"].setdefault("namespace", config["namespace"])
                failures = expected[name] if resource["kind"] == "Deployment" else {
                    NON_ROOT, REGISTRY, RESOURCES, TAG,
                }
                yield resource, failures


def verify(process, count):
    summary = f"Test Summary: {count} tests passed and 0 tests failed"
    require(process.returncode == 0 and summary in process.stdout, process.stdout + process.stderr)
    print(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kyverno", default="kyverno")
    parser.add_argument("--helm", default="helm")
    args = parser.parse_args()
    version = subprocess.check_output([args.kyverno, "version"], text=True)
    require(version.splitlines()[0] == "Version: v1.20.0", "Kyverno CLI v1.20.0 is required.")
    paths = check_configuration()
    cases = list(fixtures())
    ephemeral_cases = [case for case in cases if "ephemeralContainers" in case[0]["spec"]]
    with tempfile.TemporaryDirectory(prefix="kyverno-policies-") as tmp:
        directory = Path(tmp)
        for operation in ("CREATE", "UPDATE"):
            print(f"Policy fixtures ({operation})")
            verify(*run_suite(args.kyverno, directory / operation.lower(), cases, paths, operation))
            print(f"Ephemeral-container subresource ({operation})")
            verify(*run_suite(args.kyverno, directory / f"ephemeral-{operation.lower()}",
                              ephemeral_cases, paths, operation, ephemeral_update=True))
        print("Current Helm renders")
        renders = list(helm_cases(args.helm))
        verify(*run_suite(args.kyverno, directory / "helm-renders", renders, paths))
        print(json.dumps({resource["metadata"]["name"]: sorted(failures)
                          for resource, failures in renders}, indent=2))

        # A deliberately permissive expression must cause the real negative test to fail.
        for path in paths:
            policy = yaml.safe_load(path.read_text())
            policy["spec"]["validations"][0]["expression"] = "true"
            mutated = directory / path.name
            mutated.write_text(yaml.safe_dump(policy))
            case = next(case for case in cases if path.stem in case[1])
            process, _ = run_suite(args.kyverno, directory / f"mutation-{path.stem}", [case], [mutated])
            require(process.returncode != 0 and "0 tests passed and 1 tests failed" in process.stdout,
                    f"Mutation was not detected for {path.stem}\n{process.stdout}{process.stderr}")
            print(f"Detected permissive mutation in {path.stem}")


if __name__ == "__main__":
    main()

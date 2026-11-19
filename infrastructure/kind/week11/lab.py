"""Create or verify only the Week 11 kind lab."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import yaml


NAME = "secure-platform-w11-netpol"
CONTEXT = f"kind-{NAME}"
PROTECTED_CONTEXT = "kind-secure-platform"
KUBECONFIG = Path(__file__).resolve().with_name("week11.kubeconfig")
CONFIG = KUBECONFIG.with_name("cluster.yaml")
KIND_VERSION = "v0.33.0"
KUBERNETES_VERSION = "v1.37.0"
NODE_IMAGE = (
    "docker.io/kindest/node:v1.37.0@sha256:"
    "a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
)
KINDNET_IMAGE = "docker.io/kindest/kindnetd:v20260820-69b56db7"
KINDNET_ID = "sha256:4626fe10df5b930638e6e1662143ee1c7a698de6174fdb61a8ce658e688be2cd"
NODE_ROLES = {
    f"{NAME}-control-plane": "control-plane",
    f"{NAME}-worker": "worker",
    f"{NAME}-worker2": "worker",
}
GIB = 1024**3

ENV = dict(os.environ, KUBECONFIG=str(KUBECONFIG), DOCKER_CONTEXT="default",
           KIND_EXPERIMENTAL_PROVIDER="docker")
for variable in ("DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "KIND_CLUSTER_NAME"):
    ENV.pop(variable, None)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(*command):
    return subprocess.check_output(command, env=ENV, text=True).strip()


def validate_config():
    require(CONTEXT != PROTECTED_CONTEXT, "Protected cluster context")
    expected = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "name": NAME,
        "networking": {"apiServerAddress": "127.0.0.1", "disableDefaultCNI": False},
        "nodes": [{"role": role, "image": NODE_IMAGE} for role in NODE_ROLES.values()],
    }
    require(yaml.safe_load(CONFIG.read_text()) == expected, "Unexpected kind lab configuration")


def preflight():
    for tool in ("kind", "docker", "kubectl"):
        require(shutil.which(tool), f"Missing required tool: {tool}")
    require(run("kind", "version").split()[1] == KIND_VERSION, f"Use kind {KIND_VERSION}")
    run("kubectl", "version", "--client", "-o", "json")
    endpoint = run("docker", "context", "inspect", "default", "--format",
                   '{{(index .Endpoints "docker").Host}}')
    require(endpoint == "unix:///var/run/docker.sock", "Use the local Linux Docker daemon")
    info = json.loads(run("docker", "info", "--format", "{{json .}}"))
    require(info["OSType"] == "linux" and info["Architecture"] in ("x86_64", "amd64"),
            "This image identity check requires local Linux amd64 Docker")
    return info


def check_capacity(info):
    require(min(info["NCPU"], len(os.sched_getaffinity(0))) >= 4, "Need at least 4 CPUs")
    available = int(re.search(r"^MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text(),
                              re.MULTILINE)[1]) * 1024
    require(min(info["MemTotal"], available) >= 4 * GIB, "Need at least 4 GiB available RAM")
    require(shutil.disk_usage(info["DockerRootDir"]).free >= 10 * GIB,
            "Need at least 10 GiB free on the Docker storage filesystem")


def kubectl(*args):
    return run("kubectl", "--kubeconfig", str(KUBECONFIG), "--context", CONTEXT,
               "--request-timeout=130s", *args)


def verify():
    require(KUBECONFIG.is_file() and not KUBECONFIG.is_symlink(),
            "Expected a standalone lab kubeconfig file")
    config = json.loads(run("kubectl", "--kubeconfig", str(KUBECONFIG),
                            "config", "view", "-o", "json"))
    require(config.get("current-context") == CONTEXT
            and [entry["name"] for entry in config.get("contexts", [])] == [CONTEXT]
            and [entry["name"] for entry in config.get("clusters", [])] == [CONTEXT]
            and config["contexts"][0]["context"]["cluster"] == CONTEXT,
            "Refusing protected or unexpected kubeconfig context")
    require(set(run("kind", "get", "nodes", "--name", NAME).splitlines()) == NODE_ROLES.keys(),
            "Unexpected kind lab node containers")
    binding = run("docker", "port", f"{NAME}-control-plane", "6443/tcp")
    cluster = config["clusters"][0]["cluster"]
    require(re.fullmatch(r"127\.0\.0\.1:\d+", binding)
            and cluster["server"] == f"https://{binding}"
            and not cluster.get("insecure-skip-tls-verify")
            and not cluster.get("proxy-url"),
            "Kubeconfig must use TLS and the lab container's loopback port")

    for node, role in NODE_ROLES.items():
        container = json.loads(run("docker", "inspect", "--type", "container", node))[0]
        spec = container["Config"]
        require(spec["Labels"].get("io.x-k8s.kind.role") == role
                and spec["Image"].removeprefix("docker.io/") == NODE_IMAGE.removeprefix("docker.io/"),
                f"{node}: unexpected kind role or node image")
        print(f"{node}: {role}, {spec['Image']}, local image ID {container['Image']}")

    kubectl("wait", "--for=condition=Ready", "node", "--all", "--timeout=120s")
    nodes = json.loads(kubectl("get", "nodes", "-o", "json"))["items"]
    require({node["metadata"]["name"] for node in nodes} == NODE_ROLES.keys(),
            "Unexpected Kubernetes node inventory")
    for node in nodes:
        metadata = node["metadata"]
        control_plane = "node-role.kubernetes.io/control-plane" in metadata["labels"]
        require(control_plane == (NODE_ROLES[metadata["name"]] == "control-plane")
                and node["status"]["nodeInfo"]["kubeletVersion"] == KUBERNETES_VERSION,
                f"{metadata['name']}: unexpected Kubernetes role or version")
    version = json.loads(kubectl("version", "-o", "json"))["serverVersion"]["gitVersion"]
    require(version == KUBERNETES_VERSION, f"Unexpected API server version: {version}")

    kubectl("-n", "kube-system", "rollout", "status", "daemonset/kindnet", "--timeout=120s")
    daemonset = json.loads(kubectl("-n", "kube-system", "get", "ds", "kindnet", "-o", "json"))
    require([container["image"] for container in daemonset["spec"]["template"]["spec"]["containers"]]
            == [KINDNET_IMAGE], "Unexpected Kindnet DaemonSet image")
    pods = json.loads(kubectl("-n", "kube-system", "get", "pods", "-l", "app=kindnet", "-o", "json"))["items"]
    require(len(pods) == 3 and {pod["spec"]["nodeName"] for pod in pods} == NODE_ROLES.keys(),
            "Expected one Kindnet Pod per lab node")
    for pod in pods:
        states = pod["status"]["containerStatuses"]
        require(len(states) == 1 and states[0]["ready"]
                and states[0]["imageID"] == KINDNET_ID,
                f"{pod['metadata']['name']}: unexpected Kindnet readiness or image ID")
        print(f"{pod['spec']['nodeName']}: {KINDNET_IMAGE}, runtime image ID {states[0]['imageID']}")
    print(f"Verified {CONTEXT}: {version}, one control plane, two workers, Kindnet on all nodes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "preflight", "create", "verify"))
    args = parser.parse_args()
    validate_config()
    if args.action == "validate":
        print("PASS: fixed lab name, loopback API, pinned three-node topology, default CNI enabled")
        return

    info = preflight()
    exists = NAME in run("kind", "get", "clusters").splitlines()
    kubeconfig_exists = os.path.lexists(KUBECONFIG)
    require(exists == kubeconfig_exists, "Lab cluster name or kubeconfig conflict; inspect manually")
    if not exists:
        containers = run("docker", "ps", "-a", "--format", "{{.Names}}").splitlines()
        require(NODE_ROLES.keys().isdisjoint(containers), "Lab node container name conflict")
    if args.action == "preflight":
        require(not exists, "Lab already exists; use verify")
        check_capacity(info)
        print("PASS: tools, local Docker, lab name, kubeconfig path, and host capacity")
        return

    if not exists:
        require(args.action == "create", "Lab is absent")
        check_capacity(info)
        os.umask(0o077)
        subprocess.run(
            ["kind", "create", "cluster", "--name", NAME, "--config", str(CONFIG),
             "--kubeconfig", str(KUBECONFIG), "--wait", "5m", "--retain"],
            env=ENV, check=True,
        )
    verify()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Week 11 lab: {error}") from error

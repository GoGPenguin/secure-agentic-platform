#!/usr/bin/env python3
"""Validate the inactive Week 11 policy bundle against local inputs."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft4Validator, ValidationError
import yaml


ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "security/network-policy"
SCHEMA_SHA256 = "465276aedf437726de5a6ed23a41b86d78bb0d347edf251a755ae26a93cdd8a6"
APP = "gitops-apps"
MON = "monitoring"
NAME = "app.kubernetes.io/name"
INSTANCE = "app.kubernetes.io/instance"
API = {NAME: "web-app", INSTANCE: "platform-api"}
PROM = {NAME: "prometheus"}
GRAFANA = {NAME: "grafana"}


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate YAML mapping key")
        return super().construct_mapping(node, deep=deep)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_yaml(path):
    return yaml.safe_load(path.read_text())


def rule(peer_key, labels, ports, namespace=None):
    peer = {"podSelector": {"matchLabels": labels}}
    if namespace:
        peer["namespaceSelector"] = {"matchLabels": {"kubernetes.io/metadata.name": namespace}}
    return {peer_key: [peer], "ports": [{"protocol": protocol, "port": port} for protocol, port in ports]}


def expected_policies():
    scrape = [("TCP", 3000)]
    query = [("TCP", 9090)]
    dns = [("UDP", 53), ("TCP", 53)]
    return {
        **{(namespace, "default-deny"): {
            "podSelector": {}, "policyTypes": ["Ingress", "Egress"], "ingress": [], "egress": [],
        } for namespace in (APP, MON)},
        (MON, "prometheus-egress-to-platform-api"): {
            "podSelector": {"matchLabels": PROM}, "policyTypes": ["Egress"],
            "egress": [rule("to", API, scrape, APP)],
        },
        (APP, "platform-api-ingress-from-prometheus"): {
            "podSelector": {"matchLabels": API}, "policyTypes": ["Ingress"],
            "ingress": [rule("from", PROM, scrape, MON)],
        },
        (MON, "grafana-egress-to-prometheus-and-dns"): {
            "podSelector": {"matchLabels": GRAFANA}, "policyTypes": ["Egress"],
            "egress": [rule("to", PROM, query), rule("to", {"k8s-app": "kube-dns"}, dns, "kube-system")],
        },
        (MON, "prometheus-ingress-from-grafana"): {
            "podSelector": {"matchLabels": PROM}, "policyTypes": ["Ingress"],
            "ingress": [rule("from", GRAFANA, query)],
        },
    }


def validate_policies(documents, schema):
    remaining = expected_policies()
    for document in documents:
        schema.validate(document)
        require(isinstance(document, dict) and document.get("kind") == "NetworkPolicy"
                and document.get("apiVersion") == "networking.k8s.io/v1",
                "Expected networking.k8s.io/v1 NetworkPolicy")
        metadata = document.get("metadata", {})
        identity = (metadata.get("namespace"), metadata.get("name"))
        require(identity in remaining, f"Unexpected or duplicate policy {identity}")
        require(set(document) == {"apiVersion", "kind", "metadata", "spec"}
                and set(metadata) == {"namespace", "name"}, f"Unexpected fields in {identity}")
        require(document["spec"] == remaining.pop(identity),
                f"{identity}: selectors, directions, peers or ports differ from the approved traffic matrix")
    require(not remaining, f"Missing policies: {list(remaining)}")


def includes_labels(labels, selector):
    return all(labels.get(key) == value for key, value in selector.items())


def pod_template(deployment):
    return deployment["spec"]["template"]


def has_tcp_port(deployment, port):
    return any(
        entry["containerPort"] == port and entry.get("protocol", "TCP") == "TCP"
        for container in pod_template(deployment)["spec"]["containers"]
        for entry in container.get("ports", [])
    )


def validate_workloads():
    api_targets = []
    for path in sorted((ROOT / "app-configs").glob("*.yaml")):
        app = load_yaml(path)
        if app["namespace"] != APP:
            continue
        rendered = subprocess.check_output(
            ["helm", "template", app["name"], str(ROOT / "charts/web-app"),
             "-n", APP, "-f", str(ROOT / app["valuesFile"])], text=True,
        )
        for workload in yaml.safe_load_all(rendered):
            if workload and workload["kind"] == "Deployment":
                labels = pod_template(workload)["metadata"]["labels"]
                if includes_labels(labels, API):
                    api_targets.append((app["name"], workload))
    require(len(api_targets) == 1 and api_targets[0][0] == "platform-api"
            and has_tcp_port(api_targets[0][1], 3000), "Expected only Platform API to match on TCP 3000")

    for name, selector, port in (("prometheus", PROM, 9090), ("grafana", GRAFANA, 3000)):
        deployment = load_yaml(ROOT / f"monitoring/{name}/deployment.yaml")
        labels = pod_template(deployment)["metadata"]["labels"]
        require(deployment["metadata"]["namespace"] == MON
                and includes_labels(labels, selector) and has_tcp_port(deployment, port),
                f"{name}: Deployment labels, namespace or listener drifted")

    service = load_yaml(ROOT / "monitoring/prometheus/service.yaml")
    require(service["metadata"]["namespace"] == MON and service["spec"]["selector"] == PROM
            and any(port["port"] == 9090 and port.get("protocol", "TCP") == "TCP"
                    and port["targetPort"] == "http" for port in service["spec"]["ports"]),
            "Prometheus Service destination drifted")
    datasources = load_yaml(ROOT / "monitoring/grafana/config/datasources.yaml")["datasources"]
    require(any(source["type"] == "prometheus" and source["access"] == "proxy"
                and source["url"] == "http://prometheus.monitoring.svc.cluster.local:9090"
                for source in datasources), "Grafana datasource destination drifted")

    config = load_yaml(ROOT / "monitoring/prometheus/configmap.yaml")
    jobs = yaml.safe_load(config["data"]["prometheus.yml"])["scrape_configs"]
    scrape = next(job for job in jobs if job["job_name"] == "platform-api")
    require(scrape["kubernetes_sd_configs"] == [{
        "role": "pod", "namespaces": {"names": [APP]},
        "selectors": [{"role": "pod", "label": f"{NAME}=web-app,{INSTANCE}=platform-api"}],
    }], "Prometheus API scrape discovery drifted")


def negative_tests(documents, schema):
    mutations = (
        ("bad schema field type", 0, lambda doc: doc["spec"].update(podSelector="all")),
        ("wrong namespace", 0, lambda doc: doc["metadata"].update(namespace="argocd")),
        ("unrestricted ingress", 0, lambda doc: doc["spec"].update(ingress=[{}])),
        ("unintended direction", 0, lambda doc: doc["spec"].update(policyTypes=["Ingress"])),
        ("unrestricted egress", 2, lambda doc: doc["spec"].update(egress=[{}])),
        ("wrong selected Pods", 2, lambda doc: doc["spec"].update(podSelector={})),
        ("missing namespace peer", 2, lambda doc: doc["spec"]["egress"][0]["to"][0].pop("namespaceSelector")),
        ("unintended backend destination", 2, lambda doc: doc["spec"]["egress"][0]["to"][0]
         ["podSelector"]["matchLabels"].update({INSTANCE: "backend"})),
        ("wrong port", 2, lambda doc: doc["spec"]["egress"][0]["ports"][0].update(port=443)),
        ("missing DNS TCP", 4, lambda doc: doc["spec"]["egress"][1]["ports"].pop()),
    )
    for label, index, change in mutations:
        candidate = deepcopy(documents)
        change(candidate[index])
        try:
            validate_policies(candidate, schema)
        except (ValueError, ValidationError):
            print(f"PASS: rejected {label}")
        else:
            raise ValueError(f"Negative test passed validation: {label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--swagger", required=True, type=Path, help="Local Kubernetes v1.37.0 swagger.json")
    parser.add_argument("--negative-tests", action="store_true")
    args = parser.parse_args()
    content = args.swagger.read_bytes()
    require(hashlib.sha256(content).hexdigest() == SCHEMA_SHA256, "Unexpected Kubernetes schema checksum")
    definitions = json.loads(content)["definitions"]
    # Kubernetes Swagger v2 encodes IntOrString as a string with a custom format.
    port = definitions["io.k8s.apimachinery.pkg.util.intstr.IntOrString"]
    require(port["format"] == "int-or-string", "Unexpected NetworkPolicy port schema")
    port["type"] = ["integer", "string"]
    schema = Draft4Validator({
        "definitions": definitions,
        "allOf": [{"$ref": "#/definitions/io.k8s.api.networking.v1.NetworkPolicy"}],
    })
    documents = [
        document
        for path in sorted(POLICIES.iterdir(), reverse=True)
        if path.suffix in {".yaml", ".yml"}
        for document in yaml.load_all(path.read_text(), Loader=UniqueKeyLoader)
    ]
    validate_policies(documents, schema)
    validate_workloads()
    print(f"PASS: {len(documents)} policies match Kubernetes v1.37.0 schema and the Week 11 traffic matrix")
    print("PASS: application Helm renders and monitoring configuration match workload selectors and listeners")
    if args.negative_tests:
        negative_tests(documents, schema)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, StopIteration, TypeError, ValueError, OSError, yaml.YAMLError,
            ValidationError, subprocess.CalledProcessError) as error:
        sys.exit(f"ERROR: {error}")

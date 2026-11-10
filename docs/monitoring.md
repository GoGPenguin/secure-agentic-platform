# Prometheus validation and ownership

`platform-root` owns the `prometheus` Application resource in `argocd`.
The child `prometheus` Application owns the Deployment, Service, ConfigMap,
and ServiceAccount in `monitoring`. Root health does not prove child health.

## Configuration changes

`checksum/config` in the Deployment Pod template is SHA-256 of the decoded
ConfigMap `data["prometheus.yml"]` UTF-8 bytes, including its trailing newline.
It does not hash the surrounding Kubernetes YAML.

Run `python3 scripts/validate-prometheus-config.py` with PyYAML 6.0.3 installed.
If the checksum differs, the command fails and prints the required hash. Update
the Deployment annotation alongside the configuration and run the check again.
The validator never updates the checksum automatically.

The `Monitoring Validation` CI job checks the checksum and runs `promtool check
config` from the Deployment's image. Require this check in branch protection
before relying on it to block merges. A syntactically valid configuration can
still have a stale checksum; promtool alone cannot detect that condition.

Without a changed Pod-template checksum, updating the ConfigMap does not trigger
a rollout. The projected file eventually updates, but this deployment does not
enable automatic reload. Prometheus continues using its previously loaded
configuration until it is reloaded or restarted.

## Storage and security

The process runs as UID/GID 65534. Kubernetes applies `fsGroup: 65534` to the
`emptyDir` mounted at `/prometheus`, providing group access to the data volume.
The image directory's ownership is hidden by this mount and is not sufficient
on its own. Root filesystem read-only does not make this separate volume
read-only. Configuration is mounted read-only at `/etc/prometheus`.

TSDB files and the active query tracker are stored under `/prometheus`; no
additional writable directory is required by the current configuration.
Pod replacement loses the metrics history. Self-scraping requires no Kubernetes
API token, so token automount remains disabled.

## Verification after GitOps deployment

Check the two Applications independently:

```bash
argocd app get platform-root
argocd app get prometheus
kubectl -n monitoring rollout status deployment/prometheus
kubectl -n monitoring exec deployment/prometheus -- /bin/sh -c 'id; ls -ld /prometheus; test -w /prometheus'
kubectl -n monitoring port-forward svc/prometheus 9090:9090
```

In another terminal, verify `http://localhost:9090/-/ready` and query
`up{job="prometheus"}`; expect exactly one target with value `1`.
These checks establish runtime behavior beyond Argo CD resource sync status.

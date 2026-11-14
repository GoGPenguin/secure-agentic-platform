# Week 10 isolated live PSA admission evidence

Result: **PASS — 5/5 expected admission outcomes; post-test safeguards PASS**.
Week 10 is not complete. Runtime testing has not been performed.

Context: `kind-secure-platform`; API server: `v1.37.0` (emulation minor 37).
Cluster endpoint: `https://127.0.0.1:44663`. Test Namespace:
`psa-restricted-test`, UID `c521f403-17ee-4cdf-aeee-df08457e8d05`.
Observed timestamps and cluster/namespace identities are recorded in the JSON
files linked below. No secrets, credentials, container environment literals,
ConfigMap contents, or credential-bearing kubeconfig were recorded.

## Safety and exact cluster changes

The read-only preflight confirmed the exact current context, cluster identity,
server version, eight expected Argo CD Applications Synced/Healthy, six expected
Deployments fully updated/available, and all workload Pods Running/Ready. A
separate namespace GET returned explicit NotFound. Existing namespace identities
and PSA labels matched the reviewed baseline; no existing namespace needed changes.

The only persistent resource creation requested by this session was:

```sh
kubectl --context kind-secure-platform --request-timeout=10s create \
  -f security/psa-test/namespace.yaml -o json
```

The manifest was verified locally to contain exactly one Namespace and its six
approved labels before submission. It now has:

```yaml
pod-security.kubernetes.io/enforce: restricted
pod-security.kubernetes.io/enforce-version: v1.37
pod-security.kubernetes.io/warn: restricted
pod-security.kubernetes.io/warn-version: v1.37
pod-security.kubernetes.io/audit: restricted
pod-security.kubernetes.io/audit-version: v1.37
```

Kubernetes also added its `kubernetes.io/metadata.name: psa-restricted-test` label.
The normal namespace-initialization resources `ServiceAccount/default` and
`ConfigMap/kube-root-ca.crt` were observed with the same creation timestamp. These
are namespace initialization side effects, not resources directly created by this
session. Only metadata was inventoried; no token was requested. No RBAC,
AppProject, Application, Deployment, Helm release, monitoring resource or existing
namespace was modified. No Argo CD sync/refresh or workload restart was requested.
The test namespace is retained; no cleanup/deletion was performed.

## Admission outcomes

The existing guarded runner was executed without modification:

```sh
python3 -B scripts/test-psa-admission.py --run --context kind-secure-platform
```

It checked all namespace policy labels, submitted only strict-validation
server-side dry-run Pod requests, and exited **0**. Fixture and runner hashes,
stdout, stderr and exact diagnostics are in the admission JSON.

| Fixture | Actual result | Relevant reason |
| --- | --- | --- |
| compliant | PASS: allowed, exit 0 | `created (server dry run)` |
| privileged | PASS: rejected, exit 1 | `privileged`, `allowPrivilegeEscalation != false` |
| missing-allow-privilege-escalation | PASS: rejected, exit 1 | `allowPrivilegeEscalation != false` |
| missing-drop-all | PASS: rejected, exit 1 | `unrestricted capabilities`; drop ALL required |
| invalid-seccomp | PASS: rejected, exit 1 | `seccompProfile`; container Unconfined forbidden |

All four denials explicitly reported `violates PodSecurity "restricted:v1.37"`
and the expected control details. None was an authentication, RBAC, connectivity,
invalid schema or unrelated webhook failure. No negative was unexpectedly accepted.
The privileged/escalation pair is intentional: the API disallows privileged true
with escalation false. No test Pod was persisted.

## Before/after health comparison

| Check | Before | After |
| --- | --- | --- |
| Argo CD Applications | 8/8 Synced/Healthy | 8/8 Synced/Healthy |
| Frontend replicas | 2/2 ready/available | 2/2 ready/available |
| Backend replicas | 1/1 ready/available | 1/1 ready/available |
| Sandbox replicas | 1/1 ready/available | 1/1 ready/available |
| Platform API replicas | 1/1 ready/available | 1/1 ready/available |
| Prometheus replicas | 1/1 ready/available | 1/1 ready/available |
| Grafana replicas | 1/1 ready/available | 1/1 ready/available |
| Existing workload Pods | 7 Running/Ready | Same identities, readiness and restart counts |
| Deployment specs/templates | Baseline SHA-256 recorded | All hashes identical |
| Deployment generations / ReplicaSets | Baseline recorded | Identical; no unexpected rollout observed |
| Existing namespace identities/labels | Baseline recorded | Identical, including all PSA labels |
| Test namespace | NotFound | Present with approved labels; zero persisted Pods |

Exact equality checks covered all captured Deployment state/spec/template hashes,
ReplicaSet identities/revisions/templates/replicas, Pod UIDs/readiness/restart
counts and existing namespace labels/UIDs. The new Namespace UID and all its
labels also match the verified creation response. These are point-in-time
comparisons, not continuous monitoring or independent HTTP functionality tests.

## Deviations and limits

A local evidence recorder initially selected the historical baseline with an
incorrect list index and raised StopIteration. The failed recording attempt is
retained and annotated. No safety prerequisite failed and no write was made
before the recorder was corrected and the read-only preflight passed. There was
no unexpected cluster behavior or admission result, and no unresolved blocker
for a separately approved isolated runtime test.

This proves the five tested admission outcomes in this context/namespace at the
recorded time. It does not prove complete PSS coverage, application startup,
image pulls, seccomp runtime compatibility, filesystem behavior, probes, network
connectivity, or audit-log collection. Warn/audit label configuration was verified;
audit records were not inspected. Results do not establish the absence of other
admission configuration or exemptions elsewhere.

Recommendation: **GO for separately authorized hardened Platform API runtime
testing in this isolated namespace**, preserving current production workloads.
The runtime test must verify the selected digest, non-root process identity,
startup/readiness/liveness and metrics under the opt-in settings. It has not been
started. This recommendation does not authorize applying the shared chart to
existing workloads, production namespace enforcement, or a GitOps sync. No commit
or PR was created; local changes in this session are evidence files only.

## Evidence files

- [Safety preflight](week10-live-preflight.json)
- [Namespace creation and verification](week10-live-namespace.json)
- [Guarded runner results and rejection reasons](week10-live-admission.json)
- [Post-test health and template comparison](week10-live-posttest.json)
- [Namespace initialization metadata](week10-live-namespace-generated-resources.json)
- [Initial local recording error, preserved](week10-live-preflight-recording-attempt.json)

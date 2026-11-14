# Week 10 Phase 1: opt-in Pod Security Restricted

**Current delivery status (2026-11-14):** W10-A passed 5/5 and W10-B passed
22/22 in the authorized isolated lab. The lab is retained. Production chart sync
and merging rollout-bearing changes remain unauthorized. See the
[delivery review](week10-delivery-review.md) and [complete evidence index](week10-evidence-index.md).
The Phase 1 narrative and NOT-RUN statements below describe their original phase;
they are not the current lab state. An evidence-only delivery intentionally keeps
the implementation candidate out of main; source-dependent commands below require
that candidate and should not be treated as delivered-main instructions. Do not recreate the existing namespace or
rerun persistent create commands without fresh scoped authorization.


Status: locally implemented and statically validated, awaiting review. Week 10 is
not complete. No Kubernetes resources were applied, deleted, restarted, or
server-dry-run during Phase 1. No PR or commit was created. A read-only version
query was the only cluster operation. Local Docker ran only `id` to verify an
image identity, not an application or cluster workload.
The subsequent [final review](week10-final-review.md) adds read-only GET/LIST
preflight evidence and supersedes the initial rollout analysis below.

## Baseline and design

All four existing applications share `gitops-apps`. Frontend and sandbox render
`nginx:1.16.0` on port 80; backend renders `httpd:latest` on port 80. They have no
declared Pod/container securityContext. Their filesystem permissions, low-port
listeners and startup scripts need compatibility testing before non-root use.
Changing containerPort alone does not change an image's listener configuration.
The existing sandbox is not an isolated namespace.

The API listens on 3000, uses a digest-pinned image, and its Dockerfile declares
`USER node`. Its production values disable ServiceAccount token automount.
Prometheus and Grafana already declare the main Restricted controls, with
non-root identities, RuntimeDefault seccomp, dropped capabilities and no privilege
escalation. Prometheus intentionally mounts its token for namespace-scoped
discovery. Monitoring, production values, RBAC and AppProjects are unchanged.
Effective live namespace policy, PSA exemptions and current workload health were
not inspected in this phase; repository configuration is not proof of live state.

The chart adds `podSecurityContext` and `securityContext`, defaulting to empty
maps. Empty maps emit nothing. Both apply to the Deployment and the Helm
connection-test Pod. `connectionTest.automountServiceAccountToken` is optional;
when absent the existing test Pod is unchanged. Schema validation checks types
for the exposed security fields. It allows other Kubernetes securityContext
fields for extensibility; it is not a full Kubernetes API schema or a policy
engine. Valid but non-Restricted values such as `privileged: true` remain allowed
by the chart; only the separate validator rejects them. This is opt-in support,
not global enforcement.

Chart version moves from 0.2.0 to 0.2.1; appVersion stays 1.16.0. The initial
Phase 1 comparison found chart-version labels inside the Deployment Pod template.
The final review removes only `helm.sh/chart` from that template. Top-level
resource chart/version/managed-by metadata and selectors remain intact.
Images, replicas, ports, probes, resources, Services and ServiceAccounts are
preserved. Removing an existing Pod-template label is itself **one migration
rollout on first adoption**. Future chart-version-only upgrades no longer change
the Pod template (tested with 0.2.1 versus synthetic 0.2.2). Do not sync this chart
to existing workloads under a zero-restart requirement. Nothing has been synced.
See [initial evidence](evidence/week10-phase1-static.json) and the
[final four-application comparison](evidence/week10-final-render-comparison.json).

## Hardened API overlay and identity evidence

Use both files, in this order:

```sh
helm template platform-api charts/web-app -n psa-restricted-test \
  -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml
```

The overlay inherits the existing API digest, port, probes, resources, replicas
and SA configuration; it is not standalone. It sets non-root execution, UID/GID
1000, RuntimeDefault seccomp, no privilege escalation, drop ALL capabilities,
and disables token automount for both the API SA and independent Helm test Pod.
There is no global change to existing values.

On 2026-11-14, Docker inspect of the exact selected digest reported user `node`
and the matching RepoDigest. The following isolated local command returned
`uid=1000(node) gid=1000(node) groups=1000(node)`:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint /usr/bin/id \
  ghcr.io/gogpenguin/secure-agentic-platform/platform-api@sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421
```

These IDs are verified, not assumed from a base-image convention. Reverify
identity before changing the inherited API digest. Fixtures intentionally use
that same digest; tests detect divergence. The busybox connection-test Pod
inherits an explicitly forced numeric identity of 1000; this is not a claim
about busybox's default user. Its existing unpinned image remains unchanged for
backward compatibility and its hardened runtime behavior is not yet verified.

Read-only root filesystems, fsGroup and extra writable volumes are not required
by Restricted and are not added. The local `id` command does not prove API
startup, seccomp compatibility, probe behavior or application functionality.

## Namespace ownership and version selection

`security/psa-test/namespace.yaml` is operator-managed lab configuration. It and
the fixtures are outside all current Argo CD sources and ApplicationSet file
patterns. Do not put a test app in `app-configs/`: secure-platform currently
permits only `gitops-apps`. No existing AppProject or RBAC boundary is expanded.
The namespace is not a tenant security boundary or network isolation mechanism.

On 2026-11-14, context `kind-secure-platform`,
`kubectl version -o json --request-timeout=10s` reported server
`v1.37.0`, minor 37 and emulation minor 37. All three PSA policy versions are
therefore pinned to `v1.37`; none use latest. The initial sandboxed query failed
to access the local socket; a permitted read-only retry succeeded. Recheck the
intended context/server before deployment, especially because kind node images
are not pinned. Stop and review version labels if the cluster changes.

Only the lab namespace receives enforce/warn/audit Restricted labels. Existing
`gitops-apps`, `monitoring`, `argocd` and system namespaces are untouched. Before
creating the namespace, establish it is unused; do not adopt an existing namespace
or attach resource-tracking metadata by hand. A future persistent GitOps lab
requires a separately reviewed narrow project/Application and one namespace owner.

## Credential-free validation

Prerequisites: Helm (tested with v4.3.1), Python 3 and the existing PyYAML
dependency (CI pins 6.0.3). No cluster credentials or new dependency family is
needed. From repository root:

```sh
python3 -B scripts/test-pod-security.py
helm lint charts/web-app -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml
set -o pipefail
helm template platform-api charts/web-app -n psa-restricted-test \
  -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml \
  | python3 -B scripts/check-pod-security.py
python3 -B scripts/check-rbac.py
python3 -B scripts/test-rbac-checks.py
python3 -B scripts/validate-prometheus-config.py
python3 -B scripts/validate-grafana-config.py
```

The Helm CI job runs these new security tests and the hardened render checker.
It already gates API publishing. It does not acquire cluster credentials.
Tests lint/render defaults and all existing profiles, assert absent contexts in
legacy renders, compare hardened resources to the API baseline after removing
only the intended settings, and exercise schema errors, all fixture exit codes,
container inheritance/overrides, Deployment templates, init/ephemeral containers
and empty input. Negative fixtures remain valid Helm/Kubernetes field shapes:
Unconfined is a valid Kubernetes seccomp type but is invalid under Restricted.

### Checker boundary

This is a focused regression checker, **not complete PSS validation**. Maintained
engines such as [Kyverno's CLI](https://kyverno.io/docs/subprojects/kyverno-cli/)
and its [PSS policies](https://kyverno.io/docs/guides/pod-security/) are preferable
if a full credential-free PSS gate becomes required. Neither Kyverno nor
Kubewarden CLI is installed locally. Phase 1 avoids introducing a policy engine
dependency or copying the complete, version-sensitive PSS specification. Before
claiming complete coverage, select and pin a maintained engine and policy bundle
verified to support the chosen Kubernetes minor, or use Kubernetes' upstream PSA
library. No complete-coverage claim is made here.

The focused checker handles Linux Pod and Deployment objects only. It checks
effective non-root and seccomp inheritance, explicit false/root overrides,
allowPrivilegeEscalation false, privileged false/absent, drop ALL, and capability
additions limited to NET_BIND_SERVICE. It rejects empty input/no supported
workloads and reports malformed input. It examines normal, init and ephemeral
containers. RuntimeDefault and correctly specified Localhost are accepted;
the supplied hardened profile uses RuntimeDefault.

It does **not** cover host namespaces/ports/paths, all volume restrictions,
AppArmor, SELinux, procMount, sysctls, newer version-specific controls, Windows,
other workload kinds, full API field/schema correctness, admission exemptions,
mutating webhooks, image vulnerabilities, actual UIDs/filesystem permissions or
runtime behavior. Passing these tests is static evidence only. In particular,
passing Helm lint/template is not server schema or admission validation.
Reference: [Kubernetes PSS](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

## Recorded local results

The initial six security test groups passed, including all fixture exit codes, Helm/schema
cases and inheritance/override regressions. The hardened render passed the focused
checker. Defaults and all four existing profile comparisons passed with only
chart-version label differences. Existing static RBAC validation and four checker
regression tests passed; both monitoring validators passed. Workflow YAML parsed,
local Docker actionlint passed, and git diff --check passed. API unit/E2E/build
checks were not rerun because API source, dependencies and Dockerfile did not
change. No actual admission, Pod scheduling or application startup was tested.
The final review expands this to ten test groups, including rollout stability,
fixture isolation and live-error classification without sending any requests.

## Proposed live admission procedure — NOT RUN in Phase 1

Review and authorize cluster writes separately. First inspect the intended
context/version and establish the lab namespace does not already exist. A
connection/RBAC error is not evidence of absence:

```sh
kubectl config current-context
kubectl version -o json --request-timeout=10s
kubectl get namespace psa-restricted-test --request-timeout=10s
```

Proceed only after confirming NotFound, the intended cluster and compatible
v1.37 policy support. Creating a Namespace is a real write. A dry-run Namespace
does not establish a namespace in which to test Pod admission:

```sh
kubectl create -f security/psa-test/namespace.yaml
kubectl get namespace psa-restricted-test --show-labels
kubectl create --dry-run=server -f security/psa-test/pods/compliant.yaml
```

The compliant request must exit 0. Each of these must exit nonzero specifically
because of PodSecurity Restricted, rather than authorization, schema, network or
other admission failures:

```sh
kubectl create --dry-run=server -f security/psa-test/pods/privileged.yaml
kubectl create --dry-run=server -f security/psa-test/pods/missing-allow-privilege-escalation.yaml
kubectl create --dry-run=server -f security/psa-test/pods/missing-drop-all.yaml
kubectl create --dry-run=server -f security/psa-test/pods/invalid-seccomp.yaml
```

| Fixture | Expected admission result |
| --- | --- |
| compliant | Allowed |
| privileged | Denied: privileged container and its necessarily enabled privilege escalation |
| missing-allow-privilege-escalation | Denied: allowPrivilegeEscalation not false |
| missing-drop-all | Denied: unrestricted capabilities |
| invalid-seccomp | Denied: container Unconfined overrides Pod RuntimeDefault |

Use the guarded runner after the namespace is separately created and testing is
authorized. It reads and verifies all six namespace PSA labels, then submits only
Pod server-dry-runs with strict validation in the explicit context:

```sh
python3 -B scripts/test-psa-admission.py --run --context kind-secure-platform
```

The runner distinguishes PSA rejection, authentication/authorization, connectivity,
invalid resource schema and other failures. Negative success requires a nonzero
exit, the exact `restricted:v1.37` PSA marker and intended control names in the
violation details, not merely a Forbidden response or fixture name. An unexpectedly
accepted negative request fails. Its classifier is tested locally in CI; the live
runner was not executed during this review.

The privileged fixture uses `allowPrivilegeEscalation: true`: false together with
privileged true is API-invalid. Its two expected, causally related PSA violations
are privileged and allowPrivilegeEscalation. The other three negatives differ
from the compliant Pod only in their intended security control (plus name).
See [upstream API validation](https://github.com/kubernetes/kubernetes/blob/master/pkg/apis/core/validation/validation.go).

To exercise the actual rendered API Pod template and Helm test Pod as well,
without persisting workloads:

```sh
set -o pipefail
helm template platform-api charts/web-app -n psa-restricted-test \
  -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml \
  --show-only templates/deployment.yaml \
  | python3 -c 'import sys,yaml; d=yaml.safe_load(sys.stdin); print(yaml.safe_dump({"apiVersion":"v1","kind":"Pod","metadata":{"name":"rendered-api","namespace":"psa-restricted-test"},"spec":d["spec"]["template"]["spec"]}))' \
  | kubectl create --dry-run=server -f -
helm template platform-api charts/web-app -n psa-restricted-test \
  -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml \
  --show-only templates/tests/test-connection.yaml \
  | kubectl create --dry-run=server -n psa-restricted-test -f -
```

These requests must exit 0. Deployment dry-run alone is insufficient: PSA enforce
checks actual Pods. Capture version, namespace labels, stdout/stderr, exit codes
and expected rejection reason per request. All-PASS dry-runs are still not image
pull, startup, connectivity, probes or runtime evidence. Warn/audit label presence
does not prove audit-log collection. No fixture should be persisted to obtain a
negative result. Reference: [Kubernetes PSA](https://kubernetes.io/docs/concepts/security/pod-security-admission/).

## Compatibility risks and rollback

API runtime startup under the new settings, image availability on target nodes,
the busybox test identity and cluster PSA exemptions remain unverified. Future
API digest changes require renewed numeric identity verification. Prometheus
discovers only gitops-apps; do not expand its RBAC to scrape this lab. Monitoring
rollouts can lose emptyDir data and are outside Phase 1 scope.

Before deployment there is no cluster rollback to perform. Review/revert the
Phase 1 patch if needed; remove the overlay from a render command to recover the
existing manifest behavior. Do not change production values to consume it.
After any future deployment, reconcile workload changes through their actual
owner; Argo CD self-healing can undo manual patches. Restore the prior chart
revision to restore chart-version labels as well, accepting that this would
cause another rollout. Do not delete/recreate existing workloads.

If a later lab-only policy rollback is necessary, first record the previous
labels, then restore them on **psa-restricted-test only** using its chosen owner.
The Phase 1 lab is operator-managed, so deleting its source file would not remove
live labels. No deletion command or automatic cleanup is included. Any eventual
lab namespace cleanup is a separately reviewed destructive action. Existing
production namespaces, RBAC and AppProjects must remain unchanged.

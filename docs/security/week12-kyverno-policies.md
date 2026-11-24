# Week 12 Kyverno Audit policy readiness

The five policies are implemented and verified offline. The Audit rollout still
requires runtime acceptance. The current workload renders contain violations
that block a move to Deny.

## Policy contracts

| Policy | Contract |
| --- | --- |
| `require-non-root` | Each container must effectively set `runAsNonRoot: true`. Container fields take precedence over their Pod-level counterparts independently. An effective UID of 0 fails even with `runAsNonRoot: true`. If UID is omitted, the kubelet checks the image user at startup. |
| `restrict-image-registries` | Require an explicit `ghcr.io/` host or a single repository component under `docker.io/library/`. Short references, registry aliases and lookalikes, nested Docker Hub repositories, alternate Docker Hub namespaces and explicit registry ports fail. This allowlist permits any GHCR owner and does not attest to image provenance. |
| `require-cpu-memory` | Each regular and init container must contain CPU and memory keys in both requests and limits. This checks presence. Kubernetes validates the quantity syntax and request/limit relationships. |
| `disallow-latest-tag` | Require an explicit tag other than `latest`, or a digest. `latest` fails even when accompanied by a digest. A registry port does not count as a tag. Version tags may still be mutable. |
| `require-application-labels` | Require nonempty `app.kubernetes.io/name`, `app.kubernetes.io/instance` and `app.kubernetes.io/managed-by` on direct Pods and on the Pod template of each controller. Labels on the controller alone do not satisfy the policy. |

The namespace selector uses the Kubernetes-managed `kubernetes.io/metadata.name`
label and matches only `gitops-apps`. System namespaces, `default`, `argocd`,
`kyverno`, `monitoring`, the retained `psa-restricted-test` lab, and every other
namespace are outside the scope. Every application in `gitops-apps` is covered,
including `sandbox` and any manually created Helm test Pods.

The policies match Pod, Deployment, DaemonSet, ReplicaSet, StatefulSet, Job
and CronJob CREATE and UPDATE requests. They validate regular and init
containers. The non-root, registry and tag policies also match
`pods/ephemeralcontainers` UPDATE requests and validate ephemeral containers.
The resource policy omits ephemeral containers because Kubernetes disallows
resources on them. The label policy checks the Pod and its template metadata.

The manifests use the cluster-scoped `policies.kyverno.io/v1` ValidatingPolicy
API, with admission evaluation and background scans enabled by the API
defaults. `Audit` records findings and permits noncompliant requests.
`failurePolicy: Ignore` limits the effect of evaluation errors for these new
policies during observation. Monitor those errors directly because they can hide
findings. [Kyverno ValidatingPolicy](https://kyverno.io/docs/policy-types/validating-policy/) ·
[Kyverno policy reports](https://kyverno.io/docs/guides/reports/)

## Application compatibility

The pinned CLI evaluated the current Helm renders in their configured
namespace. The table describes the declared Pod templates. Live reports may
differ due to admission-time mutation, defaults, installed revisions or
resources that Helm does not render.

| Application or resource | Rendered image | Non-root | Registry | CPU/memory | Tag | Labels |
| --- | --- | --- | --- | --- | --- | --- |
| Backend Deployment | `httpd:latest` | Fail | Fail | Pass | Fail | Pass |
| Frontend Deployment | `nginx:1.16.0` | Fail | Fail | Pass | Pass | Pass |
| Platform API Deployment | `ghcr.io/gogpenguin/secure-agentic-platform/platform-api@sha256:…` | Fail | Pass | Pass | Pass | Pass |
| Sandbox Deployment | `nginx:1.16.0` | Fail | Fail | Pass | Pass | Pass |
| Each connection-test Pod, if run | `busybox` | Fail | Fail | Fail | Fail | Pass |

The four Deployments omit `runAsNonRoot`. Any later remediation needs to verify
that each image and entrypoint works with the chosen non-root UID, including
listening ports and writable paths. Backend needs a pinned image reference.
Frontend, sandbox and all test Pods need qualified registry references. The
test Pods also need CPU/memory declarations and an explicit version or digest.
These findings are expected during Audit.

## GitOps and rollout prerequisites

The opt-in AppProject and Application live under
[`bootstrap/argocd/opt-in/kyverno-policies`](../../bootstrap/argocd/opt-in/kyverno-policies/),
outside the nonrecursive `platform-root` source and the workload ApplicationSet.
The project permits this repository, the in-cluster `kyverno` destination and
only cluster-scoped ValidatingPolicy objects. It denies namespaced resources
and grants no Kubernetes RBAC. The child reads only the policy directory.
Sync is manual, uses server-side apply, fails on shared resources, and disables
pruning at the Application and resource levels. [Argo CD sync options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/)

For a later approved rollout, verify the Kyverno v1.20.0 engine Application
and its admission and reports controllers are healthy. Require
`validatingpolicies.policies.kyverno.io` to be Established and serve `v1`.
Confirm policy report API discovery, a working webhook path, and Argo CD's
authority to read and apply ValidatingPolicy objects. The child uses normal
dry-run discovery, so the CRD must be in place before synchronization.
Check for ownership conflicts and compare the Argo render with the five
reviewed Audit manifests. Record the current workload Application health,
deployed image digests, Pod identities and restarts, and monitoring health.
## Activation procedure after approval

The platform owner and security policy owner must explicitly approve the Audit
rollout and identify the reviewed commit on `main`. A merge by itself only
publishes the files. The cluster operator creates the opt-in objects from a
checkout of the approved commit, in this order:

```bash
kubectl --context kind-secure-platform apply -f bootstrap/argocd/opt-in/kyverno-policies/project.yaml
kubectl --context kind-secure-platform apply -f bootstrap/argocd/opt-in/kyverno-policies/application.yaml
```

Before syncing, confirm the Application destination and compare the rendered
objects at the approved commit with the reviewed manifests. Then use the Argo
CD UI to sync only `kyverno-policies` at that commit with Force and Prune
unchecked. The AppProject and Application registration leave the policies
pending manual synchronization.

## Runtime acceptance

1. Confirm Argo reports a successful sync of exactly five ValidatingPolicy
   objects and that Kyverno reports them ready, with no compile, webhook or
   report-controller errors. Confirm the resource webhook covers the
   `pods/ephemeralcontainers` UPDATE path for the applicable policies.
2. In a disposable rehearsal environment, submit compliant and violating
   fixtures with CREATE and UPDATE, including a Pod, Deployment, Job, CronJob
   and the ephemeral-container subresource. Both compliant and violating
   requests should be admitted in Audit when the fixture meets existing
   admission controls. Verify the expected policy report results on persisted
   fixtures and absence of these findings in excluded namespaces. Use
   fixtures compatible with any existing PSA.
3. On the intended cluster, verify background reports settle and reconcile
   observed findings with the compatibility matrix. Investigate missing
   reports and evaluation errors before accepting Audit. Compare application
   health, workload images, Pod identities and restarts against the baseline.
   Check Platform API readiness and Prometheus/Grafana health.

## Audit-to-Deny, exceptions and recovery

Assign owners to the observed findings, remediate workload templates and
manually exercised hooks in separate changes, and rerun the compatibility
suite with the updated expectations. Observe Audit through a representative
release and replacement cycle. Require unexplained violations and evaluation
errors to reach zero. In a disposable cluster, test compliant releases, failed
admissions, ephemeral debugging and rollback. Promote one policy at a time in a
separately reviewed change. Review `failurePolicy` as part of each promotion
because fail-open behavior can mask errors and fail-closed behavior can affect
availability.

A PolicyException can exempt matching workloads from current or future
validation and can hide violations if it uses broad name or namespace
patterns. Any future exception needs a narrowly identified subject, named
policy, owner, expiry, documented compensating control, RBAC review and
coverage for matching and nonmatching resources. This bundle contains zero
PolicyException objects.

If a rollout blocks expected admission, stop further policy syncs and capture
the affected request, policy status, reports and controller logs. Use the
policy Application to return the affected policy to its approved Audit
revision and verify recovery with a representative admission request. If
withdrawal is needed, remove only the specifically approved policy objects and
verify webhook and report convergence. Git removal alone retains live
objects because pruning is disabled. Leave the engine, its CRDs and existing
admission controls in service.

## Offline evidence

See the [recorded validation output](evidence/week12-policy-validation.txt).
To reproduce with the pinned Kyverno CLI v1.20.0, Helm v4.3.1 and
PyYAML 6.0.3:

```bash
python3 scripts/test-kyverno-policies.py --kyverno /path/to/kyverno
```

The CI job verifies the CLI archive checksum before extraction. It generates
isolated Kyverno test inputs from the fixtures and Helm renders, runs without
cluster or registry credentials, and fails on mismatched expectations, missing
tests, or an undetected permissive mutation. The offline run did not exercise
live webhook registration, Kubernetes admission, or background report
generation. [Kyverno CLI](https://kyverno.io/docs/subprojects/kyverno-cli/)

# Week 12 closure

**Audit runtime acceptance passed on Machine B on 2026-11-24.** The accepted
Git revision was `88db5fbb7f246416b14bba7645f779659284ddf3`. Machine A and
Machine B are independent Kubernetes environments that share this repository.
Machine A's earlier W12-A.2 outcome is separate. Machine B's records use its
own API endpoint, CA fingerprint and `kube-system` UID.

## Architecture and GitOps ownership

| Component | Ownership and activation | Change |
| --- | --- | --- |
| Kyverno engine v1.20.0, Helm chart 3.10.0 | `platform-root` automatically reconciles the Namespace, `secure-kyverno` AppProject and `kyverno` child. The engine itself is opt-in through a full manual sync with the PreSync guard, server-side apply and pruning disabled. | [PR #29](https://github.com/GoGPenguin/secure-agentic-platform/pull/29) |
| Five Audit ValidatingPolicies | `kyverno-policies` owns only the policy directory. Its `secure-kyverno-policies` AppProject permits ValidatingPolicy resources. Both registration manifests are outside the root source path. Sync is manual and non-pruning. | [PR #30](https://github.com/GoGPenguin/secure-agentic-platform/pull/30) |
| Reporting RBAC extension | `kyverno-reporting-rbac` owns one standalone ClusterRole. Its dedicated AppProject permits the ClusterRole kind, and the Application includes only the reviewed file. Registration and sync are explicit, manual steps outside the root source path. | [PR #31](https://github.com/GoGPenguin/secure-agentic-platform/pull/31) |
| Readiness reconciliation | A project-owned annotation changed metadata on three existing policy objects through their existing Application. | [PR #32](https://github.com/GoGPenguin/secure-agentic-platform/pull/32) |

The five policies apply in `gitops-apps`. They require effective non-root
execution, approved image references, explicit non-latest tags or digests,
CPU and memory requests and limits, and nonempty application labels. The
[policy runbook](week12-kyverno-policies.md) records the exact contracts and
controller coverage.

Kyverno checks matched resource access for the reports ServiceAccount with
an empty namespace. Three policies required permissions on
`pods/ephemeralcontainers`. The standalone role adds only cluster-wide
`get`, `list` and `watch` for that subresource through the existing reports
aggregate and binding. The admission controller's grants stayed unchanged.
Authorization was effective before the readiness conditions recovered.
Kyverno's policy-status reconciler responds to policy update events and has
no direct ClusterRole watch. The metadata-only sync gave the three policies
new resourceVersions and triggered re-evaluation. Their UIDs, generations,
specs and Audit actions stayed unchanged. [Reporting RBAC runbook](week12-kyverno-reporting-rbac.md)

## Evidence and CI

| Stage | Machine B result |
| --- | --- |
| Engine | The repo-server render matched 73 reviewed objects. All four PreSync resources succeeded, 22 CRDs became Established, two admission replicas were Ready on separate workers, and background, cleanup and reports were each 1/1 Ready. Ten webhook configurations registered. Endpoint TLS and a non-persisting admission dry-run passed. |
| Audit | All three Kyverno Applications reached Synced/Healthy. All five policies were Ready with `RBACPermissionsGranted=True` and `WebhookConfigured=True`, and no PolicyExceptions existed. The 18 background reports contained 90 results. Each of the four Deployment reports matched the compatibility matrix. |
| Ephemeral admission | Both server-side dry-run patches were admitted. The compliant request produced three passes. The noncompliant request produced three failures and three admission Events correlated to the fixture UID. Neither persisted an ephemeral container. UID-preconditioned deletion removed only the fixture. |
| Platform stability | Existing Applications stayed healthy. Deployment templates, Pod identities, image IDs, readiness and restart counts matched their baselines. The Platform API digest stayed `sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421`. |

The pinned CLI passed 690 policy assertions and detected all five permissive
mutations. The reporting RBAC suite passed 11 tests. The final main-branch
workflow passed all seven jobs, including the pinned engine render, Audit
tests, RBAC, Helm, monitoring, Platform API CI and publishing. [Final main CI](https://github.com/GoGPenguin/secure-agentic-platform/actions/runs/45380852028)

Raw Machine B execution evidence is stored locally in the workspace. The
paths below are relative to `docs/security/evidence/`.

- `week12-machine-b-engine/acceptance.md` and `sync-operation.json`
- `week12-machine-b-policies/result.md` and `compatibility-comparison.txt`
- `week12-machine-b-reporting-rbac/result.md` and `readiness-diagnosis/result.md`
- `week12-machine-b-policies/readiness-refresh/result.md`
- `week12-machine-b-policies/ephemeral-admission/result.md` and `final-verdict.json`

## Remaining risks and next milestone

All four deployed application templates fail non-root. Backend, frontend
and sandbox fail the registry check, and backend also fails the latest-tag
check. All four pass resources and labels. If run, the existing Helm test Pods
would also fail non-root, registry, resources and tag checks. Keep Audit while
owners fix and verify those templates, including image startup under the
chosen UID. A later Deny rollout needs separate approval and a staged recovery
test.

The registry allowlist accepts any GHCR owner and supplies no provenance
assurance. A non-latest tag can still be mutable. The reporting identity has
cluster-wide read authorization on the named subresource, while the policy
selector restricts evaluations to `gitops-apps`. The Audit webhook fails
open on call errors. The two admission replicas span workers that share a kind
host and a single control plane. The dry-run test established admission
evaluation and non-persistence. Background reports remain a separate path.

The next recommended milestone is the **Week 11 isolated NetworkPolicy
rehearsal**. Determine the Kubernetes API destination and port the CNI
actually evaluates, validate a narrow egress rule by discovering a newly
created target, then test the full allow/deny matrix, DNS and monitoring paths.
The bundle remains inactive on Machine B. Week 10 production migration remains
separate and [PR #26](https://github.com/GoGPenguin/secure-agentic-platform/pull/26)
was untouched. [Week 11 runbook](week11-network-policy.md)

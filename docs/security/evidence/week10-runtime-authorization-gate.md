# Platform API isolated runtime deployment authorization gate

Recommendation: GO for separately authorized lab runtime deployment and tests.
No persistent resources were created in this preparation phase. Week 10 remains
incomplete; the deployment authorization gate has not been crossed.

Proposed namespace: psa-restricted-test (existing, unchanged). Proposed creates:
ServiceAccount/platform-api-psa, Service/platform-api-psa (ClusterIP port 3000),
Deployment/platform-api-psa (one replica, with controller-created lab ReplicaSet
and Pod). No existing resource is targeted. No Helm release installation/upgrade,
GitOps synchronization, RBAC or monitoring changes are proposed. The separately
rendered hook Pod was inspected and dry-run only; it is excluded from persistent
creation.

The exact image remains
`ghcr.io/gogpenguin/secure-agentic-platform/platform-api@sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421`.
Security: verified numeric UID/GID 1000, runAsNonRoot true, RuntimeDefault seccomp,
allowPrivilegeEscalation false, drop ALL, dedicated SA token automount false.
Ports, probes and resource requests/limits match existing API values.

Validation PASS: Helm lint/schema/template, focused security checker, ten security
test groups, four existing application renders byte-identical to this phase's
baseline, static RBAC and monitoring validators, strict server-side dry-runs of
all four generated resources (no warnings), artifact hash consistency and
whitespace checks. Cluster context/version/policy and lab conflict checks passed.

Before and after: eight Applications Synced/Healthy, six existing Deployments
fully available, existing Deployment spec/template hashes and generations,
ReplicaSets, Pod identities/restart counts and namespace labels unchanged.
Lab inventory unchanged; no lab Pods, Services or Deployments were persisted.
No safety deviation or current blocker was observed.

Runtime identity, CapEff/CapPrm/CapBnd/CapAmb, NoNewPrivs, seccomp filtering,
startup, probes and HTTP endpoints are NOT TESTED. Deployment dry-run does not
admit its eventual controller Pod or create its SA. The hook Pod dry-run is
actual Pod admission with the existing default SA and disabled automount.
Do not treat these results as runtime success or complete PSS coverage.

Reviewed artifacts and future commands:
[lab runbook](../../../security/psa-test/platform-api-runtime.md),
[proposed three resources](../../../security/psa-test/rendered/platform-api-lab.yaml),
[hook, excluded from deployment](../../../security/psa-test/rendered/platform-api-hook.yaml).

Evidence:
- [Preflight](week10-runtime-preflight.json)
- [Render identity, inventory and hashes](week10-runtime-render.json)
- [Static validation](week10-runtime-static-validation.json)
- [Four existing render comparisons](week10-runtime-existing-render-comparison.json)
- [Exact server dry-run commands and output](week10-runtime-server-dry-run.json)
- [Post-validation health/state](week10-runtime-postvalidation.json)

Stop here pending separate authorization. No commit or PR was created.

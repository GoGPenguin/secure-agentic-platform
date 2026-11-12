# Week 9: Kubernetes RBAC and namespace boundaries

## Security objectives and architecture

Provide explicit read-only grants without changing workloads, monitoring discovery, image digests, or existing AppProjects. RBAC is additive: these manifests cannot revoke permissions granted by other bindings. The test suite checks effective authorization, including inherited grants, rather than assuming these Roles are the entire policy.

Implementation: [manifests](../../rbac/), [dedicated AppProject](../../bootstrap/argocd/control-plane/secure-rbac.yaml), [Application](../../bootstrap/argocd/control-plane/platform-rbac.yaml), [machine-readable expectations](authorization-matrix.json), [checker](../../scripts/check-rbac.py), [checker regression tests](../../scripts/test-rbac-checks.py).

Developer (`w09:developer`) can read Pods, logs, Services, Deployments and ReplicaSets in `gitops-apps`. Get/list/watch permits read-only rollout inspection. No monitoring access is required or granted.

Security Auditor (`w09:auditor`) can read Pods, Services, ServiceAccounts, Deployments, ReplicaSets, Roles and RoleBindings in both namespaces. Reading ServiceAccounts does not grant token issuance or Secret access. Logs are unnecessary for auditing metadata and are denied.

CI (`w09:ci`, test-only name) has no Role or RoleBinding. Inspection of `.github/workflows/platform-ci.yaml` found builds, Helm/configuration validation, tests and GHCR publishing; no cluster operation requires credentials. GitHub's temporary publishing token is unrelated to Kubernetes authentication. Argo CD remains the deployment actor.

## Authentication assumptions

The three usernames simulate identities through trusted administrator impersonation. A RoleBinding does not create a human account or authenticate anyone. No ServiceAccounts, tokens, Secrets or kubeconfigs are created. Production human access requires an external identity provider and reviewed mapping to individual users/groups; CI continues without Kubernetes credentials. Do not map shared production credentials to these demonstration usernames.

Tests impersonate each user plus `system:authenticated` to include standard authenticated-user defaults. Other production IdP groups are not simulated. The trusted caller needs `impersonate` on the three specific `users` names and the `groups` name `system:authenticated`, plus normal discovery and authorization-review access. Use an already authorized local test administrator. Never add impersonation to the personas. Preflight checks these four impersonation permissions before any assertions; transport/review errors fail the run and cannot count as Deny. An administrative kubeconfig is a property of the test invoker, not a grant to a tested persona.

## Required operations and implemented grants

`A` = explicit Allow; `D` = no grant (expected Deny). Columns show the intended implemented policy, **not a claim about live deployment**. Developer requirements map to the application namespace; Auditor requirements map to metadata/RBAC in both namespaces. All write, escalation, interactive access and Secret operations are explicit negative expectations. CI requires no API permissions. Additional watch/ReplicaSet reads support rollout inspection. All matrix operations are expected Deny in `argocd` for every persona. No cluster-scoped resources are granted.

| Verb | Resource / subresource | Dev apps | Dev monitoring | CI apps | CI monitoring | Auditor apps | Auditor monitoring |
| --- | --- | --- | --- | --- | --- | --- | --- |
| list | pods | A | D | D | D | A | A |
| get | pods | A | D | D | D | A | A |
| get | pods/log | A | D | D | D | D | D |
| get | deployments.apps | A | D | D | D | A | A |
| list | deployments.apps | A | D | D | D | A | A |
| watch | deployments.apps | A | D | D | D | A | A |
| watch | replicasets.apps | A | D | D | D | A | A |
| create | deployments.apps | D | D | D | D | D | D |
| update | deployments.apps | D | D | D | D | D | D |
| patch | deployments.apps | D | D | D | D | D | D |
| delete | deployments.apps | D | D | D | D | D | D |
| get | services | A | D | D | D | A | A |
| get | secrets | D | D | D | D | D | D |
| list | secrets | D | D | D | D | D | D |
| create | pods | D | D | D | D | D | D |
| create | pods/exec | D | D | D | D | D | D |
| get | pods/exec | D | D | D | D | D | D |
| create | pods/attach | D | D | D | D | D | D |
| create | pods/portforward | D | D | D | D | D | D |
| create | serviceaccounts/token | D | D | D | D | D | D |
| get | serviceaccounts | D | D | D | D | A | A |
| get | roles.rbac.authorization.k8s.io | D | D | D | D | A | A |
| list | roles.rbac.authorization.k8s.io | D | D | D | D | A | A |
| get | rolebindings.rbac.authorization.k8s.io | D | D | D | D | A | A |
| create | rolebindings.rbac.authorization.k8s.io | D | D | D | D | D | D |
| update | rolebindings.rbac.authorization.k8s.io | D | D | D | D | D | D |
| patch | roles.rbac.authorization.k8s.io | D | D | D | D | D | D |
| bind | roles.rbac.authorization.k8s.io | D | D | D | D | D | D |
| escalate | roles.rbac.authorization.k8s.io | D | D | D | D | D | D |
| impersonate | users | D | D | D | D | D | D |

## GitOps ownership and namespace boundaries

`platform-root` reads the nonrecursive `bootstrap/argocd/control-plane` directory using the existing default project. It owns the new `secure-rbac` AppProject (wave -1) and `platform-rbac` Application (wave 1). The child reads only `rbac/` on `main` and owns exactly three Roles and three RoleBindings, with explicit namespaces. The AppProject permits only Role/RoleBinding in the two existing namespaces, from this repository and the in-cluster destination. It permits no cluster resources or namespace creation. Shared ownership is a sync error. No ApplicationSet changes are necessary.

Existing `secure-platform` and `secure-monitoring` restrictions remain unchanged. Prometheus discovery RBAC stays owned by root; the new child uses distinct names. Existing namespace ownership remains unchanged. Parent and child use self-healing with pruning disabled, consistent with this repository. The new project is a narrow kind/destination boundary, not a rule-content validator: trusted repository reviewers and static CI must prevent future privilege increases in Role contents or subjects. Root's broad default project and controller authority remain pre-existing hardening concerns.

After review and merge to `main`, let root reconcile the new project/Application, then wait for `platform-rbac` to become Synced/Healthy before running live verification. Files in an uncommitted working tree are invisible to Argo CD. Do not manually apply the policy as a substitute for reconciliation. Deployment proceeds through a reviewed feature-branch PR; do not change controller revisions to bypass GitOps.

## Test instructions

Prerequisites: Python 3, PyYAML 6.0.3; live checks also require `kubectl`, a reachable configured cluster and the impersonation authority above. Run from repository root:

```bash
python3 scripts/check-rbac.py
python3 scripts/test-rbac-checks.py
# Optional schema/admission validation, no persistent changes:
kubectl apply --dry-run=server -f rbac/
# After GitOps reconciliation:
python3 scripts/check-rbac.py --live
kubectl get roles,rolebindings -n gitops-apps
kubectl get roles,rolebindings -n monitoring
kubectl get applications -n argocd
kubectl get applicationset platform-apps -n argocd -o yaml
kubectl get deployments -n gitops-apps
kubectl get deployments -n monitoring
```

The static checker parses YAML, enforces exact read-only grants, namespace/subject/roleRef relationships and dedicated project/Application boundaries, and checks 270 expectations. The existing GitHub workflow runs static validation and checker regression tests without cluster credentials. Server dry-run supplies live API schema/admission validation where available; no offline Kubernetes schema tool was installed in this environment. The regression tests demonstrate both unexpected Allow and unexpected Deny return failure, reject transport errors, stop on missing impersonation authority, and reject wildcard/Secret/cluster scope/binding/project mutations. They are simulated checker tests, not authorization evidence.

The live checker performs 270 non-mutating `kubectl auth can-i` checks (30 operations × three personas × three namespaces); `pods/log`, `pods/exec`, `pods/attach`, `pods/portforward` and `serviceaccounts/token` use explicit subresources. All calls have timeouts. Exit 0 requires every assertion to match; any mismatch, preflight failure or request error exits nonzero. No resource writes, token requests or destructive actions are used to establish Deny. Kubernetes can-i checks authorization rather than exercising an actual resource request or application endpoint.

## Verified deployment and results — 2026-11-12

[PR #22](https://github.com/GoGPenguin/secure-agentic-platform/pull/22) merged at `d83cb4c418bf538e6ceaa156f768de82ed375d36` after all required CI checks passed. Argo CD automatically reconciled root and the new `platform-rbac` child; no manual apply or forced sync was performed. The earlier pre-deployment baseline remains available as historical evidence, not the current result.

| Check | Status | Observed result |
| --- | --- | --- |
| Static policy / matrix | PASS | Six namespaced resources, exact grants/subjects, 270 expectations |
| Checker regression tests | PASS | Four tests, including five security mutation cases and unexpected Allow/Deny failures |
| Server dry-run | PASS | All six RBAC resources and reviewed Argo CD integration manifests accepted |
| PR CI | PASS | RBAC, monitoring, Helm, API and secret-scanning checks passed |
| Live authorization | PASS | **270 total, 270 PASS, 0 FAIL**, exit 0 |
| Developer | PASS | 90 assertions: 8 Allow, 82 Deny; application reads/logs allowed, mutations and monitoring reads denied |
| Auditor | PASS | 90 assertions: 22 Allow, 68 Deny; metadata/RBAC reads allowed in both namespaces, mutations/logs/Secrets denied |
| CI | PASS | 90 assertions: 0 Allow, 90 Deny; no Role or RoleBinding |
| Live negative probe | PASS | Two intentionally false expectations yielded 0 PASS / 2 FAIL and exit 1; cluster permissions unchanged |
| GitOps | PASS | All eight Applications Synced/Healthy, root diff empty, new child owns all six resources |
| Existing workloads | PASS | All six Deployments have available desired replicas; production API image selection unchanged |
| Monitoring permissions | PASS | Live Prometheus discovery Role and RoleBinding match the pre-deployment snapshot; Grafana manifests unchanged |
| Functional smoke | PASS | API readiness/info HTTP 200; Prometheus ready and platform-api scrape `up=1`; Grafana database health OK |

Evidence: [deployment health and effective rules](evidence/week9-deployed-health.txt), [all 270 live checks](evidence/week9-live-deployed.txt), [failure sensitivity](evidence/week9-negative-probe.txt), [HTTP smoke](evidence/week9-functional.txt), [merge/verification record](evidence/week9-delivery.json), [checkpoint A](evidence/week9-checkpoint-a.txt), [server validation](evidence/week9-reviewed-server-validation.txt), [local validations](evidence/week9-static.txt). Earlier [baseline authorization](evidence/week9-live-baseline.txt) and [baseline health](evidence/week9-health.txt) intentionally retain the initial failures for traceability. Observations are point-in-time evidence, not ongoing availability proof.

The separately captured `kubectl auth can-i --list` outputs include default `system:authenticated` discovery/self-review rights. CI's zero Allow count refers to the 90 tested resource operations; no persona binding is created for CI.

To repeat the deliberately failing live probe without changing policy:

```bash
python3 scripts/probe-rbac-failures.py
# Expected: 0 PASS, 2 FAIL, process exit 1.
# This inverts Developer get Pods and CI get Secrets expectations only in memory.
```

**Definition of Done: PASS — W09-A and W09-B complete for the documented simulated identities.** Developer/Auditor grants, both namespaces, CI assessment, matrix, narrow GitOps ownership, positive/negative live authorization, checker failure sensitivity, evidence, preserved workload functionality and documentation are independently verified. No cluster-scoped privileges were added. Remaining production identity and tenant-isolation work is described below and does not expand this milestone's claims.

## Security review and limitations

The grants contain no wildcard, Secret access, workload writes, interactive Pod access, service-account token issuance, bind/escalate, impersonation or cluster binding. Personas cannot change their own permissions or create privileged Pods. Cross-namespace Developer/CI access and access to `argocd` are tested as Deny. Auditor metadata can still expose image names, environment literals, ServiceAccount Secret references, topology and RBAC subjects; Developer logs may contain accidentally logged sensitive data. Keep secrets out of literals/logs and restrict identity membership. Read-only access and watches can still consume API resources.

RBAC cannot filter object fields or restrict reads to selected labels, and an existing external binding can expand effective access. The matrix is substantial but not an exhaustive proof across every API group/verb/resource. Namespace boundaries here are authorization boundaries, not full tenant isolation. NetworkPolicy, Pod Security admission, runtime hardening, resource quotas, admission controls, node isolation, audit retention, secret management and authenticated production identity lifecycle are separate work. Existing Prometheus permissions are preserved; no claim is made about hardening unrelated controller accounts.

## Rollback

Before merge, revert only the new Week 9 files and workflow/README additions; preserve unrelated user edits, especially `docs/PROJECT_CONTEXT.md`.

After deployment, use a reviewed Git change to empty the `subjects` arrays of the three RoleBindings, reconcile and verify former Allow operations become denied. Do not merely remove files: pruning is disabled, so deletion from Git leaves live grants in place. Once revocation is verified, an authorized operator can explicitly delete only the three `w09-*` bindings and three `w09-*` Roles, then remove the child Application/project and manifests through Git. Removing the child requires explicit cleanup because root pruning is also disabled; there is no cascading deletion finalizer. Never delete namespaces, existing discovery RBAC, workload Applications or the cluster. If another binding grants access, investigate it before claiming successful revocation.

## Checkpoint A review

The existing controller has sufficient authority: 36 non-mutating checks of Role/RoleBinding reconciliation permissions passed in both namespaces. Its pre-existing wildcard ClusterRole remains a hardening concern; Week 9 does not expand it. No existing Role/RoleBinding or Application-owned resource collides with the new names. Monitoring RBAC, workload manifests and both existing AppProjects are unchanged.

Root's exact Prometheus diff was `spec.source.directory.recurse: false` in Git versus absent live. A completed hard refresh did not clear it. Controller logs explicitly recorded normalizing the Prometheus source directory to null, explaining the recurring parent/child difference. The PR removes only the redundant false-only directory block from the Prometheus Application and omits it in platform-rbac. Both retain default nonrecursive directory behavior. No forced sync, ignoreDifferences rule, monitoring permission change or workload mutation is used. See [review evidence](evidence/week9-checkpoint-a.txt), [initial diff](evidence/week9-root-before.txt) and [hard refresh](evidence/week9-root-refreshed.txt).

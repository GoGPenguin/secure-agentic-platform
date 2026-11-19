# Week 12 Kyverno engine runbook

W12-A.1 prepares the persistent Kyverno engine for a later authorized
deployment. The checked-in configuration installs no Kyverno policies or
PolicyExceptions. Week 10 production PSA adoption and Week 11 NetworkPolicy
deployment remain separate checkpoints.

## GitOps ownership and install order

1. `platform-root` watches the nonrecursive `bootstrap/argocd/control-plane`
   directory on `main`. It owns the `kyverno` Namespace at wave −2,
   `secure-kyverno` AppProject at wave −1 and `kyverno` Application at
   wave 1. A merge to `main` authorizes root to reconcile those objects
   immediately. The engine is a standalone child outside the workload
   ApplicationSet.
2. The child reads official chart `3.10.0` and the values-only Git source.
   Chart metadata and all active runtime and hook images resolve to
   `v1.20.0`. The chart is rendered for Kubernetes `1.37.0`. The engine uses
   a manual, full, non-pruning sync with server-side apply and shared-resource
   failure detection. Use the child Application and leave pruning and force
   unchecked. There is no cascading deletion finalizer.
3. The upstream legacy-policy check maps to PreSync. Its ServiceAccount,
   ClusterRole and ClusterRoleBinding are at hook weight 100. The Job at
   weight 200 checks for existing legacy policies. Its read grants cover five
   legacy kinds and GET on their five named CRDs. The Job has a 120-second
   deadline and a 300-second TTL. Capture failed logs promptly and investigate
   the failure before retrying. Use full sync so the hook runs.
4. The child owns 22 CRDs from both bundled subcharts at Sync wave −1,
   with `Prune=false,Delete=false` on each CRD. The Namespace has the same
   deletion protection under root. The controllers and their regular
   dependencies are in Sync wave 0. Verify CRDs are Established and
   discoverable before accepting engine readiness. The storage migration hook
   is disabled for this fresh installation. Review stored versions, exports
   and the migration path before the first upgrade. The Helm test and
   uninstall cleanup hooks are outside this Argo-managed lifecycle.
5. Kyverno owns generated webhook configurations, cert Secrets and
   controller state. Argo owns the chart's declarative resources. The four
   aggregated controller ClusterRoles omit `rules` in the Helm render.
   Kubernetes owns the generated rules. The Application leaves drift visible
   and uses no diff exceptions.

Kyverno's support matrix lists v1.20 for Kubernetes v1.34–v1.37. The
published chart's archive checksum used by static validation is
`55961392dc0821eb367323f0e9585c061dd4407ef7ada921bd56ea1642c2a301`.
Argo uses the chart version pin and does not enforce this checksum itself.
Check the repo-server render against the reviewed inventory before sync.
[Kyverno releases](https://kyverno.io/docs/installation/releases/) ·
[Argo CD Helm and hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/) ·
[Kyverno upgrade guidance](https://kyverno.io/docs/installation/upgrading/)

## Render inventory and permissions

The [rendered inventory](evidence/week12-engine-inventory.yaml) records each
of the 73 resources, including CRD served/storage versions, container images
and sizing, every RBAC rule, aggregation selector and binding subject.

| Scope | Rendered resources |
| --- | --- |
| Cluster | 22 CRDs, 17 ClusterRoles and 7 ClusterRoleBindings |
| `kyverno` | 4 Deployments, 6 Services, 5 ServiceAccounts, 2 ConfigMaps, 4 Roles, 4 RoleBindings, 1 PDB and 1 legacy-check Job |

The AppProject admits only these kinds, the two named repositories and the
in-cluster `kyverno` destination. Kubernetes RBAC for the Argo CD sync identity
is a separate check. No new grant to that identity is included. The chart
renders no webhook configuration or TLS Secret, so those kinds are absent
from the AppProject allowlists.

All bindings name chart ServiceAccounts in `kyverno`. The pinned chart
retains the built-in `view` bindings for admission and reports. The
background controller drops its built-in `view` binding and the chart’s
optional cluster-wide write grants to networking, RBAC, configuration,
quota and Dynamic Resource Allocation objects. It has no Generate or
MutateExisting policies in this checkpoint.
Controller roles retain the upstream watch and reconciliation capabilities,
including workload reads, admission registration writes, policy/report
management, lease operations, and namespaced certificate Secret management.
The chart grants native admission policy and binding writes even with
automatic generation disabled, because it supports per-policy overrides.
Its aggregate controller roles can also consume other labeled ClusterRoles.
Review the effective bindings and all matching aggregation contributors before
sync. Kubernetes user-facing role aggregation is disabled. No extra roles
or grants are supplied. Chart RBAC is a cluster-wide trust decision even
though its Deployments are isolated to the Kyverno namespace.

### Aggregated ClusterRole verification

Keep the Application without a diff exception unless rehearsal demonstrates
persistent drift caused solely by generated rules. Verify server-side apply
does not take ownership of or overwrite generated rules and check the
resulting Argo diff. If filtering proves necessary, review a
`managedFieldsManagers` exception limited to the verified
`clusterrole-aggregation-controller` manager and the four named roles.
A manager filter can still hide permissions granted through an unexpected
contributor, so keep effective-rule verification independent of Argo's diff.

Before sync, inspect existing ClusterRoles for either selector on each
aggregated role in the reviewed inventory. After a separately authorized
sync and once aggregation converges, run this read-only check:

```bash
kubectl --context kind-secure-platform get clusterroles -o json > /tmp/kyverno-clusterroles.json
python3 scripts/validate-kyverno.py /tmp/kyverno-3.10.0.tgz \
  --clusterroles /tmp/kyverno-clusterroles.json
```

The validator checks the selectors, identifies all contributors from the
complete export, and compares both the core and effective rule sets against
the pinned render. The check is point-in-time and covers the four Kyverno
aggregates. Review effective bindings and the two upstream `view` grants
separately. CI runs regression cases for a matching union, a foreign
contributor, changed core rules, an expanded effective union and changed
selectors. CI uses synthetic snapshots and needs no cluster credentials.

## Initial webhook behavior and resources

Dynamic registration stays enabled. With zero user policies the resource
webhooks are expected to have no policy-driven workload matches. Kyverno's
policy, readiness and cleanup webhooks can exist and have their own failure
policies. Check the actual entries, rules, selectors, timeouts and CA bundles
after install. The rendered resource selector excludes `kube-system` and
`kyverno`; bootstrap exclusion also covers Nodes and CSRs for fail-closed
resource webhooks. Default registry mutation is disabled. Report APIs,
admission reports and the reports controller are available for the future
Audit phase. [Kyverno webhook behavior](https://kyverno.io/docs/installation/customization/) ·
[Kyverno security guidance](https://kyverno.io/docs/guides/security/)

| Component | Replicas | CPU/memory requests per Pod | CPU/memory limits per main container |
| --- | ---: | --- | --- |
| Admission | 2 | 100m / 128Mi | 1 CPU / 384Mi |
| Background | 1 | 100m / 64Mi | 500m / 128Mi |
| Cleanup | 1 | 100m / 64Mi | 500m / 128Mi |
| Reports | 1 | 100m / 64Mi | 500m / 128Mi |

Steady state requests **500m / 448Mi** and the main container limits total
**3.5 CPU / 1,152Mi**. The admission init container requests 10m / 64Mi,
below the main container requests. Reserve another 10m / 64Mi for the
PreSync Job. Three simultaneous surge Pods from the singleton controllers
can raise steady-state requests to **800m / 640Mi**, before overlap with
terminating Pods, platform workloads and host overhead.

Admission requires two distinct worker hostnames and excludes the
control-plane label. The PDB requires one available replica during voluntary
disruption. A rolling update replaces one replica at a time with no surge so
it can proceed with two worker slots. With one worker unavailable, expect one
replica to remain Pending. The single control plane and shared kind host
remain common failure points.

## Approval and verification

1. **Bootstrap approval.** Approve the reviewed diff and explicitly authorize
   merge to `main`. Confirm the target context is `kind-secure-platform`,
   Kubernetes is v1.37.0 and the installed Argo CD supports the declared
   multi-source, skip-tests, SSA and hook behavior. Capture existing app
   status and the four workload and two monitoring Deployment templates,
   replica availability, Pod identities/restarts and image references.
2. **Engine sync approval.** Capture any existing Kyverno CRDs, custom
   resources, webhooks and bindings. Stop for any ownership conflict or
   enabled legacy policy. Verify worker taints and request headroom, Docker
   host capacity, engine image access from nodes, chart access from
   repo-server and API server connectivity to the planned webhooks.
   Compare the child render and check the AppProject allowlists and effective
   Argo CD apply/bind/escalation authority. Rehearse the sync and recovery on
   a disposable equivalent cluster. After explicit approval, sync only
   the engine Application and capture the legacy-check hook outcome.
3. **Engine acceptance.** Check `argocd app get kyverno` and the full sync
   operation outcome. Confirm all four Deployments, 2/1/1/1 Ready replicas,
   worker separation and two ready endpoints for `kyverno-svc` via
   EndpointSlices. Check the admission and cleanup webhook client Service
   references, CA bundles, certificate expiration and controller logs.
   Observe Kyverno's periodic webhook health checks. Use an authorized,
   server-side dry-run of an ordinary workload and compare the returned
   Pod template to expectations. This verifies ordinary admission behavior,
   while direct webhook transport and failover evidence comes from the
   readiness checks and disposable rehearsal. Verify zero installed Kyverno
   policy and PolicyException objects across the installed APIs. Confirm
   report API discovery. An empty report set is expected with zero policies.
4. **Platform acceptance.** Compare the pre-sync baseline and verify all
   existing Argo Applications, the selected production API digest,
   deployment generations, Pod identities/restarts, API readiness/info and
   metrics, Prometheus readiness and scrape target, and Grafana health.
   Record any diff, webhook error or unexpected restart before advancing.
5. **Policy approval.** This checkpoint ends with the engine configuration
   and static evidence. Any later policy implementation, Audit deployment,
   or enforcement scope has its own approval gate.

## Rollback and recovery

For a failed first sync or regression, stop further syncs and record Argo
operation details, controller and hook logs, generated webhook inventory and
affected admission requests. Resolve the issue against the reviewed chart
and values or follow the approved engine removal procedure. Root and child
pruning are disabled. A Git revert alone leaves live resources in place.

If webhook failure blocks API writes, the designated break-glass operator
uses the captured inventory to identify the specific Kyverno configurations
and their failed endpoints. Coordinate recovery with Argo and Kyverno's
webhook reconciliation. Remove the affected Kyverno webhook configurations
only when required to recover admission, restore endpoints and TLS, then
verify registration and ordinary workload admission. Record the outage and
any admission coverage gap. Never delete another controller's webhook.
[Kyverno troubleshooting](https://kyverno.io/docs/guides/troubleshooting/)

For a separately approved uninstall, export any policies and reports, stop
Kyverno reconciliation, explicitly remove its generated webhook
configurations and verify that none still references an unavailable Service.
Then remove the engine's recorded resources and bootstrap declarations under
owner control. Protect shared resources and verify namespace/resource
ownership before every deletion. Retain CRDs and Namespace pending separate
destructive-cleanup authorization. For a version rollback, prove controller
and CRD storage compatibility first. [Kyverno uninstallation](https://kyverno.io/docs/installation/uninstallation/)

## Static validation and CI

Run from the repository root with Helm 4.3.2 and PyYAML.

```bash
helm pull kyverno --repo https://kyverno.github.io/kyverno/ --version 3.10.0 --destination /tmp
python3 scripts/validate-kyverno.py /tmp/kyverno-3.10.0.tgz --base origin/main
```

The validator checks the archive hash, chart/app versions, bootstrap
ownership, exact project allowlists, resource identities, hook scope,
controller topology and resource settings. It compares RBAC and the
rendered inventory against the checked-in review evidence. Change the
inventory only after reviewing the render. The existing platform workflow
runs this check with read-only repository permissions. PRs touching
Kyverno engine inputs also compare existing application sources, workload
values, monitoring, RBAC and bootstrap files against the PR base, which
guards both existing Pod templates and selected image digests.

Local results on the feature branch, compared with `origin/main` at
`c706b78`:

- Pinned Kyverno archive, Helm lint and static validation passed with
  73 resources and five aggregation regression cases. The four existing
  workload releases rendered identically
  to the base.
- Week 9 RBAC validation and four checker regression tests passed.
  Prometheus and Grafana static checks passed. Week 11 schema and traffic
  validations passed, including ten negative cases.
- Platform API lint, four unit tests, nineteen HTTP tests and the
  TypeScript build passed. The HTTP tests required loopback access.
- The local Docker daemon denied access for both the API image build and
  containerized `promtool` checks. These remain in the platform CI workflow.
  The new workflow job was checked locally for YAML and shell syntax.

Remaining deployment verification includes repo-server render equivalence,
effective RBAC and foreign aggregation contributors, capacity, API-server
reachability and webhook recovery. Two admission replicas cover a worker
failure only while the other worker and the control plane are available.

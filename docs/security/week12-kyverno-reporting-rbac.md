# Machine B Kyverno reporting readiness

Machine B's reporting RBAC extension is deployed and the five Audit policies
are Ready. During Audit activation, the non-root, registry and latest-tag
policies reported `RBACPermissionsGranted=False`. The extension satisfied the
permission checks. The separate metadata-only refresh triggered a recheck
and cleared all three conditions. The [Week 12 closure report](week12-closure.md)
records the final acceptance. The diagnosis and approval steps below cover
repeating this work in a separate environment.

## Cause and effective access

The admission controller hosts the policy-status reconciler. Its live
`--reportsServiceAccountName` points to
`system:serviceaccount:kyverno:kyverno-reports-controller`. The v1.20.0
reconciler constructs a SubjectAccessReview checker for that subject and
checks get, list, and watch on each matched resource with an empty
namespace. That request matches the all-namespaces authorizer scope.
A RoleBinding scoped to `gitops-apps` cannot satisfy the readiness check.
The policy namespace selector still restricts policy evaluation to
`gitops-apps`.

The upstream chart binds the reports ServiceAccount to the aggregated
`kyverno:reports-controller` ClusterRole and to `view`, and binds a
namespaced reports Role in `kyverno`. The reports core and effective
ClusterRoles matched the original reviewed render. Kubectl authorization
reviews returned no for all three verbs in both scopes. The checked-in
chart inventory has no rule for this subresource, and the reviewed reports
values specify no additional resources. No evidence shows an explicit
decision to exclude this subresource. [Pinned policy-status reconciler](https://github.com/kyverno/kyverno/blob/f666af06e9bd310c7e730f1523c0430e90371a89/pkg/controllers/policystatus/controller.go) · [Pinned admission controller wiring](https://github.com/kyverno/kyverno/blob/f666af06e9bd310c7e730f1523c0430e90371a89/cmd/kyverno/main.go)

| Subject and request | Live before | Projected after |
| --- | --- | --- |
| Reports SA, get/list/watch on core `pods/ephemeralcontainers` | No in all namespaces and in `gitops-apps` | Yes in both scopes through the existing aggregate and binding |
| Admission SA, same requests | No in both scopes | No |
| Other resources, verbs, and bindings | Existing grants | Identical |

The live API discovery advertises get, patch, and update for this subresource.
The added list and watch entries satisfy Kyverno's authorization probe.
They do not create list or watch endpoints. The grant gives the reports
identity a cluster-wide read path when an operation is served. The scope is
broader than policy evaluation, so keep the reports ServiceAccount isolated
and verify its effective permissions after deployment.

## Ownership and deployment order

The `kyverno-reporting-rbac` Application owns one standalone
ClusterRole. Its only rule grants get/list/watch on the core
`pods/ephemeralcontainers` subresource. Kyverno's existing aggregation label
adds this rule to the reports role. The existing ClusterRoleBinding supplies
the subject. The extension creates no bindings, edits no chart-managed
resources, and needs no controller configuration change.

The dedicated `secure-kyverno-reporting-rbac` AppProject permits this Git
repository and the in-cluster `kyverno` destination. It permits only the
ClusterRole kind and denies namespaced resources. AppProject permissions are
kind-level. The Application's single-file include and CI validator constrain
the actual object and rule. Both opt-in bootstrap manifests sit outside
`platform-root`. Sync is manual and pruning is disabled.

After separate owner approval, register the AppProject and then the
Application from the reviewed commit. Verify Argo renders exactly the
reviewed ClusterRole. Sync only the RBAC Application. Leave both existing
Kyverno Applications in place. Allow Kubernetes to recompute the aggregate
before checking readiness.

## Runtime verification and rollback

1. Verify the RBAC Application sync and confirm only the extension role was
   applied. Export ClusterRoles and run the pinned chart validator with
   `--clusterroles <export> --reporting-rbac-installed` to verify the effective
   union and detect any unexpected contributors.
2. Repeat authorization reviews as the reports ServiceAccount. Expect
   get/list/watch to be allowed at all-namespaces scope and patch/update on
   the subresource to remain denied. Confirm the admission ServiceAccount's
   result is unchanged.
3. Verify all five policies still use Audit in `gitops-apps`. Check for
   `RBACPermissionsGranted=True` and `WebhookConfigured=True`, then confirm
   the policy Application is Synced / Healthy. If conditions remain stale
   after aggregation, preserve them and investigate status reconciliation
   before requesting any additional write.
4. Recheck the four Deployment background reports against the compatibility
   matrix, test a non-persisting Audit admission request, and compare
   Application health and workload identities with the baseline. Background
   reports and RBAC readiness do not establish ephemeral admission coverage.

If withdrawal is approved, remove only the opt-in ClusterRole and confirm
the reports aggregate drops the three authorizations. Git removal alone
leaves the role live because pruning is disabled. Expect the original
readiness condition to recur if the grant is withdrawn while the three
policies retain the same match rules. Preserve the existing Kyverno
applications, chart roles and policies.

## Validation evidence

The pinned chart still renders 73 objects and matches the original inventory.
Offline tests verify the proposed aggregation union, reject removal of each
required verb, and reject widened access or automatic sync. The existing live
aggregate matches the pre-extension expectation. The 690 policy assertions
and five mutation checks passed, along with existing RBAC tests, Helm lint,
and local workflow syntax checks. Machine B runtime verification subsequently confirmed the projected grant and
the readiness refresh.

## Readiness refresh after RBAC activation

On Machine B, the reviewed role aggregated successfully and the reports
ServiceAccount passed the exact authorization checks. Three policy readiness
conditions retained their original denial timestamps. Kyverno v1.20.0
queues policy updates with a changed resourceVersion. The status controller
subscribes to policy and webhook-state events and has no direct ClusterRole
watch. A metadata update therefore gives Kyverno a reconciliation event
without changing the policy contract. Kyverno can also run its normal
webhook reconciliation. The annotation supplies no webhook or admission
configuration. [Pinned policy-status controller](https://github.com/kyverno/kyverno/blob/f666af06e9bd310c7e730f1523c0430e90371a89/pkg/controllers/policystatus/controller.go) · [Pinned policy event handlers](https://github.com/kyverno/kyverno/blob/f666af06e9bd310c7e730f1523c0430e90371a89/pkg/utils/controller/handlers.go)

The Git-managed annotation `gogpenguin.github.io/kyverno-rbac-readiness-refresh: "week12"`
is limited to `require-non-root`, `restrict-image-registries` and
`disallow-latest-tag`. Keep the value stable for this checkpoint.

After separate owner approval:

1. Confirm the reports identity still passes get, list and watch on
   `pods/ephemeralcontainers` at all-namespaces scope. Record all five
   resourceVersions, UIDs, generations, specs and conditions. Capture the
   webhook rules, background PolicyReports and workload identity baseline.
2. Compare the Argo render at the approved revision. The intended delta is
   the annotation on those three policies. Manually sync only
   `kyverno-policies` at that revision with Force, Replace and Prune disabled.
3. Verify the annotation and a new resourceVersion on each affected policy.
   All five must retain their original UID, spec, generation, Audit action
   and namespace scope. Confirm the two previously Ready policies have no
   readiness-refresh annotation.
4. Allow normal reconciliation. Confirm all five policies report Ready,
   `RBACPermissionsGranted=True`, and `WebhookConfigured=True`. Verify the
   policy Application reaches Synced / Healthy.
5. Compare webhook rules and scope, background reports and application health
   with the baseline. Verify workload Pod identities, image digests,
   readiness and restart counts remain stable.

If readiness still reports False, preserve the sync operation, policy
conditions and resourceVersions, Kyverno logs and authorization reviews.
Stop after the first refresh attempt. Any further write requires separate
approval.

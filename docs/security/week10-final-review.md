# Week 10 final review before isolated admission testing

Recommendation: **GO for separately authorized, isolated live admission tests**.
No live tests were run. **NO-GO for syncing this chart to existing workloads
under a zero-restart constraint**: removing their old Pod-template chart label
would cause one migration rollout. Week 10 remains incomplete.

## Chart rollout finding and local fix

The original 0.2.0 chart included `web-app.labels` in the Deployment Pod template;
that helper includes `helm.sh/chart`. The initial 0.2.1 implementation therefore
changed `spec.template.metadata.labels["helm.sh/chart"]` for every existing app,
independently of security settings.

The smallest maintainable fix omits only `helm.sh/chart` when rendering Deployment
Pod-template labels. All top-level chart, app-version and Helm managed-by metadata
remains. Existing selector labels, selectors, resource identities and Argo CD
ownership paths are untouched. AppVersion stays 1.16.0. Top-level version metadata
remains useful for identifying deployed chart revisions; copying it into the Pod
template unnecessarily couples chart packaging changes to restarts.

| Application | Pod spec versus original 0.2.0 | Selectors | Pod-template metadata |
| --- | --- | --- | --- |
| frontend | Identical | Identical | Only chart label removed |
| backend | Identical | Identical | Only chart label removed |
| sandbox | Identical | Identical | Only chart label removed |
| platform-api | Identical | Identical | Only chart label removed |

All four complete renders match the original after removing only `helm.sh/chart`
keys for comparison. This normalization is disclosed: the renders are not
byte-identical. Per-resource differences, including top-level label version
updates and the one Pod-template label removal, are in
[render evidence](evidence/week10-final-render-comparison.json). Baseline chart
files were read directly from git HEAD (0.2.0), not recreated by hand. Existing
production values remain unmodified.

A regression test renders the final chart at 0.2.1 and synthetic 0.2.2 for all
four apps and requires exact `spec.template` equality. Removing an existing label
cannot be made zero-rollout without retaining/pinning the old value or migrating
live ownership/state. Pinning obsolete metadata introduces maintenance debt;
no such workaround, ignore-differences rule or cluster mutation was introduced.
Isolated admission testing does not require promoting this shared chart to main
or syncing existing Applications.

## Security and fixture review

Pod contexts and container contexts render at their respective Kubernetes paths
in both the Deployment and Helm connection-test Pod. Non-root and seccomp inherit
from the Pod; container settings take precedence at runtime. The focused checker
also rejects explicit forbidden Pod-level values even if a container overrides
them. Escalation and capabilities are container-level controls. Init and ephemeral
container handling, container overrides and missing effective contexts have local
regressions. The chart does not enforce security globally.

The overlay retains the API digest/port/probes and sets RuntimeDefault, non-root,
numeric UID/GID 1000, no escalation, drop ALL and disabled SA token automount.
The exact digest's identity was verified by local image inspect and `id` in Phase
1; see [identity evidence](evidence/week10-phase1-static.json). Compatibility with
actual API startup remains unproven. The Helm test inherits these contexts and
explicitly disables token automount independently of the API SA. Its busybox
image/default behavior is preserved; forced UID 1000 is intentional, and wget
runtime compatibility remains unverified.

Schema validates the new common fields' types, numeric ranges, capability arrays
and seccomp type. It intentionally permits valid non-Restricted values: this is
an opt-in chart, not policy enforcement. Additional Kubernetes security fields
are allowed for extensibility; full API schema/cross-field validation is not
claimed. A future complete PSS gate should use a maintained engine. The checker,
its success output and documentation explicitly disclaim full PSS/admission
coverage. Its narrow scope is unchanged by this review.

All five fixtures explicitly target `psa-restricted-test`. Manual review of the
compliant Linux fixture against the applicable Restricted controls found:

- No privileged container, host namespaces, host ports, hostPath or other volumes.
- Non-root true and nonzero UID; no forbidden container override.
- RuntimeDefault seccomp; escalation false; drop ALL with no additions.
- No custom AppArmor, SELinux, procMount, sysctls, hostProcess or probe host fields.
- No init/ephemeral containers or other fields introducing additional controls.

This manual/static review is not server validation or admission evidence.

The original privileged fixture combined privileged true with escalation false.
That is API-invalid, as shown in
[upstream validation](https://github.com/kubernetes/kubernetes/blob/master/pkg/apis/core/validation/validation.go).
It now explicitly enables escalation, making the intended privileged scenario
structurally valid. Its expected PSA result includes **both** privileged and
escalation violations; these are necessarily coupled, not unrelated fixture
errors. The other three negative fixtures differ from the compliant Pod only in
their intended control plus resource name. A new regression restores each
intended difference and requires exact equality with the compliant fixture.

## Admission runner reliability

`scripts/test-psa-admission.py` requires explicit `--run` and `--context`. It never
creates a namespace or persists workloads. After checking all six namespace PSA
labels, it sends only strict-validation Pod server-dry-runs. It distinguishes:

| Outcome | Treatment |
| --- | --- |
| Successful compliant request | Pass |
| Intended restricted:v1.37 PSA rejection with expected control names | Pass for that negative fixture |
| Unexpectedly admitted negative | Fail |
| Authentication/authorization failure | Fail, separately identified |
| API connectivity/TLS/timeout failure | Fail, separately identified |
| Invalid schema/cross-field validation | Fail, separately identified |
| Other policy rejection, NotFound, wrong PSA version/control | Fail |

Control matching examines the details after the PSA marker, so the Pod name
`privileged` in an error prefix cannot satisfy the expected violation. A generic
Forbidden is not accepted as PSA evidence. Error-classifier tests use synthetic
responses and send no cluster requests. An explicit guard test proves no kubectl
invocation without `--run`. Human review of captured errors remains appropriate;
unrecognized diagnostics fail closed rather than being counted as success.

CI's existing Helm job automatically runs the expanded tests, including runner
classification. No credentials, cluster connections or new dependencies were
added to CI.

## Read-only preflight evidence

See [timestamped GET/LIST evidence](evidence/week10-final-preflight.json).

- Context and cluster: `kind-secure-platform`; endpoint `https://127.0.0.1:44663`.
  Node names identify secure-platform's one control plane and two workers. The
  kube-system Namespace UID is recorded to identify this specific cluster instance.
- Server and all kubelets: v1.37.0; all three Nodes Ready. The policy pin v1.37
  remains appropriate for this observed server/emulation version.
- Eight namespaces listed: argocd, default, gitops-apps, kube-node-lease,
  kube-public, kube-system, local-path-storage and monitoring. None had PSA labels.
- A separate GET of psa-restricted-test returned explicit NotFound, not an auth
  or transport error. The proposed name is currently unused.
- All eight Argo CD Applications report Synced/Healthy with no conditions.
  Status was read without refresh, sync or mutation.
- Application ready/desired replicas: frontend 2/2, backend 1/1, sandbox 1/1,
  platform-api 1/1. Prometheus and Grafana are each 1/1. All seven workload Pods
  are Running/Ready. Existing restart counts range from 3 to 5; this review did
  not cause them or investigate their historical causes. No HTTP smoke test was run.
- Successful lists found no validating/mutating webhooks, validating/mutating
  admission policies or bindings, or Kyverno/Gatekeeper/Kubewarden policy CRDs.
- The visible API-server Pod command enables NodeRestriction, with no explicit
  PodSecurity disable flag or admission-config-file flag visible. This is not
  proof of PSA defaults, effective plugin behavior or absence of exemptions.

Only configuration reads and GET/LIST/discovery calls were made. No Namespace,
Pod, Deployment or other resource was created, patched, deleted, synced or
server-dry-run. No `auth can-i` POST or admission request was used. Read access
does not establish future create/dry-run authorization. Namespace labels do not
establish admission configuration; invisible configuration, exemptions, runtime
behavior and the actual admission outcome remain unverified.

## Validation, remaining limits and next step

All ten local security test groups passed. This includes Helm lint/render for
defaults, four existing profiles and the hardened overlay, schema negatives,
fixture isolation, inheritance, rollout stability and live-error classification.
Existing static RBAC validation and four regression tests passed; both monitoring
validators and git diff --check passed. CI workflow was unchanged in this review;
its Phase 1 actionlint result remains applicable. No API source/Dockerfile changed.

No blocker was found for isolated live admission testing after explicit approval.
The namespace still needs separately authorized creation; permissions, effective
PSA behavior, possible exemptions and actual outcomes must be established by that
test. The runner must fail on exemptions that unexpectedly admit negatives.
Runtime startup, image pulls, service connectivity and probes are later work.
Production namespace enforcement and shared-chart rollout are outside this GO.

After approval, follow the context/namespace/version prechecks and namespace
creation in [the runbook](pod-security.md), then run:

```sh
python3 -B scripts/test-psa-admission.py --run --context kind-secure-platform
```

This command is proposed only; it was not executed. Local changes made during
this review: Deployment label rendering, privileged fixture, expanded local test
script, new guarded admission runner, updated runbook, this review, and the two
final evidence JSON files. No production values, monitoring, RBAC or AppProjects
were modified. No commit or PR was created.

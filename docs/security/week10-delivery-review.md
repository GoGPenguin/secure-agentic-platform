# Week 10 final engineering and delivery review

Decision: **GO for a separately authorized feature-branch commit and review-only
draft PR. NO-GO for merging the full candidate into main under the current
zero-restart constraint.** No commit, PR, branch switch, cluster request, Argo sync,
production change or lab cleanup was performed in this final review.

The fetched `origin/main` and HEAD both resolve to
`626e134cc5c44b55a11a46a3abd5227f953f4a3e`. The working tree remains on main with
uncommitted Week 10 changes; any later commit must first use an isolated feature
branch. This report does not declare Week 10 complete.

## Engineering findings

| Severity / finding | Disposition |
| --- | --- |
| **Delivery blocker:** the chart's Pod-template chart label removal changes existing workloads even without security opt-in | Keep implementation; hold its merge until an explicitly authorized production migration. Passing runtime tests do not authorize it. |
| Raw checker could accept `capabilities.drop: ALL` as a string via Python substring membership | Fixed locally: typed capability lists/context objects fail closed; regression cases include wrong arrays, element types and security-context shapes. |
| Null container seccomp was treated as a missing effective profile instead of inheriting the Pod setting | Fixed locally; null inheritance and valid Localhost override have regressions. The hardened profile still uses RuntimeDefault. |
| Frozen lab artifacts lacked an automated render-equivalence regression | Added a test that re-renders the exact three overlays and compares both artifacts after only namespace stamping. Approved artifact bytes/hashes remain unchanged. |
| CI security render pipeline relied on implicit shell behavior | Added explicit `set -euo pipefail`; workflow lint passed afterward. |
| Canonical runbooks still described the lab as not deployed | Added current-state banners; retained historical phase statements and frozen manifest comments without altering captured evidence. Updated PROJECT_CONTEXT as requested. |
| Checker covers selected Linux controls, not complete PSS/API schema | Explicitly documented limitation; not presented as a full policy engine. Maintained version-aware tooling remains future work. |
| Hook image is unpinned busybox; numeric hook execution was not runtime-tested | Preserved existing behavior; actual hook Pod admission was dry-run tested, but no hook was deployed. Debt, not a claim of runtime success. |

The chart correctly places contexts at Pod and container levels for Deployments
and test Pods. Empty defaults emit no contexts. Pod non-root/seccomp defaults
inherit, while explicit container overrides are evaluated. Escalation false and
drop ALL are container controls. Schema checks the exposed types/ranges/enums;
additional fields are intentionally extensible. A valid privileged value is
accepted by the opt-in chart schema and rejected by the focused checker/PSA where
enforced. This does not weaken existing policy or add global enforcement.

The hardened API overlay preserves production values and exact digest. UID/GID
1000 were verified both in the image and in the running process. The lab SA is
distinct and disables token mounting. Probes/ports/resources were preserved.
Fixtures target only psa-restricted-test; three negatives isolate one control.
The privileged negative intentionally violates privileged and escalation together
because privileged true/escalation false would be API-invalid. Admission runner
tests distinguish PSA from schema, auth/RBAC, connectivity and other failures;
unexpected acceptance fails. Its explicit run/context gate and namespace labels
are checked before Pod server-dry-runs. CI runs only local tests, not that runner.

Schema duplication is modest and not refactored during delivery review. No new
dependency family, production image, API code, RBAC or monitoring change was added.

## Acceptance and final validation matrix

| Criterion | Result | Evidence / limit |
| --- | --- | --- |
| W10-A live PSA outcomes | **PASS 5/5** | One allowed Pod and four specific restricted:v1.37 denials; actual prior-phase stdout |
| W10-B owner-plan runtime criteria | **PASS 22/22** | Exact imageID; UID/GID 1000; NoNewPrivs 1; CapEff and other sets zero; Seccomp 2; token absent |
| HTTP and kubelet probes | **PASS** | Four HTTP 200 responses; 127 liveness and 258 readiness successes at capture; zero restarts |
| Production regression | **PASS** | Eight Apps healthy, six Deployments available; templates/Pods/ReplicaSets/digest/namespaces unchanged |
| Application generation exception | **PASS, documented separately** | Raw hashes differed; exact reconstruction proves only metadata.generation changed. Writer cause not audited. |
| Helm/schema/checker/local tests | **PASS** | 13 security groups; lint/render for defaults, four apps, hardened overlay; malformed/inheritance/fixture/artifact tests |
| RBAC checks and regressions | **PASS** | 270 static expectations and four checker regression tests |
| Monitoring validators and promtool | **PASS** | Existing configuration/provisioning checks and network-isolated promtool |
| API lint/unit/E2E/build | **PASS** | 4 unit tests, 19 E2E tests; no API changes |
| Workflow lint | **PASS** | actionlint after pipefail change |
| Evidence consistency | **PASS** | 12 local invariants, JSON parsing, current runner/fixture/frozen artifact hashes |
| Complete inventory/index/link/whitespace checks | **PASS** | Generated inventory, exhaustive evidence index and local link validation; git diff --check |
| Safe full-candidate merge with zero restarts | **FAIL / BLOCKED** | Four existing Pod templates change; full merge unauthorized |
| Evidence-only staged merge | **PASS by proposed scope** | Reconciled inputs remain at main contents; no staged PR has been created or approved |

The [machine-readable runtime matrix](evidence/week10-phase2b-acceptance.json)
enumerates all 22 W10-B checks, mapped to the owner's runtime plan rather than an
independently supplied roadmap checklist. [Local review validation](evidence/week10-delivery-local-validation.json)
records this review's checks; [evidence validation](evidence/week10-delivery-evidence-validation.json)
records the cross-file invariants. No live cluster tests were rerun for delivery.

## GitOps reconciliation and migration impact

The unchanged ApplicationSet reads `app-configs/*.yaml`, renders `charts/web-app`
from main using each existing values file, and enables automated sync/self-heal.
The root also follows main, recursively disabled, at bootstrap/argocd/control-plane.
`prune: false` does not prevent an automatic Deployment update or rollout.

| Change | Effect when included in a main merge |
| --- | --- |
| Chart version 0.2.0 → 0.2.1 | Top-level chart labels change on existing chart resources; reconciled metadata updates |
| Remove helm.sh/chart from Deployment spec.template labels | All four existing application Pod templates change; creates migration rollouts |
| Empty optional security-context defaults and schema | No current Pod security setting changes without values opt-in |
| Hook security support | Existing default hook render unchanged apart from chart metadata; Argo skips test hooks and workload AppProject excludes Pods |
| Separate API hardened overlay | No application references it; explicit values opt-in required |
| security/psa-test namespace, fixtures, frozen artifacts | Outside root and ApplicationSet sources; no automatic namespace/workload creation |
| Documentation/evidence | No rendered Kubernetes resource difference; controller revision/status bookkeeping can advance |
| CI additions | Local validation only; no cluster credentials, deployment or promotion |

Main-versus-candidate comparison confirms all four Pod specs and selectors are
identical, but each template loses its existing chart label. Service/SA behavior,
ports, probes, replicas, resource identities and API digest remain identical.
Top-level chart/version metadata remains useful and is retained. A future
chart-version-only bump no longer changes templates, but **the first label removal
is itself a rollout**. This distinction is the delivery blocker.

There are no changes to ApplicationSet sources, existing app configs/values,
existing Namespace manifests, monitoring, RBAC or AppProjects. The evidence-only
stage keeps every reconciled source input unchanged; the recorded simulation
therefore produces exact main renders. It is a file-scope/unchanged-input proof,
not a merged-PR or live Argo experiment. See [reconciliation evidence](evidence/week10-delivery-reconciliation.json).

The existing main-push workflow publishes a fresh API artifact even for docs-only
merges. This is pre-existing behavior, not a deployment: the production values
digest remains fixed and no image promotion is automated.

## Proposed safe commit/PR scope — no action taken

Use separate PRs, not two commits merged together:

1. **Evidence-first PR:** only changed/new `docs/` files, the two frozen
   `security/psa-test/rendered/*.yaml` files, and
   `security/psa-test/platform-api-runtime.md`. This retains the complete evidence,
   project context, review and readable frozen runtime artifacts outside every
   reconciled path. It intentionally does not deliver the chart or claim its
   source-dependent commands are already usable on main. The current-state
   runbook banners explain that boundary. Its local Markdown links must resolve
   against main plus this exact file set before approval.
2. **Held implementation PR:** all five `charts/web-app` changes, CI update,
   hardened environment overlay, three scripts, namespace/fixture inputs and lab
   values overlay. Keep these together for their dependency closure. It may be
   committed to a feature branch/opened as an explicitly non-mergeable draft
   after authorization, but must not land in auto-synced main while zero-restart
   applies. Merge requires a separate production migration/rollout decision and
   refreshed validation against its actual base.

The [complete inventory](evidence/week10-delivery-inventory.json) assigns every
changed/new file to one stage. Do not use `git add .` from this mixed working tree.
No ignore-differences rule, disabled auto-sync, stale-version label pin, source
revision change or removal of security functionality is proposed to evade the
gate. Do not apply the evidence artifacts again: the lab already exists and is
retained. No production rollout or lab cleanup is authorized by this review.

## Evidence quality and current-state boundaries

The [complete evidence index](week10-evidence-index.md) includes every Week 10
record, including unsuccessful local recording/assertion attempts and their
explanations. W10-A outcomes, W10-B /proc state, imageID, HTTP bodies, kubelet probe
counters, events and pre/post state were captured from actual commands in the
authorized prior phases. Their consistency was rechecked locally. They are not
external attestations, continuous monitoring or proof of all possible PSS cases.

Application raw governance hashes were not rewritten as equal. A separate record
shows exact matches to each baseline hash after varying only generation; this
supports the specification-equality claim, not an audited claim about the writer.
No arbitrary secrets were found by the targeted credential scan, but a heuristic
scan is not a universal guarantee. No kubeconfig/token/config contents were added.

## Remaining technical debt and recommendation

- Full version-aware PSS/API schema coverage remains outside the focused checker.
- A permanent zero-rollout packaging policy and planned one-time Pod-label
  migration require review; changing appVersion or explicit podLabels can still
  intentionally roll Pods.
- Legacy nginx/httpd non-root compatibility and namespace-wide production PSA
  enforcement were not tested or authorized.
- Busybox hook pinning/runtime, read-only root filesystem, load/soak, resilience,
  network isolation, reproducible kind node pinning and sustained audit collection
  remain future work.
- UID/GID assumptions must be reverified for a future API digest; current tests
  deliberately bind fixtures and frozen artifacts to the reviewed digest.
- The lab is operator-managed and intentionally retained. Its ownership/cleanup
  lifecycle needs explicit future direction; do not silently adopt it into Argo.

Recommendation: authorize an isolated feature branch and the evidence-first PR
only if that delivery split is accepted. A full-candidate draft PR is suitable
for review but not merge. The current combined patch is **NO-GO as a merge-ready
GitOps delivery**. Stop here for repository delivery authorization.

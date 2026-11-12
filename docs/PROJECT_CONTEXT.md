# Secure Agentic Platform — Project Context

**Last updated:** 2026-11-12
**Roadmap:** Secure Agentic Platform — 36 Weeks
**Current milestone:** Week 9 complete (W09-A and W09-B): namespace-scoped RBAC deployed through GitOps; 270/270 live authorization checks passed. Week 6 completion and Week 5 observability/cleanup retained.
**Repository:** https://github.com/GoGPenguin/secure-agentic-platform

## Goal and working approach

Build a GitOps-driven platform for cloud-native applications, progressing through platform engineering, cloud security, AI infrastructure and secure agents. Platform API uses TypeScript/NestJS; a future AI Incident Agent is planned in Python.

Explain decisions and trade-offs, support hands-on learning, and distinguish user-reported outcomes from independently observed evidence. Use the roadmap when available; do not infer that the entire Week 5 checklist is complete from the checkpoints below.

Preserve existing workloads and favor incremental, reversible changes. Do not recreate the cluster, reinstall Argo CD, delete Applications or weaken security boundaries unless explicitly authorized. Follow `services/platform-api/AGENTS.md` when changing API code. Production image promotion uses a reviewed GitOps PR, not direct cluster mutation.

## Current checkpoint and evidence boundaries

The latest verified `main` revision is `00bbe81`, merging Week 9 evidence in [PR #23](https://github.com/GoGPenguin/secure-agentic-platform/pull/23). Implementation deployed at `d83cb4c418bf538e6ceaa156f768de82ed375d36` through [PR #22](https://github.com/GoGPenguin/secure-agentic-platform/pull/22). Both PRs passed required checks before merge. Historical Week 5 cleanup was committed as `30c8376` and merged in PR #20; Git history retains the removed exercise.

| Checkpoint | Status and evidence |
| --- | --- |
| Weeks 1–3 | Kubernetes, Helm, GitOps, ApplicationSet and AppProject foundation implemented |
| Week 4 | API, production container, CI publishing and digest-based delivery implemented; user confirmed completion |
| API instrumentation | Counter/histogram and metrics endpoint implemented; production image includes them |
| Prometheus | 3.13.5 deployed, API Pod discovery/scraping configured |
| Grafana / Dashboard as Code | 13.2.3 deployed with provisioned Prometheus source and six-panel API dashboard |
| W05-B.4.2 | Grafana-managed HTTP 5xx rule provisioned and validated on the pinned image |
| W05-B.4.4 | Controlled lab endpoint and separate build/container implemented; user reported successful alert verification |
| W05-B.4.5 | Temporary endpoint/build/image configuration/tests/override support removed; production behavior and observability preserved |
| Follow-up audit | 83 tracked files inspected; no remaining executable failure-injection components; no further cleanup edits needed |
| W06-A | Complete — user-confirmed manual Deployment drift exercise: Argo CD detected the difference and restored Git's desired state |
| W06-B | Complete — user-confirmed rollback drill and bootstrap README/runbook completion, including before/after evidence and recovery timing |
| Week 6 Definition of Done | Complete — user-confirmed fresh-cluster bootstrap with two healthy apps and recovery through Git; demo recording and runbook v0.1 accepted as complete |
| W09-A | PASS — Developer/Auditor namespace-scoped Roles and bindings deployed; CI needs no Kubernetes grants; matrix and dedicated GitOps project verified |
| W09-B | PASS — 270 total live authorization assertions, 270 PASS / 0 FAIL; two intentionally incorrect expectations fail with exit 1; evidence recorded |
| Week 9 Definition of Done | PASS — W09-A/W09-B complete for simulated identities; eight Applications Synced/Healthy, empty root diff, existing workloads and monitoring permissions preserved |

Historical read-only checks after the Week 5 cleanup merge found `platform-root`, `platform-api`, `prometheus` and `grafana` Synced/Healthy. Frontend, backend and sandbox were also Synced/Healthy. API rollout completed with one Ready replica on the production digest below and no lab environment variables. At that historical checkpoint, a hard refresh cleared a cached Prometheus `directory.recurse: false` diff. Week 9 found a recurring normalization difference instead; see the investigation below.

The actual ApplicationSet controller reported successful parameter/application generation. Its live spec had no `templatePatch`; API retained the chart source and `chart-repo` reference source. No Pod referenced a lab image. The unused local Docker tag `platform-api:lab-w05-b4-4-2a` was removed; the two other suggested lab tags did not exist. Kind node image caches were not pruned.

The user confirmed the HTTP 503 alert exercise was complete. Local checks independently proved endpoint gating, 503 instrumentation and Grafana expression behavior during implementation. A timed live Normal → Pending → Alerting → Normal sequence was not independently captured by the agent. On 2026-11-11, the user instructed that all Week 6 requirements be marked complete. Week 6 completion is recorded on that basis; the agent has not independently captured the drift/rollback timing, fresh-cluster recovery logs, recording or runbook artifact links. The historical Week 4 API digest rollback exercise also remains independently unverified. These evidence limits do not reopen the user-confirmed Week 6 milestone.

## Repository and controller architecture

```text
infrastructure/kind/cluster.yml                    one control plane, two workers
bootstrap/argocd/root.yaml                        platform-root bootstrap
bootstrap/argocd/control-plane/                   Applications, ApplicationSet,
                                                  projects and discovery RBAC
rbac/                                            Week 9 persona Roles / RoleBindings
docs/security/{rbac.md,authorization-matrix.json}  policy, tests and expected operations
docs/security/evidence/                          baseline and verified deployment evidence
scripts/{check-rbac,test-rbac-checks,probe-rbac-failures}.py
                                                  static/live checks and failure probes
app-configs/{frontend,backend,sandbox,platform-api}.yaml
                                                  workload discovery metadata
environments/*-values.yaml                        application values / API digest
charts/web-app/                                   shared Helm chart
services/platform-api/                            production API, tests and Dockerfile
monitoring/prometheus/                            scrape configuration / workload
monitoring/grafana/                               dashboard and alert provisioning
scripts/validate-{prometheus,grafana}-config.py    local configuration validation
.github/workflows/platform-ci.yaml                validation and publishing
docs/{monitoring,grafana}.md                      monitoring operating details
```

`platform-root` watches `bootstrap/argocd/control-plane` on `main`, in namespace `argocd`, using the default AppProject. It does not watch its own bootstrap manifest. The default bootstrap project remains a hardening item.

`platform-apps` uses a Git file generator, Go templates and `missingkey=error`. Each app-config supplies `name`, `namespace` and `valuesFile`. Generated Applications retain:

- Project `secure-platform`; in-cluster destination namespace `gitops-apps`.
- Chart source: this repository, revision `main`, path `charts/web-app`, release name matching the application.
- Values source: the same repository/revision with `ref: chart-repo`, referenced by `$chart-repo/{{.valuesFile}}`.

There is no optional lab override field or template patch. Applications self-heal with pruning disabled. ApplicationSet uses `applicationsSync: create-update` and `preserveResourcesOnDeletion: true`; inspect actual finalizers before relying on deletion protection.

Root also owns the Prometheus/Grafana Applications, monitoring namespace and existing discovery Role/RoleBinding. The monitoring Applications use `secure-monitoring`, which permits Deployment, Service, ServiceAccount and ConfigMap in `monitoring`, with no cluster-scoped resource allowlist. Prometheus has an existing namespaced Role allowing only get/list/watch of Pods in `gitops-apps`; Grafana has no discovery RBAC or mounted service-account token.

## Week 9 closure — RBAC and authorization

`platform-root` owns the `secure-rbac` AppProject and `platform-rbac` Application. The child reads `rbac/` on `main` and owns exactly three namespace-scoped Roles and three RoleBindings, tracked exclusively to that Application. The dedicated project permits only Role/RoleBinding in `gitops-apps` and `monitoring`, from this repository, with no cluster-scoped grants. Existing workload/monitoring AppProjects, ApplicationSet generation and Prometheus discovery permissions remain unchanged. Controller authority was verified through 36 non-mutating checks; its pre-existing broad ClusterRole was not expanded.

| Simulated identity | gitops-apps | monitoring |
| --- | --- | --- |
| `w09:developer` | Read Pods/logs, Services, Deployments and ReplicaSets; get/list/watch support rollout inspection | No grants |
| `w09:auditor` | Read workload metadata, ServiceAccounts, Roles and RoleBindings | Same metadata/RBAC reads |
| `w09:ci` | No grants | No grants |

CI builds, validates and publishes artifacts; Argo CD deploys. No CI Kubernetes credentials or RoleBinding were introduced. All personas are denied Secret access, workload/RBAC mutation, interactive Pod access, token issuance and privilege escalation; tested operations in `argocd` are denied. Names are simulated User subjects, not created human identities. The trusted local test administrator impersonates these users plus `system:authenticated`; production authentication/group mapping remains separate. No persona received impersonation or cluster-admin privileges, and no credentials or persistent tokens were created.

The live suite passed **270/270 assertions, 0 FAIL, exit 0**: Developer 8 Allow / 82 Deny, Auditor 22 Allow / 68 Deny, CI 0 Allow / 90 Deny. Two deliberately inverted live expectations returned 0 PASS / 2 FAIL and exit 1, demonstrating failure sensitivity without changing policy. Static policy checks, four checker regression tests (including five privilege-mutation cases), server dry-runs, all four Helm renders/lints, monitoring validators and PR CI passed. Static validation runs in public CI without cluster credentials; live tests require explicit administrator impersonation authority and preflight.

After GitOps deployment, all eight Applications were Synced/Healthy, all six Deployments had their desired replicas available, root's diff was empty, and all six new RBAC resources had the expected child tracking owner. Prometheus discovery rules/binding matched the pre-deployment snapshot. API readiness/info, Prometheus readiness and API scrape `up=1`, and Grafana database health checks passed. The selected production API digest was unchanged. Final read-only checks after the evidence merge confirmed root Synced/Healthy at `00bbe81` and all Applications healthy.

The pre-existing Prometheus diff was investigated before deployment with root get/diff, completed hard refresh and controller logs. Unlike the earlier cached-diff incident, refresh did not clear it: the controller explicitly normalized the false-only `source.directory` block to null, while root restored it from Git. PR #22 removed only the redundant block from the Prometheus child and omitted it in the RBAC child, preserving default nonrecursive behavior. Root converged through automatic GitOps reconciliation; no manual apply, forced sync, ignored diff or permission broadening was used.

Canonical documentation: [RBAC architecture, matrix, prerequisites, risks and rollback](security/rbac.md). Evidence: [deployment record](security/evidence/week9-delivery.json), [270 live checks](security/evidence/week9-live-deployed.txt), [health/effective rules](security/evidence/week9-deployed-health.txt), [negative probe](security/evidence/week9-negative-probe.txt), [HTTP smoke](security/evidence/week9-functional.txt), [pre-deployment review](security/evidence/week9-checkpoint-a.txt). The historical 240 PASS / 30 FAIL baseline remains for traceability and is superseded by the deployed result. Evidence is point-in-time, not a continuous health guarantee.

Pruning remains disabled. To revoke grants, reconcile empty RoleBinding subjects first and verify Deny before explicitly cleaning up only Week 9 resources; deleting files alone does not revoke live access. See the documented rollback. RBAC remains additive and is not full tenant isolation: production identity lifecycle, NetworkPolicy, Pod Security/admission controls, quotas, runtime/node isolation, secret management and audit retention remain separate work. Existing broad controller authority and the root default project remain hardening items.

## Workloads and chart behavior

| Application | Deployment | Replicas | Image / port |
| --- | --- | --- | --- |
| frontend | frontend-web-app | 2 | nginx:1.16.0 / 80 |
| backend | backend-web-app | 1 | httpd:latest / 80 |
| sandbox | sandbox-web-app | 1 | nginx:1.16.0 / 80 |
| platform-api | platform-api-web-app | 1 | GHCR digest / 3000 |

Frontend/backend/sandbox remain active sample GitOps workloads. Their presence does not imply authorization to retire them. Kind is the platform's local topology, not leftover injection infrastructure. Helm connection-test hooks and E2E mock controllers remain verification tools; E2E fixtures are excluded from production compilation and the Docker context.

Chart version is `0.2.0`, with `appVersion: 1.16.0` independent of API version. Nonempty `image.digest` wins over tag; an empty digest uses the tag or chart appVersion fallback. The schema validates SHA-256 digest format. Explicit `container.port` overrides `service.port`; Services/probes use named port `http`.

Generic `env: {}` support remains: empty maps emit no env block and values must be strings. No failure-injection values remain. The Helm connection-test Pod is skipped by Argo CD and is outside the workload project's allowlist. The chart does not expose Pod/container securityContext or imagePullSecrets configuration.

## Platform API and instrumentation

NestJS 12, TypeScript ESM, Vitest, Supertest and pnpm. Relative source imports use `.js`. The production application imports `MetricsModule`, `InfoModule` and `HealthModule`. There is no `/` handler, lab endpoint, database, authentication, broker or AI integration.

| GET route | Result |
| --- | --- |
| `/api/v1/info` | `{"service":"platform-api","version":"0.1.1"}` |
| `/health/live` | `{"status":"ok"}` |
| `/health/ready` | `{"status":"ready"}` |
| `/metrics` | Prometheus text exposition |

`package.json` supplies service identity/version and must remain beside `dist`. Readiness currently reflects HTTP application availability, not external dependencies or shutdown draining.

`http_requests_total` and `http_request_duration_seconds` record completed responses exactly once, with `method`, `route` and `status_code` labels. Registered route templates bound label cardinality; unmatched routes use `__unmatched__`. Aborted responses before finish are not counted. Metrics scrapes and both health routes are explicitly excluded. Each application owns its registry. Histogram buckets are 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5 and 10 seconds, plus infinity.

CI/Docker use Node.js `24.22.2` and pnpm `12.16.1`. The unchanged multi-stage Dockerfile uses `node:24.22.2-bookworm-slim`, frozen installs and separate production dependencies. Runtime contains `dist`, production dependencies and package metadata; it starts `node dist/main.js` as non-root `node`, with `NODE_ENV=production`, port 3000. The baseline is version-tagged, not digest-pinned.

API values retain ClusterIP port 3000, one replica, `IfNotPresent`, requests 100m CPU/128Mi and limits 500m CPU/256Mi. The dedicated ServiceAccount disables token automount. Liveness/readiness paths are unchanged; Ingress, HTTPRoute and HPA remain disabled.

## Monitoring and alerting

Prometheus 3.13.5 scrapes every 30s with a 5s timeout. API discovery is scoped to matching Running Pods in `gitops-apps`, the `web-app` container and named TCP port `http`/3000. Metrics path is `/metrics`, job `platform-api`; retained labels include namespace, Pod and Pod UID. See [monitoring.md](monitoring.md).

Grafana 13.2.3 is digest-pinned, uses UID/GID 472, a read-only root filesystem, dropped capabilities, RuntimeDefault seccomp and no token automount. Admin credentials come from the existing operator-managed Secret outside Git. Anonymous access is disabled. Prometheus source UID is `prometheus`; dashboard UID is `platform-api-overview`, in `Platform`, with three stats and three time series for health, rate, errors and latency. See [grafana.md](grafana.md).

Alert file `monitoring/grafana/config/alerting/platform-api-http.yaml` defines:

| Setting | Value |
| --- | --- |
| Rule UID / group | `platform-api-http-5xx` / `platform-api-http` |
| Source / condition | `prometheus`; instant query A followed by threshold B |
| Window / volume / threshold | 5m; at least 100 requests; strictly above 5% HTTP 5xx |
| Evaluation / pending | 30s / 1m |
| Special states | `NoData` / `Error` |
| Keep firing | 0s |

Missing 5xx series become zero only when total counter telemetry exists. Idle existing counters and low volume produce a non-breaching value. Missing/insufficient counter telemetry or any discovered down target yields No Data; query failures remain Error. The health gate cannot detect an expected replica removed from discovery while others remain up. Low-volume failures and route-specific issues can be hidden by the service-wide traffic gate/aggregation. `increase()` is extrapolated, not an exact audit count.

Kustomize mounts alert provisioning read-only. Stable ConfigMaps use the existing canonical `checksum/config` rollout mechanism; dashboard JSON is excluded from that checksum and polled every 30s. Alert-file projection alone does not reload rules: use normal checksum-driven rollout or an authorized provisioning reload. No external notification integration was added.

Prometheus TSDB and Grafana SQLite/application state use emptyDir. Pod replacement loses local history/state. Grafana's single-replica Recreate rollout interrupts evaluation and should be treated as resetting pending progress. Git restores provisioned definitions, not durable history or sessions. PVCs require separate design/permissions.

## CI, image identity and promotion

CI runs RBAC static validation/checker regression tests, monitoring validation, Helm validation and Platform API CI. API CI includes lint, unit/E2E tests, TypeScript build and production Docker build. Lab packaging, scripts and controller-isolation checks were removed; all pre-lab production checks were preserved and explicit lint was added. Monitoring CI validates Prometheus configuration/checksum; the Grafana validator remains a local check.

Publishing requires Helm/API validation and runs only on pushes to main. Default permissions are `contents: read`; only publishing adds `packages: write`. Checkout credentials are not persisted. SHA-pinned Docker actions publish linux/amd64 with source/revision labels and `sha-<full-commit>` tags. CI records the digest; it does not deploy or automatically promote it. A docs/GitOps-only merge can still publish a new image.

| Artifact | Digest / evidence |
| --- | --- |
| Deployed production API, version 0.1.1 | `sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421` |
| Deployed image source revision | `b2728b6580da2dd16b4037222b16795810c89635`, verified from OCI label |
| Cleanup merge build, not promoted | `sha256:b3db1830b11a8b7ae101715c555cabd1b54d8c8e3af9b547b9b740734fc6e469`, source `70d5537` |
| Cleanup publishing run | [42989393982](https://github.com/GoGPenguin/secure-agentic-platform/actions/runs/42989393982), succeeded |

Comparison against the deployed image's source revision found no production API code, dependency, Dockerfile or build-input changes; only the API README differed. No new digest promotion was needed for cleanup, and values retain the deployed digest. Historical v0.1.0/v0.1.1 artifacts remain in Git history; do not substitute their old selection status for current live evidence.

For future runtime changes: verify the successful main build and immutable artifact, change only the desired digest in a reviewed GitOps PR, compare renders, then observe rollout, running image IDs and HTTP behavior after merge. Retain a known-good digest for rollback. Restore that digest through another reviewed PR rather than rebuilding an old version or mutating workloads directly. A runtime imageID may identify a platform manifest rather than the top-level image index.

## Latest validation and continuation

W05-B.4.5 checks passed: lint, 4 unit tests, 19 E2E tests, production build, frozen-install Docker build, non-root/read-only Docker smoke, Helm lint/template, actionlint and `git diff --check`. Removed endpoint returned 404; info/health/metrics returned 200; normal counter/histogram observations and scrape/probe exclusions were preserved. Four default Helm renders remained byte-for-byte unchanged. A local Go/Sprig harness preserved all four Application identities, sources, destinations and policies; subsequent live controller checks confirmed generation.

The follow-up repository audit found no executable injection references. The API README intentionally retains a removal note. Prometheus/Grafana validators and all four Helm renders passed. Temporary files under `/tmp` are session artifacts, not durable evidence or required repository tools.

Week 9 verification is recorded above; the earlier cleanup checks above remain historical regression evidence. Routine checks from repository root:

```bash
pnpm --dir services/platform-api run lint
pnpm --dir services/platform-api test
pnpm --dir services/platform-api run test:e2e
pnpm --dir services/platform-api run build
python3 scripts/validate-prometheus-config.py
python3 scripts/validate-grafana-config.py
python3 scripts/check-rbac.py
python3 scripts/test-rbac-checks.py
# With a configured cluster and authorized impersonation:
python3 scripts/check-rbac.py --live
helm lint charts/web-app -f environments/platform-api-values.yaml
helm template platform-api charts/web-app -n gitops-apps -f environments/platform-api-values.yaml
```

After reviewed merges, inspect root/API/Prometheus/Grafana separately, ApplicationSet conditions, rollout and selected image. Root health alone does not establish child query/evaluation health. Use localhost-bound port-forwards for API/Grafana/Prometheus access.

Next: Week 9 is closed. Continue with Week 10 when its scope is supplied; this context does not independently establish completion of Weeks 7–8. Week 6 remains complete per user confirmation. Preserve alerting and existing workload/security boundaries. Outstanding platform improvements include durable monitoring storage/history, notification design, image/security scanning, network isolation and further bootstrap hardening. AppProjects do not replace Kubernetes RBAC, NetworkPolicy, Pod Security or secret management. Frontend/sandbox and backend still use mutable tags. The kind configuration does not pin node images; observed nodes and Argo CD versions alone do not establish reproducibility. Week 6 recovery completion is user-confirmed, with independent evidence limits recorded above.

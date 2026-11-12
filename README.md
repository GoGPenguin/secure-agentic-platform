# Secure Agentic Platform

A GitOps-driven Kubernetes platform, progressing toward secure agentic workloads.

**Current checkpoint:** Week 5 observability implemented through W05-B.4.5. Prometheus, Grafana dashboards and HTTP 5xx alerting are deployed. The temporary failure-injection API and its lab infrastructure have been removed after user-confirmed alert verification.

**Last verified:** 2026-11-11, after merge `70d5537`: root, Platform API, Prometheus and Grafana were Synced/Healthy; the API used the production digest below. A full clean-cluster recovery remains untested. See [project context](docs/PROJECT_CONTEXT.md) for evidence boundaries and continuation guidance.

## Architecture

```text
Pull request → Monitoring Validation + Helm Validation + Platform API CI
Merge to main → validation → Publish Platform API → GHCR
                                                    │
                                 published digest → reviewed GitOps PR
                                                    │
Git main → platform-root → platform-apps ApplicationSet
                       │                  │
                       │       app-configs + environment values
                       │                  │
                       │       charts/web-app → gitops-apps
                       │                  │
                       │       frontend, backend, sandbox, platform-api
                       │                                  │ /metrics
                       └─ monitoring Applications         ▼
                              Prometheus ← queries ─ Grafana
                                                      dashboard + alert
```

CI publishes images; Argo CD reconciles Git. Publishing does not automatically select a new deployed digest. Promotion and rollback use reviewed Git changes.

`platform-root` manages `bootstrap/argocd/control-plane/`. ApplicationSet discovers `app-configs/*.yaml`, assigns unique Helm releases, and loads values through the second source reference `$chart-repo`. Workloads use `secure-platform`; monitoring uses `secure-monitoring`. Self-healing is enabled and pruning disabled. ApplicationSet retains `create-update` and `preserveResourcesOnDeletion: true`; there is no lab override support.

## Repository layout

| Path | Responsibility |
| --- | --- |
| `infrastructure/kind/cluster.yml` | One control plane and two workers |
| `bootstrap/argocd/root.yaml` | Root Application bootstrap |
| `bootstrap/argocd/control-plane/` | Applications, ApplicationSet, projects and discovery RBAC |
| `app-configs/` | Discovery metadata for four workload Applications |
| `environments/` | Workload values and production API digest |
| `charts/web-app/` | Shared Helm chart, generic env support and image schema |
| `services/platform-api/` | NestJS API, regression tests, lockfile and Dockerfile |
| `monitoring/` | Prometheus configuration and Grafana dashboard/alert provisioning |
| `scripts/` | Monitoring configuration/checksum validators |
| `.github/workflows/platform-ci.yaml` | Validation and main-only GHCR publishing |
| `docs/PROJECT_CONTEXT.md` | Current state, evidence and next-work boundaries |

Frontend/backend/sandbox remain active sample workloads. Existing regression fixtures and Helm connection-test hooks are verification tools, not deployed failure-injection endpoints.

## Platform API

| GET endpoint | Result |
| --- | --- |
| `/api/v1/info` | `{"service":"platform-api","version":"0.1.1"}` |
| `/health/live` | `{"status":"ok"}` |
| `/health/ready` | `{"status":"ready"}` |
| `/metrics` | Prometheus request counter and duration histogram |

There is no `/` handler. The temporary HTTP 503 endpoint, flags, separate build/container and GitOps override infrastructure were removed in W05-B.4.5. See the [API README](services/platform-api/README.md).

Metrics record completed responses with bounded route-template labels. `/metrics`, `/health/live` and `/health/ready` are excluded; aborted responses before finish are not counted. Readiness currently checks HTTP application availability, not external dependencies.

CI and Docker use Node.js **24.22.2** and pnpm **12.16.1**. From repository root:

```bash
pnpm --dir services/platform-api install --frozen-lockfile
pnpm --dir services/platform-api run lint
pnpm --dir services/platform-api test
pnpm --dir services/platform-api run test:e2e
pnpm --dir services/platform-api run build
```

Latest cleanup checks passed: lint, **4 unit tests**, **19 E2E tests**, TypeScript/Docker builds and container smoke checks. No lab-specific scripts or tests remain.

## Container and immutable delivery

```bash
docker build -t platform-api:dev services/platform-api
docker run --rm -p 127.0.0.1:3000:3000 platform-api:dev
```

The unchanged multi-stage Dockerfile uses `node:24.22.2-bookworm-slim`, frozen installs and separate production dependencies. Runtime contains compiled code, dependencies and package metadata. It executes `node dist/main.js` as non-root `node`, with `NODE_ENV=production` and port 3000.

Production repository: `ghcr.io/gogpenguin/secure-agentic-platform/platform-api`.

Current selected and last verified deployed digest:

```text
sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421
```

Its OCI source revision is `b2728b6580da2dd16b4037222b16795810c89635`. Comparison with the cleanup merge found identical production code and build inputs, so cleanup required no image promotion. The new image automatically published for that merge remains unpromoted; its identity and successful CI run are recorded in [project context](docs/PROJECT_CONTEXT.md).

Chart **0.2.0** gives a nonempty image digest precedence over tag. Chart `appVersion: 1.16.0` is independent of API version. Generic environment configuration defaults to `env: {}` and requires string values. The API retains one replica, ClusterIP port 3000, unchanged resource limits/probes and a dedicated ServiceAccount with token automount disabled. Ingress, HTTPRoute and autoscaling are disabled.

CI runs monitoring, Helm and API validation, including API lint/unit/E2E/build checks. Only main pushes publish; the publish job requires Helm/API validation, uses temporary `GITHUB_TOKEN` and SHA-pinned Docker actions, and records an immutable linux/amd64 image reference. No CI step deploys or automatically promotes an image.

For a future runtime change: verify the published artifact, change only `image.digest` through a reviewed GitOps PR, compare renders, merge, then inspect rollout and HTTP behavior. Roll back by restoring a retained known-good digest through Git. Do not rebuild an old version as a substitute for restoring its artifact.

## Observability

Prometheus **3.13.5** discovers Platform API Pods with namespaced get/list/watch permissions and scrapes `/metrics` every **30 seconds**. Grafana **13.2.3** uses provisioned source UID `prometheus` and dashboard UID `platform-api-overview`, with six panels covering target health, request rate, HTTP errors and p95 latency.

The Grafana-managed rule `platform-api-http-5xx` detects **HTTP 5xx > 5%**, with **at least 100 requests over five minutes**, evaluated every **30 seconds** and pending for **one minute**. No Data and query Error remain distinct from zero errors or low/idle traffic. No external notification integration has been added.

Dashboard and alert definitions are Git-managed. Dashboard JSON is polled live; alert changes use configuration checksums and rollout, or an authorized provisioning reload. Both monitoring workloads use ephemeral storage, so Pod replacement loses local history/state. See [Prometheus operations](docs/monitoring.md) and [Grafana operations](docs/grafana.md).

```bash
python3 scripts/validate-prometheus-config.py
python3 scripts/validate-grafana-config.py
helm lint charts/web-app -f environments/platform-api-values.yaml
helm template platform-api charts/web-app -n gitops-apps -f environments/platform-api-values.yaml
```

## GitOps verification and access

```bash
argocd app get platform-root
argocd app get platform-api
argocd app get prometheus
argocd app get grafana
kubectl -n argocd get applicationset platform-apps
kubectl -n argocd get applications frontend backend sandbox platform-api
kubectl -n gitops-apps rollout status deployment/platform-api-web-app
kubectl -n gitops-apps get deployment platform-api-web-app -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n gitops-apps port-forward --address 127.0.0.1 svc/platform-api-web-app 3000:3000
```

In another terminal, request `/api/v1/info`, `/health/live`, `/health/ready` and `/metrics` on `http://127.0.0.1:3000`. Root sync/health alone does not prove child telemetry or alert evaluations are healthy.

## Security and recovery boundaries

Keep the existing cluster in place. For a fresh local cluster, use `infrastructure/kind/cluster.yml`, then install a tested Argo CD release before bootstrapping `bootstrap/argocd/root.yaml`. Root does not manage its own bootstrap file. This is an outline, not a validated recovery runbook; node images and installation steps still need reproducible pins.

AppProjects restrict repositories, destinations and resource kinds. They do not replace Kubernetes RBAC, NetworkPolicy, Pod Security, image scanning or secret management. Grafana credentials remain in an operator-owned Secret outside Git. The chart's Helm test-hook Pod is skipped by Argo CD and is outside the workload AppProject allowlist.

Remaining work includes durable monitoring storage, notification design, security scanning, workload isolation, hardened/reproducible bootstrap and clean-cluster recovery. Never commit credentials, kubeconfigs or state files; `.gitignore` excludes common sensitive/generated paths but cannot detect embedded secrets. Reconcile remaining Week 5 roadmap tasks before assuming the whole week is complete or starting Week 6.

## Kubernetes authorization (Week 9)

Namespace-scoped Developer and Security Auditor policies, CI access assessment, the authorization matrix, verification commands and deployment evidence are documented in [RBAC and isolation](docs/security/rbac.md). The policy is prepared for GitOps; Week 9 remains incomplete pending post-merge live authorization and reconciliation verification.

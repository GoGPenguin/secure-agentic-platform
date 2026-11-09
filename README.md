# Secure Agentic Platform

A 36-week hands-on learning project covering platform engineering, Kubernetes, GitOps, cloud security, and secure AI-agent operations. The Platform API uses TypeScript/NestJS; a future AI Incident Agent will use Python.

**Current milestone:** W04-B5 — Immutable Image Promotion and Rollback. W04-A is complete. Platform API v0.1.1 is released in source; this branch promotes its published image by digest. Promotion rollout and digest rollback have not yet been verified in this session. A full clean-cluster rebuild remains untested.

See [project context and evidence](docs/PROJECT_CONTEXT.md) for progress and remaining work.

## Architecture

```text
Pull request → Helm Validation + Platform API CI
Merge to main → repeat validation → Publish Platform API → GHCR
                                                      │
                                   published digest → reviewed GitOps PR
                                                      │
Git main → platform-root → secure-platform AppProject + platform-apps ApplicationSet
                                                      │
                                 app-configs/*.yaml + environments/*-values.yaml
                                                      │
                                         charts/web-app → kind / gitops-apps
                                                      │
                                   frontend, backend, sandbox, platform-api
```

CI builds and publishes images; Argo CD reconciles deployments from Git. CI does not deploy directly to Kubernetes. Image promotion and rollback require reviewed Git changes under branch protection.

`platform-root` manages `bootstrap/argocd/control-plane/`. The ApplicationSet reads `app-configs/*.yaml` from `main`, assigns unique Helm release names, and loads application values through the `$chart-repo` source reference. Automated self-healing is enabled and pruning is disabled. ApplicationSet uses `create-update` and `preserveResourcesOnDeletion: true`.

## Repository layout

| Path | Responsibility |
| --- | --- |
| `infrastructure/kind/cluster.yml` | One control plane and two workers |
| `bootstrap/argocd/root.yaml` | Initial root Application bootstrap |
| `bootstrap/argocd/control-plane/` | AppProject and ApplicationSet |
| `app-configs/` | ApplicationSet discovery metadata for four applications |
| `environments/` | Application-specific Helm values and promoted image digest |
| `charts/web-app/` | Shared chart, templates, and digest schema |
| `services/platform-api/` | NestJS API, tests, pnpm lockfile, and Dockerfile |
| `.github/workflows/platform-ci.yaml` | Validation and main-only GHCR publishing |
| `applications/demo-app/`, `bootstrap/argocd/apps/` | Legacy learning manifests; outside the current root source path |
| `docs/PROJECT_CONTEXT.md` | Progress snapshot and continuation guidance |

Do not reconcile legacy standalone Applications alongside ApplicationSet-managed applications.

## Platform API

| Endpoint | HTTP 200 response |
| --- | --- |
| `GET /api/v1/info` | `{"service":"platform-api","version":"0.1.1"}` for the v0.1.1 image |
| `GET /health/live` | `{"status":"ok"}` |
| `GET /health/ready` | `{"status":"ready"}` |

`package.json` is the single source of truth for service name and version. Readiness currently means the initialized HTTP application can serve requests; there are no external dependencies to check.

Node.js **24.22.2** and pnpm **12.16.1** are used by CI and the Docker build. From the repository root:

```bash
cd services/platform-api
pnpm install --frozen-lockfile
pnpm test
pnpm run test:e2e
pnpm run build
pnpm run start:dev
```

The tests use Vitest and Supertest; the test scripts terminate without watch mode. Latest local release checks passed: two unit tests, four HTTP tests, TypeScript compilation, Docker build, and container smoke tests.

## Container build

From the repository root:

```bash
docker build -t platform-api:dev services/platform-api
docker run --rm -p 127.0.0.1:3000:3000 platform-api:dev
```

The multi-stage Dockerfile uses `node:24.22.2-bookworm-slim`, frozen dependency installs, and a separate production dependency stage. Runtime contains compiled code, production dependencies, and `package.json`; it executes `node dist/main.js` as the non-root `node` user with `NODE_ENV=production` and port 3000.

## Immutable delivery

Image repository: `ghcr.io/gogpenguin/secure-agentic-platform/platform-api`.

| Release | Published digest | Status at this checkpoint |
| --- | --- | --- |
| v0.1.0 — A | `sha256:48ec5b5fe780bcd39fc5e1e09912b08acf4ccb777f1e37fab49d80452222b3c5` | Previously deployed, per user confirmation |
| v0.1.1 — B | `sha256:a7b7c1b24d3d260938beb4ba959e2e0530fe04c59ecd24f1c3072fb37159a861` | Selected in this branch; live promotion verification pending |

Helm chart **0.2.0** accepts optional `image.digest`. A digest takes precedence over `image.tag`, producing `repository@sha256:…`. Without a digest, tag behavior and the chart `appVersion` fallback remain intact. The schema rejects malformed digests. Chart `appVersion` remains **1.16.0** for existing workloads and is independent of the API package version.

`container.port` overrides `service.port` for the container. Services and probes use named port `http`. Platform API runs one replica with container and Service port 3000, requests of 100m CPU/128Mi memory, limits of 500m CPU/256Mi memory, and a dedicated `platform-api` ServiceAccount with token automount disabled. Ingress, HTTPRoute, and autoscaling are disabled.

The workflow runs independent Helm and API validation on PRs and main pushes. Only the publishing job receives `packages: write`; it requires both validations and runs only on main pushes. It uses temporary `GITHUB_TOKEN`, SHA-pinned Docker actions, and publishes `sha-<full-commit-sha>` tags for `linux/amd64`. The registry digest and immutable reference are recorded in job outputs and the summary. Deployment identity is the digest, not the tag. Current Helm CI renders frontend/backend/sandbox; Platform API values were also linted and rendered locally.

Promotion: publish and verify the image, change only `image.digest` through a GitOps PR, compare manifests, merge after review, then observe Argo CD. Rollback: open another reviewed PR restoring retained Digest A (or revert only the promotion change), then verify reconciliation and HTTP version. Do not rebuild an old version as a substitute for restoring its original digest.

## GitOps validation and access

```bash
helm lint charts/web-app -f environments/platform-api-values.yaml
helm template platform-api charts/web-app -n gitops-apps -f environments/platform-api-values.yaml
kubectl config current-context
kubectl get applications -n argocd
argocd app get platform-api
kubectl -n gitops-apps rollout status deployment/platform-api-web-app
kubectl -n gitops-apps get deployment platform-api-web-app -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n gitops-apps port-forward svc/platform-api-web-app 3000:3000
```

In another terminal:

```bash
curl -i http://localhost:3000/api/v1/info
curl -i http://localhost:3000/health/live
curl -i http://localhost:3000/health/ready
```

Expect the version corresponding to the reconciled digest. Before/after local promotion renders changed only the Platform API Deployment image; frontend, backend, and sandbox manifests remained byte-for-byte unchanged.

## Bootstrap and limitations

An existing cluster should be continued in place. For a fresh lab, install Docker, kind, kubectl, Helm, and a tested Argo CD release; create the cluster using `infrastructure/kind/cluster.yml`. After Argo CD is ready and the workload namespace exists, the initial handoff is:

```bash
kubectl apply -n argocd -f bootstrap/argocd/root.yaml
```

This is a bootstrap outline, not a validated disaster-recovery runbook. The node image and Argo CD installation release still need reproducible pins. Changes to `root.yaml` itself require a bootstrap update because the root watches only `control-plane/`.

AppProject restricts the repository, destination namespace, and resource kinds to Deployment, Service, and ServiceAccount. These boundaries do not replace RBAC, NetworkPolicy, Pod Security, or secret management. The chart's Helm test-hook Pod is skipped by Argo CD and is outside that allowlist. Retain deployment and rollback digests in GHCR. Anonymous image pulling has been verified for the published application image; package visibility must continue to allow cluster pulls without registry secrets.

This remains a local, single-control-plane learning environment. Monitoring, security scanning, workload network isolation, hardened bootstrap permissions, and clean-cluster recovery remain future work. Never commit credentials, local environment secrets, kubeconfigs, or Terraform state; the root `.gitignore` excludes common generated and sensitive files.

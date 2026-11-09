# Secure Agentic Platform — Project Context

**Last updated:** 2026-11-09
**Roadmap:** Secure Agentic Platform — 36 Weeks
**Current milestone:** Week 4 complete (user confirmation); next: Week 5 observability
**Repository:** https://github.com/GoGPenguin/secure-agentic-platform

## Goal and learning approach

Build a GitOps-driven platform for cloud-native applications, progressing through platform engineering, cloud security, AI infrastructure, and secure agents. The Platform API uses TypeScript/NestJS; a future AI Incident Agent will use Python.

Act as a senior Platform Engineering mentor: explain decisions and trade-offs, offer hands-on challenges, review user-written code and YAML, encourage independent debugging, and validate outcomes using observable evidence. Avoid complete copy-paste solutions unless requested. Use the roadmap Excel when available to determine subsequent milestones; it was inspected during the repository cleanup.

Preserve existing workloads and prefer incremental, reversible changes. Do not recreate the cluster, reinstall Argo CD, or delete Applications unless explicitly required for recovery or an exercise.

## Current checkpoint and evidence boundaries

Cleanup update: the user confirms Week 4 is complete. The promotion/rollback details below are historical evidence boundaries from the earlier checkpoint, not the current task list. Cleanup did not independently repeat rollout or rollback. The Hello World endpoint and its tests, unused Mau deployment tooling, and bootstrap test annotation were removed. Application values now inherit shared defaults; Helm connection tests use /health/ready for the API.

The last inspected branch is `feature/promote-platform-api-0.1.1`. Its HEAD before this documentation update is `be8de59` (`chore(gitops): promote platform API to v0.1.1`). The working tree was clean before the documentation edits. Source release v0.1.1 and repository hygiene changes were confirmed on fetched `origin/main` at `a6aa378`.

The user confirmed Platform API v0.1.0 was deployed. The current branch selects v0.1.1 Digest B. Local promotion validation passed, but promotion merge, live v0.1.1 rollout, and the digest rollback exercise have not been verified in this session. Do not report them as completed without evidence.

| Milestone | Status and evidence |
| --- | --- |
| Weeks 1–3 | Core Kubernetes, Helm, GitOps, ApplicationSet, and AppProject milestones completed |
| App-of-Apps | Implemented; root previously observed Synced/Healthy; clean recovery untested |
| W04-A | API, unit/HTTP tests, production container, and CI validation completed |
| W04-B1 | Backward-compatible chart digest support and schema merged in PR #4 |
| W04-B2 | Protected-main publishing implemented and merged in PR #5 |
| W04-B3 | Published image anonymous pull, amd64 compatibility, startup, and HTTP smoke tests confirmed by user |
| W04-B4 | Platform API ApplicationSet metadata and values merged in PR #6; v0.1.0 deployment confirmed by user |
| W04-B5 release | Source v0.1.1 merged in PR #7; hygiene follow-up merged in PR #8 |
| W04-B5 promotion | Digest-only change prepared and locally validated; branch commit `be8de59` |
| W04-B5 rollback | Pending controlled promotion verification, then a reviewed restoration of Digest A |

## Repository and controller architecture

```text
infrastructure/kind/cluster.yml                    local cluster topology
bootstrap/argocd/root.yaml                        platform-root bootstrap
bootstrap/argocd/control-plane/secure-platform.yaml AppProject
bootstrap/argocd/control-plane/platform-apps.yaml   ApplicationSet
app-configs/{frontend,backend,sandbox,platform-api}.yaml
                                                  generator metadata
environments/*-values.yaml                        per-application configuration
charts/web-app/                                   shared Helm chart and digest schema
services/platform-api/                            application, tests, Dockerfile, lockfile
.github/workflows/platform-ci.yaml                validation and publishing
docs/PROJECT_CONTEXT.md                           continuation context
```

`platform-root` watches `bootstrap/argocd/control-plane` on `main`, using the default AppProject in the `argocd` namespace. Wave -1 creates the AppProject before the wave 0 ApplicationSet. The root does not watch its own `root.yaml`. The permissive default bootstrap project remains a future hardening item.

`platform-apps` uses the Git file generator over `app-configs/*.yaml`, Go templates, and `missingkey=error`. Each file supplies `name`, `namespace`, and `valuesFile`. The generated Application uses:

- Project `secure-platform`.
- Destination `https://kubernetes.default.svc`, namespace `gitops-apps`.
- Repository `https://github.com/GoGPenguin/secure-agentic-platform.git`, revision `main`.
- Chart path `charts/web-app`, release name matching the application name.
- A second source with `ref: chart-repo`, loading `$chart-repo/{{.valuesFile}}`.

Root and generated Applications self-heal automatically with pruning disabled. ApplicationSet uses `applicationsSync: create-update` and `preserveResourcesOnDeletion: true`. These are committed settings; inspect actual finalizers before relying on deletion protection.

Legacy standalone Applications and demo manifests were removed during cleanup. A read-only live check found only backend, frontend, sandbox, platform-api, and platform-root; the root source is control-plane/. Historical exercises remain in Git history.

## Applications and chart behavior

| Application | Deployment | Replicas | Image / container and Service port |
| --- | --- | --- | --- |
| frontend | frontend-web-app | 2 | nginx:1.16.0 / 80 |
| backend | backend-web-app | 1 | httpd:latest / 80 |
| sandbox | sandbox-web-app | 1 | nginx:1.16.0 / 80 |
| platform-api | platform-api-web-app | 1 | GHCR digest / 3000 |

Before B2, frontend/backend/sandbox and the root were observed Synced/Healthy; existing deployments had all replicas available. No new live health check was run for this documentation update.

Chart version is `0.2.0`; `appVersion` remains `1.16.0`. The API version is independent of chart appVersion. Shared helpers implement:

- Nonempty `image.digest`: `repository@digest`, taking precedence over tag.
- Empty digest: existing `repository:tag`, falling back to chart appVersion for an empty tag.
- Schema validation: digest must be empty or `sha256:` plus exactly 64 hexadecimal characters.
- Explicit `container.port` takes precedence; omission falls back to `service.port`.
- Service `targetPort` and HTTP probes use named container port `http`.

B1 validation proved existing renders differed only in `helm.sh/chart` labels caused by the required chart version increment. That Pod template label can trigger a rollout. B5 promotion comparison had no chart changes: only the API Deployment image changed; existing workload manifests matched byte-for-byte.

The chart includes a Helm test-hook Pod. It is outside the AppProject allowlist and is skipped by Argo CD; normal managed resources are ServiceAccount, Service, and Deployment. The chart does not currently expose Pod/container securityContext or imagePullSecrets configuration.

## Platform API implementation

NestJS 12, TypeScript ESM, Vitest, Supertest, and pnpm. Relative application imports use `.js`. Follow `services/platform-api/AGENTS.md` when changing application code.

`InfoModule` owns `InfoController` and `InfoService`; `HealthModule` independently owns the health routes. No database, authentication, broker, external service checks, or AI functionality has been added. The starter `/` endpoint remains.

| Route | HTTP 200 body |
| --- | --- |
| `/api/v1/info` | `{"service":"platform-api","version":"0.1.1"}` for v0.1.1 |
| `/health/live` | `{"status":"ok"}` |
| `/health/ready` | `{"status":"ready"}` |

InfoService loads service name and version from `package.json` through `createRequire`. The package file must remain beside `dist` in runtime artifacts. Version 0.1.1 changed only package metadata and the two explicit test expectations; the dependency lockfile remained valid without changes. Readiness currently reflects HTTP application availability, not external dependencies or shutdown draining.

The Dockerfile and CI use Node.js `24.22.2`; Docker installs pnpm `12.16.1`. Frozen lockfile installs are used. Separate build and production dependency stages produce a runtime with `dist`, production `node_modules`, and `package.json`. It starts `node dist/main.js` as user `node` (UID/GID 1000 in local verification), with `NODE_ENV=production` and port 3000. The base is `node:24.22.2-bookworm-slim`, version-tagged rather than digest-pinned.

Platform API Helm values configure one replica, `IfNotPresent`, ClusterIP port 3000, requests of 100m CPU/128Mi memory, and limits of 500m CPU/256Mi memory. Dedicated ServiceAccount `platform-api` sets `automountServiceAccountToken: false`; the Deployment has no override, so the application Pod inherits false. Liveness uses `/health/live` with 15s delay/10s period; readiness uses `/health/ready` with 5s delay/5s period. Both have 2s timeouts and failure threshold 3. Ingress, HTTPRoute, and HPA are disabled.

## CI and publishing security

`.github/workflows/platform-ci.yaml` runs on PRs targeting main and pushes to main. Helm Validation and Platform API CI are independent jobs. Helm CI lints the chart and renders all four applications, including explicit API values validation. API CI installs frozen dependencies, runs unit and HTTP tests, builds TypeScript, and builds Docker. Platform API Helm values are validated in CI and can also be checked locally with the commands below.

The publishing job requires both validation jobs and runs only on main pushes. Workflow permissions default to `contents: read`; only publishing adds `packages: write`. Checkout credential persistence is disabled. Publishing uses temporary `GITHUB_TOKEN`, SHA-pinned Docker actions, explicit local build context, and `linux/amd64`. It adds source/revision OCI labels, tags images `sha-<full-commit-sha>`, captures the registry digest, validates its format, and writes the immutable reference to job outputs and summary.

There is no PAT, PR publishing, direct Kubernetes deployment, repository commit, or automatic GitOps promotion from CI. GitHub branch protection is established per user confirmation; remote settings were not re-audited here. A successful main push publishes an artifact; it does not itself change the deployed digest. Even a GitOps-only merge currently triggers validation and publishing again, so retain the explicitly approved artifact identity.

## Image identity, promotion, and rollback

Repository: `ghcr.io/gogpenguin/secure-agentic-platform/platform-api`.

| Artifact | Version | Registry digest |
| --- | --- | --- |
| A | 0.1.0 | `sha256:48ec5b5fe780bcd39fc5e1e09912b08acf4ccb777f1e37fab49d80452222b3c5` |
| B | 0.1.1 | `sha256:a7b7c1b24d3d260938beb4ba959e2e0530fe04c59ecd24f1c3072fb37159a861` |

Current branch values select B. The last user-confirmed deployed version was A. Publication of both artifacts was supplied as project evidence; no live B promotion or rollback was performed by the agent. Anonymous pull and local startup/smoke verification were confirmed by the user before B4. No Kubernetes registry credential was introduced.

Promotion procedure:

1. Confirm the application release and publishing run on protected main.
2. Record the published digest; verify architecture, anonymous pull, and runtime behavior.
3. Start from latest main with a clean working tree.
4. Change only `image.digest` in `environments/platform-api-values.yaml`.
5. Lint and render; compare against baselines and preserve other applications.
6. Submit a reviewed PR; after merge, observe existing Argo CD reconciliation.
7. Record Application health/sync, Deployment image, rollout, running image IDs, and HTTP version.

Rollback procedure (pending execution): create another reviewed GitOps PR restoring A, or revert the isolated promotion change without reverting unrelated configuration. Preserve both artifacts in GHCR. After merge, verify the Deployment returns to A and the API reports 0.1.0 while probes succeed. Do not use direct kubectl deployment, helm upgrade, or an Argo rollback that conflicts with Git desired state. Source package metadata may remain 0.1.1 while the older image is intentionally deployed.

Historical Git-based rollback of frontend replicas was completed with revert `084eb32` of change `836242d`; this does not constitute evidence of the new API digest rollback exercise.

## Verification evidence and commands

Latest local v0.1.1 release checks: frozen install passed; two unit tests passed; four HTTP tests passed; TypeScript and Docker builds passed. The locally built container returned 200 and exact expected bodies for info (0.1.1), liveness, and readiness.

Latest promotion checks: Helm lint passed; rendered API Deployment used exact B; comparing complete before/after renderings showed only one image substitution; frontend/backend/sandbox renderings were byte-for-byte unchanged. Baselines were saved under `/tmp/platform-api-promotion-5_nc5wyu` during the session. Temporary artifacts are not durable repository evidence.

From the repository root:

```bash
cd services/platform-api
pnpm install --frozen-lockfile
pnpm test
pnpm run test:e2e
pnpm run build
cd ../..
docker build -t platform-api:dev services/platform-api
helm lint charts/web-app -f environments/platform-api-values.yaml
helm template platform-api charts/web-app -n gitops-apps -f environments/platform-api-values.yaml
```

After a reviewed merge and reconciliation, inspect:

```bash
kubectl config current-context
kubectl get applications -n argocd -o custom-columns='NAME:.metadata.name,PROJECT:.spec.project,OWNER:.metadata.ownerReferences[*].name,SYNC:.status.sync.status,HEALTH:.status.health.status'
argocd app get platform-api
kubectl -n gitops-apps rollout status deployment/platform-api-web-app
kubectl -n gitops-apps get deployment platform-api-web-app -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n gitops-apps get pods -l app.kubernetes.io/instance=platform-api -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[*].imageID}{"\n"}{end}'
kubectl -n gitops-apps get serviceaccount platform-api -o yaml
kubectl -n gitops-apps port-forward svc/platform-api-web-app 3000:3000
```

In another terminal, curl `/api/v1/info`, `/health/live`, and `/health/ready` on `http://localhost:3000`. For a multi-manifest image, runtime imageID can identify a platform manifest rather than the top-level index; inspect that relationship before concluding there is a mismatch.

## Security boundaries and remaining limitations

AppProject allows only this Git repository, the in-cluster destination in `gitops-apps`, and namespace resource kinds Service, ServiceAccount, and Deployment. Earlier unauthorized destination (`kube-system`) and repository tests were rejected with InvalidSpecError; temporary test Applications were removed. No unrestricted cluster-resource whitelist is configured.

AppProject does not replace Kubernetes RBAC, NetworkPolicy, Pod Security Admission, image scanning, or secret management. Remaining work includes monitoring/observability, security scanning, workload isolation, multi-cluster operations, private registry authentication if visibility changes, and bootstrap project hardening. Existing frontend/sandbox images and backend `latest` still use tags; immutable delivery currently applies to Platform API.

The kind config defines one control plane and two workers but does not pin node images. Original Week 1 observations included Kubernetes v1.37.0 and Docker 29.9.3; these are historical observations, not a new environment audit. Argo CD installation and CLI version recording still need a tested reproducibility runbook. Clean-cluster restoration remains unvalidated.

The tracked root `.gitignore` excludes dependencies, compiled output, caches, common credential paths, environment files, and Terraform state while retaining source, workflows, Helm/GitOps YAML, example environment files, and pnpm-lock.yaml. It cannot detect secrets embedded in arbitrary files.

## Next actions

Begin Week 5: Prometheus/Grafana, request rate, error rate, latency, three PromQL queries, and generated traffic demonstrating metric changes. Preserve published rollback digests. Week 6 includes a clean-cluster recovery drill; reproducible bootstrap and recorded evidence remain important.

# Secure Agentic Platform
## Project Context & Progress Snapshot

**Last updated:** 2026-11-09  
**Roadmap:** Secure Agentic Platform — 36 Weeks  
**Current progress:** Week 1–3 completed (core milestones)  
**Current focus:** Platform Engineering, GitOps, Kubernetes Security  
**Repository:** https://github.com/GoGPenguin/secure-agentic-platform

---

# 1. Project Overview

## Goal

Build a secure, scalable, GitOps-driven platform for deploying and operating cloud-native applications, progressing toward:

- Platform Engineering
- Cloud Security / DevSecOps
- AI Infrastructure
- Secure AI Agents
- Agentic Platform Architecture

The project follows a 36-week hands-on learning roadmap.

Learning approach:

1. Understand architecture and core concepts.
2. Implement features through hands-on challenges.
3. Debug real problems.
4. Validate using observable evidence.
5. Document results and Git commits.
6. Progress incrementally toward production-oriented architecture.

---

# 2. Current Technology Stack

| Category | Technology |
|---|---|
| Container orchestration | Kubernetes |
| Local cluster | kind |
| GitOps controller | Argo CD |
| Application generation | Argo CD ApplicationSet |
| GitOps security | Argo CD AppProject |
| Platform bootstrap | App-of-Apps |
| Package management | Helm |
| Template engine | Helm templates |
| Source control | Git + GitHub |
| Container image | Nginx |
| Configuration management | YAML |
| Local OS | Linux |
| GitOps reconciliation | Argo CD automated sync |
| Security model | Repository, namespace and resource restrictions |

---

# 3. Repository Directory Structure

The following represents the intended repository layout after the App-of-Apps implementation.

```text
secure-agentic-platform/
│
├── README.md
│
├── infrastructure/
│   └── kind/
│       └── cluster.yml
│
├── bootstrap/
│   └── argocd/
│       │
│       ├── root.yaml
│       │
│       ├── control-plane/
│       │   ├── secure-platform.yaml
│       │   └── platform-apps.yaml
│       │
│       └── apps/
│           ├── frontend.yaml
│           ├── backend.yaml
│           └── demo-app.yaml
│
├── app-configs/
│   ├── frontend.yaml
│   ├── backend.yaml
│   └── sandbox.yaml
│
├── charts/
│   └── web-app/
│       ├── Chart.yaml
│       ├── values.yaml
│       │
│       └── templates/
│           ├── _helpers.tpl
│           ├── deployment.yaml
│           ├── service.yaml
│           ├── serviceaccount.yaml
│           ├── hpa.yaml
│           ├── ingress.yaml
│           ├── httproute.yaml
│           ├── NOTES.txt
│           └── tests/
│
├── environments/
│   ├── frontend-values.yaml
│   ├── backend-values.yaml
│   └── sandbox-values.yaml
│
├── applications/
│   └── demo-app/
│       ├── deployment.yml
│       └── service.yml
│
└── docs/
    ├── architecture/
    └── gitops/
```

**Directory verification note:** The `control-plane/` and `root.yaml` structure reflects the App-of-Apps design implemented according to the user's confirmation. The final on-disk tree has not been independently inspected. Legacy `demo-app` manifests may still exist in Git, although the corresponding live Application and Deployment were previously absent.

## Directory Responsibilities

| Directory | Responsibility |
|---|---|
| `infrastructure/kind/` | Kubernetes cluster configuration |
| `bootstrap/argocd/root.yaml` | Root Application bootstrap |
| `bootstrap/argocd/control-plane/` | GitOps-managed platform configuration |
| `bootstrap/argocd/apps/` | Legacy standalone Application definitions |
| `app-configs/` | ApplicationSet Git generator input |
| `charts/web-app/` | Shared reusable Helm chart |
| `environments/` | Application-specific Helm values |
| `applications/demo-app/` | Original Kubernetes manifest exercise |
| `docs/` | Technical documentation |

**Important:** Frontend and backend are now managed by ApplicationSet. Their old standalone Application YAML files should not be reconciled independently by another controller.

---

# 4. Current GitOps Architecture

## Architecture Pattern

The platform combines:

1. App-of-Apps
2. ApplicationSet Git File Generator
3. AppProject security boundaries
4. Helm-based application deployment

```text
                    GitHub Repository
                           |
                           v
                    platform-root
                   (Root Application)
                           |
                +----------+----------+
                |                     |
                v                     v
           AppProject             ApplicationSet
         secure-platform           platform-apps
                |                     |
                |              Git File Generator
                |                     |
                |                     v
                |                 app-configs/
                |                     |
                |          +----------+----------+
                |          |          |          |
                |          v          v          v
                |       frontend   backend    sandbox
                |          |          |          |
                +----------+----------+----------+
                                      |
                                      v
                               Helm Chart
                               charts/web-app
                                      |
                                      v
                                Kubernetes
                                 kind cluster
                                      |
                                      v
                                 gitops-apps
```

## Controller Responsibilities

### Root Application

Name:

`platform-root`

Responsibilities:

- Manage `secure-platform` AppProject.
- Manage `platform-apps` ApplicationSet.
- Reconcile platform configuration from Git.

Bootstrap mechanism:

- Root Application initially installed manually.
- Its source points to the control-plane manifests.
- Root auto-reconciliation is part of the implemented design; live verification evidence should be retained.

### ApplicationSet

Name:

`platform-apps`

Generator:

```yaml
generators:
  - git:
      repoURL: https://github.com/GoGPenguin/secure-agentic-platform.git
      revision: main
      files:
        - path: app-configs/*.yaml
```

Responsibilities:

- Discover application configuration files.
- Generate Argo CD Applications.
- Update generated Application specifications.
- Manage existing frontend, backend and sandbox Applications.

Configuration:

```yaml
goTemplate: true

goTemplateOptions:
  - missingkey=error

syncPolicy:
  applicationsSync: create-update
```

The implementation also proposed:

```yaml
preserveResourcesOnDeletion: true
```

Verify its live configuration and existing Application finalizers before relying on deletion protection.

### AppProject

Name:

`secure-platform`

Responsibilities:

- Restrict allowed Git repositories.
- Restrict Kubernetes destinations.
- Restrict resource kinds.
- Apply least-privilege deployment boundaries.

Allowed repository:

```text
https://github.com/GoGPenguin/secure-agentic-platform.git
```

Allowed cluster:

```text
https://kubernetes.default.svc
```

Allowed namespace:

```text
gitops-apps
```

Allowed namespace-scoped resource kinds:

```text
Service
ServiceAccount
Deployment
```

No unrestricted cluster-scoped resource whitelist is configured.

---

# 5. ApplicationSet Configuration

## Git File Generator

Application metadata is separated from Helm values.

Example:

`app-configs/frontend.yaml`

```yaml
name: frontend
namespace: gitops-apps
valuesFile: environments/frontend-values.yaml
```

`app-configs/backend.yaml`

```yaml
name: backend
namespace: gitops-apps
valuesFile: environments/backend-values.yaml
```

`app-configs/sandbox.yaml`

```yaml
name: sandbox
namespace: gitops-apps
valuesFile: environments/sandbox-values.yaml
```

ApplicationSet uses Go templates:

```text
{{.name}}
{{.namespace}}
{{.valuesFile}}
```

Helm release names are dynamically generated using:

```yaml
helm:
  releaseName: '{{.name}}'
```

Each Application uses the same reusable Helm chart:

```text
charts/web-app
```

Application-specific values are loaded using Argo CD multiple sources:

```text
$chart-repo/environments/<application>-values.yaml
```

## ApplicationSet Ownership

Verified Kubernetes ownership:

```text
NAME       OWNER
backend    platform-apps
frontend   platform-apps
sandbox    platform-apps
```

Verified ApplicationSet status:

```text
Health: Healthy
Resources Count: 3
```

ApplicationSet controller events confirmed:

```text
created Application "sandbox"
updated Application "backend"
updated Application "frontend"
```

---

# 6. Deployed Applications

Most recently verified Application state:

| Application | Project | Sync | Health | Owner |
|---|---|---|---|---|
| frontend | secure-platform | Synced | Healthy | platform-apps |
| backend | secure-platform | Synced | Healthy | platform-apps |
| sandbox | secure-platform | Synced | Healthy | platform-apps |

Deployment configuration:

| Deployment | Namespace | Desired replicas |
|---|---|---|
| frontend-web-app | gitops-apps | 2 |
| backend-web-app | gitops-apps | 1 |
| sandbox-web-app | gitops-apps | 1 |

All three Applications were confirmed healthy during the ApplicationSet migration.

The original `demo-app` was removed from the live cluster and is not part of the current ApplicationSet.

---

# 7. Helm Architecture

Reusable chart:

```text
charts/web-app
```

Supported configuration:

- Replica count
- Container image
- Image tag
- Service type and port
- ServiceAccount
- CPU and memory requests
- CPU and memory limits
- Liveness probe
- Readiness probe
- Ingress
- HTTPRoute
- HorizontalPodAutoscaler

## Resource Naming

The Helm chart uses:

```text
web-app.fullname
```

The resulting resource name is based on Helm release name and chart naming overrides.

Examples:

```text
frontend → frontend-web-app
backend  → backend-web-app
sandbox  → sandbox-web-app
```

This allows multiple Applications to reuse one chart without duplicating Deployment and Service manifests.

---

# 8. Security Implementation

## AppProject Least Privilege

Implemented restrictions:

```yaml
sourceRepos:
  - https://github.com/GoGPenguin/secure-agentic-platform.git

destinations:
  - namespace: gitops-apps
    server: https://kubernetes.default.svc

namespaceResourceWhitelist:
  - group: ""
    kind: ServiceAccount
  - group: ""
    kind: Service
  - group: apps
    kind: Deployment
```

Cluster-scoped resources are not broadly permitted.

## Security Test 1 — Unauthorized Destination

Test:

```text
Application: security-test
Destination: kube-system
Project: secure-platform
```

Observed:

```text
InvalidSpecError

application destination server
'https://kubernetes.default.svc'
and namespace 'kube-system'
do not match any of the allowed destinations
in project 'secure-platform'
```

Result:

**PASS — Unauthorized destination rejected.**

Temporary Application deleted after testing.

## Security Test 2 — Unauthorized Repository

Test repository:

```text
https://github.com/argoproj/argo-cd.git
```

Observed:

```text
InvalidSpecError

application repo
https://github.com/argoproj/argo-cd.git
is not permitted in project 'secure-platform'
```

Result:

**PASS — Unauthorized repository rejected.**

Temporary Application deleted after testing.

## Security Model

AppProject provides Argo CD authorization boundaries.

It does not replace:

- Kubernetes RBAC
- NetworkPolicy
- Pod Security Admission
- Git repository access controls
- Secret management
- Container image security

These remain relevant to future roadmap milestones.

---

# 9. App-of-Apps Bootstrap Automation

## Implemented Design

Root Application:

```text
platform-root
```

Git source path:

```text
bootstrap/argocd/control-plane
```

Managed resources:

```text
AppProject/secure-platform
ApplicationSet/platform-apps
```

Root Application uses:

```yaml
project: default
```

This is a temporary bootstrap design for the learning environment.

Production-oriented improvement:

Use a dedicated bootstrap AppProject with tightly controlled repository permissions.

## Sync Order

```text
Wave -1 → AppProject
Wave  0 → ApplicationSet
```

AppProject is created before the ApplicationSet is reconciled.

## Safety Controls

Recommended configuration:

- Root automatic pruning disabled.
- ApplicationSet `applicationsSync: create-update`.
- No root Application cascading-deletion finalizer.
- Preserve existing resource names.
- Avoid deleting existing Applications during migration.
- Review Argo CD diffs before major configuration changes.

## Important Limitation

The root Application watches:

```text
bootstrap/argocd/control-plane/
```

It does not watch:

```text
bootstrap/argocd/root.yaml
```

Therefore, changes to `root.yaml` itself still require an explicit bootstrap update unless another mechanism is introduced.

## Verification Status

App-of-Apps implementation was confirmed by the user.

The following evidence should be recorded separately:

```text
argocd app get platform-root
argocd app resources platform-root
```

The root auto-reconciliation annotation test was proposed but its final terminal output has not been provided.

Do not treat disaster recovery on a clean cluster as validated yet.

---

# 10. GitOps Reconciliation and Rollback

Previously completed exercises include:

### GitOps Reconciliation

- Modify Git-managed Deployment configuration.
- Commit and push changes.
- Argo CD detects changes.
- Argo CD reconciles Kubernetes resources.

### GitOps Rollback

A Git commit changed frontend replica configuration.

The change was reverted using:

```bash
git revert 836242d
```

Resulting revert commit:

```text
084eb32
```

Argo CD subsequently reconciled the reverted desired state.

This demonstrated a Git-based rollback workflow.

---

# 11. Important Git Commits

| Commit | Description |
|---|---|
| `084eb32` | GitOps rollback using Git revert |
| `4656733` | Introduced custom AppProject and frontend project migration |
| `cf2511f` | Added frontend/backend configurations for ApplicationSet |

GitHub repository:

https://github.com/GoGPenguin/secure-agentic-platform

The latest App-of-Apps commit hash has not been recorded in the conversation.

Use:

```bash
git log -10 --oneline
```

to retrieve the most recent history.

---

# 12. Roadmap Progress

## Week 1 — Kubernetes Foundation

Completed activities:

- Local Kubernetes kind cluster.
- Kubernetes workload deployment.
- Namespace and Deployment operations.
- Pod and Service inspection.
- Basic Kubernetes debugging.

## Week 2 — Helm and GitOps Foundation

Completed activities:

- Argo CD installation.
- Application synchronization.
- Reusable Helm chart.
- Frontend/backend deployment.
- GitOps reconciliation.
- Git-based rollback.
- Helm chart rendering and validation exercises.

## Week 3 — Advanced GitOps

### W03-A — ApplicationSet

**Status: Done**

Evidence:

- Git File Generator configured.
- Sandbox Application automatically generated.
- Frontend/backend migrated to ApplicationSet.
- OwnerReferences confirmed.
- All three Applications Synced/Healthy.

### W03-B — AppProject

**Status: Done**

Evidence:

- Restricted AppProject created.
- Repository allowlist implemented.
- Destination restriction implemented.
- Resource kinds restricted.
- Unauthorized namespace rejected.
- Unauthorized repository rejected.

### Additional — App-of-Apps

**Status: Implemented (user-confirmed)**

Implemented:

- Root Application architecture.
- GitOps-managed control-plane configuration.
- AppProject/ApplicationSet bootstrap design.

Follow-up verification:

- Confirm root Application ownership and health.
- Confirm root auto-reconciliation with an actual Git change.
- Test clean-cluster recovery later.

---

# 13. Current Known Limitations

The platform is suitable for learning and development but is not yet production-ready.

Known limitations:

1. Kubernetes runs locally using kind.
2. No verified multi-cluster deployment.
3. No verified production-grade secret management.
4. No verified workload NetworkPolicy implementation.
5. No verified CI security scanning pipeline.
6. No verified Kubernetes RBAC hardening beyond AppProject restrictions.
7. No validated disaster-recovery procedure on a fresh cluster.
8. Root Application uses the permissive default AppProject.
9. No demonstrated CI-based approval gates for platform configuration changes.
10. No confirmed monitoring/observability stack.

These limitations should inform future roadmap milestones rather than be treated as failures of Weeks 1–3.

---

# 14. Useful Verification Commands

## Kubernetes

```bash
kubectl get nodes

kubectl get pods -A

kubectl get deployments -A

kubectl get deployments -n gitops-apps
```

## Argo CD

```bash
argocd app list

argocd app get platform-root

argocd app get frontend

argocd app get backend

argocd app get sandbox
```

## ApplicationSet

```bash
kubectl get applicationsets -n argocd

kubectl describe applicationset platform-apps -n argocd
```

## AppProject

```bash
kubectl get appprojects -n argocd

kubectl get appproject secure-platform -n argocd -o yaml
```

## Ownership

```bash
kubectl get applications -n argocd \
  -o custom-columns='NAME:.metadata.name,PROJECT:.spec.project,OWNER:.metadata.ownerReferences[*].name,SYNC:.status.sync.status,HEALTH:.status.health.status'
```

## Repository

```bash
tree -L 5 -I '.git|node_modules|venv'

git status

git log -10 --oneline
```

---

# 15. Next Development Priorities

Recommended sequence:

1. Verify and document App-of-Apps reconciliation.
2. Finalize the GitOps architecture README.
3. Continue the next milestone from the 36-week Excel roadmap.
4. Introduce security, CI/CD, observability and infrastructure automation according to roadmap priorities.
5. Revisit disaster recovery when the platform has sufficient bootstrap automation.

Avoid introducing unnecessary additional GitOps controller layers before the roadmap requires them.

---

# 16. Instructions for Future ChatGPT Conversations

When continuing this project:

**Role:** Act as a senior Platform Engineering mentor.

**Learning approach:**

- Provide hands-on engineering challenges.
- Explain architectural decisions and trade-offs.
- Encourage independent debugging.
- Review user-written YAML and code.
- Avoid complete copy-paste solutions unless explicitly requested.
- Use the roadmap Excel to determine the next milestone.
- Preserve existing Kubernetes workloads.
- Prefer incremental, reversible changes.
- Verify success through actual commands and observed outputs.

**Existing environment:**

- Kubernetes kind cluster.
- Argo CD.
- Helm reusable chart.
- ApplicationSet `platform-apps`.
- AppProject `secure-platform`.
- App-of-Apps root `platform-root`.
- Frontend, backend and sandbox Applications.
- GitHub repository `GoGPenguin/secure-agentic-platform`.

**Important:** Do not instruct the user to recreate the cluster, reinstall Argo CD, delete Applications or repeat completed milestones unless recovery or an explicit exercise requires it.

**Current checkpoint:** Week 3 core milestones completed. App-of-Apps implemented; final live root reconciliation evidence and clean-cluster recovery remain separate verification items.

Continue from the latest unfinished milestone in the roadmap.

# Secure Agentic Platform

A hands-on learning project focused on **Platform Engineering, Kubernetes, GitOps, Cloud Security, and secure AI-agent operations**. Built incrementally over a 36-week roadmap.

> **Project status:** Week 1 lab completed on a running local cluster. A full clean-room rebuild has **not yet been tested**.

## Architecture

```text
GitHub: secure-agentic-platform
  ├── infrastructure/kind/cluster.yml    # Local cluster topology
  ├── bootstrap/argocd/demo-app.yaml     # Argo CD Application resource
  └── applications/demo-app/             # Kubernetes desired state
        ├── deployment.yaml
        └── service.yaml
                 │
                 ▼
           Argo CD (argocd namespace)
                 │  compares Git with live resources
                 ▼
         kind: secure-platform
         ├── 1 control-plane node
         ├── 2 worker nodes
         └── default namespace
              ├── demo-app Deployment (3 replicas)
              └── demo-app ClusterIP Service (port 80)
```

Argo CD is configured with **automated synchronization**, **self-healing enabled**, and **automatic pruning disabled**. The repository provides desired configuration; Argo CD reconciles it with the cluster.

## Repository layout

```text
secure-agentic-platform/
├── infrastructure/
│   └── kind/
│       └── cluster.yml
├── bootstrap/
│   └── argocd/
│       └── demo-app.yaml
├── applications/
│   └── demo-app/
│       ├── deployment.yaml
│       └── service.yaml
└── README.md
```

Additional `security/`, `observability/`, and platform directories will be introduced in later roadmap weeks.

## Lab environment

| Component | Version / configuration |
| --- | --- |
| Host OS | Ubuntu 26.04.1 LTS (x86_64) |
| Host resources | 12 logical CPUs, 18.85 GiB RAM |
| Docker Engine | 29.9.3 |
| Kubernetes node image | `kindest/node:v1.37.0` |
| Kubernetes | v1.37.0 |
| Cluster | `secure-platform`: 1 control plane + 2 workers |
| kind CLI | **TODO:** record `kind version` |
| kubectl CLI | **TODO:** record `kubectl version --client` |
| Argo CD | **TODO:** record server/CLI version and pin manifest release |

The versions above describe the **observed lab environment**. For reproducible rebuilds, pin the kind node image and Argo CD installation manifest to versions that have been tested together.

## Prerequisites

Install and verify:

- Docker Engine, running and accessible to your user.
- [`kind`](https://kind.sigs.k8s.io/docs/user/quick-start/).
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/).
- Git.
- Optionally, the [Argo CD CLI](https://argo-cd.readthedocs.io/en/stable/cli_installation/).

```bash
docker info
kind version
kubectl version --client
git --version
```

## Bootstrap from a clean local cluster

> **Caution:** These commands create cluster resources. Double-check your current Kubernetes context before applying anything. Do not delete an existing cluster unless you intend to lose its state.

### 1. Clone the repository

```bash
git clone https://github.com/GoGPenguin/secure-agentic-platform.git
cd secure-agentic-platform
```

### 2. Create the kind cluster

The committed file `infrastructure/kind/cluster.yml` defines one control-plane and two worker nodes.

```bash
kind create cluster --config infrastructure/kind/cluster.yml --name secure-platform --wait 5m
kubectl config current-context
kubectl get nodes -o wide
```

Expected: context `kind-secure-platform`, and **three** nodes in `Ready` state. The node image was `kindest/node:v1.37.0` during the original lab; **pin this explicitly in the cluster configuration** before claiming future rebuilds are version-identical.

### 3. Install Argo CD

```bash
kubectl create namespace argocd
```

**Before running the next command:** replace `REPLACE_WITH_TESTED_ARGOCD_TAG` with the actual Argo CD release tag tested in this project (for example, a tag formatted `vX.Y.Z`). Do not leave this placeholder in a production or automated script.

```bash
ARGOCD_VERSION=v3.6.1+94037c4
kubectl apply -n argocd --server-side --force-conflicts \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
```

This follows the official Argo CD installation pattern but substitutes a pinned release for the moving `stable` branch. The installation grants cluster-level permissions; inspect and trust the manifests before applying them.

Verify:

```bash
kubectl get pods -n argocd
kubectl get deployments -n argocd
kubectl get crd applications.argoproj.io
```

Allow time for Argo CD components to start. All relevant running components should become ready; completed Jobs are normal.

### 4. Bootstrap the Argo CD Application

The initial Application must be created **once** after Argo CD is installed:

```bash
kubectl apply -n argocd -f bootstrap/argocd/demo-app.yaml
kubectl get applications -n argocd
```

The Application points to the `main` branch and the `applications/demo-app` path in this repository. It deploys to the `default` namespace of the in-cluster Kubernetes API. This initial `kubectl apply` is the **bootstrap handoff**; Argo CD subsequently manages the application workloads.

Because automated synchronization is enabled, the demo Deployment and Service should appear without a separate `argocd app sync` command.

### 5. Verify application readiness

Use explicit namespaces to avoid confusion with a context's default namespace:

```bash
kubectl get deployment demo-app -n default
kubectl get pods -n default -l app=demo-app -o wide
kubectl get service demo-app -n default
kubectl rollout status deployment/demo-app -n default
```

Expected: **3/3** Deployment replicas available, with a ClusterIP Service on port 80. Pod placement across the two workers is not guaranteed to be evenly balanced.

If the Argo CD CLI is configured and authenticated:

```bash
argocd app get demo-app
```

Expected: **`Synced`** and **`Healthy`** after reconciliation completes.

### 6. Access the demo application

In one terminal:

```bash
kubectl -n default port-forward svc/demo-app 8888:80
```

In another terminal:

```bash
curl -I http://localhost:8888
```

Expected: HTTP `200 OK` from NGINX. Port-forwarding is local and temporary; it stops when the command exits.

### 7. Optional: Access the Argo CD UI

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Open `https://localhost:8080`. Your browser may warn about the self-signed certificate. Follow the [official first-login instructions](https://argo-cd.readthedocs.io/en/stable/getting_started/) to retrieve the bootstrap password if needed; **never commit it or paste it into documentation**.

## GitOps behavior verified in Week 1

1. **Manual sync:** Argo CD detected that the Git-defined Deployment and Service were missing; a manual sync created them.
2. **Git-driven change:** Updating `replicas` from `2` to `3` and pushing Git commit `fd9d585` changed the Application to `OutOfSync` until it was synchronized.
3. **Self-healing:** With automated sync and self-heal enabled, Argo CD reconciled an out-of-band replica modification back to Git's desired count.
4. **Declarative Application:** The existing Argo CD Application was adopted with `bootstrap/argocd/demo-app.yaml` and remained `Synced` and `Healthy`.

**Interpretation:** `Synced` means the tracked live configuration matches Git; `Healthy` means Argo CD's health checks report that the resources are functioning as expected. An Application can be `OutOfSync` and still `Healthy`.

## Troubleshooting

| Symptom | First checks |
| --- | --- |
| Fewer than three nodes | `kubectl get nodes -o wide` and `kind get nodes --name secure-platform` |
| Docker node missing | `docker ps` and kind cluster creation output |
| `No resources found in argocd namespace` | Include `-n default` when inspecting `demo-app`; inspect `kubectl config view --minify` |
| Argo CD shows `Missing` | Confirm repository access, revision/path, resource namespace, and whether initial sync completed |
| Argo CD shows `OutOfSync` | Run `argocd app diff demo-app`; distinguish manual policy from automated policy |
| Deployment not ready | `kubectl describe deployment demo-app -n default`, `kubectl get pods -n default`, and Pod events/logs |
| Port-forward fails | Ensure the Service exists and has ready endpoints; verify local port `8888` is unused |

## Security and operational notes

- Do **not** commit kubeconfig files, passwords, tokens, private keys, `.env` secrets, or Terraform state.
- This is a **local development lab**, not a production-ready high-availability deployment.
- A single control-plane node is not highly available.
- With automated **prune disabled**, removing resources from Git will not automatically delete their live counterparts.
- `nginx:stable` is a moving image tag; pin an immutable digest when reproducibility becomes a strict requirement.
- The cluster creation procedure has been exercised, but **complete clean-room restoration is still TODO**.

## Useful commands

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -A
kubectl get applications -n argocd
kubectl -n default get deployments,pods,services -l app=demo-app
argocd app get demo-app
argocd app diff demo-app
```

## Official references

- [kind quick start](https://kind.sigs.k8s.io/docs/user/quick-start/)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Argo CD getting started](https://argo-cd.readthedocs.io/en/stable/getting_started/)
- [Argo CD Application specification](https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/)

## Next milestones

- [ ] Record and pin CLI, node image, and Argo CD versions.
- [ ] Test a full rebuild from an empty cluster using this README.
- [ ] Add a root Application (App of Apps) to manage child Applications declaratively.
- [ ] Introduce Helm, environment overlays, observability, and security controls in later roadmap weeks.

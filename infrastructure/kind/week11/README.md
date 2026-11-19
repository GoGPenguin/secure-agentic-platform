# Week 11 Kindnet lab (W11-A.1)

This lab implements Option B from the Week 11 investigation. It uses a dedicated
three-node kind cluster and a standalone kubeconfig. It needs no Argo CD
installation, application manifests, or production GitOps credentials.
NetworkPolicy tests and rules belong to later checkpoints.

## Versions and image identities

| Component | Identity and evidence |
| --- | --- |
| kind CLI | `v0.33.0`. Local version output was `kind v0.33.0 go1.26.7 linux/amd64`. |
| Kubernetes node image | `docker.io/kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5`, the immutable reference published in the [kind v0.33.0 release](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0). All three node entries use this reference. |
| Kindnet | `docker.io/kindest/kindnetd:v20260820-69b56db7`, from the [v0.33.0 node image build source](https://github.com/kubernetes-sigs/kind/blob/v0.33.0/pkg/build/nodeimage/const_cni.go). The investigation observed runtime image ID `sha256:4626fe10df5b930638e6e1662143ee1c7a698de6174fdb61a8ce658e688be2cd` on all three existing amd64 nodes. This is a runtime image ID, distinct from a registry index digest. |

After creation the verifier checks the server and all kubelet versions, Docker
node image references, and each Ready Kindnet Pod's tag and runtime image ID.
A mismatch stops verification. The runtime checks are pending owner authorization
to create the lab. They establish the installed build and readiness. Packet
enforcement requires the later traffic tests.

## Host and tools

Use a native Linux amd64 host with a local Docker daemon at
`unix:///var/run/docker.sock`, kind v0.33.0, kubectl compatible with Kubernetes
v1.37, Python 3.9 or later, and PyYAML. The amd64 restriction lets the verifier
compare the exact observed Kindnet image ID. The Docker daemon needs registry
access if the pinned image is absent locally.

Preflight requires four CPUs visible to Docker and available to the process,
at least 4 GiB available host RAM, and at least 10 GiB free on the Docker
storage filesystem. These are lab headroom thresholds, not measured peak usage.
The lab shares host CPU, memory, disk, and the Docker daemon with existing
clusters. Allow additional capacity for concurrent workloads. Run preflight
from an account that can query Docker and inspect free space on its storage
filesystem.

## Reproduction

From the repository root, validate the configuration offline.

```bash
python3 infrastructure/kind/week11/lab.py validate
```

Run the read-only host preflight before creating the lab.

```bash
python3 infrastructure/kind/week11/lab.py preflight
```

**The owner must explicitly authorize creation of
`secure-platform-w11-netpol` before running the following command.** It invokes
kind with the checked-in config, an explicit lab name, a five-minute wait and
`--retain`, writes `infrastructure/kind/week11/week11.kubeconfig`, and runs
verification. The API binds to a Docker-assigned loopback port. The kubeconfig
is git-ignored. Keep it private.

```bash
python3 infrastructure/kind/week11/lab.py create
```

Rerun verification independently.

```bash
python3 infrastructure/kind/week11/lab.py verify
```

The tool uses the exact context `kind-secure-platform-w11-netpol` and checks
that the kubeconfig has only that context and cluster. It also checks that the
TLS endpoint matches the lab control-plane container's published port before
contacting Kubernetes. A subsequent `create` verifies a matching existing lab.
A partial state, occupied name, or conflicting kubeconfig requires manual review.
Use the standalone kubeconfig when running additional lab commands.

## Recovery and cleanup

If creation or verification fails, keep the lab for diagnosis. Inspect the
named Docker containers and the lab kubeconfig with read-only commands. An
unexpected Kindnet identity requires investigating the pinned node image and
runtime image provenance. Re-run `verify` after resolving transient readiness
issues.

**Deletion requires separate owner authorization for
`secure-platform-w11-netpol`.** Confirm that the locally listed cluster and
kubeconfig belong to the lab, then delete the named cluster using the same
local Docker daemon. Use the dedicated kubeconfig even if creation failed
before writing it. Archive any evidence first. Remove the lab kubeconfig file
separately if it still exists and its removal is authorized.

```bash
env -u DOCKER_HOST -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  DOCKER_CONTEXT=default KIND_EXPERIMENTAL_PROVIDER=docker \
  kind delete cluster --name secure-platform-w11-netpol \
  --kubeconfig infrastructure/kind/week11/week11.kubeconfig
```

There is no automatic cleanup. Pull requests and merges require separate
authorization.

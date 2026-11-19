# Week 11 NetworkPolicy

**CONFIGURATION COMPLETE — STATIC VALIDATION PASSED**

The [policy bundle](../../security/network-policy/) sits outside all reconciled
GitOps source paths. Runtime verification is deferred. No cluster was created
and the [Week 11 lab tooling](../../infrastructure/kind/week11/) was not executed
for this exercise. The intended behavior below requires a policy-capable CNI.

## Topology and default deny

The bundle selects all Pods in `gitops-apps` and `monitoring` with separate
namespace-local default-deny policies. Each explicitly isolates ingress and
egress and has empty rule lists. Kubernetes combines matching allows
additively. Where both endpoints are isolated, the source must allow egress and
the destination must allow ingress. Reply traffic is implicitly allowed.
The bundle contains policies only for these two namespaces. [Kubernetes NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

| Source | Destination | Protocol and port | Configuration evidence and intended result |
| --- | --- | --- | --- |
| `monitoring` Prometheus | `gitops-apps` Platform API Pod IP | TCP 3000 | Allow both directions of policy evaluation for the scrape connection. Prometheus discovers API Pods and scrapes `/metrics`. The policy allows the TCP listener, including its other HTTP routes. [Scrape config](../../monitoring/prometheus/configmap.yaml) |
| `monitoring` Grafana | `monitoring` Prometheus via ClusterIP Service | TCP 9090 | Allow Grafana egress and Prometheus ingress. The provisioned Grafana datasource uses server-side proxy access. [Datasource](../../monitoring/grafana/config/datasources.yaml) · [Prometheus Service](../../monitoring/prometheus/service.yaml) |
| `monitoring` Grafana | `kube-system` CoreDNS | UDP and TCP 53 | Allow Grafana egress for the configured datasource hostname. The prior read-only investigation observed the `kube-dns` Service and CoreDNS Pods labeled `k8s-app=kube-dns`. This bundle adds no policy in `kube-system`. |
| `monitoring` Prometheus | Kubernetes API for Pod discovery | HTTPS, typically Service TCP 443 with a translated control-plane endpoint | **Required and unresolved.** No API egress rule is shipped. [Scrape config](../../monitoring/prometheus/configmap.yaml) · [Discovery Role](../../bootstrap/argocd/control-plane/prometheus-discovery-role.yaml) |
| Frontend, backend, sandbox, and other independent Pod traffic | Other application or monitoring Pods | Any | Default-denied where the bundle isolates the source or destination, unless one of the explicit allows above matches. The chart and values establish listeners for frontend and backend but provide no evidence of frontend-to-backend or frontend-to-API calls. No in-cluster Grafana UI caller was established either. |

The Platform API selector combines `app.kubernetes.io/name=web-app` with
`app.kubernetes.io/instance=platform-api`. The name alone would also select
frontend, backend, and sandbox. The two monitoring Deployments supply
`app.kubernetes.io/name=prometheus` and `app.kubernetes.io/name=grafana`.
Cross-namespace rules put the namespace's `kubernetes.io/metadata.name` label
and the Pod selector in the same peer entry, so both must match. Grafana and
Prometheus share a namespace, so a Pod-only peer scopes those rules locally.
These selectors match workload labels. Control over who can create or relabel
Pods in trusted namespaces remains important.

## DNS and Kubernetes API discovery

Grafana needs DNS for `prometheus.monitoring.svc.cluster.local`. TCP 53 covers
TCP queries and fallback from UDP. The policy limits the resolver destination,
while DNS query names remain unrestricted. The current Platform API and stock
web workloads have no verified DNS dependency. Prometheus uses a literal
loopback address for its self-scrape, discovered Pod IPs for API scrapes, and
in-cluster API configuration for discovery. In-cluster client configuration
uses the injected Kubernetes Service host and port. [Prometheus Kubernetes discovery configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#kubernetes_sd_config) · [Kubernetes in-cluster service discovery](https://kubernetes.io/docs/tasks/run-application/access-api-from-pod/)

Standard NetworkPolicy has no Service selector. The Kubernetes API Service
can translate to a host-network control-plane endpoint with a different IP
and port. CNI implementation and translation order affect what a policy sees,
and host-network traffic may be treated as node traffic. The bundle therefore
contains neither a guessed Service IP rule nor a node or Service CIDR allow.
The existing discovery Role authorizes Pod reads after the connection is
established and supplies no network access.

**Keep activation blocked until the API egress path is resolved and verified.**
On an authorized target, record the injected API host and port, the Service
and backing endpoint, then establish which tuple the target CNI evaluates.
Review a narrow cluster-specific rule or an approved CNI-specific API identity
if available. Verify discovery of a newly created matching target so already
discovered Pods cannot mask an API access failure. Recheck Service translation
for the Grafana datasource and DNS too, including resolver endpoints or
node-local DNS if the target cluster uses it. [Kubernetes NetworkPolicy semantics and limits](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

## Static validation

Use Python 3 with PyYAML and jsonschema, Helm for client-side rendering, and a
local copy of the official Kubernetes v1.37.0 OpenAPI v2 schema. Download the
schema once or obtain the same file from a trusted local cache. The validator
checks its SHA-256, then runs without network access or cluster credentials.

```bash
curl -fLSs -o /tmp/week11-k8s-v137-swagger.json \
  https://raw.githubusercontent.com/kubernetes/kubernetes/v1.37.0/api/openapi-spec/swagger.json
python3 scripts/validate-network-policy.py \
  --swagger /tmp/week11-k8s-v137-swagger.json --negative-tests
```

The validation run passed for all six policy objects against the upstream
schema and exact traffic matrix. The checker also passed the application Helm
renders and monitoring selector and listener checks. All ten negative
mutations were rejected, covering schema type, namespace, isolation direction,
unrestricted ingress and egress, workload selector, missing namespace peer,
unintended backend dependency, wrong port, and missing DNS TCP.
The schema adapter recognizes the Kubernetes Swagger v2 encoding for
integer-or-string ports. Exact policy checks also reject unknown fields,
extra policies, and omitted peer or port restrictions.

Static results cover schema and checked-in configuration. Packet enforcement,
same-node and cross-node behavior, DNS Service routing, API discovery under
isolation, and real allow and deny probes remain deferred.

## Future GitOps integration and rollback

A separately authorized rollout needs a designated policy owner and a
dedicated source path. The current application and monitoring AppProjects
omit `networking.k8s.io/NetworkPolicy` from their allowlists. Review scoped
AppProject destinations, resource kinds, and controller RBAC before integrating.
Inventory additive policies and operational clients, resolve API discovery,
then sequence the intended allows and default-deny with verification at each
stage. Existing Argo CD policies remain outside this rollout.

Prepare a prior-policy manifest and explicit rollback ownership. Existing
Applications disable pruning, so deleting YAML in Git may leave live policies
in place. A future rollback must reconcile the previous policy specs and
explicitly remove the exact policies introduced by the rollout if needed.
Coordinate the desired Git state with any live removals to avoid self-heal
restoring the policies. Verify API discovery, scraping, datasource queries,
and expected isolation afterward.

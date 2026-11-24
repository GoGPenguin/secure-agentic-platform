# Week 11 isolated NetworkPolicy runtime rehearsal

**Prepared for review. Runtime execution is pending owner authorization.**
The target is the separate kind lab `secure-platform-w11-netpol` on the
Machine B host. The existing Machine B platform cluster and Machine A are
outside this rehearsal. The [Week 11 bundle](week11-network-policy.md) remains
inactive on Machine B.

## Architecture and prerequisites

Use the pinned [three-node kind lab](../../infrastructure/kind/week11/README.md)
with one control plane and two workers, Kubernetes v1.37.0, kind v0.33.0 and
Kindnet `v20260820-69b56db7`. Use its standalone kubeconfig and explicitly
select `kind-secure-platform-w11-netpol` for every lab command. Compare the
endpoint, CA fingerprint, `kube-system` UID and Docker node identities with
the protected cluster. Stop on any mismatch or ambiguous context. Record
Machine B workload identities, Argo health, monitoring health, and image
digests before and after the rehearsal with separate read-only queries.

| Lab fixture | Placement and behavior |
| --- | --- |
| `monitoring` Prometheus | Worker A. Use the checked-in version, ConfigMap, Service and Pod-discovery ServiceAccount. Use the checked-in Role and RoleBinding for Pod get/list/watch in `gitops-apps`. Use an empty TSDB for cold discovery phases. Include a small diagnostic sidecar in the same Pod network namespace for fresh, TLS-verified API and HTTP probes. |
| `monitoring` Grafana | Worker B. Use the pinned Grafana image, Prometheus datasource configuration and ClusterIP Service, with disposable storage and lab-only credentials. Include DNS and HTTP probe capability in its Pod network namespace. |
| `gitops-apps` metrics targets | Two synthetic HTTP targets at steady state, one on each worker. Label them `app.kubernetes.io/name=web-app` and `app.kubernetes.io/instance=platform-api`; use regular container `web-app` and named TCP port `http:3000`. Serve a valid `/metrics` response with a test gauge and a separate HTTP control listener on 3001. Introduce fresh targets with unique names, UIDs and gauge values when called for by the matrix. |
| Denial controls | One HTTP decoy in `gitops-apps` with the same `web-app` name and a different instance label. Use ordinary probe Pods in `monitoring`, `gitops-apps` and an unisolated `w11-observer` namespace. Give the observer Pod an HTTP control listener and the same Prometheus label to test ingress isolation across namespaces. |

Use pinned, reviewed amd64 image references for test tooling and the
synthetic server. Keep all fixtures on the lab Pod network. The synthetic
targets need no production image, ServiceAccount token, Service, or secret.
The only API credential used by a workload probe is the projected lab
Prometheus credential. Never log it. Use the Kubernetes Service DNS name for
TLS verification and override DNS resolution when isolating the IP and port
variable. Test using fresh Pod-to-Pod sockets. API-server or host
port-forwards are for observation, such as reading Prometheus's target
state. They cannot establish whether the data path passed NetworkPolicy.

The lab uses standalone Prometheus and `kubernetes_sd_configs` with
`role: pod`. Discovery uses API list/watch plus relabeling. Scraping opens a
separate connection from Prometheus to the selected Pod IP on TCP 3000.
No Prometheus Operator or monitor CRDs are required. In an Operator
deployment, PodMonitor selects Pods and ServiceMonitor selects Services
whose backing endpoints are discovered through Endpoints or EndpointSlices.
That variant would need its own API permissions and selection tests.
[Repository scrape config](../../monitoring/prometheus/configmap.yaml) ·
[Prometheus Kubernetes discovery](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#kubernetes_sd_config) ·
[Prometheus Operator design](https://prometheus-operator.dev/docs/getting-started/design/)

### Capacity and safety gates

Use native Linux amd64, local Docker, the pinned kind version, compatible
kubectl, Python and PyYAML, plus lab image registry access. Before creation,
run the existing read-only lab preflight and confirm at least four available
CPUs, 4 GiB available host RAM, and 10 GiB free on Docker storage. These are
the lab tool's floors. Confirm the host operator has headroom for both
clusters, including inotify instances and watches. Stop if pressure,
production health, image availability, lab name or kubeconfig checks fail.

Budget up to nine lab workload Pods. Use 100m/256 MiB requests for each
monitoring process and 25m/32 MiB per small probe, sidecar, or fixture
container. Reserve at least 500m CPU and 1 GiB requested memory for the lab
workloads, plus the three-node control-plane and add-on overhead. Cap
Prometheus retention at the checked-in 512 MB and use disposable storage.
Keep at most one newly introduced test target in addition to the two steady
targets. Before isolation, verify both workers are Ready and have capacity
for their placements.

## Dataplane and API destination hypothesis

The pinned Kindnet build wires the standard NetworkPolicy evaluator to
`kube-network-policies` at `f67f0fb35e2b`. It uses nftables/NFQUEUE on
new tracked connections, with queue bypass enabled. DaemonSet readiness
alone cannot establish enforcement. Check policy-controller startup and
NFQUEUE errors on each lab node, then require independent allow/deny tests on
same-node and cross-node paths. Use fresh TCP connections after every rule
change. Treat established watches and cached targets as stale evidence.
[Kindnet pinned source](https://github.com/kubernetes-sigs/kind/blob/69b56db7/images/kindnetd/cmd/kindnetd/main.go) ·
[Pinned dependency](https://github.com/kubernetes-sigs/kind/blob/69b56db7/images/kindnetd/go.mod) ·
[Dataplane implementation](https://github.com/kubernetes-sigs/kube-network-policies/blob/f67f0fb35e2b/pkg/dataplane/controller.go)

Record the lab kube-proxy mode and the injected API host/port, Kubernetes
Service VIP and port, EndpointSlice address/port, and API server node.
The pinned implementation queues forwarding in postrouting before source
NAT, and has an input hook for Pod-to-host traffic. This suggests the
forwarded API Service request may be evaluated against the translated
endpoint tuple. UDP DNS has a separate post-DNAT prerouting hook with this
Kindnet configuration. Prove both paths in the lab. Kubernetes does not
specify the ordering of Service translation and NetworkPolicy enforcement
across implementations. [Dataplane hooks](https://github.com/kubernetes-sigs/kube-network-policies/blob/f67f0fb35e2b/pkg/dataplane/controller.go#L480) ·
[Kubernetes NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

From the Prometheus sandbox, use its real projected identity and CA to
issue a fresh authenticated GET to
`/api/v1/namespaces/gitops-apps/pods?limit=1` through the Service tuple.
Test the backing endpoint directly with the same TLS identity using
`curl --connect-to`. Pin the Service address with `--resolve` so DNS does
not become an API-path prerequisite. Probe a bounded Pod watch from a
recorded list resourceVersion and corroborate it with a new target UID.
An HTTP 401/403 means the API was reachable and authentication or RBAC
needs diagnosis. A TLS error, connection refusal or timeout gets its own
classification. Only a reproducible, policy-dependent connectivity change
with healthy positive controls counts as network denial.

## Test matrix

Use the six reviewed policy objects. Add any diagnostic API rule only as
a separately reviewed lab overlay. It selects only the Prometheus Pod and
allows only TCP to one recorded IPv4 `/32` and port at a time. Keep all
other manifest inputs constant between candidate trials. Restore the
prior state between trials. If both candidates work or both fail, or if
the API remains reachable under deny, record the exact observations and
inspect the dataplane. Do not infer a portable tuple or widen to node or
Service CIDRs. An API exception caused by node traffic is a finding that
blocks production adoption until understood.

| Stage | Action and probes | Required evidence |
| --- | --- | --- |
| 0. Unisolated baseline | With no lab NetworkPolicies, use authenticated API list/watch through the Service and direct endpoint. Probe both target Pod IPs on 3000 and 3001 from Prometheus and the observer. Probe DNS over UDP and TCP against `kube-dns` Service and record CoreDNS EndpointSlices. Query Grafana's configured datasource from Grafana. | Both targets appear by UID and `up=1`. Both HTTP listeners, DNS transports, and the Grafana datasource succeed. Confirm the decoy is directly reachable and excluded by relabeling. Confirm application-to-observer HTTP succeeds. |
| 1. Default-deny only | Add the two namespace default-deny objects. Use fresh connections from `monitoring` to the target and from the unisolated observer to the target. Probe from `gitops-apps` to a healthy unisolated observer listener. Check new DNS and API connections. | Both directions are shown independently. Application ingress from observer and application egress toward observer fail, as does monitoring-to-application scraping. Expect resolver and API egress denial on enforced paths. Record a reachable host API as an exception or failure to isolate, and investigate. |
| 2. Checked-in allows only | Keep default-deny and add the four existing allows. Probe Prometheus-to-target on both workers, Grafana-to-Prometheus by service DNS and datasource query, and Grafana DNS over UDP and TCP. Cold-start lab Prometheus with an empty TSDB before evaluating API discovery. | Selected 3000 paths succeed. Wrong port 3001, wrong-instance decoy, observer with spoofed Prometheus label, unlabelled monitoring probe, reverse target-to-Prometheus and Prometheus-to-DNS fail on the intended paths. Grafana DNS and 9090 succeed. Expect fresh API discovery to fail if no API exception applies. A residual target from any earlier process cannot prove discovery. |
| 3. API tuple trials | Retain the six-policy bundle. Add only the Service VIP/TCP port overlay, then remove it. Repeat with only the backing endpoint/TCP port overlay. Include the no-overlay case again. For each trial, test Service and direct API paths from the Prometheus network namespace. | Record TCP/TLS/HTTP results, list/watch, policy selector and effective destination. The winning rule must restore the Service API path and removal must close it on fresh connections. Verify unlabelled monitoring peers still lack API egress. |
| 4. Fresh discovery, scrape allowed | Apply only the proven API overlay. Start fresh Prometheus, then create a uniquely named and labelled target in `gitops-apps` after successful discovery startup. | New target UID and Pod IP appear in `/api/v1/targets`. Active target has `health=up`, `up=1`, and the new gauge value. Existing targets on both workers also scrape successfully. |
| 5. Discovery allowed, scrape denied | Keep API egress. Remove only the selected target ingress allow, keeping its namespace default-deny and the Prometheus egress allow. Introduce a new target. Restore ingress, then repeat with only the Prometheus scrape egress allow removed. | The fresh UID appears in both variants, while scrape fails on a new socket with `health=down` and `up=0`. The healthy server is reachable in an appropriate positive-control phase. Restoring both directions returns `up=1` and the gauge. |
| 6. Scrape path allowed, discovery denied | Keep both scrape rules, remove just the API overlay and start a fresh Prometheus process. Introduce another fresh target. Use the probe sidecar to test the Pod IP directly. Restore only the API overlay. | Direct HTTP succeeds despite the new UID being absent from discovery. After restoring API egress, list/watch succeeds, the new UID appears and its scrape turns up. If removal does not block the API path, the distinction stays unproven for this build. |
| 7. Recovery | Remove the test overlay and the six lab-only policies and rerun baseline probes. | Recovery of API list/watch, DNS, datasource and both direct port controls. No policy effect remains in the lab. |

Use fresh HTTP transport connections with a five-second connection timeout
and bounded request times. A TCP refusal counts as a failed control unless
the destination is independently verified healthy and the failure tracks
the policy stage. With the repository's 30-second scrape interval and
five-second scrape timeout, allow up to 120 seconds per discovery/scrape
assertion and require two consecutive expected observations. Record each
transition in UTC and stop on an unexplained mismatch.

## Evidence, recovery and authorization

Save a timestamped lab evidence directory. Record the cluster identity and
pinned image IDs, worker and fixture placement, service and endpoint
inventories, kube-proxy mode, Kindnet logs, and sanitized lab rule/counter
snapshots when needed to resolve the API tuple. For each probe capture
source Pod UID and node, destination, transport, exit status, HTTP result
and timing. Capture Prometheus target JSON, query results for `up` and the
test gauge, sanitized API list/watch results, and Grafana datasource
results. Record applied manifest hashes and the before/after read-only
Machine B platform baseline. Exclude kubeconfigs, credentials, tokens,
and raw authenticated headers.

On failure, stop the test sequence and preserve evidence. If recovery is
authorized, remove only the named lab overlay and lab NetworkPolicies
using the verified lab context. Recheck fresh connections before removing
fixtures. Archive evidence before teardown. Deleting
`secure-platform-w11-netpol` and removing its standalone kubeconfig need
separate teardown approval and a second identity check. Never prune Docker
or alter the protected cluster to recover the lab.

Explicit owner approval is required for lab creation, lab fixture and
policy writes, each diagnostic API policy variant, lab recovery, and
teardown. Any future production adoption requires a separate review of the
proven API and DNS paths, application dependencies, and production rollback.

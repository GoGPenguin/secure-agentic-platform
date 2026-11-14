# Week 10 Phase 2B isolated runtime verification

**Result: PASS — all 22 acceptance criteria below passed. Week 10 remains
incomplete.** Criteria map to the owner-approved isolated runtime instructions;
no independent W10-B checklist was present in the repository.

Only the three approved resources were created from the unchanged reviewed
manifest in context `kind-secure-platform`, namespace `psa-restricted-test`:
ServiceAccount/platform-api-psa, Service/platform-api-psa and
Deployment/platform-api-psa. The Deployment controller created one ReplicaSet and
one Pod. The hook was excluded. All lab resources remain present; no automatic
cleanup occurred. The temporary localhost port-forward was stopped. No production
chart sync, namespace change, RBAC/monitoring change, commit or PR was performed.

## Runtime evidence

- Running Pod: `platform-api-psa-69fff699d8-jqcm8`, UID
  `03759942-7ec9-4e05-a8a1-234a5f1320bb`, on secure-platform-worker.
- Runtime imageID exactly matches the reviewed image:
  `ghcr.io/gogpenguin/secure-agentic-platform/platform-api@sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421`.
  The separate container status image/config identifier is
  `sha256:92dcf47e4cdb2176fe9c43b615dc492adb32dcd3cde9aa9f35d9116436600ea5`;
  it is not a replacement registry manifest digest.
- PID 1 real/effective/saved/filesystem UID and GID: **1000**.
- `NoNewPrivs=1`; `CapEff=0000000000000000`. CapInh, CapPrm, CapBnd and CapAmb
  are also all zero.
- `Seccomp=2` (filtering), `Seccomp_filters=1`, with RuntimeDefault configured.
- Dedicated SA automount false, no projected token volume and token file absent.
- One replica Available; Pod Running/Ready; **zero restarts**. Normal startup
  events only, with no warning/security failure events.
- Kubelet probe metrics directly show **127 successful liveness** and
  **258 successful readiness** probes at collection. Probe paths/timings and
  resource limits remained those in the approved manifest.
- All four endpoints returned **HTTP 200** through `127.0.0.1:13000`:
  live `{status: ok}`, ready `{status: ready}`, info service `platform-api`
  version `0.1.1`, and valid Prometheus metrics exposition including HTTP metrics.

The initial local HTTP assertion incorrectly expected `ok` for readiness. The
API correctly returned `ready`; this contract was verified in the controller and
E2E tests. The original attempt is retained, the corrected HTTP test passed, and
no cluster/application/security setting was changed to make it pass.

## Acceptance criteria

| ID | Criterion | Result | Evidence outcome |
| --- | --- | --- | --- |
| W10-B-01 | Approved context, version and namespace policy | **PASS** | kind-secure-platform; server v1.37.0; psa-restricted-test restricted:v1.37 for enforce/warn/audit |
| W10-B-02 | Only three authorized resources explicitly created using exact reviewed manifest | **PASS** | ServiceAccount, Service and Deployment/platform-api-psa; controller-created ReplicaSet and Pod expected; no hook |
| W10-B-03 | Bounded successful rollout and Deployment Available | **PASS** | 120-second rollout timeout; one available replica |
| W10-B-04 | Lab Pod Running/Ready | **PASS** | platform-api-psa-69fff699d8-jqcm8 |
| W10-B-05 | Exact running image identity matches reviewed digest | **PASS** | ghcr.io/gogpenguin/secure-agentic-platform/platform-api@sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421 |
| W10-B-06 | Actual process UID/GID 1000 | **PASS** | PID 1 real/effective/saved/filesystem UID/GID all 1000; exec identity also 1000 |
| W10-B-07 | NoNewPrivs enabled | **PASS** | PID 1 NoNewPrivs=1 |
| W10-B-08 | Linux capability sets appropriately restricted | **PASS** | All five capability sets zero, including CapEff=0000000000000000 |
| W10-B-09 | Seccomp filtering active with RuntimeDefault configuration | **PASS** | Seccomp=2; Seccomp_filters=1; Pod RuntimeDefault |
| W10-B-10 | Restricted controls preserved and service-account token disabled | **PASS** | No control weakened; no token file or projected volume |
| W10-B-11 | Liveness and readiness probes succeed | **PASS** | Kubelet counters: liveness successful=127; readiness successful=258 at observation |
| W10-B-12 | /health/live HTTP verification | **PASS** | HTTP 200; {"status":"ok"} |
| W10-B-13 | /health/ready HTTP verification | **PASS** | HTTP 200; {"status":"ready"} |
| W10-B-14 | /api/v1/info HTTP verification | **PASS** | HTTP 200; service platform-api, version 0.1.1 |
| W10-B-15 | /metrics HTTP verification | **PASS** | HTTP 200; Prometheus exposition including HTTP metrics |
| W10-B-16 | Localhost-only forwarding, stopped after HTTP checks | **PASS** | 127.0.0.1:13000 -> lab Service port 3000; forwarding process terminated, lab retained |
| W10-B-17 | Events/restarts show successful startup without security failures | **PASS** | Only Normal Scheduled/Pulling/Pulled/Created/Started events; zero restarts |
| W10-B-18 | Eight existing Argo Applications remain Synced/Healthy | **PASS** | All eight unchanged health statuses |
| W10-B-19 | Six existing Deployments remain available; templates/Pods/ReplicaSets unchanged | **PASS** | Spec/template hashes, generations, replica counts, Pod UIDs and restart counts identical; no unexpected rollout |
| W10-B-20 | Existing namespaces and production API image unchanged | **PASS** | All namespace UIDs/labels unchanged; production digest unchanged |
| W10-B-21 | RBAC, monitoring, AppProjects and Application definitions unchanged | **PASS** | All eight raw differences are Application metadata.generation only; exact-hash reconstruction proves other captured fields unchanged; documented separately |
| W10-B-22 | No hook, production sync, cleanup, commit or PR; lab retained | **PASS** | Only approved create and lab verification actions; no Helm install/upgrade, Argo mutation or deletion; no commit/PR commands issued |

## Production comparison and separate metadata exception

All eight existing Argo CD Applications remained Synced/Healthy. All six existing
Deployments remained available (frontend 2/2; other applications/monitoring 1/1).
Production Deployment spec/template hashes and generations, Pod UIDs and restart
counts, ReplicaSet identities/revisions, namespace UIDs/labels and production API
image reference were identical before/after. No unexpected production rollout
was observed. RBAC, monitoring and AppProject definition hashes were unchanged.

The Application definition hashes differed solely because metadata.generation
advanced. Exact-hash reconstruction proves all other captured Application fields
unchanged. See the **separate** [generation-only report](week10-phase2b-argo-generation-only.md).
This exception is explicitly retained; raw governance hashes were not declared
identical and no controller-generation counters were modified.

## Evidence index

- [Machine-readable acceptance matrix](week10-phase2b-acceptance.json)
- [Authorized preflight / production baseline](week10-runtime-authorized-preflight.json)
- [Exact manifest create operation and hash](week10-runtime-create.json)
- [Bounded rollout](week10-runtime-rollout.json)
- [Running image, process identity and kernel security state](week10-runtime-security.json)
- [Final HTTP results and response bodies](week10-runtime-http.json)
- [Preserved initial local HTTP assertion error](week10-runtime-http-initial-assertion.json)
- [Pod events, restart count and actual kubelet probe metrics](week10-runtime-events-probes.json)
- [Post-runtime platform snapshot](week10-runtime-postruntime.json)
- [Governance baseline](week10-runtime-governance-before.json)
- [Governance after, raw differences and resolution](week10-runtime-governance-after.json)
- [Application generation hash investigation](week10-runtime-application-generation-investigation.json)

## Remaining risks and recommended next steps

This is an isolated runtime result for one exact image/profile, not production
rollout authorization or comprehensive PSS coverage. Read-only root filesystem,
load/soak, resilience and network isolation were not tested. The namespace is not
a hostile-tenant boundary. Monitoring discovery permissions were not expanded;
metrics were tested directly. Future image changes need renewed identity and
runtime validation. Runtime evidence is point-in-time and should not be treated
as a continuing health guarantee.

Review and retain these results and the lab pending owner direction. Any cleanup,
production hardening or chart synchronization requires separately reviewed scope;
the existing chart-label migration rollout risk remains outside this test. No
further cluster operations were performed while finalizing this report. Week 10
is not declared complete.

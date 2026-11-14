# Hardened Platform API lab — authorization gate

Current status (2026-11-14): **authorized isolated runtime test passed; lab retained**.
See [runtime results](../../docs/security/evidence/week10-phase2b-runtime-summary.md),
[acceptance matrix](../../docs/security/evidence/week10-phase2b-acceptance.json) and
[delivery review](../../docs/security/week10-delivery-review.md). Week 10 delivery
remains pending; production synchronization is unauthorized.

The preparation/gate descriptions and commands below are retained as the original
runbook. They do not mean the resources are still absent: the three approved lab
resources already exist. Do not repeat creation, change or delete the lab without
new scoped authorization. An evidence-only delivery may intentionally omit the held chart, scripts and values
overlays. The Helm regeneration commands below require the complete implementation
candidate and are not claims about what is already delivered on main.
Frozen rendered artifacts retain their original
pre-deployment comments and reviewed hashes; their current state is documented
here rather than by editing the approved manifest.

## Reviewed artifacts and proposed changes

All resources target the existing `psa-restricted-test` Namespace, explicitly
written into each rendered object's metadata. No namespace changes are proposed.

| Kind | Name | Proposed persistent creation after authorization |
| --- | --- | --- |
| ServiceAccount | platform-api-psa | Yes; token automount disabled |
| Service | platform-api-psa | Yes; ClusterIP, port 3000, lab-only selector |
| Deployment | platform-api-psa | Yes; one replica, creates a lab ReplicaSet/Pod |
| Pod / Helm test hook | platform-api-psa-test-connection | No; reviewed and server-dry-run only |

The three proposed resources are in
[rendered/platform-api-lab.yaml](rendered/platform-api-lab.yaml). The separate
[hook artifact](rendered/platform-api-hook.yaml) retains its Helm test annotation
and existing busybox image. No Helm installation/upgrade is proposed. A raw
kubectl create would persist a hook Pod rather than execute Helm hook semantics;
it is deliberately excluded from the proposed runtime deployment. HTTP checks
will validate the API directly instead.

Names, selector instance labels and the dedicated SA are distinct from production.
No ownerReferences, Argo CD tracking metadata or Helm release ownership annotations
are present. The chart's conventional Helm managed-by and top-level chart labels
are retained; these labels alone do not establish a Helm release. No Application,
AppProject, RBAC, monitoring resource or production namespace/value is changed.

Image:

```text
ghcr.io/gogpenguin/secure-agentic-platform/platform-api@sha256:9714e2a64a7ad5b3af396b0c9fd3958245259cf7a536d748df378e21e30f0421
```

UID/GID 1000 match the exact image's previously verified identity. The Deployment
uses non-root true, numeric UID/GID 1000 and RuntimeDefault at Pod level, and
escalation false/drop ALL at container level. Its SA disables token automount;
the hook explicitly disables automount at Pod level. API port 3000, live/ready
probes, CPU/memory requests/limits and one replica match existing production
values. No additional writable mounts or weaker security settings were added.

## Render and validation

The chart and existing values are unchanged in this phase. The final lab-only
overlay changes the fullname and SA name, and explicitly retains one replica:

```sh
helm lint charts/web-app \
  -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml \
  -f security/psa-test/platform-api-lab-values.yaml
helm template platform-api-psa charts/web-app -n psa-restricted-test \
  -f environments/platform-api-values.yaml \
  -f environments/platform-api-restricted-values.yaml \
  -f security/psa-test/platform-api-lab-values.yaml
```

The raw Helm output was parsed into four resources, each stamped with
`metadata.namespace: psa-restricted-test`, then split into the three persistent
candidates and separate test hook. No other post-render edits were made. Exact
commands, inventory, raw-render hash, final artifact hashes, image and security
settings are recorded in [render evidence](../../docs/security/evidence/week10-runtime-render.json).
Re-rendering or changing any artifact invalidates these exact validation hashes
and requires renewed review/dry-runs.

Helm lint/schema/template checks, ten local security test groups and the existing
focused checker passed. All four current application renders remained
byte-identical before/after lab preparation. Static RBAC and monitoring validators
passed. The checker is not complete PSS or API schema validation.

Strict server-side create dry-runs of both artifacts passed, including actual
hook Pod admission; no warnings/errors occurred. The Deployment request does not
create a controller Pod or make its proposed SA available. Actual API Pod admission,
image pull and runtime behavior remain untested until creation is authorized.

```sh
kubectl --context kind-secure-platform --request-timeout=10s create \
  --dry-run=server --validate=strict -n psa-restricted-test \
  -f security/psa-test/rendered/platform-api-lab.yaml
kubectl --context kind-secure-platform --request-timeout=10s create \
  --dry-run=server --validate=strict -n psa-restricted-test \
  -f security/psa-test/rendered/platform-api-hook.yaml
```

## Preflight and post-validation evidence

Context is `kind-secure-platform`, server v1.37.0, namespace restricted:v1.37 for
all enforce/warn/audit labels. All eight Argo CD Applications are Synced/Healthy;
all six existing Deployments are fully available. The namespace contains no
Deployment, Service or Pod, and no conflicting lab SA. Its pre-existing default
SA is unchanged. Post-validation snapshots exactly match preflight for existing
Deployment specs/template hashes/generations, ReplicaSets, Pod identities and
restart counts, Application health, namespace identities/labels and lab inventory.
Thus no lab resource was persisted and no rollout was observed.

- [Read-only preflight](../../docs/security/evidence/week10-runtime-preflight.json)
- [Static results](../../docs/security/evidence/week10-runtime-static-validation.json)
- [Existing render comparison](../../docs/security/evidence/week10-runtime-existing-render-comparison.json)
- [Server dry-run output](../../docs/security/evidence/week10-runtime-server-dry-run.json)
- [Post-validation snapshot](../../docs/security/evidence/week10-runtime-postvalidation.json)

No current blocker was found for an authorized runtime test. This evidence proves
only the observed validation outcomes, not runtime identity, capabilities,
NoNewPrivs, seccomp filtering, startup, probes or HTTP responses. Namespace labels
do not by themselves establish admission defaults/exemptions elsewhere. No commit
or PR was created.

## Proposed execution after separate authorization — NOT RUN

First recheck context/version/policy, conflict absence, artifact hashes and
production health. Use create, not apply, so an unexpected existing lab resource
causes a conflict rather than being overwritten:

```sh
kubectl --context kind-secure-platform create --validate=strict \
  -n psa-restricted-test -f security/psa-test/rendered/platform-api-lab.yaml
kubectl --context kind-secure-platform -n psa-restricted-test rollout status \
  deployment/platform-api-psa --timeout=120s
kubectl --context kind-secure-platform -n psa-restricted-test get pods \
  -l app.kubernetes.io/instance=platform-api-psa -o wide
```

Creation is not transactional. Record and stop on partial failure; do not weaken
controls or automatically delete resources. Inspect read-only status/events and
propose a reviewed fix. A successful rollout must also show Running/Ready and
passing health probes, not merely acceptance of the Deployment object.

Read only the relevant process status fields inside the lab container:

```sh
kubectl --context kind-secure-platform -n psa-restricted-test exec \
  deployment/platform-api-psa -- node -e \
  'const fs=require("node:fs"); console.log(fs.readFileSync("/proc/1/status","utf8").split("\n").filter(x=>/^(Uid|Gid|CapInh|CapPrm|CapEff|CapBnd|CapAmb|NoNewPrivs|Seccomp|Seccomp_filters):/.test(x)).join("\n"))'
```

Expected effective UID/GID: 1000. CapEff/CapPrm/CapBnd/CapAmb should be zero,
NoNewPrivs 1, Seccomp 2 (filter mode). Record actual values and investigate any
deviation. Do not infer kernel state merely from securityContext configuration.

Use a foreground localhost-only forward and HTTP requests in a second terminal:

```sh
kubectl --context kind-secure-platform -n psa-restricted-test port-forward \
  --address 127.0.0.1 service/platform-api-psa 13000:3000
curl --fail --silent --show-error http://127.0.0.1:13000/health/live
curl --fail --silent --show-error http://127.0.0.1:13000/health/ready
curl --fail --silent --show-error http://127.0.0.1:13000/api/v1/info
curl --fail --silent --show-error http://127.0.0.1:13000/metrics
```

Stop the forward after checks. Capture statuses and expected response content,
probe configuration/readiness, events, effective image digest/security state and
before/after production health without credentials or unrestricted log dumps.
Confirm no production Pod/ReplicaSet/digest changes and no monitoring/RBAC changes.
No hook or runtime commands above have been executed in this phase.

There is currently no cluster rollback to perform: all preparation was local or
server-dry-run. Later cleanup is separately reviewed and must target only the new
lab names; do not delete the namespace or affect existing workloads automatically.

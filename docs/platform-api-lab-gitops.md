# Optional local-lab overrides (W05-B.4.4.2B)

This checkpoint adds inactive support only. `app-configs/platform-api.yaml`
still references only `environments/platform-api-values.yaml`; no current
Application selects the lab image or injection variables. Production publishing,
base image digest, AppProjects, RBAC, networking and monitoring are unchanged.

## Configuration and ownership

The shared chart accepts `env: {}` by default and emits no environment block
when it is empty. Nonempty entries render as quoted names and values; the Helm
schema requires string values, including for boolean/numeric-looking values.
Use `"true"`, not `true`. This is plain configuration, not a secret mechanism.

ApplicationSet supports an optional nonempty string `overrideValuesFile` in an
existing app-config. Its conditional `templatePatch` keeps the original chart
source and the `$chart-repo` reference source, appends the override after the
base values file, and retains the same Application/release/resource identities,
destination, project and sync policies. The absent-field branch emits `{}`,
an explicit no-op patch; it never emits an empty `spec` or a null document.
Empty, null and non-string override fields fail template evaluation.

The inactive `environments/platform-api-lab-values.yaml` reserves the unique tag
`platform-api:lab-w05-b4442b-20261111-01`. It clears the inherited production
digest, selects `pullPolicy: Never`, and supplies the two explicit lab variables.
The digest must be cleared because the chart gives a nonempty digest precedence
over a tag. This tag is a reserved local build identity, not proof that an image
has been built or loaded. Never reuse it for different image bytes; record its
source/build and image identity when preparing a future activation.

## Validation

Before this implementation, Helm 4.3.1 rendered frontend, backend, sandbox and
platform-api using namespace `gitops-apps`. Baselines were captured outside Git
at `/tmp/w05-b4442b-baseline`, before chart/ApplicationSet edits.

Run from the repository root with Helm and PyYAML available:

```bash
python3 scripts/validate-lab-overrides.py --baseline-dir /tmp/w05-b4442b-baseline
git diff --check
```

Alternatively, regenerate baselines from a known pre-change Git revision:

```bash
python3 scripts/validate-lab-overrides.py --baseline-ref <pre-change-commit>
```

The default baseline ref is `HEAD`, useful for reviewing this uncommitted change.
Use an explicit pre-change ref for historical comparisons after committing.
The script renders locally; it does not access Kubernetes or change Git files.
It verifies:

- All four default renders match the baseline byte for byte, with no `env` block.
- Default/per-application lint and the activated lab lint/template succeed.
- Activated API resources differ only in container image, pull policy and env.
- Null, boolean, numeric, list and object env values fail; string values survive.
- Production digest precedence survives a tag override; a missing values file fails.
- All four default Application templates remain unchanged; simulated override
  patches preserve both sources, destination, release, identity and sync policy.
- Invalid override fields fail and newlines in a value cannot inject YAML fields.

The ApplicationSet harness evaluates the real template strings with Helm's Go
template/Sprig engine and models map merging/list replacement for the patch
subset used here. It is not the Argo CD controller, its Git generator, CRD
validation or strict missing-key implementation. A future activation should
also inspect the generated Application using the installed Argo CD version
before allowing workload sync. The `hasKey` guard avoids reading an absent
optional key under the existing `missingkey=error` policy.

## Future activation and rollback (not performed here)

Confirm that the consuming ApplicationSet is exclusive to the intended local
lab cluster. If another cluster consumes the same app-config path, introduce
cluster-specific generator inputs before activating. Environment flags alone
cannot establish cluster identity.

Prepare the tested image before merging any activation: automatic sync from
`main` may start a rollout immediately after that merge. Example preparation:

```bash
docker tag platform-api:lab-local platform-api:lab-w05-b4442b-20261111-01
kind load docker-image platform-api:lab-w05-b4442b-20261111-01 --name <kind-cluster>
```

Confirm the expected image bytes are available on every kind node, including
both workers. `Never` deliberately fails if the local image is absent; it does
not attempt a registry pull. A recreated/new node needs the image loaded again.

In a separately reviewed activation, add only this field to the existing
`app-configs/platform-api.yaml`:

```yaml
overrideValuesFile: environments/platform-api-lab-values.yaml
```

Do not create a second Application, change release/resource names, or edit the
generated Application directly. Verify the generated sources, desired diff,
rollout/image IDs, health and scraping. Access the API through a port-forward
bound to localhost; keep existing network restrictions. Use a bounded traffic
generator with retries disabled to demonstrate the alert transitions.

Rollback by stopping the generator, removing the optional field through Git,
and verifying reconciliation to the production digest and original pull policy.
The lab route should return 404. Historical 503 samples remain in the rolling
window after traffic stops. Once no lab Pods remain, clean up unused node-local
image tags if desired; do not delete the existing Application or shared resources.

## Patching and reproducibility risks

The patch repeats the complete two-source list because source lists are replaced.
Future edits to the base sources must update the patch too; validation compares
the entire generated Application to catch drift. Keep generator inputs trusted
and reviewed: template patches can change substantial Application configuration.
Paths are JSON-quoted to prevent YAML field injection; missing files are not
ignored. List replacement also means any future env list API would need different
merge expectations; the chart currently uses a plain string map.

Git records image selection and configuration, not locally loaded image bytes.
Unique tags reduce ambiguity but do not replace a retained registry digest or
image archive. Rebuilding the same tag can produce different bytes, and a fresh
cluster cannot restore the lab from Git alone. Production publishing/promotion
continues to use the existing registry-backed image flow.

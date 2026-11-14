# Argo CD Application generation-only differences

The raw before/after governance comparison was not byte-identical. All eight
differences were Application `metadata.generation` counters; no RBAC, monitoring
or AppProject definition hashes differed. The original raw hashes/results remain
in the evidence and are not relabeled as exact equality.

| Application | Baseline generation | Investigation generation | Other captured fields |
| --- | --- | --- | --- |
| backend | 1574 | 1583 | Identical |
| frontend | 1625 | 1633 | Identical |
| grafana | 1047 | 1055 | Identical |
| platform-api | 1421 | 1430 | Identical |
| platform-rbac | 467 | 475 | Identical |
| platform-root | 3977 | 3985 | Identical |
| prometheus | 2511 | 2519 | Identical |
| sandbox | 1541 | 1549 | Identical |

The investigator recomputed each baseline hash using the observed current
Application definition while varying **only** metadata.generation. Every original
hash was reproduced exactly. This establishes equality of every other captured
field: API version/kind, spec, UID, labels, annotations and owner references.
Status/resourceVersion/managedFields were excluded by design from both hashes.
All eight Applications remained Synced/Healthy.

These counters advanced during the observation window; no Application mutation,
refresh or sync was requested by this session. They are consistent with controller
reconciliation activity, but this investigation did not capture a writer audit
trail and does not assert the exact cause. No counter was reset and no cluster
resource was edited to hide the difference. This is a metadata-only exception to
raw-hash equality, not a specification change or production rollout.

Evidence: [before hashes](week10-runtime-governance-before.json),
[raw after differences and resolved classification](week10-runtime-governance-after.json),
[exact-hash investigation](week10-runtime-application-generation-investigation.json).

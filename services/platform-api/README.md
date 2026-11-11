# Platform API

NestJS service for the Secure Agentic Platform.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/info` | Service name and package version |
| `GET /health/live` | HTTP liveness |
| `GET /health/ready` | HTTP readiness |
| `GET /metrics` | Prometheus HTTP request Counter and duration Histogram |

From this directory:

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm run test:e2e
pnpm run build
pnpm run start:dev
```

The service listens on `PORT`, defaulting to 3000. `/` has no handler.

`http_requests_total` counts completed application responses with `method`,
`route`, and `status_code` labels. Routes use registered templates (for example,
`/users/:userId`), with `__unmatched__` for requests without a controller route,
including Nest's `*path` not-found fallback. Raw request paths are never labels.
Metrics scrapes and `/health/live` and `/health/ready` probes are excluded.
Connections closed before the response finishes are not counted. Each Nest
application owns its registry. `http_request_duration_seconds` is a classic
Histogram with the same labels, measured using a monotonic clock from middleware
entry until response `finish` (server completion, not client receipt). It uses
buckets of 5, 10, 25, 50, 100, 250, 500 ms and 1, 2.5, 5, 10 seconds, plus `+Inf`.
These initial boundaries cover fast API calls and slow responses at a cost of
14 series per label combination; they are not an established latency SLO.
The Histogram shares the Counter's exclusions and aborted-response handling. This
instrumentation assumes Nest-managed Express routes, whose templates include
controller and module prefixes; manually mounted Express routers would need
explicit template handling.

## Lab-only HTTP 503 injection (W05-B.4.4.1)

The separate lab application can register
`POST /api/v1/lab/failures/http-503`. It throws Nest's
`ServiceUnavailableException` with the fixed message `Controlled lab HTTP 503`.
Request parameters/body cannot change the failure behavior. It makes no external
calls and changes no business state. The existing metrics middleware records
each completed 503 once, including a duration observation; it is not incremented
manually. Health and scrape exclusions remain unchanged.

The controller is registered only when both values are exactly:

```text
PLATFORM_ENVIRONMENT=local-lab
LAB_HTTP_503_ENABLED=true
```

The flag defaults to disabled; explicit `false` also disables it. Other flag
values are configuration errors. Enabling it outside `local-lab` fails before
the application starts listening. Configuration is evaluated per application
creation, not at import time. Disabled lab applications return 404 at this path.

From this directory, for a local lab only:

```bash
pnpm run build:lab
PLATFORM_ENVIRONMENT=local-lab LAB_HTTP_503_ENABLED=true pnpm run start:lab
```

Then issue a single request (no automatic retries):

```bash
curl -i -X POST http://127.0.0.1:3000/api/v1/lab/failures/http-503
```

Stop the process to stop injection immediately. Restart the lab entry point
without the flag or with `LAB_HTTP_503_ENABLED=false` to remove the route.
These are startup settings, not runtime toggles. Old counter observations stay
in Prometheus's rolling window after injection stops.

### Production artifact boundary

The normal `pnpm run build` excludes `src/lab` and emits `dist`. The separate
`build:lab` uses `tsconfig.lab.json` and emits `dist-lab`, including its own
entry point `dist-lab/lab/main.js`. The production entry point never imports
the controller and rejects injection enablement even in `local-lab`, directing
operators to the separate lab build. `NODE_ENV=production` remains unchanged.

The existing Dockerfile copies only `dist` from the production build to the
final image. Lab sources exist in the build stage but the controller and its
declarations/source maps are absent from the final application output. The
lab build is a local Node artifact in this checkpoint; there is no new lab
container target, deployment configuration or publishing/promotion change.

TypeScript exclusions alone do not prevent an explicitly imported excluded file
from being compiled. Keep production imports free of the lab module and run
the artifact regression check:

```bash
pnpm test
pnpm run test:e2e
pnpm run test:build-isolation
pnpm run lint
```

The artifact check builds lab then production, verifies the controller is absent
from all production output (including declarations/maps), and checks rejection
by the compiled entry points. Unit tests cover configuration and module
registration; e2e tests cover disabled/enabled routing, fixed responses, bounded
labels, exactly-once counter/histogram recording and unchanged health/scrapes.

Environment variables express operator intent, not proof of cluster identity.
The lab listener retains the existing binding behavior, so localhost in the
example is not an access-control boundary. Run only in an isolated local lab;
no RBAC, NetworkPolicy, AppProject or exposure settings are weakened here.
Review lab image separation and GitOps activation in the deployment checkpoint.

See the [repository README](../../README.md) for pinned CI tooling, Docker builds, image publishing, GitOps deployment, and rollback. Deployment uses reviewed Git changes reconciled by Argo CD.

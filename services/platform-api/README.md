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

See the [repository README](../../README.md) for pinned CI tooling, Docker builds, image publishing, GitOps deployment, and rollback. Deployment uses reviewed Git changes reconciled by Argo CD.

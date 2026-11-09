# Platform API

NestJS service for the Secure Agentic Platform.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/info` | Service name and package version |
| `GET /health/live` | HTTP liveness |
| `GET /health/ready` | HTTP readiness |

From this directory:

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm run test:e2e
pnpm run build
pnpm run start:dev
```

The service listens on `PORT`, defaulting to 3000. `/` has no handler.

See the [repository README](../../README.md) for pinned CI tooling, Docker builds, image publishing, GitOps deployment, and rollback. Deployment uses reviewed Git changes reconciled by Argo CD.

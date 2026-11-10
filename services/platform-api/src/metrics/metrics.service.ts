import { Injectable } from '@nestjs/common';
import { Counter, Histogram, Registry } from '@prometheus-io/client';

@Injectable()
export class MetricsService {
  readonly registry = new Registry();
  readonly requests = new Counter({
    name: 'http_requests_total',
    help: 'Total completed application HTTP responses.',
    labelNames: ['method', 'route', 'status_code'] as const,
    registers: [this.registry],
  });
  readonly duration = new Histogram({
    name: 'http_request_duration_seconds',
    help: 'Duration of completed application HTTP responses in seconds.',
    labelNames: ['method', 'route', 'status_code'] as const,
    buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    registers: [this.registry],
  });
}

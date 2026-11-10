import { Inject, Injectable, type NestMiddleware } from '@nestjs/common';
import type { NextFunction, Request, Response } from 'express';
import { MetricsService } from './metrics.service.js';

@Injectable()
export class HttpMetricsMiddleware implements NestMiddleware {
  constructor(
    @Inject(MetricsService) private readonly metrics: MetricsService,
  ) {}

  use(req: Request, res: Response, next: NextFunction) {
    const startedAt = process.hrtime.bigint();
    const cleanup = () => {
      res.removeListener('finish', onFinish);
      res.removeListener('close', onClose);
    };
    const onFinish = () => {
      cleanup();
      const path: unknown = req.route?.path;
      // Nest's prefixed not-found handler uses *path. Never fall back to a
      // request URL or baseUrl, which can contain user-controlled IDs.
      const route =
        typeof path === 'string' && path.startsWith('/')
          ? path
          : '__unmatched__';
      const labels = {
        method: req.method,
        route,
        status_code: String(res.statusCode),
      };
      const durationSeconds = Number(process.hrtime.bigint() - startedAt) / 1e9;
      this.metrics.requests.inc(labels);
      this.metrics.duration.observe(labels, durationSeconds);
    };
    // A close before finish is an aborted response, not a completed 200.
    const onClose = () => cleanup();
    res.once('finish', onFinish);
    res.once('close', onClose);
    next();
  }
}

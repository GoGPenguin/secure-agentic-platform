import { EventEmitter } from 'node:events';
import type { Request, Response } from 'express';
import { HttpMetricsMiddleware } from './http-metrics.middleware.js';
import { MetricsService } from './metrics.service.js';

describe('HTTP response lifecycle', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ['finish', 'close', 'finish', 1],
    ['close', 'finish', 'close', 0],
  ] as const)(
    'handles %s then %s without double counting',
    async (first, second, third, count) => {
      vi.spyOn(process.hrtime, 'bigint')
        .mockReturnValueOnce(1_000_000_000n)
        .mockReturnValue(1_250_000_000n);
      const metrics = new MetricsService();
      const middleware = new HttpMetricsMiddleware(metrics);
      const res = Object.assign(new EventEmitter(), { statusCode: 200 });
      const req = { method: 'GET', route: { path: '/users/:id' } };
      const next = vi.fn();
      middleware.use(req as Request, res as unknown as Response, next);
      expect(next).toHaveBeenCalledExactlyOnceWith();
      res.emit(first);
      res.emit(second);
      res.emit(third);
      expect(res.listenerCount('finish')).toBe(0);
      expect(res.listenerCount('close')).toBe(0);
      const metric = await metrics.requests.get();
      expect(metric.values.reduce((sum, value) => sum + value.value, 0)).toBe(
        count,
      );
      const duration = await metrics.duration.get();
      if (count === 0) {
        expect(duration.values).toEqual([]);
      } else {
        const labels = {
          method: 'GET',
          route: '/users/:id',
          status_code: '200',
        };
        expect(duration.values).toEqual(
          expect.arrayContaining([
            {
              metricName: 'http_request_duration_seconds_count',
              labels,
              value: 1,
            },
            {
              metricName: 'http_request_duration_seconds_sum',
              labels,
              value: 0.25,
            },
          ]),
        );
        const buckets = duration.values.filter(
          (value) =>
            value.metricName === 'http_request_duration_seconds_bucket',
        );
        expect(
          buckets.map((bucket) => [bucket.labels.le, bucket.value]),
        ).toEqual([
          [0.005, 0],
          [0.01, 0],
          [0.025, 0],
          [0.05, 0],
          [0.1, 0],
          [0.25, 1],
          [0.5, 1],
          [1, 1],
          [2.5, 1],
          [5, 1],
          [10, 1],
          ['+Inf', 1],
        ]);
      }
    },
  );

  it('measures overlapping requests independently using a monotonic clock', async () => {
    vi.spyOn(process.hrtime, 'bigint')
      .mockReturnValueOnce(1_000_000_000n)
      .mockReturnValueOnce(1_100_000_000n)
      .mockReturnValueOnce(1_300_000_000n)
      .mockReturnValueOnce(1_500_000_000n);
    const metrics = new MetricsService();
    const middleware = new HttpMetricsMiddleware(metrics);
    const first = Object.assign(new EventEmitter(), { statusCode: 200 });
    const second = Object.assign(new EventEmitter(), { statusCode: 500 });
    const req = { method: 'GET', route: { path: '/users/:id' } };
    middleware.use(req as Request, first as unknown as Response, vi.fn());
    middleware.use(req as Request, second as unknown as Response, vi.fn());
    second.emit('finish');
    first.emit('finish');
    const duration = await metrics.duration.get();
    expect(
      duration.values.filter(
        (value) => value.metricName === 'http_request_duration_seconds_sum',
      ),
    ).toEqual(
      expect.arrayContaining([
        {
          metricName: 'http_request_duration_seconds_sum',
          labels: { method: 'GET', route: '/users/:id', status_code: '500' },
          value: 0.2,
        },
        {
          metricName: 'http_request_duration_seconds_sum',
          labels: { method: 'GET', route: '/users/:id', status_code: '200' },
          value: 0.5,
        },
      ]),
    );
  });
});

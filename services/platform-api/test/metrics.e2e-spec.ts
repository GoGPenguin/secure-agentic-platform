import {
  Controller,
  Get,
  NotFoundException,
  Res,
  type INestApplication,
} from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { get } from 'node:http';
import type { AddressInfo } from 'node:net';
import type { Response } from 'express';
import request from 'supertest';
import type { App } from 'supertest/types.js';
import { AppModule } from '../src/app.module.js';
import { MetricsService } from '../src/metrics/metrics.service.js';

@Controller('teams/:teamId/users')
class UsersController {
  static closed: (() => void) | undefined;

  @Get(':userId/stream')
  stream(@Res() res: Response) {
    res.once('close', () => UsersController.closed?.());
    res.write('partial response');
  }

  @Get(':userId')
  get() {
    return { ok: true };
  }

  @Get(':userId/missing')
  missing() {
    throw new NotFoundException();
  }

  @Get(':userId/crash')
  crash() {
    throw new Error('test failure');
  }
}

async function createApp(prefix = '') {
  const module = await Test.createTestingModule({
    imports: [AppModule],
    controllers: [UsersController],
  }).compile();
  const app = module.createNestApplication<INestApplication<App>>();
  app.useLogger(false);
  app.setGlobalPrefix(prefix);
  await app.init();
  return app;
}

describe.each(['', '/api/v1'])('HTTP metrics with prefix "%s"', (prefix) => {
  let app: INestApplication<App>;

  beforeEach(async () => {
    app = await createApp(prefix);
  });

  afterEach(async () => {
    await app.close();
  });

  it('counts completed 200, matched 404/500 and unmatched responses once', async () => {
    const server = app.getHttpServer();
    for (const id of ['user-123', 'user-456']) {
      await request(server)
        .get(`${prefix}/teams/red/users/${id}?secret=private`)
        .expect(200);
      await request(server).get(`${prefix}/unknown/${id}`).expect(404);
    }
    await request(server)
      .get(`${prefix}/teams/red/users/user-123/missing`)
      .expect(404);
    await request(server)
      .get(`${prefix}/teams/red/users/user-123/crash`)
      .expect(500);

    const scrape = await request(server).get(`${prefix}/metrics`).expect(200);
    expect(scrape.headers['content-type']).toMatch(
      /^text\/plain;.*version=0\.0\.4/,
    );
    expect(scrape.text).toContain('# TYPE http_requests_total counter');
    expect(scrape.text).toContain(
      '# TYPE http_request_duration_seconds histogram',
    );
    expect(scrape.text).toContain('http_request_duration_seconds_bucket{');
    expect(scrape.text).toContain('le="+Inf"');
    expect(scrape.text).toContain('http_request_duration_seconds_sum{');
    expect(scrape.text).toContain('http_request_duration_seconds_count{');
    const metric = await app.get(MetricsService).requests.get();
    expect(metric.values).toEqual(
      expect.arrayContaining([
        {
          labels: {
            method: 'GET',
            route: `${prefix}/teams/:teamId/users/:userId`,
            status_code: '200',
          },
          value: 2,
        },
        {
          labels: { method: 'GET', route: '__unmatched__', status_code: '404' },
          value: 2,
        },
        {
          labels: {
            method: 'GET',
            route: `${prefix}/teams/:teamId/users/:userId/missing`,
            status_code: '404',
          },
          value: 1,
        },
        {
          labels: {
            method: 'GET',
            route: `${prefix}/teams/:teamId/users/:userId/crash`,
            status_code: '500',
          },
          value: 1,
        },
      ]),
    );
    expect(metric.values).toHaveLength(4);
    const duration = await app.get(MetricsService).duration.get();
    const counts = duration.values.filter(
      (value) => value.metricName === 'http_request_duration_seconds_count',
    );
    expect(counts.map(({ labels, value }) => ({ labels, value }))).toEqual(
      expect.arrayContaining(metric.values),
    );
    expect(counts).toHaveLength(4);
    const sums = duration.values.filter(
      (value) => value.metricName === 'http_request_duration_seconds_sum',
    );
    expect(sums).toHaveLength(4);
    for (const sum of sums) {
      expect(Number.isFinite(sum.value)).toBe(true);
      expect(sum.value).toBeGreaterThanOrEqual(0);
    }
    expect(scrape.text).not.toMatch(/user-123|user-456|private|teams\/red/);
  });

  it('excludes scrapes and both health probes, including query strings', async () => {
    for (let i = 0; i < 2; i++) {
      for (const path of ['/metrics', '/health/live', '/health/ready']) {
        await request(app.getHttpServer())
          .get(`${prefix}${path}?probe=yes`)
          .expect(200);
      }
    }
    expect((await app.get(MetricsService).requests.get()).values).toEqual([]);
    expect((await app.get(MetricsService).duration.get()).values).toEqual([]);
    await request(app.getHttpServer()).get(`${prefix}/api/v1/info`).expect(200);
    expect((await app.get(MetricsService).requests.get()).values).toEqual([
      {
        labels: {
          method: 'GET',
          route: `${prefix}/api/v1/info`,
          status_code: '200',
        },
        value: 1,
      },
    ]);
  });

  it('isolates registries between simultaneously initialized applications', async () => {
    const other = await createApp(prefix);
    try {
      expect(other.get(MetricsService).registry).not.toBe(
        app.get(MetricsService).registry,
      );
      await request(app.getHttpServer())
        .get(`${prefix}/api/v1/info`)
        .expect(200);
      expect(
        (await app.get(MetricsService).requests.get()).values,
      ).toHaveLength(1);
      expect((await other.get(MetricsService).requests.get()).values).toEqual(
        [],
      );
      expect((await other.get(MetricsService).duration.get()).values).toEqual(
        [],
      );
      expect((await app.get(MetricsService).duration.get()).values).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            metricName: 'http_request_duration_seconds_count',
            value: 1,
          }),
        ]),
      );
    } finally {
      await other.close();
    }
  });

  it('does not count a response when the client disconnects before finish', async () => {
    let closed!: () => void;
    const serverClosed = new Promise<void>((resolve) => {
      closed = resolve;
    });
    UsersController.closed = closed;
    await app.listen(0, '127.0.0.1');
    const { port } = app.getHttpServer().address() as AddressInfo;
    try {
      await new Promise<void>((resolve, reject) => {
        const client = get(
          `http://127.0.0.1:${port}${prefix}/teams/red/users/user-123/stream`,
          (response) => {
            response.once('data', () => {
              response.destroy();
              resolve();
            });
            response.on('error', reject);
          },
        );
        client.on('error', reject);
      });
      await serverClosed;
      expect((await app.get(MetricsService).requests.get()).values).toEqual([]);
      expect((await app.get(MetricsService).duration.get()).values).toEqual([]);
    } finally {
      UsersController.closed = undefined;
    }
  });
});

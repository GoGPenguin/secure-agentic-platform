import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import type { App } from 'supertest/types.js';
import { AppModule } from '../src/app.module.js';
import { LabAppModule } from '../src/lab/lab-app.module.js';
import { MetricsService } from '../src/metrics/metrics.service.js';

describe.each(['', '/prefix'])('lab HTTP 503 with prefix %j', (prefix) => {
  let app: INestApplication<App> | undefined;
  const path = `${prefix}/api/v1/lab/failures/http-503`;

  async function create(env: NodeJS.ProcessEnv, production = false) {
    const module = await Test.createTestingModule({
      imports: [production ? AppModule : LabAppModule.register(env)],
    }).compile();
    app = module.createNestApplication<INestApplication<App>>();
    app.useLogger(false);
    app.setGlobalPrefix(prefix);
    await app.init();
    return app;
  }

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it.each([
    {},
    { PLATFORM_ENVIRONMENT: 'local-lab' },
    { PLATFORM_ENVIRONMENT: 'local-lab', LAB_HTTP_503_ENABLED: 'false' },
  ])('does not register the route when disabled: %j', async (env) => {
    const disabled = await create(env);
    await request(disabled.getHttpServer()).post(path).expect(404);
    expect((await disabled.get(MetricsService).requests.get()).values).toEqual([
      {
        labels: { method: 'POST', route: '__unmatched__', status_code: '404' },
        value: 1,
      },
    ]);
  });

  it('does not expose the route in the production AppModule', async () => {
    const production = await create({}, true);
    await request(production.getHttpServer()).post(path).expect(404);
  });

  it('counts completed 503s exactly once and preserves health/metrics exclusions', async () => {
    const enabled = await create({
      PLATFORM_ENVIRONMENT: 'local-lab',
      LAB_HTTP_503_ENABLED: 'true',
    });
    const server = enabled.getHttpServer();
    const metrics = enabled.get(MetricsService);
    const labels = { method: 'POST', route: path, status_code: '503' };
    for (let count = 1; count <= 2; count++) {
      await request(server)
        .post(`${path}?arbitrary=${count}`)
        .send({ status: 200 })
        .expect(503)
        .expect({
          statusCode: 503,
          message: 'Controlled lab HTTP 503',
          error: 'Service Unavailable',
        });
      expect((await metrics.requests.get()).values).toEqual([
        { labels, value: count },
      ]);
      expect(
        (await metrics.duration.get()).values.filter(
          (value) => value.metricName === 'http_request_duration_seconds_count',
        ),
      ).toEqual([
        {
          metricName: 'http_request_duration_seconds_count',
          labels,
          value: count,
        },
      ]);
    }
    for (const health of ['/health/live', '/health/ready']) {
      await request(server).get(`${prefix}${health}?probe=yes`).expect(200);
    }
    for (let i = 0; i < 2; i++) {
      const scrape = await request(server).get(`${prefix}/metrics`).expect(200);
      expect(scrape.text).toContain(`route="${path}",status_code="503"`);
    }
    expect((await metrics.requests.get()).values).toEqual([
      { labels, value: 2 },
    ]);
    const histogram = (await metrics.duration.get()).values;
    expect(
      histogram.filter(
        (value) => value.metricName === 'http_request_duration_seconds_count',
      ),
    ).toEqual([
      { metricName: 'http_request_duration_seconds_count', labels, value: 2 },
    ]);
    const sum = histogram.find(
      (value) => value.metricName === 'http_request_duration_seconds_sum',
    );
    expect(Number.isFinite(sum?.value)).toBe(true);
    expect(sum?.value).toBeGreaterThanOrEqual(0);
    await request(server).get(`${prefix}/api/v1/info`).expect(200);
  });
});

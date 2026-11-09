import { Test } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { App } from 'supertest/types.js';
import { AppModule } from '../src/app.module.js';

describe('Health endpoints (e2e)', () => {
  let app: INestApplication<App>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = module.createNestApplication();
    await app.init();
  });

  afterEach(async () => {
    await app.close();
  });

  it('GET /health/live returns HTTP 200 and the liveness status as JSON', async () => {
    await request(app.getHttpServer())
      .get('/health/live')
      .expect(200)
      .expect('Content-Type', /application\/json/)
      .expect({ status: 'ok' });
  });

  it('GET /health/ready returns HTTP 200 and the readiness status as JSON', async () => {
    await request(app.getHttpServer())
      .get('/health/ready')
      .expect(200)
      .expect('Content-Type', /application\/json/)
      .expect({ status: 'ready' });
  });
});

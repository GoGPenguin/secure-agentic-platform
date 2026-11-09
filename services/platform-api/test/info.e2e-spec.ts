import { Test } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { App } from 'supertest/types.js';
import { AppModule } from '../src/app.module.js';

describe('Info endpoint (e2e)', () => {
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

  it('GET /api/v1/info returns the service metadata as JSON', async () => {
    await request(app.getHttpServer())
      .get('/api/v1/info')
      .expect(200)
      .expect('Content-Type', /application\/json/)
      .expect({ service: 'platform-api', version: '0.1.1' });
  });
});

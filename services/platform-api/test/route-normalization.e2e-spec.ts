import {
  Controller,
  Get,
  Module,
  NotFoundException,
  type INestApplication,
} from '@nestjs/common';
import { RouterModule } from '@nestjs/core';
import { Test } from '@nestjs/testing';
import type { NextFunction, Request, Response } from 'express';
import request from 'supertest';
import type { App } from 'supertest/types.js';

@Controller('teams/:teamId/users')
class UsersController {
  @Get(':userId')
  getUser() {
    return { status: 'ok' };
  }

  @Get(':userId/missing')
  missingUser() {
    throw new NotFoundException('User not found');
  }

  @Get(':userId/crash')
  crash() {
    throw new Error('Controller failure');
  }
}

@Module({ controllers: [UsersController] })
class UsersModule {}

interface Observation {
  route: unknown;
  baseUrl: string | undefined;
  path: string;
  status: number;
}

describe.each(['', '/api/v1'])(
  'Route normalization at response completion with prefix "%s" (e2e)',
  (prefix) => {
    let app: INestApplication<App>;
    let observations: Observation[];
    const template = `${prefix}/orgs/:orgId/teams/:teamId/users/:userId`;

    beforeEach(async () => {
      const module = await Test.createTestingModule({
        imports: [
          UsersModule,
          RouterModule.register([{ path: 'orgs/:orgId', module: UsersModule }]),
        ],
      }).compile();

      app = module.createNestApplication();
      app.useLogger(false);
      app.setGlobalPrefix(prefix);
      observations = [];

      // Read after routing and exception handling, rather than at middleware entry.
      app.use((req: Request, res: Response, next: NextFunction) => {
        res.once('finish', () => {
          observations.push({
            route: req.route?.path,
            baseUrl: req.baseUrl,
            path: req.path,
            status: res.statusCode,
          });
        });
        next();
      });
      await app.init();
    });

    afterEach(async () => {
      await app.close();
    });

    it('preserves the full template across dynamic IDs and query strings', async () => {
      for (const [orgId, teamId, userId] of [
        ['acme', 'red', 'user-123'],
        ['other', 'blue', 'user-456'],
      ]) {
        const path = `${prefix}/orgs/${orgId}/teams/${teamId}/users/${userId}`;
        await request(app.getHttpServer())
          .get(`${path}?search=private`)
          .expect(200);

        expect(observations.at(-1)).toEqual({
          route: template,
          baseUrl: '',
          path,
          status: 200,
        });
      }

      expect(observations).toHaveLength(2);
      for (const observation of observations) {
        expect(observation.route).not.toMatch(/user-123|user-456|private/);
      }
    });

    it('keeps user IDs out of route metadata for unmatched URLs', async () => {
      for (const userId of ['user-123', 'user-456']) {
        const localPath = `/orgs/acme/teams/red/users/${userId}/unknown`;
        const path = `${prefix}${localPath}`;
        await request(app.getHttpServer()).get(path).expect(404);

        // Nest's prefixed 404 handler is an Express wildcard route, not a
        // controller match. Without a prefix, no route is assigned.
        expect(observations.at(-1)).toMatchObject({
          route: prefix ? '*path' : undefined,
          path: localPath,
          status: 404,
        });
      }
      expect(observations).toHaveLength(2);
    });

    it.each([
      ['missing', 404],
      ['crash', 500],
    ])(
      'retains the matched template for %s responses',
      async (suffix, status) => {
        const path = `${prefix}/orgs/acme/teams/red/users/user-123/${suffix}`;
        await request(app.getHttpServer()).get(path).expect(status);

        expect(observations).toEqual([
          { route: `${template}/${suffix}`, baseUrl: '', path, status },
        ]);
        expect(observations[0].route).not.toContain('user-123');
      },
    );
  },
);

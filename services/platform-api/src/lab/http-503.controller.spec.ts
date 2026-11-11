import { ServiceUnavailableException } from '@nestjs/common';
import { Http503Controller } from './http-503.controller.js';
import { LabAppModule } from './lab-app.module.js';

describe('lab HTTP 503 controller', () => {
  it('throws a fixed NestJS 503', () => {
    try {
      new Http503Controller().fail();
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(ServiceUnavailableException);
      expect((error as ServiceUnavailableException).getStatus()).toBe(503);
      expect((error as ServiceUnavailableException).getResponse()).toEqual({
        statusCode: 503,
        message: 'Controlled lab HTTP 503',
        error: 'Service Unavailable',
      });
    }
  });

  it('resolves registration per application, without import-time environment capture', () => {
    expect(LabAppModule.register({}).controllers).toEqual([]);
    expect(
      LabAppModule.register({
        PLATFORM_ENVIRONMENT: 'local-lab',
        LAB_HTTP_503_ENABLED: 'true',
      }).controllers,
    ).toEqual([Http503Controller]);
    expect(LabAppModule.register({}).controllers).toEqual([]);
  });

  it('rejects invalid enablement before creating the application', () => {
    expect(() =>
      LabAppModule.register({
        PLATFORM_ENVIRONMENT: 'production',
        LAB_HTTP_503_ENABLED: 'true',
      }),
    ).toThrow('PLATFORM_ENVIRONMENT=local-lab');
  });
});

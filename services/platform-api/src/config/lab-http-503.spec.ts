import {
  labHttp503Enabled,
  validateProductionEnvironment,
} from './lab-http-503.js';

describe('HTTP 503 injection configuration', () => {
  it.each([
    {},
    { PLATFORM_ENVIRONMENT: 'local-lab' },
    { LAB_HTTP_503_ENABLED: 'false', PLATFORM_ENVIRONMENT: 'production' },
  ])('defaults to disabled: %j', (env) => {
    expect(labHttp503Enabled(env)).toBe(false);
    expect(() => validateProductionEnvironment(env)).not.toThrow();
  });

  it('enables only an explicitly selected local lab', () => {
    const env = {
      PLATFORM_ENVIRONMENT: 'local-lab',
      LAB_HTTP_503_ENABLED: 'true',
    };
    expect(labHttp503Enabled(env)).toBe(true);
    expect(() => validateProductionEnvironment(env)).toThrow(
      'separate lab build',
    );
  });

  it.each([undefined, '', 'production', 'staging', 'development', 'LOCAL-LAB'])(
    'rejects enablement in environment %s',
    (environment) => {
      const env = {
        PLATFORM_ENVIRONMENT: environment,
        LAB_HTTP_503_ENABLED: 'true',
      };
      expect(() => labHttp503Enabled(env)).toThrow(
        'PLATFORM_ENVIRONMENT=local-lab',
      );
      expect(() => validateProductionEnvironment(env)).toThrow();
    },
  );

  it.each(['', 'TRUE', '1', 'yes', ' true ', 'FALSE'])(
    'rejects malformed flag %j',
    (flag) => {
      expect(() =>
        labHttp503Enabled({
          PLATFORM_ENVIRONMENT: 'local-lab',
          LAB_HTTP_503_ENABLED: flag,
        }),
      ).toThrow('must be true or false');
    },
  );
});

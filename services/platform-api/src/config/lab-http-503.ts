export function labHttp503Enabled(env: NodeJS.ProcessEnv): boolean {
  const flag = env.LAB_HTTP_503_ENABLED;
  if (flag === undefined || flag === 'false') return false;
  if (flag !== 'true') {
    throw new Error('LAB_HTTP_503_ENABLED must be true or false');
  }
  if (env.PLATFORM_ENVIRONMENT !== 'local-lab') {
    throw new Error(
      'HTTP 503 injection requires PLATFORM_ENVIRONMENT=local-lab',
    );
  }
  return true;
}

export function validateProductionEnvironment(env: NodeJS.ProcessEnv): void {
  if (labHttp503Enabled(env)) {
    throw new Error('HTTP 503 injection requires the separate lab build');
  }
}

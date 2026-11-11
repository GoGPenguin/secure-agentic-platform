import assert from 'node:assert/strict';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

// Run after build:lab followed by build, to detect stale cross-build output too.
assert.ok(existsSync('dist-lab/lab/http-503.controller.js'));
assert.ok(existsSync('dist-lab/lab/main.js'));
assert.ok(!existsSync('dist/lab'));
function inspect(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) inspect(path);
    else {
      assert.doesNotMatch(entry.name, /http-503\.controller|lab-app\.module/);
      assert.doesNotMatch(
        readFileSync(path, 'utf8'),
        /Http503Controller|Controlled lab HTTP 503/,
      );
    }
  }
}
inspect('dist');
console.log(
  'PASS: production dist excludes the controller, including declarations/maps; lab output is separate',
);

for (const [entry, environment, message] of [
  ['dist-lab/lab/main.js', 'production', 'PLATFORM_ENVIRONMENT=local-lab'],
  ['dist-lab/lab/main.js', undefined, 'PLATFORM_ENVIRONMENT=local-lab'],
  ['dist/main.js', 'production', 'PLATFORM_ENVIRONMENT=local-lab'],
  ['dist/main.js', 'local-lab', 'separate lab build'],
]) {
  const env = { ...process.env, LAB_HTTP_503_ENABLED: 'true' };
  delete env.PLATFORM_ENVIRONMENT;
  if (environment !== undefined) env.PLATFORM_ENVIRONMENT = environment;
  const result = spawnSync(process.execPath, [entry], {
    env,
    encoding: 'utf8',
    timeout: 5000,
  });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 1, result.stderr);
  assert.ok(result.stderr.includes(message), result.stderr);
}
console.log(
  'PASS: compiled entry points reject invalid enablement before listening',
);

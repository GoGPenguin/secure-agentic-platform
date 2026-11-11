import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

// Feed this script to the final image's Node via stdin; no test dependencies
// or host mounts enter the image. No published ports or external network needed.
const kind = process.argv[2];
assert.ok(['production', 'lab'].includes(kind));
const lab = kind === 'lab';
assert.equal(process.version, 'v24.22.2');
assert.notEqual(process.getuid(), 0);
assert.equal(process.env.NODE_ENV, 'production');
if (lab) {
  assert.ok(existsSync('dist-lab/lab/http-503.controller.js'));
  assert.equal(existsSync('dist'), false);
} else {
  assert.equal(existsSync('dist-lab'), false);
  assert.equal(existsSync('dist/lab'), false);
  for (const name of readdirSync('dist', { recursive: true })) {
    assert.doesNotMatch(name, /http-503\.controller|lab-app\.module/);
    if (/\.(js|map|ts)$/.test(name)) {
      assert.doesNotMatch(
        readFileSync(`dist/${name}`, 'utf8'),
        /Http503Controller|Controlled lab HTTP 503/,
      );
    }
  }
}

await import(
  pathToFileURL(resolve(lab ? 'dist-lab/lab/main.js' : 'dist/main.js')).href
);
const base = `http://127.0.0.1:${process.env.PORT ?? 3000}`;
for (const path of ['/health/live', '/health/ready', '/metrics']) {
  assert.equal((await fetch(base + path)).status, 200);
}
const enabled = lab && process.env.LAB_HTTP_503_ENABLED === 'true';
const response = await fetch(base + '/api/v1/lab/failures/http-503', {
  method: 'POST',
});
assert.equal(response.status, enabled ? 503 : 404);
if (enabled) {
  assert.deepEqual(await response.json(), {
    statusCode: 503,
    message: 'Controlled lab HTTP 503',
    error: 'Service Unavailable',
  });
}
const scrape = await (await fetch(base + '/metrics')).text();
const counter =
  'http_requests_total{method="POST",route="/api/v1/lab/failures/http-503",status_code="503"} 1';
const histogram =
  'http_request_duration_seconds_count{method="POST",route="/api/v1/lab/failures/http-503",status_code="503"} 1';
if (enabled) {
  assert.ok(scrape.includes(counter), scrape);
  assert.ok(scrape.includes(histogram), scrape);
} else {
  assert.ok(!scrape.includes('status_code="503"'), scrape);
}
console.log(
  `PASS: ${kind} image, non-root Node ${process.version}, route ${response.status}, health/metrics 200, artifact and metrics checks`,
);
process.exit(0);

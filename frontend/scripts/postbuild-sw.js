/**
 * Post-build script: injects a unique build hash into the service worker
 * so that every deployment automatically busts client caches.
 *
 * Runs automatically after `npm run build` via the "postbuild" npm script.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SW_PATH = path.resolve(__dirname, '../build/service-worker.js');

if (!fs.existsSync(SW_PATH)) {
  console.warn('[postbuild-sw] service-worker.js not found in build output, skipping.');
  process.exit(0);
}

let gitHash;
try {
  gitHash = execSync('git rev-parse --short HEAD').toString().trim();
} catch {
  gitHash = 'nogit';
}

const version = `${gitHash}-${Date.now()}`;
let content = fs.readFileSync(SW_PATH, 'utf8');
const replaced = content.replace(/__BUILD_HASH__/g, version);

if (replaced === content) {
  console.warn('[postbuild-sw] __BUILD_HASH__ placeholder not found in service-worker.js');
} else {
  fs.writeFileSync(SW_PATH, replaced);
  console.log(`[postbuild-sw] SW_VERSION set to: ${version}`);
}

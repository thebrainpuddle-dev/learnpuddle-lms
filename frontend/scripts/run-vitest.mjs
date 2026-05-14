#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const vitestBin = join(process.cwd(), 'node_modules', 'vitest', 'vitest.mjs');
if (!existsSync(vitestBin)) {
  console.error(`Vitest entrypoint not found at ${vitestBin}`);
  process.exit(1);
}
const args = process.argv.slice(2);
const env = { ...process.env };
const major = Number.parseInt(process.versions.node.split('.')[0] || '0', 10);

// Node 25 exposes experimental Web Storage globals that collide with this
// repo's real browser-storage test setup. Older CI Node versions reject this
// flag in NODE_OPTIONS, so add it only where it is supported.
if (major >= 25) {
  env.NODE_OPTIONS = [env.NODE_OPTIONS, '--no-experimental-webstorage']
    .filter(Boolean)
    .join(' ');
} else if (env.NODE_OPTIONS) {
  env.NODE_OPTIONS = env.NODE_OPTIONS
    .split(/\s+/)
    .filter((part) => part && part !== '--no-experimental-webstorage')
    .join(' ');
}

const child = spawn(process.execPath, [vitestBin, ...args], {
  stdio: 'inherit',
  env,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

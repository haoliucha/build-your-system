#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const repo = path.resolve(__dirname, '..');
const source = path.join(repo, 'targets/codex/build-your-system-assistant/skills/x-unfollow');
const target = path.join(repo, 'x/skills/x-unfollow');

function syncTree(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  const sourceNames = new Set(fs.readdirSync(src));
  for (const name of fs.readdirSync(dst)) {
    if (!sourceNames.has(name)) fs.rmSync(path.join(dst, name), { recursive: true, force: true });
  }
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dst, entry.name);
    if (entry.isDirectory()) syncTree(from, to);
    else fs.copyFileSync(from, to);
  }
}

if (!fs.existsSync(source)) throw new Error(`Canonical source missing: ${source}`);
syncTree(source, target);
console.log(`Synced canonical Codex x-unfollow source to Claude target: ${target}`);

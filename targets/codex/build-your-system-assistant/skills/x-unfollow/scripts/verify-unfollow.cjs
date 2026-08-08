#!/usr/bin/env node
// verify-unfollow.cjs — verify every target locally from one post-action /following snapshot.
// This script makes zero X requests and never opens individual profile pages.

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { todayInShanghai } = require('./lib/hygiene.cjs');
const { diffFollowing } = require('./lib/following-diff.cjs');

const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');
const SNAP_DIR = path.join(DATA_DIR, 'snapshots');
const argv = process.argv.slice(2);
const valueOf = (prefix) => (argv.find((arg) => arg.startsWith(prefix)) || '').slice(prefix.length);
const DATE = valueOf('--date=') || todayInShanghai();
const SNAPSHOT_DATE = valueOf('--snapshot-date=') || `${DATE}-post-unfollow`;
const HANDLES_ARG = valueOf('--handles=');

function ensureDir(dir) { fs.mkdirSync(dir, { recursive: true }); }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }

function loadHandles() {
  if (HANDLES_ARG) return HANDLES_ARG.split(',').map((item) => item.trim()).filter(Boolean);
  const file = path.join(REPORTS_DIR, `unfollow-${DATE}.json`);
  if (!fs.existsSync(file)) throw new Error(`unfollow log not found: ${file}`);
  const obj = readJson(file);
  return (obj.results || []).filter((row) => row.action === 'unfollowed').map((row) => row.handle);
}

function loadSnapshot() {
  const file = path.join(SNAP_DIR, `${SNAPSHOT_DATE}.jsonl`);
  if (!fs.existsSync(file)) throw new Error(`post-action snapshot not found: ${file}`);
  const rows = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
  const metaFile = path.join(SNAP_DIR, `${SNAPSHOT_DATE}.meta.json`);
  const meta = fs.existsSync(metaFile) ? readJson(metaFile) : null;
  return { file, metaFile: fs.existsSync(metaFile) ? metaFile : null, rows, meta };
}

function main() {
  ensureDir(REPORTS_DIR);
  const handles = loadHandles();
  const snapshot = loadSnapshot();
  const diff = diffFollowing(handles, snapshot.rows);
  const coverageReliable = Boolean(snapshot.meta && snapshot.meta.coverageWarning === false);
  const report = {
    date: DATE,
    generatedAt: new Date().toISOString(),
    method: 'single-following-list-set-diff',
    snapshotDate: SNAPSHOT_DATE,
    snapshotFile: snapshot.file,
    snapshotMetaFile: snapshot.metaFile,
    coverage: snapshot.meta,
    coverageReliable,
    results: diff.results,
    removed: diff.removed,
    remaining: diff.remaining,
    counts: {
      requested: diff.requested.length,
      not_following: diff.removed.length,
      still_following: diff.remaining.length,
    },
  };
  const output = path.join(REPORTS_DIR, `verify-unfollow-${DATE}.json`);
  fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  process.stderr.write(`[verify] one-list diff: removed=${diff.removed.length} remaining=${diff.remaining.length} coverage=${coverageReliable ? 'reliable' : 'unknown/low'}\n`);
  console.log(JSON.stringify(report, null, 2));
}

try { main(); } catch (error) { console.error(`FATAL: ${error.message}`); process.exit(2); }

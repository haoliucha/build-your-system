#!/usr/bin/env node
'use strict';
// Local-only verification against current/following.jsonl. No browser, no profile visits.
const fs = require('fs');
const path = require('path');
const os = require('os');
const { diffFollowing } = require('./lib/following-diff.cjs');
const dataDir = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const handlesArg = (process.argv.find((arg) => arg.startsWith('--handles=')) || '').slice(10);
const actionFile = process.env.XU_ACTION_REPORT || '';
let handles = handlesArg.split(',').filter(Boolean);
if (!handles.length && actionFile && fs.existsSync(actionFile)) {
  const action = JSON.parse(fs.readFileSync(actionFile, 'utf8'));
  handles = (action.results || []).filter((row) => row.action === 'unfollowed').map((row) => row.handle);
}
const currentFile = path.join(dataDir, 'current', 'following.jsonl');
const metaFile = path.join(dataDir, 'current', 'following.meta.json');
const current = fs.readFileSync(currentFile, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
const meta = JSON.parse(fs.readFileSync(metaFile, 'utf8'));
const diff = diffFollowing(handles, current);
const report = { generatedAt: new Date().toISOString(), method: 'current-following-local-set-diff', coverageReliable: meta.usableForNegativeDiff === true, results: diff.results, removed: diff.removed, remaining: diff.remaining };
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (!report.coverageReliable) process.exitCode = 17;

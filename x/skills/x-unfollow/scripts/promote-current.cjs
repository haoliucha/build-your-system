#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const Store = require('./lib/current-store.cjs');
const { todayInShanghai } = require('./lib/hygiene.cjs');

const value = (name) => (process.argv.find((arg) => arg.startsWith(`${name}=`)) || '').slice(name.length + 1);
const dataDir = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const runId = value('--run-id') || process.env.XU_RUN_TOKEN;
const listType = value('--list');
const stage = path.join(dataDir, '.staging', runId || '');
const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const readRows = (file) => fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
function staged(type) {
  return { rows: readRows(path.join(stage, `${type}.jsonl`)), meta: readJson(path.join(stage, `${type}.meta.json`)) };
}
if (!runId || !['following', 'followers', 'both'].includes(listType)) throw new Error('--run-id and --list=following|followers|both required');
const date = process.env.SNAPSHOT_DATE || todayInShanghai();
let result;
if (listType === 'both') {
  const following = staged('following'); const followers = staged('followers');
  result = Store.promoteBoth({ dataDir, followingRows: following.rows, followingMeta: following.meta, followersRows: followers.rows, followersMeta: followers.meta, observedDate: date });
} else {
  const scan = staged(listType);
  result = Store.promoteList({ dataDir, listType, rows: scan.rows, meta: scan.meta, observedDate: date });
}
process.stdout.write(`${JSON.stringify({ promoted: listType, relationships: result.relationship.rows.length })}\n`);

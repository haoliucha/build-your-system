#!/usr/bin/env node
'use strict';
// v3 current-only classifier. It never reads dated snapshots or historical reports.
const fs = require('fs');
const path = require('path');
const os = require('os');
const H = require('./lib/hygiene.cjs');
const Store = require('./lib/current-store.cjs');
const dataDir = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const arg = (name, fallback) => (process.argv.find((a) => a.startsWith(`${name}=`)) || `=${fallback}`).split('=').slice(1).join('=');
const date = arg('--date', H.todayInShanghai());
const minDays = Number(arg('--min-days', 3));
const threshold = Number(arg('--follower-threshold', 2000));
const relationships = Store.readJsonl(path.join(dataDir, 'current', 'relationships.jsonl'));
if (!relationships) throw new Error('Missing current/relationships.jsonl; run a list report first');
const rows = relationships.filter((row) => row.inFollowing && row.followsMeBadge === false && !row.evidenceConflict).map((row) => {
  const elapsed = row.nonRecipSince ? H.naturalDaysBetween(row.nonRecipSince, date) : null;
  const refreshed = Number.isFinite(row.refreshedFollowersCount) ? row.refreshedFollowersCount : null;
  const verdict = H.classifyDecision({
    validHandle: H.isValidHandle(row.handle), navOrMiscrape: H.isNavOrMiscrape(row.handle), excluded: false,
    elapsed, hasRefreshed: refreshed !== null, refreshedFollowers: refreshed,
  }, { minDays, followerThreshold: threshold });
  return {
    ...row, decision: verdict.decision, reason_code: verdict.reason_code,
    reason_label_zh: verdict.reason_label_zh, needs_profile_refresh: verdict.needs_profile_refresh,
    natural_elapsed_days: elapsed, refreshed_followers_count: refreshed,
    follower_threshold: threshold,
  };
});
const byReason = {}; for (const row of rows) byReason[row.reason_code] = (byReason[row.reason_code] || 0) + 1;
const payload = { generatedAt: new Date().toISOString(), observedDate: date, criteria: { minDaysExclusive: minDays, followerThresholdExclusive: threshold }, totals: { rows: rows.length, byReason }, rows };
fs.mkdirSync(path.join(dataDir, 'reports'), { recursive: true });
Store.atomicWrite(path.join(dataDir, 'reports', 'latest-non-recip.json'), `${JSON.stringify(payload, null, 2)}\n`);
const fields = ['handle','name','reason_code','decision','nonRecipSince','consecutiveDays','natural_elapsed_days','refreshed_followers_count'];
Store.atomicWrite(path.join(dataDir, 'reports', 'latest-non-recip.csv'), `${fields.join(',')}\n${rows.map((r) => fields.map((f) => String(r[f] ?? '')).join(',')).join('\n')}${rows.length ? '\n' : ''}`);
process.stdout.write(`${JSON.stringify(payload.totals, null, 2)}\n`);

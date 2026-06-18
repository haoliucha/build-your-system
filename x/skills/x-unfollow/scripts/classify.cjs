#!/usr/bin/env node
// classify.cjs — turn the dated snapshot series into a per-account decision table.
//
// For each handle in today's snapshot, assign one reason code (decision order is the PURE
// lib/hygiene.classifyDecision contract):
//   EXCLUDE_INVALID_HANDLE / EXCLUDE_NAV_OR_MISCRAPE / EXCLUDE_ALREADY_UNFOLLOWED
//   KEEP_WAITING_GT3            (elapsed <= minDays)
//   ELIGIBLE_FOR_FOLLOWER_REFRESH (past wait, no refreshed follower count yet)
//   EXCLUDE_FOLLOWERS_GE_THRESHOLD (refreshed count >= threshold)
//   ELIGIBLE_FOR_UNFOLLOW       (past wait AND refreshed count < threshold)  -> candidate_unfollow
//
// Ported from the Codex classify-nonrecip.cjs; history is sourced ONLY from the local
// snapshot series (no vault), and exclusions come from prior unfollow / verify logs.
//
// Usage: node classify.cjs [--date=YYYY-MM-DD] [--min-days=3] [--follower-threshold=2000] [--no-write]
// Env: XU_DATA_DIR. Reads snapshots/*.jsonl + reports/profile-refresh-<date>.json +
//      reports/{unfollow,verify-unfollow}-*.json. Writes reports/non-recip-reasons-<date>.{json,csv}.

const fs = require('fs');
const path = require('path');
const os = require('os');
const H = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const SNAP_DIR = path.join(DATA_DIR, 'snapshots');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');

function parseArgs(argv) {
  const out = { date: H.todayInShanghai(), minDays: 3, followerThreshold: 2000, write: true };
  for (const a of argv) {
    if (a.startsWith('--date=')) out.date = a.split('=')[1];
    else if (a.startsWith('--min-days=')) out.minDays = Number(a.split('=')[1]);
    else if (a.startsWith('--follower-threshold=')) out.followerThreshold = Number(a.split('=')[1]);
    else if (a === '--no-write') out.write = false;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(out.date)) throw new Error('Use --date=YYYY-MM-DD');
  if (!Number.isFinite(out.minDays) || out.minDays < 0) throw new Error('Invalid --min-days');
  if (!Number.isFinite(out.followerThreshold) || out.followerThreshold < 0) throw new Error('Invalid --follower-threshold');
  return out;
}

function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function fileDate(name) { return (name.match(/(\d{4}-\d{2}-\d{2})/) || [null, null])[1]; }

// Flatten all snapshot rows up to and including targetDate (for history/firstSeen).
function loadAllSnapshotRows(targetDate) {
  if (!fs.existsSync(SNAP_DIR)) return [];
  const rows = [];
  for (const f of fs.readdirSync(SNAP_DIR).filter((x) => /^\d{4}-\d{2}-\d{2}\.jsonl$/.test(x)).sort()) {
    const date = f.replace('.jsonl', '');
    if (date > targetDate) continue;
    for (const line of fs.readFileSync(path.join(SNAP_DIR, f), 'utf8').split('\n').filter(Boolean)) {
      try { rows.push({ ...JSON.parse(line), snapshotDate: date }); } catch {}
    }
  }
  return rows;
}

function loadTodaySnapshot(targetDate) {
  const file = path.join(SNAP_DIR, `${targetDate}.jsonl`);
  if (!fs.existsSync(file)) throw new Error(`Missing snapshot: ${file} (run snapshot.cjs first)`);
  const rows = [];
  for (const [idx, line] of fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).entries()) {
    rows.push({ row_index: idx + 1, ...JSON.parse(line) });
  }
  return rows;
}

// Accounts already unfollowed (and verified) in prior logs — never re-target.
function loadExclusions(targetDate) {
  const excl = new Map();
  const mark = (handle, source) => {
    const key = H.normalizeHandle(handle);
    if (!key) return;
    const prev = excl.get(key) || { sources: [] };
    if (!prev.sources.includes(source)) prev.sources.push(source);
    excl.set(key, prev);
  };
  if (!fs.existsSync(REPORTS_DIR)) return excl;
  for (const f of fs.readdirSync(REPORTS_DIR).filter((x) => /^unfollow-\d{4}-\d{2}-\d{2}\.json$/.test(x)).sort()) {
    if ((fileDate(f) || '') > targetDate) continue;
    const obj = readJson(path.join(REPORTS_DIR, f));
    for (const row of (Array.isArray(obj.results) ? obj.results : [])) {
      // Only DOM-confirmed unfollows exclude here; 'unfollow_assumed' waits for verify-unfollow.
      if (row.action === 'unfollowed') mark(row.handle, f);
    }
  }
  for (const f of fs.readdirSync(REPORTS_DIR).filter((x) => /^verify-unfollow-\d{4}-\d{2}-\d{2}\.json$/.test(x)).sort()) {
    if ((fileDate(f) || '') > targetDate) continue;
    const obj = readJson(path.join(REPORTS_DIR, f));
    for (const row of (Array.isArray(obj.results) ? obj.results : [])) {
      if (row.not_following === true) mark(row.handle, f);
    }
  }
  return excl;
}

function loadProfileRefresh(targetDate) {
  const out = new Map();
  const file = path.join(REPORTS_DIR, `profile-refresh-${targetDate}.json`);
  if (!fs.existsSync(file)) return out;
  const obj = readJson(file);
  const rows = Array.isArray(obj.results) ? obj.results : (Array.isArray(obj) ? obj : []);
  for (const row of rows) {
    const key = H.normalizeHandle(row.handle || row.screen_name);
    if (key) out.set(key, row);
  }
  return out;
}

function buildRow(snapRow, ctx) {
  const key = H.normalizeHandle(snapRow.handle);
  const hist = ctx.history.get(key);
  const refreshed = ctx.profileRefresh.get(key);
  const firstSeen = hist?.firstSeen || null;
  const elapsed = firstSeen ? H.naturalDaysBetween(firstSeen, ctx.date) : null;
  const refreshedFollowers = Number.isFinite(refreshed?.followers_count) ? refreshed.followers_count : null;

  const verdict = H.classifyDecision({
    validHandle: H.isValidHandle(snapRow.handle),
    navOrMiscrape: H.isNavOrMiscrape(snapRow.handle),
    excluded: ctx.exclusions.has(key),
    elapsed,
    hasRefreshed: refreshedFollowers !== null,
    refreshedFollowers,
  }, { minDays: ctx.minDays, followerThreshold: ctx.followerThreshold });

  return {
    handle: snapRow.handle,
    name: hist?.name || snapRow.name || snapRow.handle,
    reason_code: verdict.reason_code,
    reason_label_zh: verdict.reason_label_zh,
    decision: verdict.decision,
    needs_profile_refresh: verdict.needs_profile_refresh,
    snapshot_date: ctx.date,
    first_seen_not_following_back: firstSeen,
    last_confirmed_not_following_back: hist?.lastSeen || ctx.date,
    natural_elapsed_days: elapsed,
    consecutive_days_inclusive: elapsed === null ? null : elapsed + 1,
    wait_until_date_for_gt3: firstSeen ? H.addDays(firstSeen, ctx.minDays + 1) : null,
    raw_snapshot_followers: Number.isFinite(snapRow.followers) ? snapRow.followers : null,
    raw_snapshot_followers_trusted: false,
    follower_threshold: ctx.followerThreshold,
    refreshed_followers_count: refreshedFollowers,
    profile_url: `https://x.com/${snapRow.handle}`,
    exclusion_sources: ctx.exclusions.get(key)?.sources || [],
  };
}

const CSV_FIELDS = [
  'handle', 'name', 'reason_code', 'reason_label_zh', 'decision', 'snapshot_date',
  'first_seen_not_following_back', 'last_confirmed_not_following_back',
  'natural_elapsed_days', 'consecutive_days_inclusive', 'wait_until_date_for_gt3',
  'raw_snapshot_followers', 'raw_snapshot_followers_trusted', 'follower_threshold',
  'refreshed_followers_count', 'needs_profile_refresh', 'profile_url', 'exclusion_sources',
];
function csvValue(v) {
  if (v === null || v === undefined) return '';
  const s = Array.isArray(v) ? v.join(';') : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function toCsv(rows) {
  const lines = [CSV_FIELDS.join(',')];
  for (const row of rows) lines.push(CSV_FIELDS.map((f) => csvValue(row[f])).join(','));
  return lines.join('\n') + '\n';
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  ensureDir(REPORTS_DIR);

  const todayRows = loadTodaySnapshot(args.date);
  const seen = new Set();
  const uniqueRows = todayRows.filter((r) => {
    const k = H.normalizeHandle(r.handle);
    if (seen.has(k)) return false; seen.add(k); return true;
  });

  const ctx = {
    date: args.date, minDays: args.minDays, followerThreshold: args.followerThreshold,
    history: H.buildHistoryFromSnapshots(loadAllSnapshotRows(args.date)),
    exclusions: loadExclusions(args.date),
    profileRefresh: loadProfileRefresh(args.date),
  };
  const rows = uniqueRows.map((r) => buildRow(r, ctx));

  const byReason = {}, byDecision = {};
  for (const r of rows) { byReason[r.reason_code] = (byReason[r.reason_code] || 0) + 1; byDecision[r.decision] = (byDecision[r.decision] || 0) + 1; }

  const payload = {
    generatedAt: new Date().toISOString(),
    snapshotDate: args.date,
    criteria: { minNaturalElapsedDaysExclusive: args.minDays, followerThresholdExclusive: args.followerThreshold, actionRule: 'Only ELIGIBLE_FOR_UNFOLLOW rows may be unfollowed.' },
    totals: { rawSnapshotRows: todayRows.length, uniqueSnapshotHandles: uniqueRows.length, historyHandles: ctx.history.size, exclusionHandles: ctx.exclusions.size, profileRefreshRows: ctx.profileRefresh.size, byReason, byDecision },
    rows,
  };

  if (args.write) {
    const jsonFile = path.join(REPORTS_DIR, `non-recip-reasons-${args.date}.json`);
    const csvFile = path.join(REPORTS_DIR, `non-recip-reasons-${args.date}.csv`);
    fs.writeFileSync(jsonFile, JSON.stringify(payload, null, 2) + '\n', 'utf8');
    fs.writeFileSync(csvFile, toCsv(rows), 'utf8');
    process.stderr.write(`[classify] wrote ${rows.length} rows -> ${jsonFile}\n`);
    process.stderr.write(`[classify] wrote ${rows.length} rows -> ${csvFile}\n`);
  }
  console.log(JSON.stringify(payload.totals, null, 2));
}

main();

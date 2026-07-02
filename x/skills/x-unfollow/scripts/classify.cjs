#!/usr/bin/env node
// classify.cjs — turn the dated snapshot series into a per-account decision table.
//
// For each handle in today's snapshot, assign one reason code (decision order is the PURE
// lib/hygiene.classifyDecision contract):
//   EXCLUDE_INVALID_HANDLE / EXCLUDE_NAV_OR_MISCRAPE / EXCLUDE_ALREADY_UNFOLLOWED
//   KEEP_WAITING_GT3            (elapsed <= minDays)
//   ELIGIBLE_FOR_FOLLOWER_REFRESH (past wait, no FRESH follower count — never refreshed,
//                                  or last refresh is older than the TTL)
//   EXCLUDE_FOLLOWERS_GE_THRESHOLD (refreshed count >= threshold)
//   ELIGIBLE_FOR_UNFOLLOW       (past wait AND refreshed count < threshold)  -> candidate_unfollow
//
// Ported from the Codex classify-nonrecip.cjs; history is sourced ONLY from the local
// snapshot series (no vault), and exclusions come from prior unfollow / verify logs.
//
// Follower counts are REUSED across days: a profile-refresh result stays valid for
// --refresh-ttl-days (default 14). So an account refreshed within the TTL is NOT re-fetched
// — only accounts that were never refreshed (or whose last refresh aged past the TTL) land in
// ELIGIBLE_FOR_FOLLOWER_REFRESH and get a fresh profile-counts.cjs pass. This is what keeps
// re-runs cheap: only the truly-stale/new accounts hit the network.
//
// Usage: node classify.cjs [--date=YYYY-MM-DD] [--min-days=3] [--follower-threshold=2000]
//                          [--refresh-ttl-days=14] [--no-write]
// Env: XU_DATA_DIR. Reads snapshots/*.jsonl + ALL reports/profile-refresh-*.json (≤ date,
//      within TTL) + reports/{unfollow,verify-unfollow}-*.json.
//      Writes reports/non-recip-reasons-<date>.{json,csv}.

const fs = require('fs');
const path = require('path');
const os = require('os');
const H = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const SNAP_DIR = path.join(DATA_DIR, 'snapshots');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');

function parseArgs(argv) {
  const out = { date: H.todayInShanghai(), minDays: 3, followerThreshold: 2000, refreshTtlDays: 14, write: true };
  for (const a of argv) {
    if (a.startsWith('--date=')) out.date = a.split('=')[1];
    else if (a.startsWith('--min-days=')) out.minDays = Number(a.split('=')[1]);
    else if (a.startsWith('--follower-threshold=')) out.followerThreshold = Number(a.split('=')[1]);
    else if (a.startsWith('--refresh-ttl-days=')) out.refreshTtlDays = Number(a.split('=')[1]);
    else if (a === '--no-write') out.write = false;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(out.date)) throw new Error('Use --date=YYYY-MM-DD');
  if (!Number.isFinite(out.minDays) || out.minDays < 0) throw new Error('Invalid --min-days');
  if (!Number.isFinite(out.followerThreshold) || out.followerThreshold < 0) throw new Error('Invalid --follower-threshold');
  if (!Number.isFinite(out.refreshTtlDays) || out.refreshTtlDays < 0) throw new Error('Invalid --refresh-ttl-days');
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
  let mutualRowsSkipped = 0;
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
  for (const [idx, line] of lines.entries()) {
    const parsed = JSON.parse(line);
    // Post-fix snapshots also record mutual (isFollowingMe: true) rows so scan
    // coverage is auditable in-file; only non-reciprocal rows enter classification.
    if (parsed.isFollowingMe !== false) { mutualRowsSkipped++; continue; }
    rows.push({ row_index: idx + 1, ...parsed });
  }
  return { rows, mutualRowsSkipped, rawRows: lines.length };
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

// Reuse follower counts across days. Scan ALL profile-refresh-*.json up to targetDate and,
// per handle, keep the NEWEST SUCCESSFUL refresh whose age is within the TTL. A follower
// count doesn't swing across the threshold day-to-day, so re-fetching one already gathered a
// few days ago is wasted work — that single串行 fetch loop is the whole skill's bottleneck.
//   - ttlDays<=0 disables reuse (everything past-wait re-refreshes; old single-day behavior).
//   - The "update time" of a row is its per-row `refreshedAt` (written by profile-counts.cjs),
//     falling back to the file's date for legacy rows that predate that field.
//   - Only rows with a finite followers_count are reusable; a failed refresh (followers_count
//     null) is skipped so it can't shadow an earlier good value for the same handle.
function loadProfileRefresh(targetDate, ttlDays) {
  const out = new Map(); // key -> row (augmented with refreshedAt)
  if (!fs.existsSync(REPORTS_DIR)) return out;
  if (!(ttlDays > 0)) return out; // ttl<=0: never reuse — force a fresh fetch for every past-wait account
  const cutoff = H.addDays(targetDate, -ttlDays); // earliest reusable date (inclusive)
  const files = fs.readdirSync(REPORTS_DIR)
    .filter((x) => /^profile-refresh-\d{4}-\d{2}-\d{2}\.json$/.test(x))
    .sort(); // oldest -> newest, so later (newer) rows naturally win on ties
  for (const f of files) {
    const fdate = fileDate(f);
    if (!fdate || fdate > targetDate) continue; // never read future refreshes
    let obj; try { obj = readJson(path.join(REPORTS_DIR, f)); } catch { continue; }
    const rows = Array.isArray(obj.results) ? obj.results : (Array.isArray(obj) ? obj : []);
    for (const row of rows) {
      const key = H.normalizeHandle(row.handle || row.screen_name);
      if (!key) continue;
      if (!Number.isFinite(row.followers_count)) continue; // skip failed/empty refreshes
      const refreshedAt = row.refreshedAt || `${fdate}T00:00:00.000Z`;
      const refreshDate = String(refreshedAt).slice(0, 10);
      if (refreshDate < cutoff) continue; // aged past TTL — treat as stale, re-fetch
      const prev = out.get(key);
      if (!prev || String(refreshedAt) > String(prev.refreshedAt || '')) out.set(key, { ...row, refreshedAt });
    }
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
    refreshed_at: refreshed?.refreshedAt || null,
    profile_url: `https://x.com/${snapRow.handle}`,
    exclusion_sources: ctx.exclusions.get(key)?.sources || [],
  };
}

const CSV_FIELDS = [
  'handle', 'name', 'reason_code', 'reason_label_zh', 'decision', 'snapshot_date',
  'first_seen_not_following_back', 'last_confirmed_not_following_back',
  'natural_elapsed_days', 'consecutive_days_inclusive', 'wait_until_date_for_gt3',
  'raw_snapshot_followers', 'raw_snapshot_followers_trusted', 'follower_threshold',
  'refreshed_followers_count', 'refreshed_at', 'needs_profile_refresh', 'profile_url', 'exclusion_sources',
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

  const { rows: todayRows, mutualRowsSkipped, rawRows } = loadTodaySnapshot(args.date);
  const seen = new Set();
  const uniqueRows = todayRows.filter((r) => {
    const k = H.normalizeHandle(r.handle);
    if (seen.has(k)) return false; seen.add(k); return true;
  });

  const ctx = {
    date: args.date, minDays: args.minDays, followerThreshold: args.followerThreshold,
    history: H.buildHistoryFromSnapshots(loadAllSnapshotRows(args.date)),
    exclusions: loadExclusions(args.date),
    profileRefresh: loadProfileRefresh(args.date, args.refreshTtlDays),
  };
  const rows = uniqueRows.map((r) => buildRow(r, ctx));

  const byReason = {}, byDecision = {};
  for (const r of rows) { byReason[r.reason_code] = (byReason[r.reason_code] || 0) + 1; byDecision[r.decision] = (byDecision[r.decision] || 0) + 1; }

  const payload = {
    generatedAt: new Date().toISOString(),
    snapshotDate: args.date,
    criteria: { minNaturalElapsedDaysExclusive: args.minDays, followerThresholdExclusive: args.followerThreshold, followerCountReuseTtlDays: args.refreshTtlDays, actionRule: 'Only ELIGIBLE_FOR_UNFOLLOW rows may be unfollowed.' },
    totals: { rawSnapshotRows: rawRows, todayMutualRowsSkipped: mutualRowsSkipped, uniqueSnapshotHandles: uniqueRows.length, historyHandles: ctx.history.size, exclusionHandles: ctx.exclusions.size, reusableRefreshHandles: ctx.profileRefresh.size, byReason, byDecision },
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

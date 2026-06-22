#!/usr/bin/env node
// build-queue.cjs — merge harvested candidates into queue.json, filtered & deduped.
//
// Inputs (in JOB dir, default = cwd):
//   priority.json        optional [handle,...] placed first (human-picked, never blue-filtered)
//   cand-*.json          harvest outputs { items:[{handle, blue, ...}] } — globbed, name-sorted
//   tracker.json         { followed:[{handle}], rejected:[{h}] } — the skip-set source
// Output: queue.json = [handle, ...]
//
// FIX vs original: skip set = followed ∪ rejected (the old build-queue skipped only
// rejected, so already-followed accounts leaked back into the queue).
//
// SKIP SOURCE: when SKIP_GLOB is set, the skip-set is computed DYNAMICALLY from every
// prior tracker (with lib/skipset's tiered release: transient errors and TTL-expired soft
// rejects are NOT skipped) ∪ this run's local tracker. This replaces the old design where
// run.sh froze the whole historical skip-set into each new tracker as `pre_existing` rows —
// which (a) made trackers grow ~unboundedly and (b) flattened away the reason+timestamp,
// so tiered release could never fire. Now nothing is frozen; each run re-derives the live
// skip-set, automatically reclaiming误杀的瞬时错误 and stale threshold rejects.
//
// PERF: when DROP_NONBLUE=1, harvested items whose `blue` flag is false are dropped HERE
// (cheap, no browser) instead of leaking into the campaign, where each one cost a full
// profile navigation just to be rejected as `not_blue` (~half of all rejects). The blue
// flag comes from the search-result DOM badge, which is reliable for verified accounts;
// VERIFIED_REQUIRED runs therefore lose nothing by trusting it. priority.json handles are
// human-picked and bypass this filter.
// Env: JOB_DIR (default cwd), NOCRYPTO (default 1; 0 KEEPs crypto handles),
//      DROP_NONBLUE (0), SKIP_GLOB (prior trackers glob; empty = local tracker only),
//      SOFT_TTL_DAYS (30).

const fs = require('fs');
const path = require('path');
const { isCryptoHandle } = require(path.join(__dirname, 'lib', 'filters.cjs'));
const { buildSkipSet, buildSkipSetFromPaths } = require(path.join(__dirname, 'lib', 'skipset.cjs'));

// Expand a shell-style glob (only `*` in the basename direction) WITHOUT a shell, so a
// crafted SKIP_GLOB can never inject a command. Node 22's fs.globSync handles `*`/`**`.
function expandGlob(pattern) {
  try { return Array.from(fs.globSync(pattern)); }
  catch { return []; }
}

const JOB = process.env.JOB_DIR || process.cwd();
const NOCRYPTO = process.env.NOCRYPTO !== '0';
const DROP_NONBLUE = process.env.DROP_NONBLUE === '1';
const SKIP_GLOB = process.env.SKIP_GLOB || '';
const SOFT_TTL_DAYS = parseInt(process.env.SOFT_TTL_DAYS || '30', 10);
const read = (f) => { try { return JSON.parse(fs.readFileSync(path.join(JOB, f), 'utf8')); } catch { return null; } };

const tracker = read('tracker.json') || { followed: [], rejected: [] };
const skipStats = {};
let skipHandles = buildSkipSet([tracker], { softTtlDays: SOFT_TTL_DAYS, stats: skipStats }); // this run's own decisions
if (SKIP_GLOB) {
  const paths = expandGlob(SKIP_GLOB);
  const fromGlob = buildSkipSetFromPaths(paths, { softTtlDays: SOFT_TTL_DAYS, stats: skipStats });
  skipHandles = skipHandles.concat(fromGlob);
  process.stderr.write(`[build-queue] skip-glob trackers=${paths.length} released=${JSON.stringify(skipStats)}\n`);
}
const skip = new Set(skipHandles);

const seen = new Set();
const queue = [];
const stats = { raw: 0, dup: 0, inSkip: 0, crypto: 0, nonblue: 0, kept: 0 };
// `trusted` skips the blue filter (priority handles have no blue flag but are pre-qualified).
const push = (h, blue, trusted) => {
  if (!h || !/^[A-Za-z0-9_]+$/.test(h)) return;
  stats.raw++;
  if (seen.has(h)) { stats.dup++; return; }
  seen.add(h);
  if (skip.has(h)) { stats.inSkip++; return; }
  if (NOCRYPTO && isCryptoHandle(h)) { stats.crypto++; return; }
  if (DROP_NONBLUE && !trusted && blue === false) { stats.nonblue++; return; }
  queue.push(h); stats.kept++;
};

// 1) priority handles first (e.g. qualified comment-target OPs) — never blue-filtered
const pri = read('priority.json');
if (Array.isArray(pri)) for (const h of pri) push(h, undefined, true);

// 2) all harvested cand-*.json, name-sorted (name your best sources to sort first)
const files = fs.readdirSync(JOB).filter((f) => /^cand-.*\.json$/.test(f)).sort();
for (const f of files) { const d = read(f); if (d && d.items) for (const it of d.items) push(it.handle, it.blue, false); }

fs.writeFileSync(path.join(JOB, 'queue.json'), JSON.stringify(queue));
process.stderr.write(`[build-queue] files=${files.length} crypto=${NOCRYPTO ? 'filtered' : 'KEPT'} nonblue=${DROP_NONBLUE ? 'dropped' : 'kept'} ${JSON.stringify(stats)}\n`);
process.stderr.write(`[build-queue] queue size: ${queue.length}\n`);
console.log(queue.length);

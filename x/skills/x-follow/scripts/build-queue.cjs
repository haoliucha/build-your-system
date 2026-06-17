#!/usr/bin/env node
// build-queue.cjs — merge harvested candidates into queue.json, filtered & deduped.
//
// Inputs (in JOB dir, default = cwd):
//   priority.json        optional [handle,...] placed first
//   cand-*.json          harvest outputs { items:[{handle,...}] } — globbed, name-sorted
//   tracker.json         { followed:[{handle}], rejected:[{h}] } — the skip-set source
// Output: queue.json = [handle, ...]
//
// FIX vs original: skip set = followed ∪ rejected (the old build-queue skipped only
// rejected, so already-followed accounts leaked back into the queue).
// Skip is REASON-AWARE: REEVAL_REASONS (comma list of reason-prefixes) are NOT skipped, so
// config-bound rejects (e.g. reject:blacklist when crypto is re-allowed, reject:fers> when the
// follower cap is raised) re-enter the pool. Transient errors are always re-evaluated.
// Env: JOB_DIR (default cwd), NOCRYPTO (default 1; set 0 to KEEP crypto handles),
//      REEVAL_REASONS (default "" = legacy skip-all-rejected, minus transient).

const fs = require('fs');
const path = require('path');
const { isCryptoHandle } = require(path.join(__dirname, 'lib', 'filters.cjs'));
const { buildSkipSet } = require(path.join(__dirname, 'lib', 'skipset.cjs'));

const JOB = process.env.JOB_DIR || process.cwd();
const NOCRYPTO = process.env.NOCRYPTO !== '0';
const REEVAL = (process.env.REEVAL_REASONS || '').split(',').map((s) => s.trim()).filter(Boolean);
const read = (f) => { try { return JSON.parse(fs.readFileSync(path.join(JOB, f), 'utf8')); } catch { return null; } };

const tracker = read('tracker.json') || { followed: [], rejected: [] };
const skip = new Set(buildSkipSet([tracker], { reeval: REEVAL })); // followed ∪ (rejected still binding)

const seen = new Set();
const queue = [];
const stats = { raw: 0, dup: 0, inSkip: 0, crypto: 0, kept: 0 };
const push = (h) => {
  if (!h || !/^[A-Za-z0-9_]+$/.test(h)) return;
  stats.raw++;
  if (seen.has(h)) { stats.dup++; return; }
  seen.add(h);
  if (skip.has(h)) { stats.inSkip++; return; }
  if (NOCRYPTO && isCryptoHandle(h)) { stats.crypto++; return; }
  queue.push(h); stats.kept++;
};

// 1) priority handles first (e.g. qualified comment-target OPs)
const pri = read('priority.json');
if (Array.isArray(pri)) for (const h of pri) push(h);

// 2) all harvested cand-*.json, name-sorted (name your best sources to sort first)
const files = fs.readdirSync(JOB).filter((f) => /^cand-.*\.json$/.test(f)).sort();
for (const f of files) { const d = read(f); if (d && d.items) for (const it of d.items) push(it.handle); }

fs.writeFileSync(path.join(JOB, 'queue.json'), JSON.stringify(queue));
process.stderr.write(`[build-queue] files=${files.length} crypto=${NOCRYPTO ? 'filtered' : 'KEPT'} reeval=[${REEVAL.join(',')}] ${JSON.stringify(stats)}\n`);
process.stderr.write(`[build-queue] queue size: ${queue.length}\n`);
console.log(queue.length);

#!/usr/bin/env node
// clean-snapshots.cjs — retro-clean contaminated daily snapshots by removing rows
// whose handle appears in an authoritative followers list (they follow me, so they
// were false-positive "non-reciprocal" flags — see the 2026-07-02 postmortem: the
// old snapshot extractor flagged 72% of mutuals via ghost sub-div rows).
//
// Safety:
//   -每份文件先备份到 snapshots-bad/<date>.jsonl,备份已存在则 REFUSE(除非 --force)
//     —— 防止重跑时用已清洗文件覆盖污染原件。
//   - --dates 必填且显式列出(无默认全量),干净的历史文件不会被误碰。
//   - --dry-run 只打印统计,不写任何文件。
//
// Usage:
//   node clean-snapshots.cjs --followers-file=<json> --dates=YYYY-MM-DD[,YYYY-MM-DD...]
//                            [--dry-run] [--force]
// Env: XU_DATA_DIR (default ~/.config/x-unfollow-data)
// followers-file: JSON with { handles: [...] } or a bare array of handles.
// Output: one JSON summary line per file { file, before, after, removed, backup }.

const fs = require('fs');
const path = require('path');
const os = require('os');
const H = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

// PURE: keep only rows whose normalized handle is NOT in followersSet.
// rows keep their original casing/serialization upstream; this only decides membership.
function cleanSnapshotRows(rows, followersSet) {
  return (rows || []).filter((r) => !followersSet.has(H.normalizeHandle(r && r.handle)));
}

function parseArgs(argv) {
  const out = { followersFile: null, dates: [], dryRun: false, force: false };
  for (const a of argv) {
    if (a.startsWith('--followers-file=')) out.followersFile = a.split('=').slice(1).join('=');
    else if (a.startsWith('--dates=')) out.dates = a.split('=')[1].split(',').map((s) => s.trim()).filter(Boolean);
    else if (a === '--dry-run') out.dryRun = true;
    else if (a === '--force') out.force = true;
    else throw new Error(`Unknown arg: ${a}`);
  }
  if (!out.followersFile) throw new Error('--followers-file=<json> is required');
  if (!out.dates.length) throw new Error('--dates=YYYY-MM-DD[,..] is required (explicit; no default-all)');
  for (const d of out.dates) if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) throw new Error(`Bad date: ${d}`);
  return out;
}

function loadFollowersSet(file) {
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  const arr = Array.isArray(parsed) ? parsed : parsed.handles;
  if (!Array.isArray(arr) || !arr.length) throw new Error(`No handles in ${file} (expect {handles:[...]} or a bare array)`);
  return new Set(arr.map((h) => H.normalizeHandle(h)).filter(Boolean));
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const dataDir = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
  const snapDir = path.join(dataDir, 'snapshots');
  const badDir = path.join(dataDir, 'snapshots-bad');
  const followers = loadFollowersSet(args.followersFile);
  process.stderr.write(`[clean] followers set: ${followers.size} handles from ${args.followersFile}\n`);

  let hadError = false;
  for (const date of args.dates) {
    const file = path.join(snapDir, `${date}.jsonl`);
    if (!fs.existsSync(file)) {
      process.stderr.write(`[clean] SKIP ${date}: ${file} does not exist\n`);
      hadError = true;
      continue;
    }
    const backup = path.join(badDir, `${date}.jsonl`);
    if (fs.existsSync(backup) && !args.force) {
      process.stderr.write(`[clean] REFUSE ${date}: backup already exists at ${backup} (re-run would back up an already-cleaned file over the contaminated original; use --force to override)\n`);
      hadError = true;
      continue;
    }

    const rawLines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
    let malformed = 0;
    const parsedRows = [];
    for (const line of rawLines) {
      try { parsedRows.push({ line, row: JSON.parse(line) }); } catch { malformed++; }
    }
    const keptRows = new Set(cleanSnapshotRows(parsedRows.map((p) => p.row), followers));
    const keptLines = parsedRows.filter((p) => keptRows.has(p.row)).map((p) => p.line);
    if (malformed) process.stderr.write(`[clean] WARN ${date}: dropped ${malformed} malformed line(s)\n`);

    const summary = { file, before: rawLines.length, after: keptLines.length, removed: rawLines.length - keptLines.length, backup: args.dryRun ? null : backup };
    if (!args.dryRun) {
      fs.mkdirSync(badDir, { recursive: true });
      fs.copyFileSync(file, backup);
      fs.writeFileSync(file, keptLines.join('\n') + (keptLines.length ? '\n' : ''), 'utf8');
    }
    console.log(JSON.stringify({ ...(args.dryRun ? { dryRun: true } : {}), ...summary }));
  }
  process.exit(hadError ? 1 : 0);
}

module.exports = { cleanSnapshotRows };
if (require.main === module) main();

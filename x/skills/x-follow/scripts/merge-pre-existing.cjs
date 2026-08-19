#!/usr/bin/env node
// merge-pre-existing.cjs — offline snapshot -> tracker.rejected merge with atomic persistence.

const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');

function emptyTracker() {
  return { followed: [], rejected: [], stats: { profiles_checked: 0, follow_success: 0 } };
}

function validateSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || !Array.isArray(snapshot.handles)) {
    throw new Error('snapshot must be a JSON object with a handles array');
  }
}

function validateTracker(tracker) {
  if (!tracker || typeof tracker !== 'object' || Array.isArray(tracker)
    || !Array.isArray(tracker.followed) || !Array.isArray(tracker.rejected)) {
    throw new Error('tracker must be a JSON object with followed and rejected arrays');
  }
}

function handleFrom(entry) {
  if (!entry || typeof entry !== 'object') return '';
  return typeof entry.handle === 'string' ? entry.handle : (typeof entry.h === 'string' ? entry.h : '');
}

function validHandle(handle) {
  return typeof handle === 'string' && /^[A-Za-z0-9_]{1,15}$/.test(handle);
}

function mergePreExisting(snapshot, tracker = emptyTracker()) {
  validateSnapshot(snapshot);
  validateTracker(tracker);
  const rejected = [...tracker.rejected];
  const seen = new Set();
  for (const entry of [...tracker.followed, ...tracker.rejected]) {
    const handle = handleFrom(entry);
    if (validHandle(handle)) seen.add(handle.toLowerCase());
  }
  for (const handle of snapshot.handles) {
    if (!validHandle(handle)) continue;
    const key = handle.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    rejected.push({ h: handle, r: 'pre_existing_follow' });
  }
  return { ...tracker, followed: [...tracker.followed], rejected };
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeJsonAtomic(file, value) {
  const directory = path.dirname(file);
  const temporary = path.join(directory, `.${path.basename(file)}.${process.pid}.${randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
    fs.renameSync(temporary, file);
  } finally {
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

function mergePreExistingFiles(snapshotPath, trackerPath) {
  const snapshot = readJson(snapshotPath);
  let tracker;
  try { tracker = readJson(trackerPath); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    tracker = emptyTracker();
  }
  const merged = mergePreExisting(snapshot, tracker);
  writeJsonAtomic(trackerPath, merged);
  return merged;
}

if (require.main === module) {
  const [snapshotPath, trackerPath] = process.argv.slice(2);
  if (!snapshotPath || !trackerPath) {
    process.stderr.write('FATAL: usage: node merge-pre-existing.cjs <snapshot.json> <tracker.json>\n');
    process.exitCode = 2;
  } else {
    try {
      const merged = mergePreExistingFiles(snapshotPath, trackerPath);
      process.stdout.write(`pre-existing following merged: ${merged.rejected.length} total rejects\n`);
    } catch (error) {
      process.stderr.write(`FATAL: ${error.message}\n`);
      process.exitCode = 2;
    }
  }
}

module.exports = { emptyTracker, mergePreExisting, mergePreExistingFiles, writeJsonAtomic };

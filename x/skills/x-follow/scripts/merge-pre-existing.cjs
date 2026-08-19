#!/usr/bin/env node
// merge-pre-existing.cjs — strict offline snapshot -> tracker merge, with optional two-file publication.

const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');

function emptyTracker() {
  return { followed: [], rejected: [], stats: { profiles_checked: 0, follow_success: 0 } };
}

function validateSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) throw new Error('snapshot must be a JSON object');
  if (Object.prototype.hasOwnProperty.call(snapshot, 'error')) throw new Error(`snapshot reported ${snapshot.error}`);
  if (!Number.isInteger(snapshot.count) || snapshot.count < 0) throw new Error('snapshot count must be a non-negative integer');
  if (!Array.isArray(snapshot.handles)) throw new Error('snapshot handles must be an array');
  if (snapshot.count !== snapshot.handles.length) throw new Error('snapshot count must equal handles.length');
  if (!snapshot.handles.every(validHandle)) throw new Error('snapshot contains an invalid X handle');
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

function readJson(file, fsModule = fs) {
  return JSON.parse(fsModule.readFileSync(file, 'utf8'));
}

function writeJsonAtomic(file, value, fsModule = fs) {
  const directory = path.dirname(file);
  const temporary = path.join(directory, `.${path.basename(file)}.${process.pid}.${randomUUID()}.tmp`);
  try {
    fsModule.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
    fsModule.renameSync(temporary, file);
  } finally {
    try { fsModule.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

function mergePreExistingFiles(snapshotPath, trackerPath, fsModule = fs) {
  const snapshot = readJson(snapshotPath, fsModule);
  validateSnapshot(snapshot);
  let tracker;
  try { tracker = readJson(trackerPath, fsModule); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    tracker = emptyTracker();
  }
  const merged = mergePreExisting(snapshot, tracker);
  writeJsonAtomic(trackerPath, merged, fsModule);
  return merged;
}

function restoreSnapshot(file, previous, fsModule) {
  if (previous === null) {
    try { fsModule.unlinkSync(file); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    return;
  }
  const temporary = path.join(path.dirname(file), `.${path.basename(file)}.restore.${process.pid}.${randomUUID()}.tmp`);
  try {
    fsModule.writeFileSync(temporary, previous, { flag: 'wx', mode: 0o600 });
    fsModule.renameSync(temporary, file);
  } finally {
    try { fsModule.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

function publishSnapshotAndTracker(stagedSnapshotPath, finalSnapshotPath, trackerPath, fsModule = fs) {
  const snapshot = readJson(stagedSnapshotPath, fsModule);
  validateSnapshot(snapshot);
  let tracker;
  try { tracker = readJson(trackerPath, fsModule); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    tracker = emptyTracker();
  }
  const merged = mergePreExisting(snapshot, tracker);
  let previousSnapshot = null;
  try { previousSnapshot = fsModule.readFileSync(finalSnapshotPath); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  fsModule.renameSync(stagedSnapshotPath, finalSnapshotPath);
  try {
    writeJsonAtomic(trackerPath, merged, fsModule);
  } catch (error) {
    restoreSnapshot(finalSnapshotPath, previousSnapshot, fsModule);
    throw error;
  }
  return merged;
}

if (require.main === module) {
  const [snapshotPath, trackerPath, finalSnapshotPath] = process.argv.slice(2);
  if (!snapshotPath || !trackerPath) {
    process.stderr.write('FATAL: usage: node merge-pre-existing.cjs <snapshot.json> <tracker.json> [final-snapshot.json]\n');
    process.exitCode = 2;
  } else {
    try {
      const merged = finalSnapshotPath
        ? publishSnapshotAndTracker(snapshotPath, finalSnapshotPath, trackerPath)
        : mergePreExistingFiles(snapshotPath, trackerPath);
      process.stdout.write(`pre-existing following merged: ${merged.rejected.length} total rejects\n`);
    } catch (error) {
      process.stderr.write(`FATAL: ${error.message}\n`);
      process.exitCode = 2;
    }
  }
}

module.exports = { emptyTracker, mergePreExisting, mergePreExistingFiles, publishSnapshotAndTracker, writeJsonAtomic };

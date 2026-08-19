#!/usr/bin/env node
// run-lock.cjs — filesystem lock for X-facing x-follow runs; safe to test offline.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function readLock(lockPath) {
  try { return JSON.parse(fs.readFileSync(lockPath, 'utf8')); } catch { return null; }
}

function isPidActive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; }
  catch (error) { return error.code === 'EPERM'; }
}

function acquireLock(lockPath, details = {}) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const lock = {
    pid: Number.isInteger(details.pid) ? details.pid : process.pid,
    token: details.token || crypto.randomUUID(),
    jobDir: details.jobDir || '',
    startedAt: details.startedAt || new Date().toISOString(),
  };
  let recovered = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const fd = fs.openSync(lockPath, 'wx', 0o600);
      fs.writeFileSync(fd, JSON.stringify(lock) + '\n');
      fs.closeSync(fd);
      return { ...lock, recovered };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const existing = readLock(lockPath);
      if (existing && isPidActive(existing.pid)) {
        throw new Error(`network run lock already active (pid=${existing.pid}, jobDir=${existing.jobDir || 'unknown'})`);
      }
      recovered = existing || { malformed: true };
      try { fs.unlinkSync(lockPath); } catch (unlinkError) { if (unlinkError.code !== 'ENOENT') throw unlinkError; }
    }
  }
  throw new Error('could not acquire network run lock');
}

function releaseLock(lockPath, token) {
  const existing = readLock(lockPath);
  if (!existing || existing.token !== token) return false;
  fs.unlinkSync(lockPath);
  return true;
}

if (require.main === module) {
  const [command, lockPath, value, pidArg] = process.argv.slice(2);
  try {
    if (command === 'acquire') {
      const lock = acquireLock(lockPath, { jobDir: value, pid: Number(pidArg) });
      process.stdout.write(lock.token + '\n');
    } else if (command === 'release') {
      process.stdout.write(releaseLock(lockPath, value) ? 'released\n' : 'not-owner\n');
    } else {
      throw new Error('usage: run-lock.cjs acquire <lock-path> <job-dir> <pid> | release <lock-path> <token>');
    }
  } catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { acquireLock, releaseLock, readLock, isPidActive };

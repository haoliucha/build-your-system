'use strict';

const fs = require('fs');
const path = require('path');
const R = require('./relationship-state.cjs');

function ensureLayout(dataDir) {
  fs.mkdirSync(path.join(dataDir, 'current'), { recursive: true });
  fs.mkdirSync(path.join(dataDir, 'reports'), { recursive: true });
  fs.mkdirSync(path.join(dataDir, '.staging'), { recursive: true });
}
function readJson(file) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; } }
function readJsonl(file) {
  try { return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line)); }
  catch { return null; }
}
function jsonl(rows) { return rows.map((row) => JSON.stringify(row)).join('\n') + (rows.length ? '\n' : ''); }
function atomicWrite(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(temp, content, 'utf8');
  fs.renameSync(temp, file);
}
function csv(rows) {
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const value = (v) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return `${keys.join(',')}\n${rows.map((row) => keys.map((key) => value(row[key])).join(',')).join('\n')}${rows.length ? '\n' : ''}`;
}
function writeReport(dataDir, base, payload) {
  atomicWrite(path.join(dataDir, 'reports', `${base}.json`), `${JSON.stringify(payload, null, 2)}\n`);
  atomicWrite(path.join(dataDir, 'reports', `${base}.csv`), csv(payload.rows || []));
}

function promoteList({ dataDir, listType, rows, meta, observedDate }) {
  if (!['following', 'followers'].includes(listType)) throw new Error('invalid list type');
  if (!Array.isArray(rows) || !meta || meta.complete === false) throw new Error('scan is not promotable');
  ensureLayout(dataDir);
  const current = path.join(dataDir, 'current');
  const oldRows = readJsonl(path.join(current, `${listType}.jsonl`));
  const otherType = listType === 'following' ? 'followers' : 'following';
  const otherRows = readJsonl(path.join(current, `${otherType}.jsonl`));
  const oldRelationships = readJsonl(path.join(current, 'relationships.jsonl')) || [];
  const otherMeta = readJson(path.join(current, `${otherType}.meta.json`));
  const followingRows = listType === 'following' ? rows : otherRows;
  const followersRows = listType === 'followers' ? rows : otherRows;
  const followingMeta = listType === 'following' ? meta : otherMeta;
  const followersMeta = listType === 'followers' ? meta : otherMeta;
  const relationship = R.buildRelationships({ previous: oldRelationships, followingRows, followersRows, followingMeta, followersMeta, observedDate, followingRefreshed: listType === 'following' });
  const scanDate = observedDate || meta.observedDate || String(meta.generatedAt || '').slice(0, 10);
  const change = listType === 'followers'
    ? R.diffFollowers({ previousRows: oldRows, currentRows: rows, followingRows: followingRows || [], scanMeta: meta })
    : R.diffFollowing({ previousRows: oldRows, currentRows: rows, scanMeta: meta });
  const changeBase = listType === 'followers' ? 'latest-follower-changes' : 'latest-relationship-changes';
  const changePayload = { generatedAt: new Date().toISOString(), observedDate: scanDate, status: change.status, comparable: change.comparable, rows: change.rows };
  const nonRecipRows = relationship.rows.filter((row) => row.inFollowing && row.followsMeBadge === false && !row.evidenceConflict);

  // Validation and report construction above are side-effect free. Promotion begins here;
  // every file replacement itself is atomic and no dated generation remains afterward.
  atomicWrite(path.join(current, `${listType}.jsonl`), jsonl(rows));
  atomicWrite(path.join(current, `${listType}.meta.json`), `${JSON.stringify({ ...meta, observedDate: scanDate, count: rows.length }, null, 2)}\n`);
  atomicWrite(path.join(current, 'relationships.jsonl'), jsonl(relationship.rows));
  atomicWrite(path.join(current, 'relationships.meta.json'), `${JSON.stringify(relationship.meta, null, 2)}\n`);
  writeReport(dataDir, changeBase, changePayload);
  writeReport(dataDir, 'latest-non-recip', { generatedAt: new Date().toISOString(), observedDate: scanDate, rows: nonRecipRows });
  return { relationship, change };
}

function promoteBoth({ dataDir, followingRows, followingMeta, followersRows, followersMeta, observedDate }) {
  if (!Array.isArray(followingRows) || !Array.isArray(followersRows)
      || !followingMeta || !followersMeta || followingMeta.complete === false || followersMeta.complete === false) {
    throw new Error('complete staged scans are required');
  }
  if (!followingMeta.runId || followingMeta.runId !== followersMeta.runId) throw new Error('staged scans must share one runId');
  ensureLayout(dataDir);
  const current = path.join(dataDir, 'current');
  const oldFollowing = readJsonl(path.join(current, 'following.jsonl'));
  const oldFollowers = readJsonl(path.join(current, 'followers.jsonl'));
  const oldRelationships = readJsonl(path.join(current, 'relationships.jsonl')) || [];
  const relationship = R.buildRelationships({ previous: oldRelationships, followingRows, followersRows, followingMeta, followersMeta, observedDate, followingRefreshed: true });
  const followingDiff = R.diffFollowing({ previousRows: oldFollowing, currentRows: followingRows, scanMeta: followingMeta });
  const followerDiff = R.diffFollowers({ previousRows: oldFollowers, currentRows: followersRows, followingRows, scanMeta: followersMeta });
  const nonRecipRows = relationship.rows.filter((row) => row.inFollowing && row.followsMeBadge === false && !row.evidenceConflict);
  atomicWrite(path.join(current, 'following.jsonl'), jsonl(followingRows));
  atomicWrite(path.join(current, 'following.meta.json'), `${JSON.stringify({ ...followingMeta, observedDate, count: followingRows.length }, null, 2)}\n`);
  atomicWrite(path.join(current, 'followers.jsonl'), jsonl(followersRows));
  atomicWrite(path.join(current, 'followers.meta.json'), `${JSON.stringify({ ...followersMeta, observedDate, count: followersRows.length }, null, 2)}\n`);
  atomicWrite(path.join(current, 'relationships.jsonl'), jsonl(relationship.rows));
  atomicWrite(path.join(current, 'relationships.meta.json'), `${JSON.stringify(relationship.meta, null, 2)}\n`);
  writeReport(dataDir, 'latest-follower-changes', { generatedAt: new Date().toISOString(), observedDate, status: followerDiff.status, comparable: followerDiff.comparable, rows: followerDiff.rows });
  writeReport(dataDir, 'latest-relationship-changes', { generatedAt: new Date().toISOString(), observedDate, status: followingDiff.status, comparable: followingDiff.comparable, rows: followingDiff.rows });
  writeReport(dataDir, 'latest-non-recip', { generatedAt: new Date().toISOString(), observedDate, rows: nonRecipRows });
  return { relationship, followerDiff, followingDiff };
}

module.exports = { ensureLayout, readJsonl, atomicWrite, promoteList, promoteBoth };

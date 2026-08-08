'use strict';

const fs = require('fs');
const path = require('path');

function normalizeHandle(value) {
  return String(value || '').trim().replace(/^@/, '').toLowerCase();
}

function loadResults(file) {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Array.isArray(parsed.results) ? parsed.results : [];
  } catch {
    return [];
  }
}

function mergeResultsByHandle(existing, incoming) {
  const out = [];
  const index = new Map();
  for (const row of [...(existing || []), ...(incoming || [])]) {
    const key = normalizeHandle(row && row.handle);
    if (!key) continue;
    if (index.has(key)) out[index.get(key)] = row;
    else { index.set(key, out.length); out.push(row); }
  }
  return out;
}

function writeActionLog(file, date, results) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.tmp`);
  const body = { date, generatedAt: new Date().toISOString(), results };
  fs.writeFileSync(temp, `${JSON.stringify(body, null, 2)}\n`, 'utf8');
  fs.renameSync(temp, file);
  return body;
}

module.exports = { normalizeHandle, loadResults, mergeResultsByHandle, writeActionLog };

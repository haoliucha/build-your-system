#!/usr/bin/env node
// smoke-test.cjs — local-only pre-run health check for the x-unfollow skill.
// It intentionally makes ZERO X requests; snapshot.cjs owns live list checks.
// Usage: PROFILE_DIR=~/.config/playwright-chrome-profile-campaign MY_HANDLE=you node smoke-test.cjs

const path = require('path');
const fs = require('fs');
const os = require('os');

const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const MY_HANDLE = (process.env.MY_HANDLE || '').replace(/^@/, '').trim();

const G = '\x1b[32m', R = '\x1b[31m', Y = '\x1b[33m', X = '\x1b[0m';
const ok = (m) => console.log(`${G}✅ PASS${X} ${m}`);
const fail = (m) => console.log(`${R}❌ FAIL${X} ${m}`);
const info = (m) => console.log(`${Y}ℹ️  ${X} ${m}`);

async function main() {
  console.log(`\n=== X-UNFOLLOW SMOKE TEST ===`);
  console.log(`PROFILE_DIR: ${PROFILE_DIR}`);
  console.log(`MY_HANDLE: ${MY_HANDLE || '(not set)'}\n`);

  if (!fs.existsSync(PROFILE_DIR)) {
    fail(`Profile dir does not exist: ${PROFILE_DIR}`);
    console.log(`\nFix: cp -R ~/.config/playwright-chrome-profile ${PROFILE_DIR} && rm -f ${PROFILE_DIR}/Singleton*`);
    process.exit(3);
  }
  ok(`Profile dir exists`);
  if (fs.existsSync(path.join(PROFILE_DIR, 'SingletonLock'))) {
    fail(`SingletonLock present`);
    console.log(`\nFix: rm -f ${PROFILE_DIR}/Singleton*`);
    process.exit(3);
  }
  ok(`No SingletonLock`);

  try {
    require.resolve('playwright');
    ok('Playwright module resolves');
  } catch (e) {
    fail(`Playwright module unavailable: ${e.message}`);
    process.exit(1);
  }

  info('Local-only smoke test made 0 X requests; live login/DOM checks occur after the exclusive run lock is claimed.');
  console.log(`${G}=== ALL GREEN — local preflight passed ===${X}`);
}

main().catch((e) => { console.error('FATAL', e); process.exit(99); });

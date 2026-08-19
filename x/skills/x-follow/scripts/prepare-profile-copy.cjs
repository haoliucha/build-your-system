#!/usr/bin/env node
// prepare-profile-copy.cjs — offline, fail-closed creation of an independent profile copy.

const fs = require('fs');
const path = require('path');
const { assertIndependentProfile } = require('./lib/runtime-state.cjs');

function prepareProfileCopy(env = process.env, fsModule = fs) {
  // This canonical overlap gate is deliberately first: no destination may be created and no
  // source/target content may be changed until the existing profile policy has accepted both.
  const policy = assertIndependentProfile(env);
  let sourceStat;
  try {
    sourceStat = fsModule.statSync(policy.sourceCanonicalPath);
  } catch {
    throw new Error('SOURCE_PROFILE_DIR must be an existing directory');
  }
  if (!sourceStat.isDirectory()) throw new Error('SOURCE_PROFILE_DIR must be an existing directory');
  if (fsModule.existsSync(policy.profileDir)) throw new Error('PROFILE_DIR already exists; refusing to overwrite');
  const target = path.resolve(policy.profileDir);
  const parent = path.dirname(target);
  fsModule.mkdirSync(parent, { recursive: true });
  const staging = fsModule.mkdtempSync(path.join(parent, `.${path.basename(target)}.x-follow-stage-`));
  try {
    fsModule.cpSync(policy.sourceCanonicalPath, staging, {
      recursive: true,
      force: false,
      errorOnExist: true,
    });
    assertIndependentProfile({ ...env, SOURCE_PROFILE_DIR: policy.sourceCanonicalPath, PROFILE_DIR: staging });
    if (fsModule.existsSync(target)) throw new Error('PROFILE_DIR appeared during copy; refusing to overwrite');
    fsModule.renameSync(staging, target);
    return assertIndependentProfile({ ...env, PROFILE_DIR: target });
  } finally {
    try { fsModule.rmSync(staging, { recursive: true, force: true }); } catch {}
  }
}

if (require.main === module) {
  try {
    const policy = prepareProfileCopy(process.env);
    process.stdout.write(`profile copy prepared: ${policy.profileDir}\n`);
  } catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { prepareProfileCopy };

#!/usr/bin/env node
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const PLUGIN_NAME = 'x';
const ACCOUNT_SKILLS = ['x-follow', 'x-unfollow'];

class ProvenanceError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'ProvenanceError';
    this.code = code;
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function realpathExisting(file) {
  return fs.realpathSync(file);
}

function pluginManifests(pluginRoot) {
  const claudePath = path.join(pluginRoot, '.claude-plugin', 'plugin.json');
  const codexPath = path.join(pluginRoot, '.codex-plugin', 'plugin.json');
  if (!fs.existsSync(claudePath) || !fs.existsSync(codexPath)) {
    throw new ProvenanceError(
      'LEGACY_STANDALONE_INSTALL',
      `x account skills must run from the x plugin. Missing dual-host manifests above ${pluginRoot}. ` +
      'Use $x:x-unfollow in Codex or /x:x-unfollow in Claude Code; do not run ~/.agents/skills/x-unfollow.',
    );
  }
  const claude = readJson(claudePath);
  const codex = readJson(codexPath);
  if (claude.name !== PLUGIN_NAME || codex.name !== PLUGIN_NAME) {
    throw new ProvenanceError('PLUGIN_IDENTITY_MISMATCH', 'dual-host manifests must both identify plugin x');
  }
  if (!claude.version || claude.version !== codex.version) {
    throw new ProvenanceError(
      'PLUGIN_VERSION_MISMATCH',
      `Claude/Codex manifest versions differ: ${claude.version || 'missing'} vs ${codex.version || 'missing'}`,
    );
  }
  return { claude, codex, version: codex.version };
}

function filesUnder(root) {
  const rows = [];
  function visit(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const absolute = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) {
        throw new ProvenanceError('PLUGIN_SYMLINK_UNSUPPORTED', `plugin content contains a symlink: ${absolute}`);
      }
      if (entry.isDirectory()) visit(absolute);
      else if (entry.isFile()) rows.push(absolute);
    }
  }
  visit(root);
  return rows;
}

function fingerprintTree(root) {
  const canonical = realpathExisting(root);
  const hash = crypto.createHash('sha256');
  for (const file of filesUnder(canonical)) {
    const relative = path.relative(canonical, file).split(path.sep).join('/');
    hash.update(relative);
    hash.update('\0');
    hash.update(fs.readFileSync(file));
    hash.update('\0');
  }
  return hash.digest('hex');
}

function pluginFingerprint(pluginRoot) {
  const root = realpathExisting(pluginRoot);
  const hash = crypto.createHash('sha256');
  for (const relative of [
    '.claude-plugin/plugin.json',
    '.codex-plugin/plugin.json',
    ...ACCOUNT_SKILLS.map((name) => `skills/${name}`),
  ]) {
    const absolute = path.join(root, relative);
    if (!fs.existsSync(absolute)) {
      throw new ProvenanceError('PLUGIN_CONTENT_MISSING', `required plugin content missing: ${absolute}`);
    }
    hash.update(relative);
    hash.update('\0');
    if (fs.statSync(absolute).isDirectory()) hash.update(fingerprintTree(absolute));
    else hash.update(fs.readFileSync(absolute));
    hash.update('\0');
  }
  return hash.digest('hex');
}

function inferHost(pluginRoot) {
  const normalized = pluginRoot.split(path.sep).join('/');
  if (normalized.includes('/.codex/plugins/cache/')) return 'codex';
  if (normalized.includes('/.claude/plugins/cache/')) return 'claude';
  try {
    execFileSync('git', ['-C', path.dirname(pluginRoot), 'rev-parse', '--show-toplevel'], { stdio: 'ignore' });
    return 'source';
  } catch {
    return 'plugin';
  }
}

function gitShaForPluginRoot(pluginRoot) {
  try {
    return execFileSync('git', ['-C', path.dirname(pluginRoot), 'rev-parse', 'HEAD'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return null;
  }
}

function runtimeProvenance({ skillDir, skill }) {
  if (!ACCOUNT_SKILLS.includes(skill)) {
    throw new ProvenanceError('UNKNOWN_SKILL', `unsupported account skill: ${skill || 'missing'}`);
  }
  const canonicalSkill = realpathExisting(skillDir);
  const pluginRoot = path.resolve(canonicalSkill, '..', '..');
  const manifests = pluginManifests(pluginRoot);
  const expectedSkill = realpathExisting(path.join(pluginRoot, 'skills', skill));
  if (canonicalSkill !== expectedSkill) {
    throw new ProvenanceError(
      'PLUGIN_LAYOUT_MISMATCH',
      `skill path is not the canonical ${PLUGIN_NAME}/skills/${skill} directory`,
    );
  }
  return {
    plugin: PLUGIN_NAME,
    version: manifests.version,
    skill,
    host: inferHost(pluginRoot),
    skillDir: canonicalSkill,
    pluginRoot: realpathExisting(pluginRoot),
    skillSha256: fingerprintTree(canonicalSkill),
    gitSha: gitShaForPluginRoot(pluginRoot),
  };
}

function parseArgs(argv) {
  const result = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) {
      result._.push(token);
      continue;
    }
    const [rawKey, inline] = token.slice(2).split('=', 2);
    if (inline !== undefined) result[rawKey] = inline;
    else if (argv[index + 1] && !argv[index + 1].startsWith('--')) result[rawKey] = argv[++index];
    else result[rawKey] = true;
  }
  return result;
}

function codexPayload(args, env) {
  const fixture = args['codex-list'] || env.X_PLUGIN_CODEX_LIST_PATH;
  if (fixture) return readJson(fixture);
  return JSON.parse(execFileSync('codex', ['plugin', 'list', '--json'], { encoding: 'utf8' }));
}

function claudePayload(args, env) {
  const fixture = args['claude-list'] || env.X_PLUGIN_CLAUDE_LIST_PATH;
  if (fixture) return readJson(fixture);
  return JSON.parse(execFileSync('claude', ['plugin', 'list', '--json'], { encoding: 'utf8' }));
}

function doctor(options = {}) {
  const env = options.env || process.env;
  const home = path.resolve(options.home || env.X_PLUGIN_HOME || os.homedir());
  const pluginRoot = realpathExisting(options.pluginRoot || path.resolve(__dirname, '..'));
  const manifests = pluginManifests(pluginRoot);
  const expectedVersion = manifests.version;
  const expectedFingerprint = pluginFingerprint(pluginRoot);
  const checks = [];
  const add = (name, ok, detail) => checks.push({ name, ok, detail });

  const legacy = path.resolve(options.legacySkill || env.X_PLUGIN_LEGACY_SKILL_DIR || path.join(home, '.agents', 'skills', 'x-unfollow'));
  add('legacy-standalone', !fs.existsSync(legacy), fs.existsSync(legacy) ? `active legacy path exists: ${legacy}` : 'absent');

  if (!options.skipHosts) {
    try {
      const payload = options.codexList || codexPayload(options.args || {}, env);
      const active = (payload.installed || []).filter((item) => item.name === PLUGIN_NAME && item.installed && item.enabled);
      add('codex-single-active', active.length === 1, `active=${active.length}`);
      if (active.length === 1) {
        const item = active[0];
        add('codex-version', item.version === expectedVersion, `${item.version || 'missing'} expected=${expectedVersion}`);
        const cacheRoot = path.resolve(options.codexCacheRoot || env.X_PLUGIN_CODEX_CACHE_ROOT || path.join(home, '.codex', 'plugins', 'cache'));
        const cache = path.join(cacheRoot, item.marketplaceName, PLUGIN_NAME, item.version);
        const matches = fs.existsSync(cache) && pluginFingerprint(cache) === expectedFingerprint;
        add('codex-fingerprint', matches, fs.existsSync(cache) ? cache : `missing ${cache}`);
      }
    } catch (error) {
      add('codex-state', false, error.message);
    }

    try {
      const entries = Array.isArray(options.claudeList) ? options.claudeList : claudePayload(options.args || {}, env);
      const active = entries.filter((item) => /^x@/.test(String(item.id || '')) && item.enabled === true);
      add(
        'claude-single-active',
        active.length === 1,
        `active=${active.length}${active.length ? ` ids=${active.map((item) => `${item.id}:${item.scope || 'unknown'}`).join(',')}` : ''}`,
      );
      if (active.length === 1) {
        const item = active[0];
        add('claude-version', item.version === expectedVersion, `${item.version || 'missing'} expected=${expectedVersion}`);
        const matches = fs.existsSync(item.installPath) && pluginFingerprint(item.installPath) === expectedFingerprint;
        add('claude-fingerprint', matches, fs.existsSync(item.installPath) ? item.installPath : `missing ${item.installPath}`);
      }
    } catch (error) {
      add('claude-state', false, error.message);
    }
  }

  if (options.release) {
    try {
      const repoRoot = execFileSync('git', ['-C', path.dirname(pluginRoot), 'rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
      const dirty = execFileSync('git', ['-C', repoRoot, 'status', '--porcelain'], { encoding: 'utf8' }).trim();
      add('release-worktree-clean', dirty === '', dirty || 'clean');
      add('release-git-sha', true, execFileSync('git', ['-C', repoRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim());
    } catch (error) {
      add('release-git-state', false, error.message);
    }
  }

  return {
    ok: checks.every((item) => item.ok),
    plugin: PLUGIN_NAME,
    version: expectedVersion,
    pluginRoot,
    fingerprint: expectedFingerprint,
    checks,
  };
}

function printRuntime(info) {
  const fields = [
    `plugin=${info.plugin}`,
    `version=${info.version}`,
    `skill=${info.skill}`,
    `host=${info.host}`,
    `skill_dir=${info.skillDir}`,
    `fingerprint=${info.skillSha256.slice(0, 16)}`,
    `git=${info.gitSha ? info.gitSha.slice(0, 12) : 'unavailable'}`,
  ];
  process.stdout.write(`[x-plugin] ${fields.join(' ')}\n`);
}

function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const command = args._[0];
  if (command === 'runtime') {
    const skillDir = args['skill-dir'];
    const skill = args.skill;
    if (!skillDir || !skill) throw new ProvenanceError('USAGE', 'runtime requires --skill-dir and --skill');
    const info = runtimeProvenance({ skillDir, skill });
    if (args.json) process.stdout.write(`${JSON.stringify(info, null, 2)}\n`);
    else printRuntime(info);
    return 0;
  }
  if (command === 'doctor') {
    const report = doctor({
      args,
      pluginRoot: args['plugin-root'],
      home: args.home,
      legacySkill: args['legacy-skill'],
      codexCacheRoot: args['codex-cache-root'],
      claudeList: args['claude-list'],
      skipHosts: Boolean(args['skip-hosts']),
      release: Boolean(args.release),
    });
    if (args.json) process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    else {
      process.stdout.write(`[x-plugin doctor] version=${report.version} fingerprint=${report.fingerprint.slice(0, 16)}\n`);
      for (const check of report.checks) process.stdout.write(`${check.ok ? 'PASS' : 'FAIL'} ${check.name}: ${check.detail}\n`);
    }
    return report.ok ? 0 : 1;
  }
  throw new ProvenanceError('USAGE', 'usage: plugin-provenance.cjs runtime|doctor [options]');
}

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (error) {
    const code = error instanceof ProvenanceError ? error.code : 'PROVENANCE_ERROR';
    process.stderr.write(`${code}: ${error.message}\n`);
    process.exitCode = error instanceof ProvenanceError ? 2 : 1;
  }
}

module.exports = {
  ACCOUNT_SKILLS,
  ProvenanceError,
  doctor,
  fingerprintTree,
  pluginFingerprint,
  pluginManifests,
  runtimeProvenance,
};

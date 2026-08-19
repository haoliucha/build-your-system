#!/usr/bin/env node
'use strict';

const path = require('path');
const {
  maskEmail,
  preflightBrowserConfig,
  writeAccountConfig,
} = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));

function arg(name, argv = process.argv.slice(2)) {
  const prefix = `--${name}=`;
  return (argv.find((value) => value.startsWith(prefix)) || '').slice(prefix.length);
}

function run(argv = process.argv.slice(2), env = process.env) {
  const command = argv[0] || 'check';
  if (command === 'set') {
    const email = arg('email', argv);
    if (!email) throw new Error('Usage: configure-account.cjs set --email=<chrome-account-email>');
    const candidateEnv = { ...env, X_CHROME_ACCOUNT_EMAIL: email };
    const browser = preflightBrowserConfig(candidateEnv);
    const saved = writeAccountConfig(email, env);
    process.stdout.write(`Configured ${maskEmail(saved.email)} -> ${browser.profileDirectory} (${saved.configPath})\n`);
    return;
  }
  if (command !== 'check') throw new Error('Usage: configure-account.cjs check | set --email=<chrome-account-email>');
  const browser = preflightBrowserConfig(env);
  process.stdout.write(`Chrome account ${maskEmail(browser.accountEmail)} -> ${browser.profileDirectory}; transport=cdp; profile=${browser.profileDir}\n`);
}

if (require.main === module) {
  try { run(); }
  catch (error) {
    process.stderr.write(`FATAL${error.code ? ` [${error.code}]` : ''}: ${error.message}\n`);
    process.exit(2);
  }
}

module.exports = { arg, run };

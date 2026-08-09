#!/usr/bin/env node
// Compatibility entry point. v3 stores no dated snapshots; this delegates to the
// generic staged list scanner with the following list selected.
if (!process.argv.some((arg) => arg.startsWith('--list='))) process.argv.push('--list=following');
require('./list-snapshot.cjs');

#!/usr/bin/env node
// Compatibility shim. Whole-profile copying was retired in 4.1.1: the shared CDP
// browser module now performs a selective, transactional authentication refresh.

function prepareProfileCopy() {
  throw new Error(
    'Manual whole-profile copy is retired. Configure the Chrome account with '
    + 'configure-account.cjs, then run run.sh; authentication refresh is automatic.',
  );
}

if (require.main === module) {
  try {
    prepareProfileCopy();
  } catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { prepareProfileCopy };

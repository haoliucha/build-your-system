'use strict';

function authoritativeMap({ networkStarted, networkRows, domRows }) {
  return networkStarted ? networkRows : domRows;
}

function authoritativeRows(options) {
  const source = authoritativeMap(options);
  return source instanceof Map ? [...source.values()] : [...source];
}

module.exports = { authoritativeMap, authoritativeRows };

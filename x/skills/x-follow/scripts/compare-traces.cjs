#!/usr/bin/env node
// compare-traces.cjs — compare manual Computer Use and automated DRY_RUN traces.

const fs = require('fs');
const path = require('path');

function readJsonl(filePath) {
  return fs.readFileSync(filePath, 'utf8').split(/\r?\n/).filter(Boolean).map((line, index) => {
    try { return JSON.parse(line); }
    catch (error) { throw new Error(`${filePath}:${index + 1}: ${error.message}`); }
  });
}

function summarize(events) {
  const responses = events.filter((event) => event.event === 'network_response');
  const operations = {};
  for (const event of responses) {
    const key = event.operation || event.endpointKey || event.path || 'unknown';
    const bucket = operations[key] || (operations[key] = { count: 0, statuses: {}, phases: {}, durations: [], rateHeaders: 0 });
    bucket.count++;
    bucket.statuses[event.status] = (bucket.statuses[event.status] || 0) + 1;
    bucket.phases[event.phase || 'unknown'] = (bucket.phases[event.phase || 'unknown'] || 0) + 1;
    if (Number.isFinite(event.durationMs)) bucket.durations.push(event.durationMs);
    if (event.rateLimit && Object.keys(event.rateLimit).length) bucket.rateHeaders++;
  }
  for (const bucket of Object.values(operations)) {
    bucket.meanDurationMs = bucket.durations.length
      ? Math.round(bucket.durations.reduce((sum, value) => sum + value, 0) / bucket.durations.length)
      : null;
    delete bucket.durations;
  }
  return {
    eventCount: events.length,
    profileCount: new Set(events
      .map((event) => event.correlationId)
      .filter((value) => /^(?:manual-)?profile-/.test(value || ''))).size,
    operations,
  };
}

function markdownTable(manual, automatic) {
  const keys = [...new Set([...Object.keys(manual.operations), ...Object.keys(automatic.operations)])]
    .sort((a, b) => ((automatic.operations[b]?.count || 0) - (automatic.operations[a]?.count || 0)) || a.localeCompare(b));
  const lines = [
    '| Operation | Manual | Auto | Delta | Manual phases | Auto phases | Rate headers |',
    '|---|---:|---:|---:|---|---|---|',
  ];
  for (const key of keys) {
    const m = manual.operations[key] || { count: 0, phases: {}, rateHeaders: 0 };
    const a = automatic.operations[key] || { count: 0, phases: {}, rateHeaders: 0 };
    lines.push(`| ${key} | ${m.count} | ${a.count} | ${a.count - m.count} | ${JSON.stringify(m.phases)} | ${JSON.stringify(a.phases)} | ${m.rateHeaders}/${a.rateHeaders} |`);
  }
  return lines.join('\n');
}

function main() {
  const [manualPath, autoPath, outputPath] = process.argv.slice(2);
  if (!manualPath || !autoPath || !outputPath) {
    console.error('Usage: node compare-traces.cjs <manual-flow.jsonl> <auto-flow.jsonl> <comparison.md>');
    process.exit(2);
  }
  const manual = summarize(readJsonl(manualPath));
  const automatic = summarize(readJsonl(autoPath));
  const usersManual = manual.operations.UsersByRestIds?.count || 0;
  const usersAuto = automatic.operations.UsersByRestIds?.count || 0;
  const conclusion = usersAuto > usersManual
    ? `Automatic flow emitted ${usersAuto - usersManual} more UsersByRestIds responses than manual flow.`
    : usersAuto === usersManual
      ? 'Manual and automatic flows emitted the same number of UsersByRestIds responses.'
      : `Manual flow emitted ${usersManual - usersAuto} more UsersByRestIds responses than automatic flow.`;
  const report = [
    '# Manual vs Auto X profile trace',
    '',
    `- Manual profiles: ${manual.profileCount}; events: ${manual.eventCount}`,
    `- Auto profiles: ${automatic.profileCount}; events: ${automatic.eventCount}`,
    `- UsersByRestIds: manual=${usersManual}, auto=${usersAuto}`,
    `- Conclusion: ${conclusion}`,
    '',
    markdownTable(manual, automatic),
    '',
    '## Decision boundary',
    '',
    '- Do not block or re-route an operation from this count alone; inspect its phases and required-selector validation first.',
  ].join('\n');
  fs.mkdirSync(path.dirname(outputPath), { recursive: true, mode: 0o700 });
  fs.writeFileSync(outputPath, `${report}\n`, { mode: 0o600 });
  console.log(outputPath);
}

if (require.main === module) main();
module.exports = { markdownTable, readJsonl, summarize };

#!/usr/bin/env node
// profile-counts.cjs — fetch CURRENT public follower counts from profile JSON-LD, with no
// authenticated browser state. Used to refresh threshold-relevant accounts before the
// final unfollow decision (the /following-list follower counts are unreliable).
//
// Ported from the Codex public-profile-counts.cjs. Two input modes:
//   node profile-counts.cjs handle1 @handle2 https://x.com/handle3   # explicit handles
//   node profile-counts.cjs --from-classify[=YYYY-MM-DD]            # all needs_profile_refresh rows
// With --from-classify it writes XU_DATA_DIR/reports/profile-refresh-<date>.json so a
// re-run of classify.cjs can move those rows past the refresh gate.
// Env: XU_DATA_DIR.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');

function normalizeHandle(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const withoutUrl = raw.replace(/^https?:\/\/(www\.)?(x|twitter)\.com\//i, '');
  const handle = withoutUrl.replace(/^@/, '').split(/[/?#\s]/)[0];
  return /^[A-Za-z0-9_]{1,15}$/.test(handle) ? handle : null;
}

function decodeHtml(s) {
  return String(s)
    .replace(/&quot;/g, '"').replace(/&#34;/g, '"')
    .replace(/&#x27;/g, "'").replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
}

function extractJsonLd(html) {
  const out = [];
  const re = /<script type="application\/ld\+json">([\s\S]*?)<\/script>/g;
  let m;
  while ((m = re.exec(html))) { try { out.push(JSON.parse(decodeHtml(m[1]))); } catch {} }
  return out;
}

function stat(profile, name, action) {
  const stats = profile?.mainEntity?.interactionStatistic || [];
  const item = stats.find((s) => s.name === name || String(s.interactionType || '').includes(action));
  return typeof item?.userInteractionCount === 'number' ? item.userInteractionCount : null;
}

async function fetchProfile(handle) {
  const url = `https://x.com/${handle}`;
  const res = await fetch(url, { headers: { 'user-agent': 'Mozilla/5.0', accept: 'text/html,application/xhtml+xml' } });
  const html = await res.text();
  const profile = extractJsonLd(html).find((o) => o && o['@type'] === 'ProfilePage');
  return {
    handle, status: res.status, ok: res.ok && Boolean(profile),
    name: profile?.mainEntity?.name || null,
    followers_count: stat(profile, 'Follows', 'FollowAction'),
    friends_count: stat(profile, 'Friends', 'SubscribeAction'),
    tweets_count: stat(profile, 'Tweets', 'WriteAction'),
    profile_url: url,
  };
}

function handlesFromClassify(date) {
  const file = path.join(REPORTS_DIR, `non-recip-reasons-${date}.json`);
  if (!fs.existsSync(file)) throw new Error(`Missing classify report: ${file} (run classify.cjs first)`);
  const obj = JSON.parse(fs.readFileSync(file, 'utf8'));
  return (obj.rows || []).filter((r) => r.needs_profile_refresh).map((r) => r.handle);
}

async function main() {
  const argv = process.argv.slice(2);
  const fromClassifyArg = argv.find((a) => a === '--from-classify' || a.startsWith('--from-classify='));
  let inputs, writeDate = null;
  if (fromClassifyArg) {
    writeDate = fromClassifyArg.includes('=') ? fromClassifyArg.split('=')[1] : todayInShanghai();
    inputs = handlesFromClassify(writeDate);
  } else {
    inputs = argv;
    if (inputs.length === 0 && !process.stdin.isTTY) inputs = fs.readFileSync(0, 'utf8').split(/\s+/).filter(Boolean);
  }

  const handles = [...new Set(inputs.map(normalizeHandle).filter(Boolean))];
  if (handles.length === 0) {
    if (writeDate) { process.stderr.write('[profile-counts] no accounts need refresh\n'); console.log('[]'); return; }
    console.error('Usage: profile-counts.cjs handle1 @handle2 https://x.com/handle3  |  --from-classify[=DATE]');
    process.exit(2);
  }

  const results = [];
  for (const handle of handles) {
    try { results.push(await fetchProfile(handle)); }
    catch (error) { results.push({ handle, ok: false, error: String((error && error.message) || error) }); }
    await new Promise((r) => setTimeout(r, 400));
  }

  if (writeDate) {
    if (!fs.existsSync(REPORTS_DIR)) fs.mkdirSync(REPORTS_DIR, { recursive: true });
    const file = path.join(REPORTS_DIR, `profile-refresh-${writeDate}.json`);
    fs.writeFileSync(file, JSON.stringify({ generatedAt: new Date().toISOString(), results }, null, 2) + '\n', 'utf8');
    process.stderr.write(`[profile-counts] refreshed ${results.length} -> ${file}\n`);
  }
  process.stdout.write(JSON.stringify(results, null, 2) + '\n');
}

main().catch((error) => { console.error(error); process.exit(1); });

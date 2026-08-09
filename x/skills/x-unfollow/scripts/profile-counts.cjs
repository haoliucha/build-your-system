#!/usr/bin/env node
// profile-counts.cjs — fetch CURRENT public follower counts from profile JSON-LD, with no
// authenticated browser state. Used to refresh threshold-relevant accounts before the
// final unfollow decision (the /following-list follower counts are unreliable).
//
// Ported from the Codex public-profile-counts.cjs. Two input modes:
//   node profile-counts.cjs handle1 @handle2 https://x.com/handle3   # explicit handles
//   node profile-counts.cjs --from-classify[=YYYY-MM-DD]            # all needs_profile_refresh rows
// With --from-classify it updates follower-count evidence directly in the current
// relationship rows. No dated profile history is created.
// Env: XU_DATA_DIR.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));
const Store = require(path.join(__dirname, 'lib', 'current-store.cjs'));
const { assertRunToken } = require(path.join(__dirname, 'lib', 'rate-gate.cjs'));
const {
  PROFILE_MAX_PER_RUN,
  PROFILE_WAIT_MIN_MS,
  PROFILE_WAIT_MAX_MS,
  PROFILE_RETRIES,
  boundedInt,
  jitterMs,
} = require(path.join(__dirname, 'lib', 'rate-policy.cjs'));

const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const MAX_PER_RUN = boundedInt(process.env.PROFILE_MAX_PER_RUN, PROFILE_MAX_PER_RUN, { min: 1, max: PROFILE_MAX_PER_RUN });
const WAIT_MIN = boundedInt(process.env.PROFILE_WAIT_MIN_MS, PROFILE_WAIT_MIN_MS, { min: PROFILE_WAIT_MIN_MS });
const WAIT_MAX = boundedInt(process.env.PROFILE_WAIT_MAX_MS, PROFILE_WAIT_MAX_MS, { min: WAIT_MIN });

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
  // Tolerate extra attributes on the tag. X serves the JSON-LD with a CSP nonce, e.g.
  // <script type="application/ld+json" nonce="...">. A `">"`-only match silently breaks
  // the day the site adds ANY attribute, yielding followers_count:null for every account
  // (status:200, ok:false) — which then parks all rows in ELIGIBLE_FOR_FOLLOWER_REFRESH.
  const re = /<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = re.exec(html))) { try { out.push(JSON.parse(decodeHtml(m[1]))); } catch {} }
  return out;
}

function stat(profile, name, action) {
  const stats = profile?.mainEntity?.interactionStatistic || [];
  const item = stats.find((s) => s.name === name || String(s.interactionType || '').includes(action));
  return typeof item?.userInteractionCount === 'number' ? item.userInteractionCount : null;
}

// X's logged-out profile HTML is non-deterministic: the same URL sometimes returns the
// data-rich SSR page (with the ProfilePage JSON-LD) and sometimes a thin shell, depending
// on UA heuristics + rate-limit pressure. So: send a realistic full Chrome UA (matches the
// rest of the skill's fingerprint — a bare 'Mozilla/5.0' yields the shell more often), and
// treat "no ProfilePage extracted" as a SOFT failure worth one retry with a short backoff.
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchProfileOnce(handle) {
  const url = `https://x.com/${handle}`;
  const res = await fetch(url, { headers: { 'user-agent': UA, accept: 'text/html,application/xhtml+xml' } });
  const html = await res.text();
  const profile = extractJsonLd(html).find((o) => o && o['@type'] === 'ProfilePage');
  return {
    handle, status: res.status, ok: res.ok && Boolean(profile),
    name: profile?.mainEntity?.name || null,
    followers_count: stat(profile, 'Follows', 'FollowAction'),
    friends_count: stat(profile, 'Friends', 'SubscribeAction'),
    tweets_count: stat(profile, 'Tweets', 'WriteAction'),
    profile_url: url,
    // Per-row update time so classify.cjs can reuse this count for a TTL window instead of
    // re-fetching every run. Stamped per fetch (not per file) so a merged file with rows
    // gathered at different times keeps each row's true age.
    refreshedAt: new Date().toISOString(),
  };
}

async function fetchProfile(handle, retries = PROFILE_RETRIES) {
  let last;
  for (let attempt = 0; attempt <= retries; attempt++) {
    // Retry BOTH soft-failure classes: a thin-shell 200 (response, no ProfilePage) returns
    // {ok:false}; a transport reset (X drops the TLS connection under rate pressure) throws
    // ECONNRESET. Either way, back off and try again — don't record a transient as permanent.
    try {
      last = await fetchProfileOnce(handle);
      if (last.ok) return last;
    } catch (error) {
      last = { handle, ok: false, error: String((error && error.message) || error), profile_url: `https://x.com/${handle}`, refreshedAt: new Date().toISOString() };
    }
    if (attempt < retries) await sleep(WAIT_MIN);
  }
  return last;
}

function handlesFromClassify() {
  const file = path.join(REPORTS_DIR, 'latest-non-recip.json');
  if (!fs.existsSync(file)) throw new Error(`Missing classify report: ${file} (run classify.cjs first)`);
  const obj = JSON.parse(fs.readFileSync(file, 'utf8'));
  return (obj.rows || []).filter((r) => r.needs_profile_refresh).map((r) => r.handle);
}

async function main() {
  assertRunToken();
  const argv = process.argv.slice(2);
  const fromClassifyArg = argv.find((a) => a === '--from-classify' || a.startsWith('--from-classify='));
  let inputs, updateCurrent = false;
  if (fromClassifyArg) {
    updateCurrent = true;
    inputs = handlesFromClassify();
  } else {
    inputs = argv;
    if (inputs.length === 0 && !process.stdin.isTTY) inputs = fs.readFileSync(0, 'utf8').split(/\s+/).filter(Boolean);
  }

  const allHandles = [...new Set(inputs.map(normalizeHandle).filter(Boolean))];
  const handles = allHandles.slice(0, MAX_PER_RUN);
  if (handles.length === 0) {
    if (updateCurrent) { process.stderr.write('[profile-counts] no accounts need refresh\n'); console.log('[]'); return; }
    console.error('Usage: profile-counts.cjs handle1 @handle2 https://x.com/handle3  |  --from-classify[=DATE]');
    process.exit(2);
  }

  const results = [];
  for (let index = 0; index < handles.length; index++) {
    const handle = handles[index];
    try { results.push(await fetchProfile(handle)); }
    catch (error) { results.push({ handle, ok: false, error: String((error && error.message) || error) }); }
    const latest = results[results.length - 1];
    if (latest && latest.status === 429) {
      fs.mkdirSync(DATA_DIR, { recursive: true });
      fs.writeFileSync(ALERT_PATH, `[profile-counts] RATE_LIMIT at @${handle}; stopped immediately at ${new Date().toISOString()}\n`, 'utf8');
      process.stderr.write(`[profile-counts] RATE_LIMIT at @${handle}; STOP. See ${ALERT_PATH}\n`);
      break;
    }
    if (index < handles.length - 1) {
      const wait = jitterMs(WAIT_MIN, WAIT_MAX);
      process.stderr.write(`[profile-counts] safe wait ${Math.ceil(wait / 1000)}s before next profile\n`);
      await sleep(wait);
    }
  }

  if (updateCurrent) {
    const file = path.join(DATA_DIR, 'current', 'relationships.jsonl');
    const current = Store.readJsonl(file);
    if (!current) throw new Error(`Missing current relationships: ${file}`);
    const successful = new Map(results.filter((row) => row.ok && Number.isFinite(row.followers_count)).map((row) => [normalizeHandle(row.handle).toLowerCase(), row]));
    const updated = current.map((row) => {
      const refresh = successful.get(normalizeHandle(row.handle).toLowerCase());
      return refresh ? { ...row, refreshedFollowersCount: refresh.followers_count, refreshedAt: refresh.refreshedAt } : row;
    });
    Store.atomicWrite(file, updated.map((row) => JSON.stringify(row)).join('\n') + (updated.length ? '\n' : ''));
    process.stderr.write(`[profile-counts] refreshed ${successful.size}/${allHandles.length} pending (cap=${MAX_PER_RUN}); evidence embedded in current relationships\n`);
  }
  process.stdout.write(JSON.stringify(results, null, 2) + '\n');
}

if (require.main === module) {
  main().catch((error) => { console.error(error); process.exit(1); });
}

module.exports = { extractJsonLd, stat, normalizeHandle, fetchProfile };

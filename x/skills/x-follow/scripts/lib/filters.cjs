// lib/filters.cjs — PURE, side-effect-free logic shared across scripts & unit tests.
// Nothing here touches the network, the filesystem, or a browser, so every function
// is directly testable in tests/run-tests.cjs.

// ---- crypto token list (single source of truth) ----------------------------
// Used by build-queue (handle filter) and campaign's BIO_BLACKLIST default.
// Keep handle-substring tokens (latin) separate-friendly; zh tokens match bio substrings.
const CRYPTO_TOKENS = [
  'crypto', 'web3', 'btc', 'eth', 'sol', 'defi', 'nft', 'blockchain', 'binance', 'okx',
  'bybit', 'coinbase', 'coin', 'airdrop', 'wallet', 'bitcoin', 'ethereum', 'solana',
  'satoshi', 'doge', 'shib', 'pump', 'memecoin', 'token', 'onchain', 'altcoin',
  'hyperliquid', 'ordinal', 'bnb', 'usdt', 'degen', 'dao', 'meme', 'trader', 'mining',
  'staking', 'gamefi', 'layer2', 'tokenomic', 'sui', 'aptos', 'arbitrum', 'optimism',
  'hashrate', 'ico', 'ido', 'launchpad', 'presale', 'perp', 'quant', 'shitcoin', 'pumpfun',
  '币圈', '币安', '合约', '空投', '铭文', '打新', '钱包', '量化', '操盘', '建仓', '加仓',
  '止盈', '撸毛', '羊毛', '空投党', '矿工', '矿池', '去中心化', '链上', '加密', '炒币',
  '土狗', '梭哈', '埋伏',
];

// Parse X follower/following counts: "1,234" "1.2万" "12K" "1.5M" "2亿" "3B".
// Returns an integer, or -1 when unparseable (mirrors VERIFY_JS convention).
function parseCount(v) {
  if (v == null) return -1;
  const s = String(v).replace(/,/g, '').trim();
  const m = s.match(/([\d.]+)\s*([万千亿KkMmBb])?/);
  if (!m) return -1;
  let n = parseFloat(m[1]);
  if (isNaN(n)) return -1;
  const u = m[2];
  if (u === '亿') n *= 1e8;
  else if (u === '万') n *= 1e4;
  else if (u === '千') n *= 1e3;
  else if (u === 'K' || u === 'k') n *= 1e3;
  else if (u === 'M' || u === 'm') n *= 1e6;
  else if (u === 'B' || u === 'b') n *= 1e9;
  return Math.round(n);
}

// True if the handle contains any latin crypto token (case-insensitive substring).
// Used by build-queue to drop obvious crypto handles when NOCRYPTO is on.
function isCryptoHandle(handle, tokens = CRYPTO_TOKENS) {
  if (!handle) return false;
  const l = String(handle).toLowerCase();
  return tokens.some((k) => /^[a-z0-9_.-]+$/i.test(k) && l.includes(k.toLowerCase()));
}

// Exponential backoff schedule: base * 2^(attempt-1), capped. attempt is 1-based.
function backoffMs(attempt, base = 20000, cap = 300000) {
  if (attempt < 1) attempt = 1;
  return Math.min(base * Math.pow(2, attempt - 1), cap);
}

// PURE mirror of campaign VERIFY_JS decision logic — lets the criteria be unit-tested
// without a browser. `p` is the parsed profile, `cfg` the gates.
//   p: { blue, gold, hasFollowBtn, hasUnfollowBtn, fers, fing, cryptoMatch, whitelistFail }
//   cfg: { VERIFIED_REQUIRED, FOLLOWING_GT_FOLLOWERS, FERS_MAX }
// Order matters and MUST match VERIFY_JS so tests reflect production behavior.
function decide(p, cfg) {
  const fers = p.fers == null ? -1 : p.fers;
  const fing = p.fing == null ? -1 : p.fing;
  if (cfg.VERIFIED_REQUIRED && !p.blue) return 'reject:not_blue';
  if (p.gold) return 'reject:gold_org';
  if (p.hasUnfollowBtn) return 'reject:already_following'; // SAFETY: never click if already followed
  if (!p.hasFollowBtn) return 'reject:no_follow_btn';
  if (fers < 0 || fing < 0) return 'reject:cant_parse_stats';
  if (fers > cfg.FERS_MAX) return `reject:fers>${cfg.FERS_MAX}(${fers})`;
  if (cfg.FOLLOWING_GT_FOLLOWERS && fing <= fers) return `reject:fing<=fers(${fing}<=${fers})`;
  if (p.cryptoMatch) return `reject:blacklist(${p.cryptoMatch})`;
  if (p.whitelistFail) return 'reject:not_in_whitelist';
  return 'pass';
}

module.exports = { CRYPTO_TOKENS, parseCount, isCryptoHandle, backoffMs, decide };

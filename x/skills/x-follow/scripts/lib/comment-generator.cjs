// comment-generator.cjs — varied follow引流 comment pool.
// Returns a fresh comment each call to avoid spam-detection pattern matching.
// Pools are split by register (zh short / zh with praise / en / mixed) so consecutive
// calls to generateComment() tend to rotate through different registers.

'use strict';

const ZH_SHORT = [
  '已关注，内容很不错！',
  '关注了，期待后续分享~',
  '刚关注，内容真的挺有质量的',
  '内容很实用，关注了👍',
  '看了你的帖子，关注一波',
  '已关注，多多交流',
  '这分享很及时，关注了！',
  '已关注，保持更新哦',
  '内容不错，关注了一下',
  '刚关注你，继续加油！',
];

const ZH_WITH_PRAISE = [
  '写得很好，已关注，期待更多干货',
  '思路清晰，受益匪浅，关注了',
  '很有深度的内容，已关注 🙌',
  '分析得很到位，关注了！',
  '讲得很清楚，已关注，多多交流',
  '内容很扎实，关注了，期待互动',
  '受益了，关注了，希望以后多学习',
  '这个角度很有意思，关注了！',
  '观点很独到，已关注',
  '这种干货太需要了，已关注 🔥',
];

const EN_SHORT = [
  'Just followed! Great content 👍',
  'Followed — really valuable insights!',
  'Love the content, just hit follow!',
  'Following for more of this 🙌',
  'Great post, just followed!',
  'Really insightful, followed!',
  'Just followed — keep it up! 💪',
  'Solid content, just followed.',
  'Following! Always good to find quality posts.',
  'Great stuff, just followed 🙌',
];

const MIXED = [
  '已关注！Great content ✨',
  'Followed! 内容很不错 👍',
  '很有价值的分享，following now!',
  '学到了！Just followed 🙌',
  '已关注 — nice content!',
  'Great post 👍 已关注！',
  '内容不错！Following now~',
];

const ALL = [...ZH_SHORT, ...ZH_WITH_PRAISE, ...EN_SHORT, ...MIXED];

// Simple shuffle-pick: pick from a full-pool index that resets after exhaustion so a 50-
// follow run hits every template at most once before any repeats.
let _remaining = [];
function generateComment() {
  if (_remaining.length === 0) {
    _remaining = ALL.map((_, i) => i);
    for (let i = _remaining.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [_remaining[i], _remaining[j]] = [_remaining[j], _remaining[i]];
    }
  }
  return ALL[_remaining.pop()];
}

module.exports = { generateComment };

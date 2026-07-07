#!/usr/bin/env node
/* level.cjs — 通用资源平衡器(resource leveler)
 *
 * 在「依赖拓扑约束 + 单人单周人天上限」下,自动计算每个工作包的起止周,
 * 并内置依赖倒挂 / 单人周超载 / 窗口溢出三项机器校验。
 *
 * 用法:
 *   node level.cjs <input.json> [--json] [--strict]
 *   cat input.json | node level.cjs - [--json]
 *   node level.cjs --selftest
 *
 * 输入格式详见 ../references/input-format.md
 *
 * 退出码:
 *   0 = 校验通过(或仅有警告且未加 --strict)
 *   1 = --strict 下存在超载/溢出
 *   2 = 存在依赖倒挂(硬伤,恒为错误)
 *   3 = 输入不合法
 */
'use strict';

const fs = require('fs');

const r1 = (n) => Math.round(n * 10) / 10;
const r2 = (n) => Math.round(n * 100) / 100;
const pertOf = (t) =>
  t.pert && typeof t.pert === 'object'
    ? r2((t.pert.o + 4 * t.pert.m + t.pert.p) / 6)
    : r2(t.effort);

// ── 输入规范化与合法性检查 ──────────────────────────────
function normalize(input) {
  const weeks = input.weeks;
  if (!Number.isInteger(weeks) || weeks < 1) throw new Error('weeks 必须为正整数');

  const weeklyCapacity = input.weeklyCapacity ?? 5; // 单人单周硬上限(人天)
  const packTarget = input.packTarget ?? r2(weeklyCapacity * 0.9); // 打包目标强度(留缓冲不拉满)
  const perTaskCap = input.perTaskCap ?? r2(packTarget * 0.6); // 非关键包单周强度上限(限双线程,填空隙不挤占关键路径)
  const tailMergeMax = input.tailMergeMax ?? 0.6; // 收尾零头并入最后一周的上限(人天)
  const effectiveCapacityFactor = input.effectiveCapacityFactor ?? 1; // 有效可投产能系数(扣非交付工时),用于利用率分母

  const roles = (input.roles || []).map((r) =>
    typeof r === 'string' ? { id: r, name: r } : { id: r.id, name: r.name || r.id }
  );
  if (!roles.length) throw new Error('roles 不能为空');
  const roleIds = new Set(roles.map((r) => r.id));

  const msWeek = Object.fromEntries((input.milestones || []).map((m) => [m.id, m.week]));

  const tasks = (input.tasks || []).map((t) => {
    if (!t.id) throw new Error('task 缺 id');
    if (!roleIds.has(t.role)) throw new Error(`task ${t.id}: role "${t.role}" 不在 roles 中`);
    const pert = pertOf(t);
    if (!(pert > 0)) throw new Error(`task ${t.id}: 需提供 pert:{o,m,p} 或 effort(人天)`);
    if (t.background && !(t.background.start >= 1 && t.background.end <= weeks && t.background.start <= t.background.end))
      throw new Error(`task ${t.id}: background.start/end 必须落在 1..${weeks} 内`);
    return {
      id: String(t.id),
      name: t.name || String(t.id),
      role: t.role,
      pert,
      deps: (t.deps || []).map(String),
      critical: !!t.critical, // 关键路径包:允许满速(packTarget)推进
      priority: Number.isInteger(t.priority) ? t.priority : 1, // 0 最高
      background: t.background || null, // {start,end}: 贯穿型负载,固定跨度薄摊
      earliestStart: t.earliestStart || null, // 硬约束:外部前置(如外包资产到位周)
      preferredStart: t.preferredStart || null, // 软意图:仅参与排序,不人为延后开工
    };
  });
  if (!tasks.length) throw new Error('tasks 不能为空');

  const ids = new Set(tasks.map((t) => t.id));
  tasks.forEach((t) =>
    t.deps.forEach((d) => {
      if (!ids.has(d) && msWeek[d] == null) throw new Error(`task ${t.id}: 依赖 "${d}" 既不是任务也不是里程碑`);
    })
  );

  return { weeks, weeklyCapacity, packTarget, perTaskCap, tailMergeMax, effectiveCapacityFactor, roles, msWeek, tasks };
}

// ── 平衡器主体 ──────────────────────────────────────────
function level(model) {
  const { weeks, weeklyCapacity, packTarget, perTaskCap, tailMergeMax, roles, msWeek, tasks } = model;
  const byId = Object.fromEntries(tasks.map((t) => [t.id, t]));

  // 负载矩阵 load[roleId][week], week ∈ 1..weeks
  const load = {};
  roles.forEach((r) => (load[r.id] = Array(weeks + 1).fill(0)));

  // 1) 背景任务:固定跨度薄摊(如贯穿全程的评审/合规建设)
  const bg = tasks.filter((t) => t.background);
  bg.forEach((t) => {
    t._w0 = t.background.start;
    t._w1 = t.background.end;
    t._rate = t.pert / (t._w1 - t._w0 + 1);
  });

  // 2) 依赖完成周(允许同周衔接:前置在 W 内完成,后继可自 W 起步)
  const depFinish = (t) =>
    t.deps.reduce((f, d) => {
      if (msWeek[d] != null) return Math.max(f, msWeek[d]);
      const dep = byId[d];
      return dep && dep._w1 != null ? Math.max(f, dep._w1) : f;
    }, 0);

  // 3) 拓扑深度(依赖成环直接报错)
  const depthCache = {};
  const depth = (id, path = new Set()) => {
    if (depthCache[id] != null) return depthCache[id];
    if (path.has(id)) throw new Error('依赖成环,涉及: ' + id);
    path.add(id);
    const t = byId[id];
    const d = t.deps.filter((x) => byId[x]).reduce((mx, x) => Math.max(mx, 1 + depth(x, path)), 0);
    path.delete(id);
    return (depthCache[id] = d);
  };

  // 排序:拓扑深度(保证前置先排,杜绝倒挂) → 关键路径优先 → 优先级 → 软意图起周 → id
  const normal = tasks
    .filter((t) => !t.background)
    .sort(
      (a, b) =>
        depth(a.id) - depth(b.id) ||
        (b.critical === a.critical ? 0 : b.critical ? 1 : -1) ||
        a.priority - b.priority ||
        (a.preferredStart || 1) - (b.preferredStart || 1) ||
        a.id.localeCompare(b.id)
    );

  // 4) 贪心填充,跑 3 遍收敛(依赖完成周依赖于排程结果)
  for (let pass = 0; pass < 3; pass++) {
    normal.forEach((t) => {
      t._w0 = null;
      t._w1 = null;
    });
    roles.forEach((r) => load[r.id].fill(0));
    bg.forEach((t) => {
      for (let w = t._w0; w <= t._w1; w++) load[t.role][w] += t._rate;
    });

    normal.forEach((t) => {
      const est = Math.max(depFinish(t), t.earliestStart || 1, 1);
      let remaining = t.pert,
        w = est,
        first = null,
        last = null,
        guard = 0;
      while (remaining > 0.01 && w <= weeks && guard++ < 10000) {
        const cap = t.critical ? packTarget : perTaskCap;
        const avail = packTarget - load[t.role][w];
        const take = Math.min(remaining, cap, avail);
        if (take >= 0.05) {
          load[t.role][w] = r2(load[t.role][w] + take);
          remaining = r2(remaining - take);
          if (first == null) first = w;
          last = w;
        }
        w++;
      }
      // 收尾零头并入最后一周(不破单人周硬上限),避免假性溢出
      if (remaining > 0.01 && remaining < tailMergeMax && last != null) {
        const room = weeklyCapacity - load[t.role][last];
        const d = Math.min(remaining, room);
        if (d > 0) {
          load[t.role][last] = r2(load[t.role][last] + d);
          remaining = r2(remaining - d);
        }
      }
      t._w0 = first ?? est;
      t._w1 = last ?? first ?? est;
      t._overflow = remaining > 0.01;
    });
  }

  // 5) 汇总
  const items = tasks.map((t) => ({
    id: t.id,
    name: t.name,
    role: t.role,
    pert: t.pert,
    deps: t.deps,
    critical: t.critical,
    background: !!t.background,
    w0: t._w0,
    w1: t._w1,
    span: t._w1 - t._w0 + 1,
    overflow: !!t._overflow,
  }));
  const byRole = {};
  roles.forEach((r) => (byRole[r.id] = 0));
  items.forEach((i) => (byRole[i.role] = r1(byRole[i.role] + i.pert)));
  const total = r1(items.reduce((a, i) => a + i.pert, 0));

  // 利用率 = 角色总人天 / 有效可投产能(理论产能 × effectiveCapacityFactor)
  const effCap = r2(model.weeks * model.weeklyCapacity * model.effectiveCapacityFactor);
  const utilization = {};
  roles.forEach((r) => (utilization[r.id] = Math.round((byRole[r.id] / effCap) * 100)));

  return { items, load, byRole, total, effCapPerPerson: effCap, utilization };
}

// ── 机器校验 ────────────────────────────────────────────
function validate(model, result) {
  const byId = Object.fromEntries(result.items.map((i) => [i.id, i]));
  const issues = { inversions: [], overload: [], overflow: [] };

  // 依赖倒挂:每包开始周必须 ≥ 全部前置完成周
  result.items.forEach((t) => {
    t.deps.forEach((d) => {
      const f = model.msWeek[d] != null ? model.msWeek[d] : byId[d] ? byId[d].w1 : null;
      if (f != null && t.w0 < f) issues.inversions.push(`${t.id} 起于 W${t.w0},早于前置 ${d} 完成周 W${f}`);
    });
  });

  // 单人周超载(> weeklyCapacity)
  model.roles.forEach((r) => {
    for (let w = 1; w <= model.weeks; w++)
      if (result.load[r.id][w] > model.weeklyCapacity + 0.01)
        issues.overload.push(`${r.id}/W${w}=${r1(result.load[r.id][w])}`);
  });

  // 窗口溢出(工时排不进 weeks 内)
  issues.overflow = result.items.filter((i) => i.overflow).map((i) => i.id);

  return issues;
}

// ── 人读诊断输出 ────────────────────────────────────────
function printReport(model, result, issues) {
  const { weeks, weeklyCapacity, roles } = model;
  const grossCap = weeks * weeklyCapacity * roles.length;
  console.log(
    `PERT合计 ${result.total} 人天 | 理论产能 ${grossCap} | 储备 ${r1(grossCap - result.total)} (${Math.round((1 - result.total / grossCap) * 100)}%)`
  );
  console.log(
    '利用率(分母=有效可投产能 ' + result.effCapPerPerson + '/人): ' +
      roles.map((r) => `${r.id} ${result.utilization[r.id]}%`).join('  ')
  );
  console.log('\n周次:      ' + Array.from({ length: weeks }, (_, i) => ('W' + (i + 1)).padStart(5)).join(''));
  roles.forEach((r) => {
    let s = '';
    for (let w = 1; w <= weeks; w++) {
      const v = r1(result.load[r.id][w]);
      s += (v > weeklyCapacity + 0.01 ? '*' : ' ') + String(v).padStart(4);
    }
    console.log(String(r.id).padEnd(10) + ':' + s);
  });
  console.log('\n各包排定起止周:');
  result.items.forEach((i) =>
    console.log(
      '  ' + i.id.padEnd(6) + ` W${i.w0}-W${i.w1}`.padEnd(9) + ` (${i.role}, ${i.pert}pd)` +
        (i.critical ? ' [CP]' : '') + (i.background ? ' [背景]' : '') + (i.overflow ? '  ⚠溢出' : '')
    )
  );
  console.log('\n── 机器校验 ──');
  console.log('依赖倒挂:', issues.inversions.length ? '\n  ' + issues.inversions.join('\n  ') : '无 ✓');
  console.log('超载单元(>' + weeklyCapacity + '):', issues.overload.length ? issues.overload.join('  ') : '无 ✓');
  console.log('溢出窗口(>W' + weeks + '未排完):', issues.overflow.length ? issues.overflow.join(', ') : '无 ✓');
}

// ── 自测(教学示例数据,亦是最小输入样例) ───────────────
const SELFTEST_INPUT = {
  weeks: 10,
  weeklyCapacity: 5,
  effectiveCapacityFactor: 0.85,
  roles: ['R1', 'R2'],
  milestones: [{ id: 'M1', week: 4 }],
  tasks: [
    { id: 'A', name: '底座', role: 'R1', pert: { o: 6, m: 8, p: 12 }, deps: [], critical: true },
    { id: 'B', name: '引擎', role: 'R1', pert: { o: 6, m: 9, p: 14 }, deps: ['A'], critical: true },
    { id: 'C', name: '前端核心', role: 'R2', pert: { o: 8, m: 10, p: 15 }, deps: ['A'], critical: true },
    { id: 'D', name: '集成联调', role: 'R2', pert: { o: 4, m: 5, p: 8 }, deps: ['B', 'C', 'M1'] },
    { id: 'E', name: '次要功能', role: 'R2', effort: 6, deps: ['A'], priority: 2 },
    { id: 'G', name: '评审贯穿', role: 'R1', effort: 5, deps: [], background: { start: 1, end: 10 } },
  ],
};

function selftest() {
  const model = normalize(SELFTEST_INPUT);
  const result = level(model);
  const issues = validate(model, result);
  printReport(model, result, issues);
  const ok = !issues.inversions.length && !issues.overload.length && !issues.overflow.length;
  console.log('\nselftest:', ok ? 'PASS ✓' : 'FAIL ✗');
  process.exit(ok ? 0 : 2);
}

// ── CLI ─────────────────────────────────────────────────
function main() {
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) return selftest();
  const jsonOut = args.includes('--json');
  const strict = args.includes('--strict');
  const src = args.find((a) => !a.startsWith('--'));
  if (!src) {
    console.error('用法: node level.cjs <input.json|-> [--json] [--strict] | node level.cjs --selftest');
    process.exit(3);
  }

  let model, result, issues;
  try {
    const raw = src === '-' ? fs.readFileSync(0, 'utf8') : fs.readFileSync(src, 'utf8');
    model = normalize(JSON.parse(raw));
    result = level(model);
    issues = validate(model, result);
  } catch (e) {
    console.error('输入错误: ' + e.message);
    process.exit(3);
  }

  if (jsonOut) {
    console.log(
      JSON.stringify(
        {
          params: {
            weeks: model.weeks,
            weeklyCapacity: model.weeklyCapacity,
            packTarget: model.packTarget,
            perTaskCap: model.perTaskCap,
            effectiveCapacityFactor: model.effectiveCapacityFactor,
          },
          total: result.total,
          byRole: result.byRole,
          utilization: result.utilization,
          effCapPerPerson: result.effCapPerPerson,
          items: result.items,
          load: result.load,
          issues,
        },
        null,
        2
      )
    );
  } else {
    printReport(model, result, issues);
  }

  if (issues.inversions.length) process.exit(2); // 倒挂恒为硬错误
  if (strict && (issues.overload.length || issues.overflow.length)) process.exit(1);
  process.exit(0);
}

main();

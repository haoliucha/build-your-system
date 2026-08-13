# 质检契约

`quality_v1` 精确包含 `schema_version`、`scores`、`revision_count`、`concerns`。`scores` 必须包含 `coverage`、`evidence`、`privacy`、`actionability`、`incremental` 五项，整数范围 1–5。

隐私、证据、增量一致性是硬门，任一低于 4 就不提交。覆盖或可行动性低于 4 时，只修订最弱项一次并复评；`revision_count` 只能是 0 或 1。软评分仍低时可交付，但 `concerns` 必须在报告方法章节显示。

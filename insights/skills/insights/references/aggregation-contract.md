# 聚合契约

聚合版本为 `aggregation_v1`，包含六个分组：`goals`、`friction`、`successes`、`tools`、`instructions`、`concurrency`。每项精确包含 `kind`、`claim`、`evidence`、`confidence`；`kind` 只能是 `repeat`、`contradiction`、`evolution`。

“规律、常见、反复”等语义必须由至少两个不同 opaque session key 支持；单例要在 claim 中明确标记“单例”。不能把相似但语义不同的句子机械合并，也不能由重复次数推断因果。矛盾保留双方条件、结果和反馈，演进必须说明时间顺序。

聚合按最多 50 个 facet 的批次产生材料，主代理再统一合成，避免子代理并发覆盖最终缓存。

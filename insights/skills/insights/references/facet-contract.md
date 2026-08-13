# native-facet-v1 契约

模型字段与本机 Claude Code 2.1.229 的可观察 facet 语义一致：

    underlying_goal: 用户根本想完成什么
    goal_categories: {category: count}
    outcome: fully_achieved | mostly_achieved | partially_achieved | not_achieved | unclear_from_transcript
    user_satisfaction_counts: {explicit_signal: count}
    claude_helpfulness: unhelpful | slightly_helpful | moderately_helpful | very_helpful | essential
    session_type: single_task | multi_task | iterative_refinement | exploration | quick_question
    friction_counts: {friction_type: count}
    friction_detail: 一句具体说明或空字符串
    primary_success: none | fast_accurate_search | correct_code_edits | good_explanations | proactive_help | multi_file_changes | good_debugging
    brief_summary: 一句目标与结果摘要
    user_instructions_to_codex: [可复用的显式指令]
    evidence_anchors: [短事件锚点]

只计算用户明确提出的目标，不把 Codex 自主探索、计划或子任务算成用户目标。短设置、问候或热身使用 goal_categories.warmup_minimal，不把 warmup_minimal 当 session_type。

满意度使用 Claude Code 2.1.229 可观察提示中的显式信号：Yay/great/perfect→happy，thanks/looks good/that works→satisfied，ok now let's… 且无抱怨继续→likely_satisfied，that's not right/try again→dissatisfied，this is broken/I give up→frustrated；单纯继续对话不等于满意。摩擦优先使用 misunderstood_request、wrong_approach、buggy_code、user_rejected_action、excessive_changes 等提示给出的类别，同一事件不得重复计算。

helper 另外持久化版本、opaque session key、source hash、日期、安全项目标签、来源和确定性 session meta。模型不得生成或改写这些字段。analysis_origin 必须为 model；占位、fallback 或手工模板不得写入已分析缓存。

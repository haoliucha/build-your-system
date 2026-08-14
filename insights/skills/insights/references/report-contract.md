# 静态 HTML 报告契约

最新报告为 report.html，归档为 report-YYYYMMDDTHHMMSSZ.html。默认 html lang 为 zh-CN；语言变化只重跑报告 lens，不使 facet 缓存失效。

信息顺序：

1. 标题与严格一行摘要：`{messages} 条消息，来自 {analyzed} 个会话（共 {primary_total} 个）｜{start} 至 {end}`；messages、项目和行为统计与 analyzed 使用同一 Facet 样本，primary_total 是资格过滤前的主会话总数；
2. 黄色线性 At-a-Glance 四段及章节跳转；
3. 顶部导航；
4. 五项横向核心统计：用户消息、代码行、文件、活跃天数、日均消息；
5. 七个语义章节：section-work、section-usage、section-wins、section-friction、section-features、section-patterns、section-horizon；
6. 独立难忘时刻；
7. 方法与覆盖量。

12 张 CSS 条形图依次表示：目标、工具、语言、会话类型、响应时间、多任务并行、消息时段、工具错误、有效帮助、结果、摩擦、推断满意度。前四张属于项目领域，接着四张属于协作方式，帮助度和结果属于有效做法，摩擦和满意度属于摩擦章节。统计事实与模型推断要通过标题和上下文区分。

功能、AGENTS.md、使用模式和未来机会必须完整显示原因、细节、示例代码或可复制提示；静态版使用 pre/code，不伪造复制按钮。

HTML 为 UTF-8 单文件、单一内联 CSS；禁止 JavaScript、外部字体/样式、iframe、表单、Canvas、SVG 和自动网络请求。CSP 至少限制 default-src none、script-src none、connect-src none、frame-src none、object-src none、base-uri none、form-action none。所有动态文本先 HTML 转义。叙事按空行拆为独立段落；只允许在转义后安全解释 `**粗体**`。展示标题统一本地化，只有真实工具名、命令、语言名和代码标识保留原文。

桌面采用约 800px 居中单栏、顶部导航和扁平章节；删除侧栏、巨型标题、外层章节大卡与嵌套阴影。移动端保持单栏，提供键盘焦点和打印样式。导航只链接实际存在的章节，不能复制 Claude 2.1.229 的 dormant feedback 死链。remaining、skipped、subagent、automation 与快照时间只放页尾方法区，不在每个 lens 或项目卡重复。

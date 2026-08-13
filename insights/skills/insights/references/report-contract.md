# 静态 HTML 报告契约

最新报告为 report.html，归档为 report-YYYYMMDDTHHMMSSZ.html。默认 html lang 为 zh-CN；语言变化只重跑报告 lens，不使 facet 缓存失效。

信息顺序：

1. 标题、日期范围；
2. At-a-Glance 四格；
3. 五项核心统计：用户消息、代码行、文件、活跃天数、日均消息；
4. 七个导航章节：section-work、section-usage、section-wins、section-friction、section-features、section-patterns、section-horizon；
5. 难忘时刻与方法/覆盖量。

12 张 CSS 条形图依次表示：目标、工具、语言、会话类型、响应时间、多任务并行、消息时段、工具错误、有效帮助、结果、摩擦、推断满意度。统计事实与模型推断要通过标题和上下文区分。

功能、AGENTS.md、使用模式和未来机会必须完整显示原因、细节、示例代码或可复制提示；静态版使用 pre/code，不伪造复制按钮。

HTML 为 UTF-8 单文件、单一内联 CSS；禁止 JavaScript、外部字体/样式、iframe、表单、Canvas、SVG 和自动网络请求。CSP 至少限制 default-src none、script-src none、connect-src none、frame-src none、object-src none、base-uri none、form-action none。所有动态文本先 HTML 转义。

桌面采用约 220px 粘性左导航与约 800px 正文；640px 以下变为顶部导航，并提供键盘焦点和打印样式。导航只链接实际存在的章节，不能复制 Claude 2.1.228 的 dormant feedback 死链。

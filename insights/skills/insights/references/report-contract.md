# 静态 HTML 报告契约

最新报告为 `report.html`，归档为 `report-YYYYMMDDTHHMMSSZ.html`。默认 `<html lang="zh-CN">`，只有用户显式提供合法 BCP 47 标签才覆盖；语言变化不使 facet 缓存失效。

报告固定 11 个章节和锚点：`overview`、`project_domains`、`collaboration`、`what_works`、`friction`、`features_workflows`、`agents_suggestions`、`new_uses`、`future_opportunities`、`memorable_moments`、`method_coverage`。章节导航必须逐一对应。

HTML 为 UTF-8 单文件，只含一段内联 CSS；禁止 JavaScript、外部字体/样式、iframe、表单、Canvas、SVG、自动网络请求。CSP 至少限制 `default-src 'none'`、`script-src 'none'`、`connect-src 'none'`、`object-src 'none'`、`base-uri 'none'` 和 `form-action 'none'`。动态文本先 HTML 转义。桌面采用约 220px 粘性左导航与约 800px 正文，640px 以下变为顶部导航，并提供键盘焦点和打印样式。

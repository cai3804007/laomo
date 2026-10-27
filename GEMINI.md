# 项目规则

本项目的 AI 助手规则统一维护在 [AGENTS.md](./AGENTS.md)，请先完整阅读该文件。

要点速览（详情见 AGENTS.md）：
- 绝不提交机密（`.env` 含 Server酱 SendKey），绝不绕过微信验证码
- 只做信息提取与提醒，**不给投资建议**
- `plans.json` 里真实计划与推定计划混存，推定值在任何输出中**必须显式标注**
- 遇到词典里没有的标的化名**不要猜**，放进 `aliases.json` 的 `unresolved`
- `.gitignore` 不支持行尾注释，注释必须独占一行

# narrative-block-enrichment

## Why

当前叙事块只有一行 ≤60 字 LLM 短句，信息量低（用户反馈「太简陋」）；社交链接（X/官网/TG）在 token_info 的 `link` 对象里但从未展示。目标：叙事句 ≤100 字覆盖 6 个信息维度（主题/定位/社区热度/风险/开发者背景/聪明钱信号），底部增加**确定性提取**的链接行（X 超链接 + 官网/TG 域名文本），总块 2-3 行。

## What Changes

- **叙事句升级**：`NARRATIVE_MAX_LEN` 60→100；prompt 覆盖 6 维（主题概念/定位来源含发行平台/社区热度信号/风险线索/开发者发币历史/聪明钱·老鼠仓信号），**真实数据注入 prompt，强制 LLM「只能引用给定数值，不得编造数字或链接」**；信息不足的维度省略。
- **链接行（确定性提取，不进 LLM，短标签 + `·` 分隔）**：每类型取第一个去重，一行容纳全部链接：
  - `X`（twitter_username → `x.com/{username}`，`[A-Za-z0-9_]{1,15}` 校验）
  - `官网`（website）、`TG`（telegram）、`社区`（dev.cto_flag=1 时 telegram 标签改为社区）
  - `DC`（discord）/ `YT` / `IG` / `TT`（其余类型）
  - 全部为超链接；**安全防线 = Telegram 点击确认弹窗**（客户端展示完整 URL 供确认，伪装域名可见）；非法 URL/用户名整项省略
- **叙事块结构**：`📚` 叙事句（可折 1-2 行）+ `🔗` 链接行（0-1 行）——信号卡与 CA 查询卡共用，位于卡片底部。
- **安全**：链接永不进 LLM prompt（防幻觉编造）；全部链接为超链接，伪装域名由 Telegram 点击确认弹窗（完整 URL 展示）兜底；X 用户名正则校验防注入。

## Capabilities

### New Capabilities

- `narrative-generation`: LLM 叙事生成规则（6 维、≤100 字、真实数据引用约束、禁编造数字/链接）与确定性链接提取（X 超链接校验、官网/TG 域名文本）

### Modified Capabilities

- `telegram-card-layout`: 叙事块从单行 `📚` 升级为 `📚` 句 + `🔗` 链接行结构（两卡共用）

## Impact

- 代码：`src/lumibot/narrative.py`（`NARRATIVE_MAX_LEN`、`SYSTEM_PROMPT`、`_infer` user prompt 注入真实数据、新增链接提取函数）；`src/lumibot/telegram_notify.py`（`render_narrative_block` 回归 `info` 参数输出 📚+🔗 两行）；`src/lumibot/telegram_bot.py`（query 路径传 info，已具备）
- 行为：叙事块从 1 行变 2-3 行；句长上限 100 字；有社交信息的 token 底部出现链接行
- 测试：链接提取校验（注入/伪装域名/非法用户名）、块渲染、字数上限、HTML 合法性守卫并入
- 文档：spec 同步

# narrative-block-enrichment Design

## Context

现状：叙事块 = `📚` + ≤60 字 LLM 单句；输入仅 symbol/name/desc/website；社交链接（`link.twitter_username/website/telegram`）在 token_info 中但未展示。用户反馈叙事「太简陋」，要求更丰富全面、可插链接、≤120 字。

约束：数据正确性优先（用户此前明确「不要计算这类不准确的表达」）；链接是攻击者可控元数据（官方 skill 明确警告 prompt-injection 与钓鱼）；叙事走异步 edit（不影响回复延迟）。

## Goals / Non-Goals

**Goals:**
- 叙事句 ≤100 字，6 维信息（主题/定位含平台/社区热度/风险/开发者背景/聪明钱信号）
- 链接行确定性提取（X 超链接 + 官网/TG 域名文本），绝不由 LLM 生成
- 信号卡与 CA 查询卡共用叙事块（2-3 行：📚 句 + 🔗 行）
- 安全：注入校验、域名可见、Telegram 确认弹窗兜底

**Non-Goals:**
- 修改指标网格/版式（叙事块独立演进）
- 链接点击统计/跳转中转
- Discord/其他平台链接（本期仅 X/官网/TG）
- 叙事进入回复热路径（保持异步 edit）

## Decisions（用户逐项确认）

1. **字数分配：句 ≤100 + 独立链接行**（用户选 A）
   LLM 只生成句子；链接由代码提取——句子截断不影响链接正确性；LLM 幻觉链接风险归零。
   *备选*：句 120 字链接并入——LLM 可能编造用户名/URL，否决。

2. **链接形态：短标签 + `·` 分隔 + 全超链接**（用户确认映射表）
   - 标签映射：`X`（twitter_username→`x.com/{u}`，`[A-Za-z0-9_]{1,15}` 校验）、`官网`（website）、`TG`（telegram）、`社区`（dev.cto_flag=1 时 telegram 标签）、`DC`/`YT`/`IG`/`TT`（discord/youtube/instagram/tiktok）
   - 每类型第一个生效（去重）；`gmgn`/`geckoterminal` 跳过（已有 GMGN 按钮）
   - **全超链接**：短标签无域名信息，安全防线移至 Telegram 点击确认弹窗（Bot API 明确：点击 `<a>` 前客户端弹窗展示完整 URL，伪装域名 `gmgn.ai.evil.com` 可见）；非法 URL/用户名整项省略
   - **实测发现（2026-08-05）**：`link.twitter_username` 可能为 tweet URL 路径（`boycott_pumpfun/status/…`）——严格校验拒绝并省略
   - **转义边界**：`render_narrative_block` 只对 📚 句转义；🔗 行来自校验后的值直接输出，不得二次转义

3. **内容维度：6 维全开**（用户选）
   prompt 注入真实数据：symbol/name/desc(200)/website/launchpad_platform/stat.creator_created_count/stat.top_rat_trader_percentage/stat.top_bundler_trader_percentage/wallet_tags_stat.smart_wallets。prompt 强制「只能引用给定数值，不得编造数字或链接」；信息不足维度省略；N/A 输出沿用 fail-open。

4. **行数：2-3 行**（用户选）
   `📚` 句（≤100 字，窄屏可折行）+ `🔗` 链接行（有链接才出现）。
   **🔗 行独立于句子渲染**：LLM N/A 但有社交链接时，async edit 仍触发、卡片底部仅出 `🔗` 行（信息最大化；`render_narrative_block` 以「句子或链接任一存在」为渲染条件）。

5. **实现落点**
   - `narrative.py`：`NARRATIVE_MAX_LEN=100`；`SYSTEM_PROMPT` 6 维重写；`_infer` user prompt 注入真实数据；新增 `extract_social_links(info) -> list[str]`（返回已渲染 HTML 片段，X 超链接/域名文本）
   - `telegram_notify.py`：`render_narrative_block(info, line)` 输出 `📚 {句}` + `🔗 {' · '.join(links)}`
   - `telegram_bot.py` query 路径已传 info ✓；signal 路径已传 info ✓
   - 链接行渲染在代码层（narrative.py 或 notify），非 LLM

## Risks / Trade-offs

- [钓鱼链接] → website/TG 不做超链接仅显示域名；X 用户名格式固定；Telegram 确认弹窗展示完整 URL
- [LLM 编造数字] → prompt 注入真实数值 + 强制引用约束 + N/A 兜底（fail-open 不阻断卡片）
- [句长超限] → `[:100]` 截断（现有机制）
- [信息贫乏 token 无链接行] → 块只含 📚 句（或不渲染），版式稳定

## Migration Plan

1. narrative.py 升级（len/prompt/数据注入/链接提取）→ telegram_notify 块渲染 → 测试（注入/伪装/非法/字数/HTML 守卫）
2. 全量 pytest → 提交部署
3. 部署后观察：有社交信息的 token 底部出现 🔗 行；N/A token 行为不变

## Open Questions

- 无

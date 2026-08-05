## Why

信号卡片只有链上指标（市值/流动性/热度），缺少代币"叙事"上下文——运营无法一眼判断这个 meme 币在讲什么故事（特朗普概念？AI Agent？动物园板块？）。此前尝试的第三方新闻源（6551 OpenNews）服务不可用且无公开注册渠道，已整体移除。现改用 LLM 叙事标签：用 DeepSeek 从代币名称/简介/官网推断一句话叙事，异步追加到卡片。

## What Changes

- 新增 `NarrativeService`（LLM 叙事推断服务）：DeepSeek chat（OpenAI 兼容接口）调用，输入 token_info 的 `symbol/name/link.description/link.website`，输出 ≤30 汉字的一句话叙事（JSON 解析，信息不足输出 `N/A` 不展示）
- 新增叙事缓存（按 `(chain, address)`，TTL 1h，每币最多 1 次 LLM 调用）与短符号/黑名单跳过
- 卡片异步追加 📚 叙事行：开仓成功后才触发（非阻塞），失败/超时静默保持卡片原样
- 新增配置 `global.narrative`（enabled / base_url / model / timeout_sec / min_symbol_len / symbol_blocklist / cache_ttl_sec）与环境变量 `NARRATIVE_API_KEY`
- 叙事为纯展示，不参与任何门禁/风控
- 同步更新 `telegram-cards` / `telegram-card-layout` 两份活跃 spec：📰 news 死要求改写为 📚 narrative；robinhood DexScreener 过时要求修正

## Capabilities

### New Capabilities
- `llm-narrative`: LLM 叙事标签——DeepSeek 调用、缓存、黑名单、异步卡片追加行

### Modified Capabilities
- `telegram-cards`: 将「Optional post-send news line on signal cards」要求（📰 行，新闻功能已删除成为死要求）改写为「Optional post-send narrative line on signal cards」（📚 行）
- `telegram-card-layout`: 卡片结构要求中「optional `📰` news line」及其场景（位置/替换/转义）改写为 📚 叙事行；顺带修正已过时的 robinhood DexScreener 按钮要求（上轮按钮统一后 robinhood 已含 DexScreener 按钮，spec 仍写 MUST NOT）

## Impact

- 新增 `src/lumibot/narrative.py`（client / cache / service）
- `src/lumibot/pipeline.py`：开仓成功后 `_spawn_narrative` 异步任务
- `src/lumibot/telegram_notify.py`：`append_narrative_line` + `edit_candidate_with_narrative`（📚 行追加/替换，保留 GMGN 按钮与状态行）
- `src/lumibot/config.py`：`NarrativeCfg` + `Settings.narrative_api_key`
- `config/chains.yaml`：`global.narrative` 段
- `src/lumibot/__main__.py`：装配 NarrativeService
- `.env.example` / `docs/runtime-params.md`：新环境变量与配置说明
- 新增测试：mock LLM、缓存命中、黑名单/短符号跳过、超时静默、仅 opened 追加、卡片格式
- 依赖：DeepSeek API（用户提供 `NARRATIVE_API_KEY`）；成本约 <¥0.1/天（每币 1 次 × ~150 token）

## Why

信号推送只有链上指标，缺少市场叙事/新闻上下文，运营难以判断热点相关性。6551 OpenNews 可提供实时加密新闻，但若同步等待会拖慢过门推送时效。

同时纠正现网实现漂移：代码当前是「过门 → 开仓 → 推送」，与产品意图「过门 → 推送 → 推送成功才开仓」不一致。本变更按正确顺序落地，并在推送成功后异步补新闻行。

## What Changes

- **纠正流水线顺序**：过门后先即时推送；仅当至少一路 Telegram 发送成功后再尝试 Paper 开仓；推送全失败则不开仓。
- 接入 OpenNews REST（`OPENNEWS_TOKEN`），后台轮询缓存；**不**在主进程运行 MCP。
- 推送成功后后台匹配新闻并 **edit** 原卡片，最多补 1 行 `📰`；可与开仓结果状态的二次 edit 合并。
- 匹配：代币 symbol/name 优先；短符号/黑名单跳过代币级；市场级（SOL/meme）须高分才 edit。
- 新闻为软参考：永不硬拦；失败 fail-open。
- 「润色」仅清洗截断，不做 LLM 改写。

## Capabilities

### New Capabilities
- `news-enrichment`: OpenNews 拉取、缓存、匹配、推送成功后异步 edit 补新闻行

### Modified Capabilities
- `unified-admission-gate`: 明确顺序为过门 → 推送 →（推送成功后）开仓；推送失败不得开仓
- `telegram-cards`: 允许事后 edit 插入新闻行/更新执行状态行，并保留 GMGN 按钮与首发主体

## Impact

- 代码：`pipeline.py` 调换推送/开仓顺序；`telegram_notify.py` 返回多 chat `message_id` 并支持 edit；新建 `src/lumibot/news/`；`config` / `.env`
- 行为：**相对现网顺序变更**（先推后开；TG 全失败不再 abort 已开仓，因为根本不开）
- 卡片：首发 `⏳ 开仓中`（或预检未新开）→ status edit → 可选 📰 edit
- 依赖：6551 OpenNews（可选）

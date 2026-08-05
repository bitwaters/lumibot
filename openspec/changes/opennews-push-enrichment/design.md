## Context

产品意图是统一门控后以**信号推送**为准，推送成功才开模拟仓。现网 [`pipeline.py`](src/lumibot/pipeline.py) 实际为 `on_alert`（开仓）→ `send_candidate`（推送），推送失败再 `abort_paper_open`——属于实现漂移。

OpenNews 软参考应挂在「推送成功之后」的异步路径，不得挡推送时效。

## Goals / Non-Goals

**Goals:**
- 恢复顺序：**过门 → 即时推送 → 推送成功才开仓 → 后台 edit（新闻/状态）**
- 首发推送不 await OpenNews
- 多 chat 记录 message_id；edit 保留键盘；冻结首发主体文本
- 无 `OPENNEWS_TOKEN` 时仍执行「先推后开」，只是不做新闻补编

**Non-Goals:**
- 人工确认后才开仓（仍是机器人自动：推送成功即开）
- 新闻硬门禁 / LLM 改写 / OpenTwitter / WebSocket / 主进程 MCP

## Decisions

1. **流水线顺序（纠正漂移）**  
   `gate → acquire → re-entry 再检 → quote`（均在副作用前）→ `send_candidate` → 仅当 `any_ok` → `on_alert` 开仓。  
   推送全失败：不开仓、释放告警冷却。  
   再检仍在**推送前**执行（沿用现网 acquire 后 re-check），避免已推送却因 loss 冷却不能开仓的常态窗口。

2. **首发卡执行行**  
   默认底部 `⏳ 开仓中`；推送前只读预检若已有持仓则 `↪️ 未新开`。  
   **禁止**首发卡写 `✅ 已开仓`。开仓完成后立刻 edit 状态行。

3. **Edit 串行，避免双写打架**  
   热路径：`push → open → status edit`（开仓是本地 DB，可 await）。  
   新闻任务在 status edit 之后启动（或启动时传入「冻结主体 + 最终状态行」），只再插 📰，禁止并行两次整卡重写。

4. **部分聊天成功**  
   `any_ok && !all_ok`：仍开仓；只对成功的 `(chat_id, message_id)` edit；保留冷却（与现网 partial 语义一致）。

5. **满仓 / 已开仓**  
   `already_open` / `blocked_max_positions`：仍可推送（运营可见）；不新建仓；满仓时释放冷却的现网语义保留。

6. **REST 直连 OpenNews**  
   `https://ai.6551.io` + `OPENNEWS_TOKEN`，不跑 MCP。

7. **冻结主体，不整卡重算行情**  
   市值/流动性等以首发为准；edit 只改状态行与 📰 行，保留 GMGN 按钮。

8. **匹配与短符号降级**  
   代币优先；短符号/黑名单跳过；市场回落须 `min_score`。

9. **缓存优先**  
   60s 轮询预热；合格符号缓存未命中才补查。

## Risks / Trade-offs

- [首发卡短暂「开仓中」] → 开仓后立刻 status edit  
- [push 成功、open 失败] → status edit 为失败/未开；不 abort（本来就没开成）  
- [push 与 open 之间极端 TOCTOU] → 再检在 push 前；push 后偶发 loss 武装则推送已出、不开仓并 edit 说明（可接受）  
- [错配新闻] → 短符号黑名单 + 「相关/市场」措辞  
- [edit 失败] → 保留上一版卡片  
- [旧 abort 单测] → 改为「push 失败不开仓」

## Migration Plan

1. 部署后确认日志顺序：send → open；TG 全失败无 abort 已开仓  
2. 配置 `OPENNEWS_TOKEN` 后观察 📰  
3. 关新闻：去 token / `news.enabled: false`；顺序纠正需回旧代码才能完全复原

## Open Questions

- 无。
## Context

统一门控（`unified-signal-gate`）已上线：过门后推送并尝试开仓。Telegram 文案仍在 `telegram_notify.py` 用旧布局（来源分型标题、策略/命令复读、优先 `cand.price` 开仓）。运营已确认目标通卡模版与严格取价策略。

约束：plain text（`parse_mode=None`）；单 GMGN 按钮；Paper only；不改 stage1 基准；延迟起点为本机见到信号时刻。

**与 `unified-signal-gate` 卡片要求的关系：** 本变更 **supersede** 其「推送卡必须展示 open_mark / 硬止损基准 / 买滑点成本」的展示要求。成交语义仍用持久化 `open_mark` 做硬止损；推送卡底部仅简略执行状态。规则说明迁到 `/help`。

## Goals / Non-Goals

**Goals:**
- 统一卡片视觉语言与图标约定
- 信号推送不按来源分型；完整 CA 可复制
- 显示开盘相对时长与端到端延迟
- 门控后重取价再开仓；失败短重试后不推不开
- rejects 中文映射；查询/出场卡同风格

**Non-Goals:**
- 推送卡展示聪明钱/KOL/热门作主标题
- 回退旧 `cand.price` 开仓
- 用 `creation_timestamp` 冒充开盘
- Telegram HTML/Markdown 复杂排版、自定义复制按钮（本轮）
- live 下单
- 过门后二次门控（用新市值重跑 filters）——本轮明确不做

## Decisions

1. **延迟 T0**  
   在 `_handle_signal` / `_handle_trending` **入口、任何 await 之前** 打 `seen_at = time.time()`。卡片 `⏱ 延迟 Xs` = 发送前时刻 − `seen_at`。  
   备选（载荷事件时间）本轮不做主指标。

2. **开仓报价与时序**  
   - **门控**使用 enrich/筛选当时的市值与指标快照（可略旧）。  
   - **成交**在 acquire + re-entry re-check 成功后：`get_price_and_market_cap(..., use_cache=False)`；失败则 sleep ~250ms 再试一次；仍失败 → `bump_reject(..., "no_price")`、释放冷却、**不**开仓、**不**推送。禁止回退旧 `cand.price`。  
   - `open_mark` / 成本基于此次报价；推送卡 **💰 市值** 在报价返回 MC 时 **MUST** 用该 MC（触发市值仍可来自 signal 载荷以显示扩张比）。  
   - 接受：门控合格后价格/市值已变仍开仓（不做二次门控）。

3. **开盘时间**  
   从 token info 解析 `open_timestamp`（Unix 秒）→ 相对时长；缺失显示 `🕐 开盘 —`。不回退 `creation_timestamp`。可在 enrich 时写入 candidate，不额外为开盘单独请求（过门报价另计）。

4. **卡片结构（信号推送）**  
   ```
   📡 [链] 信号推送  $SYMBOL
   <full CA>
   🕐 开盘 …
   💰 市值 …（有 trigger 则 → 触发 … (+%)）
   💧 流动性 … · 👥 …
   📊 Top10 … · 🔥 …
   🛡 安全 …
   ⏱ 延迟 …
   ✅/⏭/⛔ 简略执行行
   ```
   无策略页脚、无命令页脚、无「类型 N」、无 open_mark/滑点三行。

5. **rejects 映射**  
   集中字典覆盖：filters 全套（mc/liq/top10/holders/visiting/platform 及 `*_missing`）、`mc_extension` / `mc_extension_soft`、`loss_cooldown` / `post_close_cooldown` / `cooldown`、`no_price`、`safety_fetch`、以及现有 `safety_*` hard-fail reasons；`SOURCE_LABELS`：signal→信号、trending→热门。未知 reason/source 原样显示。

6. **出场市值**  
   优先在 manage 通知路径拉取当前 MC，并用存档 `open_mark` 与当前价估算入场市值（或存 open 时 MC 若易得）。**无 MC 时允许降级为价格口径**，标题/图标风格仍统一。

7. **Alert payload**  
   保留 `exec_status`；增加 `latency_ms`；可选 `open_timestamp`。`/alerts` **本轮不展示延迟**（第二轮再加）。

8. **流水线顺序**  
   门控通过 → 过门报价（含重试）→ 开仓 → 渲染（含延迟）→ TG。TG 全失败仍走既有 `abort_paper_open` + 释放冷却。

## Risks / Trade-offs

- [严格无价不推] 偶发 API 抖丢失信号 → 一次短重试；`no_price` 进 reject 计数  
- [强制刷新价] 多一次 token_info → 正确性优先  
- [门控快照 ≠ 成交价] 运营需理解两阶段；help 可一句说明  
- [出场 MC 估算] 有误差 → 无 MC 则价格降级  
- [supersede 旧卡字段] 推送不再展示止损基准细节 → `/help` + 持仓/出场补齐

## Migration Plan

1. 实现 + 单测（卡片快照、取价失败、`seen_at` 位置、reject 中文）  
2. 推送部署；冒烟：延迟/开盘/CA、`/rejects` 中文、`/help`、无价不推  
3. 回滚：revert 部署（无强制 DB 迁移）

## Open Questions

- （已关闭）出场无 MC：允许价格降级  
- （已关闭）`/alerts` 延迟：本轮不做  
- （已关闭）过门后 MC 出区间：不二次门控，仍开仓

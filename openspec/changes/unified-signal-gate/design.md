## Context

Paper 在 VPS `/www/lumibot` 运行；pipeline 现为先开仓再推送，TG 全失败时仓位残留，且冷却表 kind 仅 `source_key`/`cross` 参与 acquire。本变更落实统一门控，并规定 abort、re-check、统计落库，避免「无推送开仓」与「假冷却」。

约束：不上 live；trending 最小窗口 `1m`；SQLite 在 `/www/lumibot/data`；单 TG token 单轮询。

## Goals / Non-Goals

**Goals:**
- 过门 = 推送 + 开仓尝试；拒绝 = 不推不开
- 硬止损相对 `open_mark`；trending `1m`；两源同门
- `loss`/`post_close` 真正拦截；TG 全失败 abort 新仓且不写再入场冷却
- 告警记录 `exec_status`，`/stats` 分计 opened / skipped_open
- soft extension 可观测

**Non-Goals:**
- 分源只推不开、双源硬 AND
- 本轮改 stage1 基准
- 放宽 mc/visiting、live、迁盘
- 承诺胜率短期大幅上升

## Decisions

1. **Admission 顺序（固定）**  
   1) 轻量指标 → 2) 安全 → 3) enforce 时 `mc_extension`；soft 时只 `bump_reject(mc_extension_soft)` → 4) `has_reentry_block`：`loss` 优先否则 `post_close` → 5) `try_acquire_cooldown`（source/cross）。  
   `loss_cooldown_min` 或 `post_close_cooldown_min` 为 **0** 表示不武装、不因该 kind 拦截。

2. **`has_reentry_block(chain, token) -> "loss"|"post_close"|None`**  
   显式查 `cooldowns`；**禁止**假设旧 `try_acquire_cooldown` 会看到这些 kind。  
   单测：仅有 `loss` 行时 admission 失败。

3. **Acquire 后、开仓前再 `has_reentry_block`**  
   若失败：MUST `release_cooldown(source_key)`，reject `loss_cooldown`/`post_close_cooldown`，不开仓不推送。

4. **TG 全失败 → abort 新仓**  
   - API：`abort_paper_open(position_id)`（或等价）：删除该仓及其 fills，或标记作废且 **不** 调用正常 `close_paper`，**不** 写 `loss`/`post_close`。  
   - 同时 `release_cooldown`。  
   - `skipped_open` 时只 release 冷却。  
   - 部分 chat 成功：保留仓与冷却（现网）。

5. **`open_mark`**  
   - 新开写入真实 mark。  
   - 迁移：在 `Database.connect` 后由启动路径用 **AppConfig 各链 `slippage_buy_pct`** 回填；若某行 chain 未知则用 `1.05` 兜底一次。

6. **配置键**

```yaml
strategy:
  hard_stop_pct: -0.20
  loss_cooldown_min: 180      # 0 = off
  post_close_cooldown_min: 45 # 0 = off

chains.<name>:
  sources.trending.window: 1m
  filters.max_mc_extension: 2.0
  filters.enforce_mc_extension: false
  cooldown.same_type_min / cross_source_min: unchanged
  execution.slippage_buy_pct: used for open_mark backfill
```

7. **统计**  
   - `insert_alert` 仅在 TG `any_ok` 后；payload 含 `exec_status`（`opened`|`skipped_open`|…）。  
   - `/stats`：`opened_count` / `skipped_open_count`（可由 alerts 聚合或增量计数器）；交易质量以 **opened→closed** 仓位为准。

8. **平仓写冷却**  
   仅 **正常** `close_paper`（含 hard_stop/trail/timeout/stage1_full）武装 `post_close`；hard_stop 另武装 `loss`。同一 write 锁序列内完成。abort 不武装。

9. **stage1** 本轮不改。

## Risks / Trade-offs

- [1m 两源] 量偏多 → soft 计数后 enforce；盯 rejects  
- [abort 删仓] 丢未推送样本 → 优于幽灵仓  
- [竞态] 残余窗口 → pre-open re-check + release  
- [回填滑点兜底] 非 SOL 链偏差 → 启动用链配置；仅一次  
- [胜率预期] 验收重机制

## Migration Plan

1. 实现 + 测试 → push → `./scripts/deploy_remote.sh`  
2. 加列并按链滑点回填 `open_mark`  
3. 验证：loss 拦截、TG 全失败无残留 open、alerts 含 exec_status、`/stats` 分计  
4. 回滚：revert + redeploy；冷却分钟数改 `0` 可临时关闭

## Open Questions

- 何时 `enforce_mc_extension: true`（建议 soft 计数充分后）  
- stage1 相对 `open_mark` 的后续变更

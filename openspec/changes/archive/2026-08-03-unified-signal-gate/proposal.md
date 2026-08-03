## Why

Paper 运行数据显示：硬止损占比过高（约 76%），止损相对含买滑点的 `entry` 实际约 −16% 就触发，且同 token 反复推送/开仓连亏。同时若「推送」与「开仓」分源控制，无法用模拟盈亏衡量推送质量。需要一道**统一筛选门**：过门即推送且开仓，并修正止损基准与失败后再入场冷却。

## What Changes

- 明确 **统一门控**：轻量指标 + 安全 + 质量加严 + 冷却 全部通过后，才推送 Telegram 并尝试 Paper 开仓；拒绝则不推不开。
- **唯一执行例外**：同链同 token 已有未平仓时仍可推送，但不开第二笔；质量统计分计 **新开仓** vs **已有仓跳过**（告警 payload 持久化 `exec_status`）。
- **TG 全失败**：对本次新建仓执行 **abort（删除/作废）**，**不得**走正常平仓路径以免误写 `loss`/`post_close`；并释放告警冷却。
- 硬止损相对持久化 **`open_mark`** −20%。本轮 **不改** stage1 相对 `cost_basis`。
- trending 窗口 **`1m`**；signal 12/20 与 trending 同一套门。
- 再入场冷却：`hard_stop` → `loss` 180m；任意正常平仓 → `post_close` 45m；`0` 表示关闭该冷却。admission 顺序固定；acquire 后若 re-check 失败 MUST 释放刚占用的告警冷却。
- `max_mc_extension`（默认 2.0）+ `enforce_mc_extension`（默认 false）；soft 计 `mc_extension_soft`。

## Capabilities

### New Capabilities

- `unified-admission-gate`: 统一门控、冷却顺序、TG 失败 abort、re-check 释放冷却
- `open-mark-hard-stop`: `open_mark` 持久化与硬止损基准
- `market-ingestion`: trending 默认 `1m`
- `signal-filtering`: 追高扩展比与同源开仓
- `strategy-execution`: 平仓写再入场冷却；abort 开仓 API
- `telegram-alerts`: 卡片字段；exec_status 落库；opened/skipped 分计

### Modified Capabilities

- （无）无已归档主 specs；全部 ADDED。

## Impact

- 代码：`strategy.py`、`db.py`、`executors.py`、`pipeline.py`、`filters.py`、`config.py`、`telegram_notify.py`、`telegram_bot.py`、`chains.yaml`、测试
- 运维：`/www/lumibot` 部署后行为变化
- 不上 live；不放宽主过滤；不迁 Docker 盘

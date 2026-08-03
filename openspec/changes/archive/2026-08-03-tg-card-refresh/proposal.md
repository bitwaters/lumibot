## Why

统一门控后，Telegram 推送/查询卡片仍按来源分型、堆叠策略说明书，且开仓优先使用采集时的旧价，延迟与开盘新鲜度不可见，运营扫读成本高、纸面成交失真。需要按「过门 = 信号推送」重做卡片语言，并让开仓价对齐筛选完成后的当时市价。

## What Changes

- 信号推送通卡：标题为「信号推送」（不区分聪明钱/KOL/热门）；完整 CA 独占一行便于复制；指标/安全/延迟/开盘用固定图标；底部执行状态简略（已开仓 / 未新开 / 无价格）
- 展示端到端延迟：本机「poll 见到该条 → TG 发出」；开盘时长取 GMGN `open_timestamp`（相对时长；缺失显示 —，不挡推送）
- **开仓价**：门控通过后重取现价（可短重试一次）再开仓；失败则不推不开并释放冷却；过门报价若含市值，推送卡 **💰 市值 MUST** 用该值（与开仓同一时刻）
- 出场卡、`/positions` `/stats` `/rejects` `/alerts` `/status` `/help` 统一同一视觉语言；策略细则仅 `/help`
- `/rejects` 展示中文字段名（reason 码映射），来源显示为「信号/热门」
- 出场卡市值口径：有数据则显示入场→平仓市值；本轮补齐事件侧所需字段或查询路径

## Capabilities

### New Capabilities

- `telegram-cards`: Telegram 主动推送与命令回复的卡片排版、图标约定、延迟/开盘展示、rejects 中文映射
- `post-gate-quote`: 门控通过后重取市价用于 Paper 开仓与卡片市值；取价失败策略

### Modified Capabilities

- （无 `openspec/specs/` 主库。）相对进行中的 `unified-signal-gate` / telegram-alerts：**BREAKING（展示）** — 推送卡不再强制 open_mark / 硬止损基准 / 买滑点行；硬止损仍按 DB `open_mark` 执行。本变更 specs 为卡片与过门报价的权威要求。

## Impact

- 代码：`telegram_notify.py`、`pipeline.py`、`executors.py`、`models.py` / `filters.py`（`open_timestamp`/`seen_at`）、`exec_types.py`、相关测试
- 行为：取价失败不推不开并计 `no_price`；门控用筛选快照、成交用过门后报价（不二次门控）
- 无 live / DB schema 大迁移；alert payload 增 `latency_ms` 等
- `/alerts` 本轮不展示延迟；出场无 MC 允许价格降级

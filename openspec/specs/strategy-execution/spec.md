# strategy-execution Specification

## Purpose
Paper/Live 共用 `StrategyOrder` 状态机与执行抽象。出场比例、名义、超时、滑点等以 `config/chains.yaml` 为准（见 [docs/runtime-params.md](../../docs/runtime-params.md)）。硬止损基准见 `open-mark-hard-stop`（相对 `open_mark`，不是归档文案里的「相对入场价 -20%」）。

## Requirements
### Requirement: 共用 StrategyOrder 模型
Paper 与 Live 路径 MUST 共用同一 `StrategyOrder` 模型，包含链、代币、`open_mark`、买入成交价、名义美元仓位、买/卖滑点、硬止损比例、第一段止盈比例、相对入场后峰值的回撤比例、超时时间。上述比例与名义 MUST 从配置加载。买入按买滑点成交；第一段/硬止损/峰值回撤/超时等所有卖出 MUST 按卖滑点记账成交。第一段完成后剩余仓位成本上移仅用于记账与展示；硬止损仍相对 `open_mark`；剩余仓主要靠峰值回撤与超时出场。

#### Scenario: 第一段卖出收回成本
- **WHEN** 标记价格相对计入买入滑点后的成本上涨达到配置的 `stage1_tp_pct`
- **THEN** 引擎按**卖出滑点后净回收 ≥ 初始名义本金**计算卖出数量并成交，然后将剩余仓位成本上移至该次卖出价

#### Scenario: 峰值回撤平掉剩余
- **WHEN** 第一段已完成，且价格相对入场后最高点回撤达到配置的 `trail_drawdown_pct`
- **THEN** 引擎平掉剩余仓位

#### Scenario: 硬止损相对 open_mark
- **WHEN** 标记价格相对 `open_mark` 达到配置的 `hard_stop_pct`（无论第一段是否已发生、剩余成本是否已上移）
- **THEN** 引擎立即平掉全部剩余仓位

### Requirement: Paper 执行记录盈亏与快照
在执行模式为 `paper` 时，系统 MUST 在告警通过后尝试开模拟仓：对同链同 token，「检查无未平仓 + 创建开仓」MUST 为原子操作。若已存在未平 Paper 仓，MUST 仍可推送告警但 MUST NOT 再开第二笔。开仓按买滑点记账，按 StrategyOrder 规则管理出场，并在入场后 `1m`、`5m`、`15m`、`1h` 各记录一条价格快照（若该时点仓位已平，仍记录当时标记价，并标注 `position_closed=true`）。统计 MUST 可按链查询。Paper MUST NOT 受 Live 日亏损 / 日笔数限额约束。

#### Scenario: Paper 不调用 swap
- **WHEN** paper 模式处理开仓或平仓
- **THEN** 系统 MUST NOT 提交 GMGN swap，也不得要求私钥

#### Scenario: 已有未平仓时不再开 Paper
- **WHEN** 同链同 token 已有未平 Paper 仓位，又产生新的通过告警
- **THEN** 系统发送告警但 MUST NOT 再开一笔新的 Paper 仓

#### Scenario: 并发告警只开一笔 Paper
- **WHEN** 同链同 token 在无未平仓时几乎同时收到两条通过告警
- **THEN** 原子开仓 MUST 仅成功一笔，另一笔走「已有未平仓」路径

### Requirement: Live 执行器受闸且 P0 仅占位
系统 MUST 提供 Live 执行器接口与配置开关 `global.live_master_switch`、`chains.<chain>.live_enabled`，以及**仅作用于 Live** 的分链限额（默认单笔名义 `$20`、日亏损 `$50`、日成交笔数 `10`）。「当日」MUST 按 **UTC** 日历日切分。P0 即使误配开关也不得真实下单；P0 实现 MUST NOT 加载或使用交易私钥。

#### Scenario: 总开关关闭时阻断 Live
- **WHEN** `chains.<chain>.live_enabled` 为 true 但 `global.live_master_switch` 为 false
- **THEN** 不得提交任何 Live 订单

#### Scenario: Live 日亏损限额不约束 Paper
- **WHEN** 某链在当前 UTC 日内 Live 已实现亏损达到配置的日亏损上限
- **THEN** 系统 MUST 停止该链当日继续开 **Live** 新仓，且 MUST NOT 因此停止 Paper 开仓

### Requirement: 执行层抽象对齐
策略决策 MUST 与执行器类型解耦；Paper 与 Live 仅在成交/提交适配器不同。Live 设计 MUST 允许优先走 GMGN 策略/条件单，并在不可用时降级为与同一 StrategyOrder 规则一致的盯价 + swap。

#### Scenario: 切换模式复用同一策略状态机
- **WHEN** 某链在 Live 实现完成后将执行模式从 `paper` 改为 `live`
- **THEN** 仍应用同一套 StrategyOrder 规则，无需另写一套止盈止损定义

### Requirement: StrategyOrder hard stop uses open_mark
`StrategyOrder` MUST carry `open_mark` and evaluate hard stop against open_mark. Peak tracking MUST continue from mark updates as today.

#### Scenario: Evaluate uses open_mark
- **WHEN** StrategyOrder.evaluate runs for hard stop
- **THEN** the threshold is open_mark * (1 + hard_stop_pct)

### Requirement: Manage path loads open_mark
When reconstructing StrategyOrder from an open DB row, the system MUST load persisted open_mark (after migration) into the order used for evaluation.

#### Scenario: Manage uses stored open_mark
- **WHEN** an open position is managed on a price tick
- **THEN** hard stop evaluation uses the row open_mark, not entry_price as the stop basis

### Requirement: Close writes re-entry cooldowns
On normal Paper close, the executor MUST write post_close cooldown when configured duration > 0. On hard_stop close, it MUST also write loss cooldown when configured duration > 0. Abort of a never-alerted open MUST NOT write these cooldowns.

#### Scenario: Hard stop writes both cooldowns
- **WHEN** a position closes with reason hard_stop and both durations are positive
- **THEN** both loss and post_close cooldown records are armed for that chain and token

#### Scenario: Abort does not arm re-entry
- **WHEN** a newly opened position is aborted due to Telegram total failure
- **THEN** no loss or post_close cooldown is armed for that abort

### Requirement: Close arms cooldowns in the same write path
Arming loss/post_close cooldowns MUST happen in the normal Paper close write path promptly (same locked write sequence as status transition). Callers MUST re-check re-entry block immediately before open after acquire.

#### Scenario: Re-check before open
- **WHEN** admission previously passed acquire but a concurrent close armed loss before open
- **THEN** a pre-open re-entry check MUST prevent opening when loss is active

### Requirement: Abort paper open API
The database/executor layer MUST provide an abort path that removes or voids a newly opened position and its related fills without marking a normal close_reason used for strategy stats as a completed trade, suitable for Telegram total-failure rollback.

#### Scenario: Abort removes open position
- **WHEN** abort_paper_open is invoked for a just-opened position id
- **THEN** that position is no longer status open and is not counted as a normal hard_stop/trail close


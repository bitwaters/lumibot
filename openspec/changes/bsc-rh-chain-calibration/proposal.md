## Why

SOL Paper 已在跑，BSC / Robinhood 仍停在 `draft`。多链骨架已在，但出场策略仍是**全局一份** `strategy`，TG `/stats` `/status` 等汇总也把各链混在一张卡里——校准 BSC/RH 时会和 SOL 调参、SOL 统计搅在一起。现在要把**三链策略与汇总展示都改成按链独立**，并以 `config/chains.yaml` 为唯一策略真源，再按 `docs/calibration.md` 校准启用 BSC→RH。

## What Changes

- **策略只写在 yaml，且按链独立**：废除顶层全局 `strategy` 作为运行真源；在 `chains.sol` / `chains.bsc` / `chains.robinhood` 各自挂载完整 `strategy` 块。代码、`/help`、文档、OpenSpec **不得**再硬编码或另建一份「现行策略数字」；展示与执行一律读该链 yaml 配置
- **TG 汇总卡片按链分列**：`/stats`、`/status`、`/positions`、`/alerts`（及同类总览）MUST 按链分段/分组，禁止把多链数字加总成一行「全局模拟」或时间线混排看不出链
- **按链重置 Paper（BREAKING）**：`/reset_paper <chain> confirm` 只清该链；`/reset_paper all confirm` 显式清全部。旧用法 `/reset_paper confirm`（无 scope）**不再清库**，只提示新用法
- 按校准清单做 BSC 优先、RH 随后的连通性 → Paper 试跑 → `calibrated` + `enabled`；试跑期只调**该链**的 filters/safety/sources/slippage/**strategy**
- 补齐 EVM 字段回归、分链 stats/reset DB API、calibration 状态表；profile 绑定校验必做
- **不**启用 Live；**不**在代码或其它文档里维护第二套策略表

## Capabilities

### New Capabilities

- `chain-calibration`: 分链校准启用契约（连通性、试跑顺序、与其它链隔离）
- `per-chain-strategy`: 策略配置仅存在于 `chains.<name>.strategy`；加载/执行/帮助均按链读取
- `per-chain-telegram-summary`: TG 总览类命令按链分段渲染；含按链 `/reset_paper`

### Modified Capabilities

- `multi-chain-config`: 默认启用场景、profile 绑定、策略块位置
- `strategy-execution`: 执行器使用**该链** strategy，不再读全局份
- `signal-filtering`: BSC/RH + `evm_v1` 分链阈值；rejects 已按 chain
- `market-ingestion`: 多链限流时优先调新链 interval
- `telegram-cards`: `/help` 按启用链列出各自规则；汇总卡分链

## Impact

- 配置：`config/chains.yaml` 结构迁移（顶层 `strategy` → 每链 `strategy`；SOL 先搬现网数值，BSC/RH 可先复制同值作初值再各自调）
- 代码：`config.py`、`pipeline`/`executors` 注入链级 strategy；`db.paper_stats_summary(chain=…)` / `reset_paper_experiment(chain=…)`；`telegram_bot` / `telegram_notify` 分链渲染与按链 reset
- 文档：`docs/runtime-params.md`、`docs/calibration.md` 写明「策略只在 yaml 分链块」
- 运行：共享限流仍全局；统计与出场按链独立

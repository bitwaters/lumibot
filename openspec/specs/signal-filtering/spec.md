# signal-filtering Specification

## Purpose
统一的轻量指标 / visiting / 安全筛选与冷却占用。数值阈值以 `config/chains.yaml` 为准（见 [docs/runtime-params.md](../../docs/runtime-params.md)）；归档提案中的历史数字不作现行要求。
## Requirements
### Requirement: 轻量指标筛选
告警前，候选 MUST 通过该链配置的市值区间、最低流动性、最高 top10 持仓占比、最低持有人数。平台过滤可选；空平台列表表示不限制平台。

对 signal 候选：当前 `market_cap` 与 `trigger_mc`（若存在）MUST 同时落入市值区间；流动性 / top10 / holders 优先取 signal 载荷中的 `cur_data`（及同级字段），缺失时再补查 token info / security。对 trending 候选：使用 rank 载荷中的对应字段；若无 `trigger_mc` 则仅约束当前市值。若经优先序与补查后，市值/流动性/top10/holders 任一必需字段仍缺失或无法解析，MUST 拒绝该候选（fail-closed）。

#### Scenario: 按链配置阈值放行
- **WHEN** 使用某链 `filters.*` 评估候选
- **THEN** 仅当相关市值 / 流动性 / top10 / holders 均满足该链当前配置时通过

#### Scenario: 草案链同样读自身 filters
- **WHEN** 评估 draft 链（如 BSC / Robinhood）候选
- **THEN** 阈值取自该链配置块，而非其它链或归档文档中的历史默认值

#### Scenario: signal 双市值约束
- **WHEN** signal 候选当前 `market_cap` 在区间内但 `trigger_mc` 低于区间下限
- **THEN** 该候选 MUST 被拒绝

#### Scenario: 必需轻量字段缺失则拒绝
- **WHEN** 候选流动性在补查后仍缺失
- **THEN** 该候选 MUST 被拒绝

### Requirement: 双源 visiting 门槛
trending 候选 MUST 使用 trending 载荷中的 visiting 满足该链 `filters.visiting_min`。signal 候选 MUST 通过 token info 补查 visiting，并 MUST 达到同一链 visiting 阈值后才可告警。visiting 缺失或无法解析时 MUST 拒绝（fail-closed）。

#### Scenario: 补查后 visiting 不足则拒绝 signal
- **WHEN** signal 候选其它条件已通过，但补查后的 `visiting_count` 低于该链阈值
- **THEN** 系统 MUST NOT 为其发送 Telegram 告警

#### Scenario: visiting 缺失则拒绝
- **WHEN** signal 候选的 token info 补查失败或未返回 `visiting_count`
- **THEN** 该候选 MUST 被拒绝且不得告警

### Requirement: 分链安全 profile
系统 MUST 在 Solana 应用 `sol_v1`，在 BSC 与 Robinhood 应用 `evm_v1`。硬拒绝包括洗盘交易，以及风险比率超过配置上限（默认 `rug_ratio`、bundler（优先 `bundler_rate`，否则 `bundler_trader_amount_rate`）、`rat_trader_amount_rate` 任一 `> 0.3`）。`sol_v1` 要求 mint 与 freeze 已放弃，且 MUST 忽略空的蜜罐字段。`evm_v1` MUST 拒绝蜜罐、要求所有权 renounced、要求开源、强制买/卖税小数比例均 `≤ 0.05`（即 5%；API 值如 `0.03` 表示 3%；空字符串/缺失 MUST 视为 `0.0`），且 MUST NOT 要求 Solana mint/freeze 字段。开发者仍持仓默认可告警但 MUST NOT 硬拒绝。若 EVM 安全必需字段（蜜罐/renounced/开源）在补查后仍缺失，MUST 拒绝（fail-closed）。

#### Scenario: EVM 蜜罐被拦截
- **WHEN** EVM 候选蜜罐标记为 true/yes
- **THEN** 系统硬拒绝该候选且不告警

#### Scenario: EVM 高税被拦截
- **WHEN** EVM 候选 `buy_tax` 或 `sell_tax` 解析为 `0.06`（6%）
- **THEN** 系统硬拒绝该候选

#### Scenario: EVM 常见 3% 税可通过
- **WHEN** EVM 候选买/卖税均为 `0.03` 且其它 `evm_v1` 条件满足
- **THEN** 税项检查 MUST 通过

#### Scenario: EVM 税字段为空视为 0
- **WHEN** EVM 候选 `buy_tax` / `sell_tax` 为空字符串且其它条件满足
- **THEN** 税项按 `0.0` 处理并通过税检

#### Scenario: SOL 蜜罐字段为空不单独决定结果
- **WHEN** SOL 候选蜜罐字段为空/null，且其它方面通过 `sol_v1`
- **THEN** 仅因蜜罐字段为空 MUST NOT 导致通过或拒绝

### Requirement: 去重与冷却
系统 MUST 将冷却状态按链持久化到 SQLite。同类型冷却默认 45 分钟（同 token + 同源/信号类型）。同链跨源 token 冷却默认 15 分钟。对同一链，冷却的「检查是否可告警 + 占用/写入冷却」MUST 为原子操作（SQLite 事务或单写者队列），防止 signal 与 trending 并发双推。

#### Scenario: 跨源抑制
- **WHEN** 某 token 刚被 signal 告警，且 15 分钟内同链 trending 再次命中
- **THEN** trending 告警被抑制

#### Scenario: 冷却跨重启保留
- **WHEN** 冷却窗口仍有效时进程重启
- **THEN** 系统从 SQLite 恢复冷却状态并继续抑制重复

#### Scenario: 并发占用只放行一次
- **WHEN** 同链同 token 的 signal 与 trending 在冷却未占用前几乎同时通过筛选
- **THEN** 原子占用 MUST 仅允许其中一条完成告警，另一条 MUST 被冷却抑制

### Requirement: Market-cap extension gate for signals
When a signal candidate has `trigger_mc`, the system MUST compute `market_cap / trigger_mc`. When `enforce_mc_extension` is true and the ratio exceeds `max_mc_extension` (default 2.0), admission MUST fail with reason `mc_extension` (no push, no open). When enforce is false, the system MUST record soft counter `mc_extension_soft` without rejecting solely for extension.

#### Scenario: Enforce blocks extended signal
- **WHEN** enforce_mc_extension is true, trigger_mc is 100k, market_cap is 250k, and max_mc_extension is 2.0
- **THEN** the candidate is rejected with mc_extension and not pushed

#### Scenario: Soft mode does not reject but is observable
- **WHEN** enforce_mc_extension is false and the ratio exceeds max_mc_extension
- **THEN** extension alone MUST NOT reject the candidate AND the system MUST record an observable soft counter such as reject reason `mc_extension_soft`

### Requirement: All enabled sources share the same admission filters
Signal types configured for the chain and trending MUST use the same light filters, safety profile, extension policy (where applicable), and admission cooldowns. The system MUST NOT admit a source for push while excluding it from Paper open by source whitelist.

#### Scenario: Trending pass opens paper
- **WHEN** a trending candidate passes the unified admission gate and no open position exists
- **THEN** Paper open is attempted and a Telegram alert is sent

### Requirement: Enabled EVM chains use evm_v1 independently
When `bsc` or `robinhood` is enabled, candidates on that chain MUST be evaluated with `evm_v1` and that chain's own `filters` / `safety` thresholds. Admission MUST fail closed on missing EVM-required security fields (honeypot / renounced / open_source) after enrichment.

#### Scenario: BSC candidate uses BSC filters
- **WHEN** an enabled BSC candidate is lightly filtered
- **THEN** thresholds come from `chains.bsc.filters`, not from `chains.sol.filters`

#### Scenario: Missing renounced rejects on EVM
- **WHEN** a BSC or Robinhood security payload has `renounced` missing after fetch
- **THEN** the candidate MUST be rejected with an EVM safety reason and MUST NOT be pushed or opened

### Requirement: Per-chain reject observability
Reject counters MUST remain keyed by `chain` so operators can tune each chain from `/rejects` without conflating distributions.

#### Scenario: BSC rejects do not overwrite SOL rows
- **WHEN** BSC rejects for reason `mc` and SOL also rejects for `mc`
- **THEN** `reject_counts` stores separate rows distinguished by chain


# multi-chain-config Specification

## Purpose
分链配置加载与 `draft` → `calibrated` → `enabled` 启动门禁。阈值真源见 [docs/runtime-params.md](../../docs/runtime-params.md)。
## Requirements
### Requirement: 分链配置
系统 MUST 为 `sol`、`bsc`、`robinhood` 分别加载配置，包括启用状态、校准状态、报价资产、采集间隔、筛选阈值、**链级 strategy**、安全 profile、冷却时间与执行限额。运行时 MUST NOT 静默把一条链的数值过滤器或 strategy 复制到另一条链。

#### Scenario: 未校准链保持禁用
- **WHEN** 某链尚未完成连通性与校准启用流程
- **THEN** 该链 MUST 为 `enabled: false`（`calibration_status` 可为 `draft` 或已 `calibrated` 但未启用）

#### Scenario: 校准后可启用 BSC 且与 SOL 共存
- **WHEN** `chains.bsc.calibration_status` 为 `calibrated` 且 `enabled` 为 true，且 `chains.sol` 保持启用
- **THEN** 服务 MUST 启动成功并为 `sol` 与 `bsc` 各建一条 pipeline，各自使用本链 `strategy`

#### Scenario: draft 链禁止启用
- **WHEN** 某链 `enabled: true` 且 `calibration_status` 不是 `calibrated`
- **THEN** 服务 MUST 启动失败，并在错误信息中指出该链

### Requirement: 报价资产白名单
系统 MUST 将可交易报价资产限制在各链配置白名单内：SOL 为 SOL 与 USDC；BSC 为 BNB（native）与 USDC；Robinhood 为 native（`0x000…0`）与 WETH（`0x0bd7d308f8e1639fab988df18a8011f41eacad73`）。

#### Scenario: 非白名单报价在 Live 路径被拒绝
- **WHEN** Live 执行将使用不在该链白名单内的报价资产
- **THEN** 系统 MUST 拒绝该请求且不得提交 swap

### Requirement: 安全 profile 绑定
系统 MUST 将 `sol` 绑定到 `sol_v1`，将 `bsc` 与 `robinhood` 绑定到 `evm_v1`，同时保持各链筛选阈值相互独立。

#### Scenario: Robinhood 使用 EVM 安全规则
- **WHEN** 对 Robinhood 候选做安全检查
- **THEN** 系统应用 `evm_v1`（蜜罐 / renounced / 开源 / 税），且不得要求 Solana 的 mint/freeze renounce 字段

### Requirement: Profile binding for chain safety
Configuration load MUST require `sol` → `safety_profile: sol_v1` and `bsc` / `robinhood` → `evm_v1`. A mismatch MUST fail at load time.

#### Scenario: BSC with sol_v1 rejected
- **WHEN** `chains.bsc.safety_profile` is `sol_v1`
- **THEN** config load MUST fail before pipelines start

### Requirement: Top-level strategy is not authoritative
If a legacy top-level `strategy` key exists in yaml, the loader MUST NOT use it as the runtime strategy for any chain after per-chain strategy is required. Operators MUST define `chains.<name>.strategy` for each chain.

#### Scenario: Per-chain strategy wins
- **WHEN** yaml contains both a top-level `strategy` and `chains.sol.strategy`
- **THEN** sol Paper MUST execute using `chains.sol.strategy` only


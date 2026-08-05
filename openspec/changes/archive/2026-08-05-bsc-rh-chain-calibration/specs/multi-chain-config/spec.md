## MODIFIED Requirements

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

## ADDED Requirements

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

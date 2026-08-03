## ADDED Requirements

### Requirement: 分链配置
系统 MUST 为 `sol`、`bsc`、`robinhood` 分别加载配置，包括启用状态、校准状态、报价资产、采集间隔、筛选阈值、安全 profile、冷却时间与执行限额。运行时 MUST NOT 静默把一条链的数值过滤器复制到另一条链。

#### Scenario: P0 仅启用 SOL
- **WHEN** 服务以项目默认配置启动
- **THEN** `sol` 为 `enabled: true` 且 `calibration_status: calibrated`，`bsc` / `robinhood` 为 `enabled: false` 且 `calibration_status: draft`

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

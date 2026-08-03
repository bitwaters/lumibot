# telegram-alerts Specification

## Purpose
Telegram 扇出、失败 abort、exec_status / 统计口径。卡片版式以 `telegram-cards` 为准。
## Requirements
### Requirement: 双目标推送
系统 MUST 将每条通过审核的告警发送到所有已配置的 Telegram chat id；在同时配置私聊与测试群时，两者都要收到。

#### Scenario: 扇出到私聊与群组
- **WHEN** 候选通过筛选与去重
- **THEN** 相同告警内容投递到每一个已配置 chat id

### Requirement: 带链标签的精简卡片
每条告警 MUST 以链标签开头（`[SOL]`、`[BSC]` 或 `[RH]`），并包含符号/名称、合约地址、来源（信号类型或 trending）、市值、流动性、持有人或浏览热度（如有）、安全摘要（通过/告警），以及 GMGN 代币链接。可配置额外深链模板，但 P0 除 GMGN 外不强制。

#### Scenario: SOL 信号卡片
- **WHEN** 告警一条 SOL 聪明钱信号
- **THEN** 消息以 `[SOL]` 开头，包含信号类型 12 相关信息，以及 `gmgn.ai/sol/token/...` 链接

### Requirement: 被过滤或不安全的代币不推送
对筛选、安全、visiting 门槛或冷却拒绝的候选，系统 MUST NOT 发送 Telegram 消息。

#### Scenario: 拒绝候选保持静默
- **WHEN** 候选未通过安全检查
- **THEN** 不为该候选发送任何 Telegram 消息

### Requirement: Alert card shows mark stop context
When a Paper position is opened, the Telegram alert MUST include open mark (or equivalent), hard-stop line reference, and buy-fill / slip cost context in plain text so operators can verify stop basis.

#### Scenario: Opened card fields
- **WHEN** exec status is opened
- **THEN** the card text includes open mark and indicates the hard stop is relative to that mark

### Requirement: Skipped-open already-open messaging
When admission passed but open was skipped because a position already exists, the card MUST state that simulation did not open a second position for that reason.

#### Scenario: Already open card
- **WHEN** paper status is skipped_open
- **THEN** the card includes a clear already-open skip message

### Requirement: Alert payload records exec_status
When an alert is persisted after successful Telegram delivery, the payload MUST include `exec_status` reflecting the paper result for that admission (at least `opened` and `skipped_open`).

#### Scenario: Opened alert payload
- **WHEN** a new position was opened and Telegram any_ok is true
- **THEN** insert_alert payload contains exec_status opened

### Requirement: Stats separate opens from already-open skips
Paper stats surfaces MUST expose counts that distinguish newly opened positions from admission-passed already-open skips, preferably derived from persisted alert exec_status and/or position rows. Push-quality judgment for trading outcomes MUST primarily use the newly opened cohort. Already-open skips MUST NOT be counted as admission rejects. Soft extension breaches MUST appear in reject/observability counters without blocking admission when enforce is false.

#### Scenario: Rejects vs skips
- **WHEN** operators query reject counts and paper stats
- **THEN** admission rejects are counted in rejects, already-open skips are counted separately from opens, and mc_extension_soft is visible when soft mode records breaches

#### Scenario: Quality cohort
- **WHEN** operators assess alert trading quality by source
- **THEN** win rate and PnL summaries are based on positions that were newly opened, not on skipped_open-only alerts


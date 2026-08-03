## ADDED Requirements

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

# signal-filtering Delta

## MODIFIED Requirements

### Requirement: 双源 visiting 门槛
signal 与 trending 候选 MUST 均通过 token info 补查 `visiting_count`（优先缓存，300s TTL），并 MUST 达到该链 visiting 阈值后才可告警；载荷中的 visiting 值 MUST NOT 作为门禁依据。trending 候选的阈值按 `filters.visiting_min_trending`（若配置）否则 `filters.visiting_min`；signal 候选按 `filters.visiting_min`。visiting 补查失败或无法解析时 MUST 拒绝（fail-closed）。

#### Scenario: 补查后 visiting 不足则拒绝 signal
- **WHEN** signal 候选其它条件已通过，但补查后的 `visiting_count` 低于该链阈值
- **THEN** 系统 MUST NOT 为其发送 Telegram 告警

#### Scenario: 补查后 visiting 不足则拒绝 trending
- **WHEN** trending 候选其它条件已通过，但 token info 补查后的 `visiting_count` 低于该链阈值
- **THEN** 系统 MUST NOT 为其发送 Telegram 告警，且不得使用载荷 visiting 替代

#### Scenario: visiting 缺失则拒绝
- **WHEN** signal 或 trending 候选的 token info 补查失败或未返回 `visiting_count`
- **THEN** 该候选 MUST 被拒绝且不得告警

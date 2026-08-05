## ADDED Requirements

### Requirement: 叙事推断调用（DeepSeek）

系统通过 OpenAI 兼容的 chat/completions 接口调用 DeepSeek，输入代币的 `symbol`、`name`、`link.description`、`link.website`，输出不超过 30 个汉字的一句话叙事（JSON 解析 `{"narrative": "..."}`）。信息不足时返回 `N/A` 且不展示。

#### Scenario: 正常叙事推断
- **WHEN** 一个已开仓代币进入叙事流程且 LLM 返回 `{"narrative": "特朗普概念官方迷因币"}`
- **THEN** 系统缓存该结果并在卡片上追加 📚 叙事行「📚 特朗普概念官方迷因币」

#### Scenario: 信息不足
- **WHEN** LLM 返回 `{"narrative": "N/A"}` 或空字符串
- **THEN** 卡片不追加叙事行，不产生任何展示变化

#### Scenario: 调用失败或超时
- **WHEN** LLM 请求抛错、HTTP 非 2xx 或超过 `timeout_sec`
- **THEN** 流程静默失败，卡片保持原样，不重试、不阻塞推送

### Requirement: 叙事缓存与成本控制

系统按 `(chain, address)` 缓存叙事结果（TTL 为 `cache_ttl_sec`，默认 3600 秒），同一代币在 TTL 内只发起一次 LLM 调用；叙事流程仅对实际开仓成功（`opened`）的代币触发。

#### Scenario: 缓存命中
- **WHEN** 同一代币在 TTL 内再次进入叙事流程
- **THEN** 直接使用缓存结果，不发起新的 LLM 调用

#### Scenario: 非开仓状态不触发
- **WHEN** 代币推送后状态为 `already_open` / `blocked_max_positions` / `no_price` / `executor_error`
- **THEN** 不发起叙事调用，卡片无 📚 行

### Requirement: 符号黑名单与短符号跳过

`symbol` 长度小于 `min_symbol_len`（默认 3）或命中 `symbol_blocklist` 的代币跳过叙事推断。

#### Scenario: 短符号跳过
- **WHEN** 代币 symbol 为 `X`（长度 1）且 `min_symbol_len=3`
- **THEN** 不发起 LLM 调用，卡片无 📚 行

#### Scenario: 黑名单跳过
- **WHEN** 代币 symbol 命中 `symbol_blocklist`
- **THEN** 不发起 LLM 调用

### Requirement: 卡片异步追加叙事行

叙事行在开仓成功后的后台任务中追加，编辑保留卡片状态行与 GMGN 按钮；📚 行重复追加时替换旧行，保持卡片仅一行叙事。叙事为纯展示，不参与任何筛选/风控。

#### Scenario: 追加叙事行
- **WHEN** 叙事结果可用且卡片已被编辑为「已开仓」
- **THEN** 卡片文本末尾出现一行 `📚 <叙事句>`，状态行与按钮不变

#### Scenario: 重复追加
- **WHEN** 同一卡片第二次获得叙事结果
- **THEN** 旧 📚 行被替换，卡片始终最多一行 📚

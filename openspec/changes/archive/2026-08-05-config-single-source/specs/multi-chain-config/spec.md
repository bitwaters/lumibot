# multi-chain-config Delta

## ADDED Requirements

### Requirement: 配置单一真源
所有交易规则（止盈止损/冷却/超时）、门禁与筛选阈值、安全阈值、采集间隔、执行限额 MUST 由 `config/chains.yaml` 单一文件控制（链级归 `chains.<name>.*`，全局归 `global.*`）。代码中 MUST NOT 引入规则类硬编码；新规则参数 MUST 先入 yaml 再被代码读取。`.env` 仅承载密钥、chat ID、路径等基础设施配置，MUST NOT 承载交易/筛选规则。配置加载 MUST 在启动时校验，规则参数缺失或非法 MUST 启动失败（fail-fast）。

#### Scenario: 新规则参数先入 yaml
- **WHEN** 新增任何交易/门禁/筛选规则参数
- **THEN** 该参数 MUST 定义在 `config/chains.yaml` 并由代码读取，而非硬编码在源码

#### Scenario: 全局参数归 global 节
- **WHEN** 规则参数不属于任何特定链（如 manage 轮询间隔、双源判定窗口、告警条数）
- **THEN** 该参数 MUST 定义在 `global.*` 并在运行时从配置读取

#### Scenario: 非法配置启动失败
- **WHEN** yaml 中规则参数类型非法或缺失必需参数
- **THEN** 服务 MUST 启动失败并在错误信息中指出具体键

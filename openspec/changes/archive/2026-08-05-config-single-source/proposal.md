# config-single-source

## Why

运营要求：**所有规则必须从一个文件控制**——止盈止损、门禁、筛选、冷却、安全阈值全部由 `config/chains.yaml` 单一文件承载，避免多配置文件造成配置冲突。审计发现主体已满足（strategy/filters/safety/cooldown/execution/sources/global 全部在 yaml），但仍有 3 处规则类硬编码散落在代码里（manage 间隔、双源窗口、告警条数），且「单一配置源」原则从未被 spec 固化——新功能（ca-query 等）可能无意识地引入硬编码。

## What Changes

- **固化原则进 spec**：`multi-chain-config` 新增 Requirement「配置单一真源」——所有交易/门禁/筛选/冷却/安全规则 MUST 由 `config/chains.yaml` 单一文件控制；代码中不得新增规则类硬编码；`.env` 仅承载密钥/chat ID/路径等基础设施。
- **迁移 4 处硬编码到 `global` 节**：
  - `manage_interval_sec: 5.0`（pipeline manage 循环间隔，现硬编码 `5 + uniform(0,2)`）
  - `dual_source_ttl_sec: 30.0`（双源判定窗口，现硬编码 `_dual_source_ttl_sec = 30.0`）
  - `alerts_per_chain: 5`（/alerts 每链条数，现硬编码 `ALERTS_PER_CHAIN`）
  - `trending_defer_budget: 4.0`（trending 轮询限流预算门槛，现硬编码 `available() < 4`）
- 代码改为读取配置值（保持默认值一致的 fallback），注释指向 yaml。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `multi-chain-config`: 新增「配置单一真源」Requirement（含全局参数归属 `global` 节、禁止规则类硬编码）

## Impact

- 代码：`src/lumibot/config.py`（GlobalCfg 新增 3 字段）；`src/lumibot/pipeline.py`（manage 间隔 + 双源窗口读配置）；`src/lumibot/telegram_bot.py`（alerts_per_chain 读配置）；`config/chains.yaml`（global 节补 3 键）
- 行为：无行为变化（默认值与现硬编码一致）
- 测试：配置加载断言（新键默认值）；pipeline/bot 相关测试核对
- 文档：`docs/runtime-params.md` 补 3 键说明；「硬编码 5s」注记更新

## 为什么做

需要一套可自用的 meme 代币信号系统：从 GMGN 拉取实时信号与热度，经分链独立筛选与安全检验后推送到 Telegram，并用与实盘对齐的模拟交易验证策略质量。仓库从零开始，先把多链架构与 SOL 可运行闭环一次设计清楚，避免后期为 BSC / Robinhood 返工。

## 改什么

- 新增 Python 服务：轮询 GMGN `token_signal` + `trending`，经轻量指标与安全检验后推送到私聊与测试群
- 新增按链独立的配置、采集、筛选、去重、统计与限额（SOL / BSC / Robinhood）；P0 仅启用 SOL
- 新增统一 `StrategyOrder` 与执行层抽象：第一版实现 Paper（回本止盈 + 峰值回撤 + 硬止损 + 超时），预留 Live（GMGN swap/策略单）双重安全闸
- 新增 SQLite 持久化：去重冷却、已推送、模拟持仓与盈亏快照
- 新增全局 API 调度（token bucket + security/token-info 缓存），避免多链与二次校验打爆限流
- 第一版不实盘下单、不接私钥；不限 launchpad 平台，靠市值/流动性/热度/安全过滤

## 能力范围

### 新增能力

- `multi-chain-config`：三链配置模型、启用门禁（`calibrated`）、报价资产与分链阈值
- `market-ingestion`：GMGN signal/trending 采集、轮询间隔、全局限流与结果缓存
- `signal-filtering`：轻量筛选、分链安全 profile、跨源去重冷却、A 源 visiting 补查
- `telegram-alerts`：私聊 + 测试群推送、精简卡片、链标签
- `strategy-execution`：StrategyOrder 语义、Paper 执行、价格快照统计、Live Executor 占位与安全闸

### 修改中的既有能力

- （无；仓库尚无既有 spec）

## 影响面

- 新建应用代码（Python + aiogram + GMGN REST + SQLite），当前空仓库无既有模块可改
- 外部依赖：GMGN Agent API（IPv4）、Telegram Bot API
- 运行环境：固定 IPv4 VPS；密钥仅存环境变量 / 本地 `.env`（不入库）
- 后续启用 BSC / Robinhood 时主要改配置与校准状态，不改核心流水线语义

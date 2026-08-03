## 1. 项目脚手架

- [x] 1.1 初始化 Python 项目结构（`src/lumibot/…`）、`pyproject.toml` / requirements、`.env.example`、`.gitignore`
- [x] 1.2 添加依赖：httpx/aiohttp、aiogram、pyyaml、aiosqlite（或 sqlite3）、按需 pydantic/settings
- [x] 1.3 创建默认 `config/chains.yaml`：sol 为 calibrated；bsc/robinhood 为 draft 且禁用；写入已确认阈值
- [x] 1.4 实现配置加载与启动门禁：拒绝 `enabled && calibration_status != calibrated`

## 2. 存储与模型

- [x] 2.1 定义 SQLite 表结构：cooldowns、alerts、paper_positions、paper_fills、snapshots、daily_stats（均含 chain）
- [x] 2.2 实现仓库层：冷却写入/检查、告警与 Paper 持久化
- [x] 2.3 定义归一化模型 `TokenCandidate`、`NormalizedSafety`

## 3. GMGN 客户端与采集

- [x] 3.1 实现 GMGN REST 客户端（API Key 鉴权 + 进程级全局限流 + 强制 IPv4 出站）
- [x] 3.2 实现 429 退避（使用 `reset_at` / `X-RateLimit-Reset`）
- [x] 3.3 按已启用链实现 signal 轮询（类型 12/20）与 trending 轮询（`5m`）
- [x] 3.4 实现 token info / token security 查询，并按 `(chain, address)` 缓存 5 分钟
- [x] 3.5 接入异步调度：SOL 默认 signal 5s、trending 20s
- [x] 3.6 启动时做 IPv4 出站探测；失败则明确报错退出

## 4. 筛选与安全

- [x] 4.1 实现轻量筛选：市值（signal 同时约束 `market_cap`+`trigger_mc`）/ 流动性 / top10 / holders；字段按 design 优先序取值
- [x] 4.2 实现 A 源 visiting 补查（token info）后再决定是否通过
- [x] 4.3 实现 `sol_v1` 安全规则（含字段映射表）
- [x] 4.4 实现 `evm_v1` 安全规则（蜜罐、renounced、开源、税小数 `≤ 0.05`；单测覆盖 0.03 通过 / 0.06 拒绝）
- [x] 4.5 实现同类型 45 分钟、跨源 15 分钟去重（检查+占用原子），并持久化到 SQLite
- [x] 4.6 实现按 `chain + reject_reason`（及 source）的拦截计数与结构化日志

## 5. Telegram 推送

- [x] 5.1 用 aiogram 实现向配置的多个 chat id 扇出推送
- [x] 5.2 渲染精简卡片：`[SOL]|[BSC]|[RH]`、关键指标、安全摘要、GMGN 链接
- [x] 5.3 确保被筛选/安全拦截的候选绝不推送

## 6. 策略与模拟交易

- [x] 6.1 实现共用 `StrategyOrder` 状态机（硬止损相对初始入场、+30% 卖回本且净回收含卖滑点、峰值回撤 30%、4h 超时、滑点）
- [x] 6.2 实现 `PaperExecutor` 开平仓记账与分链统计；同链同 token「检查未平+开仓」原子化，冲突时只推送不开第二仓
- [x] 6.3 实现入场后 1m/5m/15m/1h 价格快照
- [x] 6.4 实现可配置的只读 GMGN 价格源用于盯价
- [x] 6.5 增加 `LiveExecutor` 占位 + 全局/分链开关 + **仅 Live** 日限额校验（UTC 日切；不读私钥、不下真实单；不约束 Paper）

## 7. 流水线串联与运维

- [x] 7.1 组装 SOL Paper 模式端到端 `ChainPipeline`
- [x] 7.2 增加进程入口与优雅退出
- [x] 7.3 增加 Dockerfile / IPv4 VPS 运行说明（可选 compose）
- [x] 7.4 补充最小单测：双市值约束、税率单位、安全 profile、策略硬止损/含卖滑点回本、未平仓跳过开仓、冷却原子占用
- [x] 7.5 使用个人 GMGN API Key 与 Telegram 测试会话做 SOL 冒烟测试

## 8. 多链就绪（不启用）

- [x] 8.1 验证 bsc/robinhood 配置块在禁用状态下可正常加载
- [x] 8.2 编写校准清单文档：`draft` → `calibrated` → `enabled`

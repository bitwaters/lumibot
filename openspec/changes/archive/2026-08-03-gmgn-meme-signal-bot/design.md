## 背景

空仓库从零建设 meme 信号 Telegram bot。数据与交易能力来自 GMGN Agent API（REST；仅 IPv4）。产品形态为自用私聊 + 测试群；第一版只推送与 Paper 模拟，不实盘。已确认三链（SOL / BSC / Robinhood）结构一次设计、P0 仅启用 SOL；BSC/RH 为 EVM 安全骨架、分链阈值，须 `calibrated` 后才能启用。

## 目标 / 非目标

**目标：**

- 实现可运行的 SOL 闭环：采集 → 筛选/安全 → 去重 → TG 推送 → Paper 策略与统计
- 代码与配置按链独立 pipeline，共享推送、策略语义、Executor、限流客户端
- StrategyOrder 与 Paper/Live 执行接口对齐，便于日后切实盘
- 默认阈值、安全规则、报价资产写入配置，避免硬编码散落

**非目标：**

- P0 实盘下单、私钥管理、跟单仓位管理
- 多用户订阅 / TG 动态改规则 UI（仅预留钩子）
- trenches / hot-searches 作为主源（可留扩展位）
- 同时校准并启用 BSC / Robinhood

## 关键决策

### 1. 技术栈：Python + 直接 REST + aiogram + SQLite

- **选择**：自管 GMGN HTTP 客户端，不绑死 `gmgn-sdk`；异步 bot 与双轮询同进程。
- **替代**：Node/Telegraf、或壳脚本调 `gmgn-cli`。
- **理由**：量化脚本习惯、字段可控、单机 SQLite 零运维。

### 2. 架构：Shared 核心 + 分链 Pipeline

```
Scheduler (global rate limit)
  └─ ChainPipeline(sol|bsc|robinhood) if enabled && calibrated
        ├─ SignalPoller / TrendingPoller
        ├─ Enrichment (token info visiting, token security) + cache
        ├─ FilterEngine + SafetyProfile (sol_v1 | evm_v1)
        └─ Deduper
              ├─ TelegramNotifier ([CHAIN] card)
              └─ StrategyEngine → Executor (Paper | Live stub)
```

- 所有持久化 key 含 `chain`。
- 禁止 `bsc_filters = copy(sol_filters)` 作为默认行为。

### 3. 数据源：A+C，求稳补查 visiting

- A：`POST /v1/market/token_signal`，类型 12+20；命中后查 `token info` 取 `visiting_count`。
- C：`GET/trending` 等价接口，`interval=5m`，用返回内 visiting。
- 不限 launchpad 平台（空 allow-list = 不限）。
- Signal 显式请求禁止 14/15/16。
- 市值：signal 要求当前 `market_cap` 与 `trigger_mc`（若有）**同时**落入区间；trending 仅约束当前市值。
- 轻量字段来源优先序：
  - signal：`cur_data` / 同级字段 → 缺失再补查 token info / security
  - trending：rank 载荷字段
  - 补查后仍缺必需字段 → fail-closed 拒绝

### 4. 安全 profile 与字段映射

| Profile | 适用 | 硬拦要点 |
|---------|------|----------|
| `sol_v1` | SOL | mint+freeze renounced；rug/bundler/rat ≤0.3；wash 拒绝；忽略 honeypot 空值 |
| `evm_v1` | BSC, Robinhood | honeypot 拒绝；owner/is_renounced；open_source；买/卖税小数 `≤ 0.05`；rug/bundler/rat ≤0.3；wash 拒绝；忽略 mint/freeze |

- `creator_hold`：告警不硬拦。
- 税率单位：API 返回 `0.03` = 3%；阈值比较一律用小数比例，**禁止**与整数 `5` 比较。

| 逻辑字段 | 优先 API 字段 | 备注 |
|----------|---------------|------|
| honeypot | `is_honeypot` / `honeypot` | SOL 空值忽略 |
| renounced (EVM) | `is_renounced` / `owner_renounced` / `renounced` | yes/true/1 为通过 |
| open_source (EVM) | `is_open_source` / `open_source` | 必需 |
| mint/freeze (SOL) | `renounced_mint` / `renounced_freeze_account` | true/1 |
| buy/sell tax | `buy_tax` / `sell_tax` | 解析为 float，阈值 `≤ 0.05`；空/缺失视为 `0.0` |
| rug | `rug_ratio` | `> 0.3` 硬拦 |
| bundler | 优先 `bundler_rate`，缺失再用 `bundler_trader_amount_rate` | 归一后比较 |
| rat | `rat_trader_amount_rate` | 勿与未映射的 insider 混用 |
| wash | `is_wash_trading` | true 硬拦 |
| visiting | trending.`visiting_count`；signal 用 token info.`visiting_count` | |
| top10 / holders / liq | signal.`cur_data.*` 或 trending rank 同名字段 | 见 §3 优先序 |

### 5. 去重

- 同链同类型：45 分钟 cooldown（`token + signal_type|trending`）。
- 同链跨源：15 分钟 token 级冷却。
- 重启后从 SQLite 恢复冷却窗口。
- 同链冷却「检查 + 占用」必须原子（SQLite 事务或单写者队列），避免双源并发双推。

### 6. 策略与执行

- 统一 `StrategyOrder`：初始入场、名义 $20、买/卖滑点、硬止损相对**初始入场** -20%、+30% 卖回本（**卖出滑点后净回收 ≥ 初始名义**）、成本上移（记账）、入场后峰值回撤 30% 清仓、4h 超时；所有卖出均按卖滑点成交。
- Paper：本地盯价模拟成交；记录 1m/5m/15m/1h 快照；同链同 token「检查未平 + 开仓」原子化，已有未平仓则只推送不再开仓；**不受** Live 日亏损/日笔数限制。
- Live：接口 + `global.live_master_switch` + `chains.<c>.live_enabled` + 单笔/日亏损/日笔数限额（仅 Live，**UTC 日切**）；P0 不实现真实 swap，不读私钥。
- Live 优先路径预留 GMGN 策略单，降级为盯价 + swap。

### 6b. 可观测性

- 按 `chain + reject_reason`（及可选 source）计数：如 `mc` / `liq` / `visiting` / `safety_*` / `cooldown` / `paper_skip_open`。
- 结构化日志需能区分「推送但未开 Paper」与「开仓失败」。

### 7. 分链默认参数（摘要）

| | SOL | BSC (draft) | Robinhood (draft) |
|--|-----|-------------|-------------------|
| enabled | true | false | false |
| calibration | calibrated | draft | draft |
| mc | 50k–2M | 50k–2M | 30k–2M |
| liq | ≥10k | ≥10k | ≥8k |
| top10 | ≤0.30 | ≤0.30 | ≤0.30 |
| holders | ≥100 | ≥100 | ≥80 |
| visiting | ≥100 | ≥80 | ≥50 |
| slip | 5%/5% | 8%/8% | 8%/8% |
| poll | 5s / 20s | 8s / 30s | 8s / 30s |
| quotes | SOL, USDC | BNB, USDC | native 0x0…0, WETH 0x0bd7…ad73 |

### 8. 限流、缓存与 IPv4

- 全局 leaky/token bucket 包裹所有 GMGN 请求。
- `token security` / `token info` 缓存 TTL 5 分钟。
- 429：尊重 `reset_at` / `X-RateLimit-Reset`，禁止狂重试。
- 多链时优先 signal，trending 可降频。
- 客户端强制 IPv4 出站；双栈/仅 IPv6 时启动失败并给出可操作提示。

### 9. 配置与密钥

- YAML/JSON 分链配置；`.env`：`GMGN_API_KEY`、`TELEGRAM_BOT_TOKEN`、chat ids；私钥仅 Live 阶段需要且默认不加载。
- 启动时：`enabled && calibration_status != calibrated` → 失败退出。

## 风险与取舍

- [API 限流 / 多二次校验] → 全局 bucket + 5 分钟缓存；A 源求稳补查 visiting 会增加延迟与消耗
- [Paper 与实盘成交差异] → 统一滑点假设与 StrategyOrder；Live 另开双重闸与按链限额
- [EVM 税/蜜罐字段质量] → 硬拦 + Paper 观察误杀率再调
- [demo key 不可用于生产] → 文档要求个人 API Key + IPv4 VPS
- [信号噪音] → 冷却 + 安全 + visiting；统计面板指导调参

## 分期与回滚

1. P0：实现 shared + SOL calibrated 全链路 Paper，部署单进程到 IPv4 VPS
2. P1：用 Paper 报表调 SOL 阈值
3. P2/P3：校准 BSC / RH → `calibrated` → `enabled`
4. P4：按链评估后打开 Live（仍受全局 master switch）
5. 回滚：关对应 `enabled` 或停进程；SQLite 保留历史不影响重启

## 待决问题

- 个人 GMGN API Key 与 Telegram bot/chat id 部署时提供（不入库）
- Paper 盯价用 `token info` 价格还是 kline 最新价：实施时优先选延迟更低且稳定的只读接口，并在配置中可切换
- GMGN 策略单字段与「卖回本 + 峰值回撤」的映射细节：Live 阶段再 spike，Paper 先完整本地状态机

（已闭合项见历次审查：含回本卖滑点、冷却/开仓原子性、UTC 日切、字段缺失 fail-closed、空税=0、全卖出按卖滑点等。）

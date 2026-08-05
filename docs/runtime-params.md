# 现行运行参数

**唯一真源：`config/chains.yaml`（经 `lumibot.config` 加载）。**

OpenSpec 归档里的 design / delta specs 可能仍写着历史数字（例如硬止损 `-20%`、市值 `$50k–$2M`、超时 `4h`）。那些是当时提案快照，**不以归档文案为准**。

调参、验收、`/help` 展示都以仓库内当前 yaml 与线上部署配置为准。改阈值只改 yaml + 部署，不必回头改已归档 OpenSpec。

## 键位（按链）

出场 / 名义 / 冷却全部在 **`chains.<name>.strategy`**，不再有顶层 `strategy` 真源。

| 区域 | 键 | 含义 |
|------|----|------|
| `chains.<name>.strategy` | `hard_stop_pct` / `stage1_tp_pct` / `trail_drawdown_pct` / `timeout_hours` | 出场（`stage1_tp_pct` 相对 **买入成本含买滑点**；硬止损相对开仓标记） |
| `chains.<name>.strategy` | `stage1_sell_mode` / `stage1_sell_ratio` | 回本减仓：`ratio` 固定比例 / `notional` 回收名义 |
| `chains.<name>.strategy` | `pre_stage1_trail_*` / `timeout_extend_*` / `trail_dynamic` | 回本前追踪、盈利延时、动态回撤 |
| `chains.<name>.strategy` | `loss_cooldown_min` / `post_close_cooldown_min` / `symbol_cooldown_min` | 再入场冷却（`0`=关；symbol 冷却按同名币拦截） |
| `chains.<name>.strategy` | `notional_usd` / `snapshots_sec` | Paper 名义；快照 offset |
| `chains.<name>.filters` | `mc_*` / `liquidity_min` / `liquidity_ratio_min` / `top10_max` / `holders_min` / `visiting_min` / `visiting_min_trending` | 门禁 |
| `chains.<name>.filters` | `volume_1h_min` / `volume_mc_ratio_min` / `age_*` | 量与年龄 |
| `chains.<name>.filters` | `max_mc_extension` / `enforce_mc_extension` | 市值延伸 |
| `chains.<name>.filters` | `chase_max_pct` | signal 追高门禁：执行时新报价比推送价高出的比例上限（`0`=关） |
| `chains.<name>.sources.*` | `interval_sec` / `window`（含可选 `trending_5m`） | 采集 |
| `chains.<name>.execution` | `slippage_*` / `mode` / `limits.max_concurrent_positions` | 成交与并发上限 |
| `global` | `enrichment_cache_ttl_sec` / `security_cache_ttl_sec` / `rate_limit` | 缓存与全局限流 |
| `global.news` | `enabled` / `poll_sec` / `lookback_min` / `min_score` / `edit_timeout_ms` / `min_symbol_len` / `symbol_blocklist` / `market_coins` / `market_keywords` | OpenNews 增强推送。`enabled=true` 仅在 `OPENNEWS_TOKEN` 存在时生效 |

## 环境变量

| 键名 | 说明 | 默认 |
|---|---|---|
| `OPENNEWS_TOKEN` | OpenNews API 调用凭证。为空时即使 `global.news.enabled=true`，后台也不会启动新闻补充。 |
| `LUMIBOT_CONFIG` | 配置文件路径，默认 `config/chains.yaml` |
| `LUMIBOT_DB_PATH` | sqlite 数据库路径，默认 `data/lumibot.db` |

## 快照精度（FL5）

关仓后补写的 due 快照若本机曾长时间离线，缺失的 offset（如 60s/300s）会用**关仓时同一标记价**补齐。这是 best-effort：时间序列在该场景下不精确，仅保证 offset 行存在便于事后对齐。

## 实验轮次归档

`/reset_paper <chain|all> confirm` 不再物理丢弃旧数据：`paper_positions / paper_fills / snapshots / alerts` 在删除前先按 `round_id`（自增轮次序号，1/2/3…）复制进 `*_archive` 表，随后才清空活跃表。`signal_log`（拒绝日志）从不删除；`reject_counts / cooldowns / paper_skip_opens` 无归档价值直接清。

- 查询：`/rounds` 列出归档轮次概览；`/rounds <id>` 查看该轮各链统计与最近平仓
- 直接 SQL 分析：`SELECT * FROM paper_positions_archive WHERE round_id=<id>`；跨轮对比按 `round_id` 分组即可
- 重启不丢：归档表持久化在同一个 lumibot.db

## Live（U1）

`LiveExecutor` 为 Paper-first 桩：不落实盘单、不加载私钥。`execution.mode: live` 仅做风控检查后 noop。实盘路由另开变更。

## 限流优先级（P6）

完整多桶优先级未实现。现状：trending 在 `available() < 4` 时延后轮询，为 post-gate 报价与 manage 留预算。

持仓管理（manage）循环间隔**硬编码 5s**（pipeline `_loop_manage`，含 0-2s jitter），配合全局 1s 最小请求间隔与 token bucket（capacity 20 / refill 6/s），3 并发持仓下安全。

校准流程见 [calibration.md](./calibration.md)。

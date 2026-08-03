# 现行运行参数

**唯一真源：`config/chains.yaml`（经 `lumibot.config` 加载）。**

OpenSpec 归档里的 design / delta specs 可能仍写着历史数字（例如硬止损 `-20%`、市值 `$50k–$2M`、超时 `4h`）。那些是当时提案快照，**不以归档文案为准**。

调参、验收、`/help` 展示都以仓库内当前 yaml 与线上部署配置为准。改阈值只改 yaml + 部署，不必回头改已归档 OpenSpec。

常用键位：

| 区域 | 键 | 含义 |
|------|----|------|
| `strategy` | `hard_stop_pct` / `stage1_tp_pct` / `trail_drawdown_pct` / `timeout_hours` | 出场 |
| `strategy` | `loss_cooldown_min` / `post_close_cooldown_min` | 再入场冷却（`0`=关） |
| `strategy` | `notional_usd` | Paper 名义 |
| `chains.<name>.filters` | `mc_*` / `liquidity_min` / `top10_max` / `holders_min` / `visiting_min` | 门禁 |
| `chains.<name>.filters` | `max_mc_extension` / `enforce_mc_extension` | 市值延伸 |
| `chains.<name>.sources.*.window` | trending 窗口等 | 采集 |
| `chains.<name>.execution` | `slippage_*` / `mode` | 成交与模式 |

校准流程见 [calibration.md](./calibration.md)。

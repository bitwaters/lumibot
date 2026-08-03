# 多链校准清单

流程：`draft` → `calibrated` → `enabled`。启动门禁会拒绝 `enabled && calibration_status != calibrated`。

## 每条链需完成

1. **连通性**：在目标 IPv4 环境用真实 API Key 拉取该链 `token_signal` / trending / token info / security，确认字段齐全。
2. **安全 profile**：SOL 用 `sol_v1`；BSC/RH 用 `evm_v1`。核对蜜罐、renounced、开源、税字段是否与实盘样本一致。
3. **阈值试跑**：用 Paper 观察 24–72h 拦截原因分布（`reject_counts`），再调 mc/liq/top10/holders/visiting。
4. **报价资产**：确认 `quote_tokens` 与日后 Live swap 路径一致。
5. **滑点**：按链流动性设置 `slippage_buy_pct` / `slippage_sell_pct`。
6. **轮询间隔**：在全局限流预算内设置 signal/trending interval。
7. **标记校准**：将 `calibration_status` 改为 `calibrated`，再将 `enabled: true`。
8. **回归**：跑单测 + 短时冒烟，确认冷却、Paper 开仓与告警正常。

## 当前状态

| 链 | status | enabled |
|----|--------|---------|
| sol | calibrated | true |
| bsc | draft | false |
| robinhood | draft | false |

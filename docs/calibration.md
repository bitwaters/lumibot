# 多链校准清单

流程：`draft` → `calibrated` → `enabled`。启动门禁会拒绝 `enabled && calibration_status != calibrated`。

现行数值阈值见 [runtime-params.md](./runtime-params.md)（真源 `config/chains.yaml`）。**每条链的出场规则只写在 `chains.<name>.strategy`**，不要维护第二套 strategy 表。

## 可执行顺序（隔离调参）

1. **连通性**：目标 IPv4 + API Key 抽样该链 signal / trending / info / security / price；记录字段完整率。未通 → 保持 `enabled: false`。
2. **标定并启用**：仅在连通性 go 后将该链 `calibration_status: calibrated` 且 `enabled: true`；其他链保持不动。
3. **只调该链**：观察 Paper / rejects /stats 分节；只改 `chains.<that_chain>.*`（含 strategy）。**不要**在 BSC/RH 校准期间改 `chains.sol`。
4. **压力**：共享 `global.rate_limit`；先拉长或关闭新链 `sources.*.interval_sec` / trending，不动 SOL。
5. **冻结**：更新下表 status；再考虑下一条链。

## 每条链检查项

1. **连通性**：真实 Key 拉 `token_signal` / trending / token info / security。
2. **安全 profile**：`sol`→`sol_v1`；`bsc`/`robinhood`→`evm_v1`（加载时强制绑定）。
3. **阈值试跑**：Paper 24–72h 看 `reject_counts`，再调 mc/liq/top10/holders/visiting。
4. **报价资产**：`quote_tokens` 与日后 Live swap 路径一致。
5. **滑点**：按链流动性设 `slippage_*`。
6. **轮询间隔**：在全局限流预算内设 signal/trending（及可选 `trending_5m`）。
7. **标记校准**：`calibrated` 后再 `enabled: true`。
8. **回归**：单测 + 短时冒烟；TG `/status` `/stats` 按链分节。

## 当前状态

| 链 | status | enabled | 说明 |
|----|--------|---------|------|
| sol | calibrated | true | 主跑 Paper |
| bsc | draft | false | 待连通性（任务 4.x）后再标定 |
| robinhood | draft | false | 待 BSC 稳定后（任务 7.x） |

## 远程重置

```bash
CHAIN=sol ./scripts/reset_paper_remote.sh   # 或 bsc|robinhood|all
```

TG：`/reset_paper <sol|bsc|robinhood|all> confirm`（必须带链作用域，**BREAKING** 相对旧 `/reset_paper confirm`）。

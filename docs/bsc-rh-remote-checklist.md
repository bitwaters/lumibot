# BSC / RH 标定执行清单（推荐顺序）

> 目标：完成 `openspec/changes/bsc-rh-chain-calibration/tasks.md` 中 4.x～7.x 的剩余项并形成可审计证据。

## 0. 前置

1. 在 VPS 上确认 bot 已停止旧进程并切到最新代码。
   - `git status`（工作区干净，当前链路应使用已变更配置）
   - `git rev-parse --short HEAD`
2. 环境变量
   - `GMGN_API_KEY`（BSC / RH）
   - `OPENNEWS_TOKEN`（可选）
   - Telegram 以及 DB 路径不变

## 1. BSC 连通性（任务 4.1）

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/check_chain_connectivity.py --chain bsc --api-key "$GMGN_API_KEY" --json --require-ok
```

验收项（至少满足）：
- `signal_count > 0`
- `trending_count > 0`
- `token_info_ok = True`
- `token_security_ok = True`
- `price_ok = True`
- `errors` 为空（或仅有非关键告警）

若失败，记录 `errors` 并先修 API key/IP/限流后重试（不要推进标定）。

## 2. RH 连通性（任务 4.2）

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/check_chain_connectivity.py --chain robinhood --api-key "$GMGN_API_KEY" --json --require-ok
```

判定标准同上。

## 3. quote_tokens & go/no-go（任务 4.3）

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/check_chain_connectivity.py --chain bsc --api-key "$GMGN_API_KEY" --json --require-quote-tokens
```

抽样 token 直接 `info/security` 后确认：
- BSC `quote_tokens` 是否是 `BNB + USDC`（如需可替换）
- 空安全率是否可接受（作为 BSC Paper 起跑门槛）

## 4. BSC 标定（任务 6）

1) 编辑 `config/chains.yaml`
   - `chains.bsc.calibration_status: calibrated`
   - `chains.bsc.enabled: true`
   - `chains.robinhood.enabled: false`（保持禁用）
2) deploy 到 VPS 后观察
   - `/status`：含 `[SOL]` 与 `[BSC]`
   - `/stats`：分节展示，不混合
   - `/alerts`：`BSC` 与 `SOL` 分链显示
   - `/rejects` 中 `chain` 字段能见到 `bsc`
3) Paper 试跑阶段仅改 BSC
   - `chains.bsc.filters`
   - `chains.bsc.safety`
   - `chains.bsc.sources`
   - `chains.bsc.execution`
   - `chains.bsc.strategy`
   - **SOL 不改、RH 不改**

## 5. RH 标定（任务 7）

同样流程：
1) 复测 RH 连通性与错误率（任务 4.2 复核）
2) `chains.robinhood.calibration_status: calibrated` 且 `chains.robinhood.enabled: true`
3) `/status /stats /alerts` 分链展示
4) 仅改 `chains.robinhood.*` 相关字段

## 6. 闭环收口（任务 8）

- 4.x、6.x、7.x 结果写入 `docs/calibration.md`
- 确认未再在仓外维护策略数值（仅 `config/chains.yaml` + 真实部署配置）

记录模板（建议）：
```
chain: bsc | robinhood
sample_addr: <token address>
signal_count: <int>
trending_count: <int>
token_info_ok: <bool>
token_security_ok: <bool>
price_ok: <bool>
errors: <list>
decision: go/no-go
```
  
执行提示：若你希望把连通性纳入一键脚本，使用 `--require-ok` 可让该命令在未达标时返回码 `2` 自动中断。

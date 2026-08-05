# market-ingestion Specification

## Purpose
GMGN signal / trending 轮询、限流与 enrichment。窗口等间隔以链配置为准（见 [docs/runtime-params.md](../../docs/runtime-params.md)）。
## Requirements
### Requirement: 已启用链双源轮询
对每个已启用且已校准的链，系统 MUST 按配置间隔轮询 GMGN token signal 与 trending。SOL 默认：signal 每 5 秒、trending 每 20 秒。BSC 与 Robinhood 草案默认：signal 每 8 秒、trending 每 30 秒。

#### Scenario: SOL 信号类型
- **WHEN** SOL signal 轮询执行
- **THEN** 仅请求信号类型 12 与 20，且 MUST NOT 显式请求 14、15 或 16

#### Scenario: trending 时间窗
- **WHEN** 对已启用链执行 trending 轮询
- **THEN** 使用间隔 `5m`，除非该链配置另有覆盖

### Requirement: 强制 IPv4 出站
GMGN 客户端 MUST 仅通过 IPv4 出站访问 API。启动时 MUST 探测出站地址族；若仅能走 IPv6 或请求因地址族导致 401/403，MUST 以明确错误失败并提示禁用 IPv6 / 使用 IPv4 网络。

#### Scenario: IPv6-only 环境启动失败可诊断
- **WHEN** 运行环境出站只有 IPv6
- **THEN** 服务 MUST 不以静默空转继续；MUST 输出可操作的 IPv4 相关错误信息

### Requirement: 全局 GMGN 限流
所有 GMGN HTTP 请求 MUST 经过进程级统一限流器。遇到 HTTP 429 时，客户端 MUST 按 `reset_at` 或 `X-RateLimit-Reset` 退避，且 MUST NOT 紧密循环重试。

#### Scenario: 多链共享额度
- **WHEN** 多条链同时启用
- **THEN** 请求共享同一限流器；额度紧张时 signal 轮询优先于 trending

### Requirement: 二次校验结果缓存
系统 MUST 按 `(chain, token_address)` 缓存 `token security` 与 `token info` 响应，TTL 可配置，默认 5 分钟。

#### Scenario: 缓存命中避免重复请求
- **WHEN** 同一代币在 TTL 内再次需要 security 或 visiting 补查
- **THEN** 第二次查找使用缓存，不得对该资源再发 GMGN 请求

### Requirement: Trending default window is 1m
For enabled chains, trending polling MUST use interval `1m` unless the chain config explicitly overrides the window. Supported GMGN windows remain `1m|5m|1h|6h|24h`; `1m` is the minimum.

#### Scenario: SOL default trending window
- **WHEN** SOL trending is enabled with stock config
- **THEN** the trending API is called with interval 1m

### Requirement: Multi-chain enable respects shared rate limit
When more than one chain is enabled, all GMGN calls MUST share the process-wide rate limiter. Under sustained 429 / trending defer, configuration relief MUST target the newly enabled chain's `sources.*.interval_sec` (or disable that chain's trending) before changing another chain's intervals.

#### Scenario: New chain interval adjusted under 429 pressure
- **WHEN** enabling BSC causes sustained 429 while SOL remains enabled
- **THEN** relief edits MUST target `chains.bsc.sources` before `chains.sol.sources`

### Requirement: API chain key for Robinhood
Robinhood market API requests MUST use chain key `robinhood`. Telegram deep links MUST use the `/rh/` path segment. The API chain key and URL segment MUST NOT be conflated.

#### Scenario: Trending uses robinhood chain key
- **WHEN** Robinhood trending polling runs
- **THEN** the GMGN request includes `chain=robinhood`


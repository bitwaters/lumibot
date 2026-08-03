## 1. Per-chain strategy in yaml + config

- [ ] 1.1 Move `StrategyCfg` onto `ChainCfg.strategy` (required); stop using top-level `AppConfig.strategy` for runtime
- [ ] 1.2 Migrate `config/chains.yaml`: copy current top-level strategy into `chains.sol|bsc|robinhood.strategy`; delete top-level `strategy` block
- [ ] 1.3 Loader: ignore legacy top-level `strategy` with warning if present; fail if any chain lacks `strategy`
- [ ] 1.4 Enforce profile binding (`sol`→`sol_v1`, `bsc|robinhood`→`evm_v1`) at load time with tests
- [ ] 1.5 Wire `pipeline` / `PaperExecutor` to `chain_cfg.strategy` only; update all tests/fixtures

## 2. Per-chain TG summaries + DB

- [ ] 2.1 Add `paper_stats_summary(chain: str | None)` (and cooldown counts by chain) — TG uses per-chain calls only
- [ ] 2.2 Rewrite `render_stats` / `cmd_stats` to emit separate `[SOL]` / `[BSC]` / `[RH]` sections (no blended primary totals)
- [ ] 2.3 Rewrite `render_status` / `cmd_status` to list each enabled chain’s mode / opens / cooldowns
- [ ] 2.4 Group `/positions` under per-chain headings when multiple chains have opens
- [ ] 2.5 `/alerts`: fetch up to N per chain (default 5) via `list_recent_alerts(chain=…)` then render under chain headings — do not global-LIMIT-then-group
- [ ] 2.6 `/help` prints each enabled chain’s strategy + slippage from yaml (no single global rule block)
- [ ] 2.7 `reset_paper_experiment(chain | "all")` with subquery deletes for fills/snapshots (see design §5 order); TG `/reset_paper <sol|bsc|robinhood|all> confirm` — bare/`confirm`-only does not delete (**BREAKING**)
- [ ] 2.8 Update `render_reset_paper_hint` / help / remote script (`CHAIN=`) for per-chain vs `all`
- [ ] 2.9 Unit tests: distinct strategy per chain; stats/status/alerts/help do not mix; busy-sol fixture still shows bsc alerts; reset bsc leaves sol fills/snapshots/positions

## 3. Docs aligned to yaml-only strategy

- [ ] 3.1 Update `docs/runtime-params.md`: strategy keys live under `chains.<name>.strategy`; do not paste live numbers
- [ ] 3.2 Update `docs/calibration.md`: executable order connectivity → calibrated+enabled → tune that chain only; status table; no second strategy table

## 4. Connectivity (chains still disabled)

- [ ] 4.1 VPS IPv4 + API key: sample `bsc` signal / trending / info / security / price; record completeness
- [ ] 4.2 Repeat for `robinhood` (API key `robinhood`, TG path `/rh/`)
- [ ] 4.3 Spot-check quote_tokens; go/no-go for BSC Paper from security empty-rate

## 5. EVM / chain regression tests

- [ ] 5.1 `evm_v1` missing honeypot / renounced / open_source → reject
- [ ] 5.2 TG `[BSC]` / `[RH]` labels + gmgn URLs
- [ ] 5.3 Optional: `ChainPipeline("bsc")` smoke with EVM fixtures
- [ ] 5.4 Full pytest green

## 6. BSC trial → enable (isolate from SOL)

- [ ] 6.1 After 4.x go: `chains.bsc` → `calibrated` + `enabled: true`; `robinhood.enabled: false`; deploy
- [ ] 6.2 Smoke: `/status` shows SOL and BSC separately; `/stats` sections independent; rejects keyed by chain
- [ ] 6.3 Paper observe; tune **only** `chains.bsc.*` (including `strategy` if needed) — do not edit `chains.sol`
- [ ] 6.4 Rate-limit pressure → lengthen/pause BSC sources only
- [ ] 6.5 Freeze BSC block; update calibration status table

## 7. Robinhood after BSC stable

- [ ] 7.1 Re-check 4.2; separate deploy: RH `calibrated` + `enabled`; reassess rate limit
- [ ] 7.2 Paper + tune only `chains.robinhood.*`; update calibration table

## 8. Close-out

- [ ] 8.1 Confirm no strategy numbers maintained outside yaml; diff has no accidental SOL edits during BSC/RH work
- [ ] 8.2 Summarize connectivity + final per-chain strategy/filter pointers (keys only) in PR / calibration notes

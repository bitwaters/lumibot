## 1. Per-chain strategy in yaml + config

- [x] 1.1 Move `StrategyCfg` onto `ChainCfg.strategy` (required); stop using top-level `AppConfig.strategy` for runtime
- [x] 1.2 Migrate `config/chains.yaml`: copy current top-level strategy into `chains.sol|bsc|robinhood.strategy`; delete top-level `strategy` block
- [x] 1.3 Loader: ignore legacy top-level `strategy` with warning if present; fail if any chain lacks `strategy`
- [x] 1.4 Enforce profile binding (`sol`→`sol_v1`, `bsc|robinhood`→`evm_v1`) at load time with tests
- [x] 1.5 Wire `pipeline` / `PaperExecutor` to `chain_cfg.strategy` only; update all tests/fixtures

## 2. Per-chain TG summaries + DB

- [x] 2.1 Add `paper_stats_summary(chain: str | None)` (and cooldown counts by chain) — TG uses per-chain calls only
- [x] 2.2 Rewrite `render_stats` / `cmd_stats` to emit separate `[SOL]` / `[BSC]` / `[RH]` sections (no blended primary totals)
- [x] 2.3 Rewrite `render_status` / `cmd_status` to list each enabled chain’s mode / opens / cooldowns
- [x] 2.4 Group `/positions` under per-chain headings when multiple chains have opens
- [x] 2.5 `/alerts`: fetch up to N per chain (default 5) via `list_recent_alerts(chain=…)` then render under chain headings — do not global-LIMIT-then-group
- [x] 2.6 `/help` prints each enabled chain’s strategy + slippage from yaml (no single global rule block)
- [x] 2.7 `reset_paper_experiment(chain | "all")` with subquery deletes for fills/snapshots (see design §5 order); TG `/reset_paper <sol|bsc|robinhood|all> confirm` — bare/`confirm`-only does not delete (**BREAKING**)
- [x] 2.8 Update `render_reset_paper_hint` / help / remote script (`CHAIN=`) for per-chain vs `all`
- [x] 2.9 Unit tests: distinct strategy per chain; stats/status/alerts/help do not mix; busy-sol fixture still shows bsc alerts; reset bsc leaves sol fills/snapshots/positions

## 3. Docs aligned to yaml-only strategy

- [x] 3.1 Update `docs/runtime-params.md`: strategy keys live under `chains.<name>.strategy`; do not paste live numbers
- [x] 3.2 Update `docs/calibration.md`: executable order connectivity → calibrated+enabled → tune that chain only; status table; no second strategy table

## 4. Connectivity (chains still disabled)

- [x] 4.1 VPS IPv4 + API key: sample `bsc` signal / trending / info / security / price; record completeness
      — GO: signal=50, trending=10, info_ok (37 fields), security_ok, price_ok, errors=[]
- [x] 4.2 Repeat for `robinhood` (API key `robinhood`, TG path `/rh/`)
      — GO: signal=14, trending=10, info_ok, security_ok, price_ok, errors=[]
- [x] 4.3 Spot-check quote_tokens; go/no-go for BSC Paper from security empty-rate
      — BNB+USDC ok; security empty-rate 0/10 (10/10 non-empty) → GO

## 5. EVM / chain regression tests

- [x] 5.1 `evm_v1` missing honeypot / renounced / open_source → reject
- [x] 5.2 TG `[BSC]` / `[RH]` labels + gmgn URLs
- [x] 5.3 Optional: `ChainPipeline("bsc")` smoke with EVM fixtures
- [x] 5.4 Full pytest green

## 6. BSC trial → enable (isolate from SOL)

- [x] 6.1 After 4.x go: `chains.bsc` → `calibrated` + `enabled: true`; `robinhood.enabled: false`; deploy
- [x] 6.2 Smoke: `/status` shows SOL and BSC separately; `/stats` sections independent; rejects keyed by chain
      — verified at DB level: reject_counts/alerts/paper_positions keyed by chain; TG rendering covered by unit tests
- [x] 6.3 Paper observe; tune **only** `chains.bsc.*` (including `strategy` if needed) — do not edit `chains.sol`
      — 2026-08-05: 5 opens (4 trending + 1 signal), 1 hard_stop, 1 trail close, 3 open in profit; gates (liq/mc/holders/visiting) filtering as designed; no SOL edits
- [x] 6.4 Rate-limit pressure → lengthen/pause BSC sources only
      — GMGN default limit is 1 req/s; cold-cache bursts + original rates caused a 5-min IP ban.
        Fixes: global `min_interval_sec: 1.0` client throttle + fail-fast during 429 `reset_at`;
        BSC sources reduced to signal 30s / trending 120s. Post-fix: 0 bans over 10+ min.
- [x] 6.5 Freeze BSC block; update calibration status table
      — `chains.bsc` frozen as `calibrated`+`enabled`; table + trial record in docs/calibration.md

## 7. Robinhood after BSC stable

- [x] 7.1 Re-check 4.2; separate deploy: RH `calibrated` + `enabled`; reassess rate limit
      — connectivity re-confirmed GO (4.2); enabled with reduced intervals (signal 30s / trending 120s);
        3 chains running with 0 x 429 over 10+ min (shared 1 req/s throttle holds)
- [x] 7.2 Paper + tune only `chains.robinhood.*`; update calibration table
      — 2026-08-05: 1 open (STONKS, $20), rejects keyed by chain (liq/trigger_mc/mc);
        gates filtering as designed; no tuning yet; calibration table updated

## 8. Close-out

- [x] 8.1 Confirm no strategy numbers maintained outside yaml; diff has no accidental SOL edits during BSC/RH work
      — strategy lives only in chains.yaml (verified: no numbers in code/docs; docs point to yaml keys only).
        NOTE: SOL tuning (visiting_min 350 / hard_stop -0.20 / chase_max_pct / symbol_cooldown_min) was
        added by a concurrent session and swept into rate-limit commits 4e95fc7/745e14e — attributed there,
        not part of bsc-rh work; no further sol edits in bsc-rh commits
- [x] 8.2 Summarize connectivity + final per-chain strategy/filter pointers (keys only) in PR / calibration notes
      — connectivity: sol/bsc/robinhood all GO (records in docs/calibration.md + tasks 4.x);
        per-chain pointers: `chains.sol|bsc|robinhood.filters|safety|strategy|execution` (yaml keys only)

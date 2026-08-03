## 1. Config and schema

- [x] 1.1 Add under `strategy`: `loss_cooldown_min` (180), `post_close_cooldown_min` (45); treat `0` as disabled
- [x] 1.2 Add under `chains.*.filters`: `max_mc_extension` (2.0), `enforce_mc_extension` (false)
- [x] 1.3 Set SOL (and draft chains) `sources.trending.window` to `1m` in `config/chains.yaml`
- [x] 1.4 Wire fields through `config.py` models with validation

## 2. Open-mark hard stop

- [x] 2.1 Add `open_mark` to `StrategyOrder`; hard stop compares mark to `open_mark`
- [x] 2.2 Persist `open_mark` on `paper_positions` (schema + startup backfill using per-chain buy slip, else 0.05)
- [x] 2.3 Pass and store `open_mark` in `PaperExecutor.on_alert` / `try_open_paper`; manage path loads `open_mark` into `StrategyOrder`
- [x] 2.4 Expose `open_mark` on `ExecResult` (or reuse mark) for alert card rendering
- [x] 2.5 Unit tests: −16% from mark does not stop; −20% from mark does

## 3. Unified admission cooldowns and extension

- [x] 3.1 On normal paper close (same write path): arm `post_close` if duration > 0; on `hard_stop` also arm `loss` if duration > 0
- [x] 3.2 Add `has_reentry_block(chain, token)` for active `loss`/`post_close` (legacy acquire alone insufficient)
- [x] 3.3 Pipeline order: filters → safety → extension → re-entry block → try_acquire; reasons `loss_cooldown` / `post_close_cooldown` / `cooldown` / `mc_extension`
- [x] 3.4 Soft extension: over max and enforce false → bump `mc_extension_soft` only
- [x] 3.5 After acquire, pre-open re-check `has_reentry_block`; on block release acquire and do not push/open
- [x] 3.6 Confirm no source whitelist that pushes without open attempt (already-open remains only skip)

## 4. Telegram consistency and observability

- [x] 4.1 Add `abort_paper_open(position_id)` that voids/deletes the new open without arming loss/post_close
- [x] 4.2 On TG any_ok false after `opened`: abort that position + release alert cooldown; skipped_open only releases cooldown
- [x] 4.3 Alert card: open mark, hard-stop basis, slip cost; clear skipped_open messaging
- [x] 4.4 Persist alert payload `exec_status`; `/stats` exposes opened vs skipped_open; quality cohort = newly opened
- [x] 4.5 Reject counters include `loss_cooldown`, `post_close_cooldown`, `mc_extension`, `mc_extension_soft`

## 5. Tests and deploy

- [x] 5.1 Tests: only-loss-row blocks; soft vs enforce extension; acquire+recheck releases cooldown; TG all-fail aborts without re-entry cooldown
- [x] 5.2 Tests: trending window `1m`; open_mark hard stop thresholds; duration 0 disables arming
- [x] 5.3 Run full pytest suite
- [x] 5.4 Commit, push main, `./scripts/deploy_remote.sh`; verify column, loss block, abort path, exec_status in alerts
- [x] 5.5 Smoke: `/status` `/stats` `/rejects`; hard_stop re-entry blocked for 3h
  - 2026-08-03 `be8df99` Up；`open_mark` / `paper_skip_opens` 表存在；`reject_counts` 有 mc/liq/visiting 等；多条 `loss` 冷却约 150–160m 剩余（`loss_cooldown_min=180`），`post_close` 亦在武装

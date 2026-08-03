## 1. Data model and quote path

- [x] 1.1 Add `seen_at` and optional `open_timestamp` on `TokenCandidate`; set `seen_at` at `_handle_signal` / `_handle_trending` entry **before any await**
- [x] 1.2 Extract `open_timestamp` from token info into candidate during enrich (no `creation_timestamp` fallback)
- [x] 1.3 After admission acquire+recheck: fresh `get_price_and_market_cap` with `use_cache=False`; one ~250ms retry; on failure `bump_reject(no_price)`, release cooldown, do not open, do not push
- [x] 1.4 Pass fresh mark/mc into open path; never prefer pre-filter `cand.price` when opening after a successful fresh quote; do not re-run mc filters on the fresh quote
- [x] 1.5 Alert payload: keep `exec_status`; add `latency_ms`; optional `open_timestamp`

## 2. Signal push and shared render helpers

- [x] 2.1 Implement signal push layout (通卡、完整 CA、图标指标两行、安全、延迟、简略执行行)；remove strategy/command footers, source-type headline, and open_mark/slippage detail lines (supersede prior alert-card field requirements)
- [x] 2.2 Format helpers: relative open age, latency seconds, reject/source Chinese label maps covering filters, cooldowns, `no_price`, `safety_fetch`, and known `safety_*`
- [x] 2.3 Restyle paper exit/stage1 cards; prefer MC lines when quote available, else price fallback
- [x] 2.4 Restyle `/positions` `/stats` `/alerts` `/status` `/help`; help documents post-gate quote, stop rules, and gate-snapshot vs execution-quote timing

## 3. Rejects display

- [x] 3.1 Wire label maps into `render_rejects` (信号/热门 + 中文字段名; unknown → raw)
- [x] 3.2 Update rejects/card unit tests

## 4. Tests and deploy

- [x] 4.1 Unit tests: card snapshots opened/skipped; latency/open age; reject labels; no open_mark/slippage lines on push
- [x] 4.2 Integration: post-gate quote failure → no TG, cooldown released, `no_price` reject; success opens with fresh mark/mc on card
- [x] 4.3 Run full pytest; commit/push; deploy; smoke push + `/rejects` + `/help`

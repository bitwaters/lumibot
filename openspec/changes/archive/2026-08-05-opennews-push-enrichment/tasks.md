## 1. Config and settings

- [x] 1.1 Add `global.news` schema in `config.py` (enabled, poll_sec, lookback_min, min_score, edit_timeout_ms, min_symbol_len, symbol_blocklist, market_coins, market_keywords)
- [x] 1.2 Wire defaults into `config/chains.yaml`
- [x] 1.3 Add `OPENNEWS_TOKEN` to Settings; empty token disables news even if enabled

## 2. OpenNews client and cache

- [x] 2.1 Create `src/lumibot/news/opennews.py` REST client with loose JSON parsing
- [x] 2.2 Create in-memory `NewsCache` + background poller (~60s)
- [x] 2.3 Implement `enrich.match_news`：短符号/黑名单跳过代币级；代币优先；市场回落须 `min_score`；摘要清洗截断

## 3. Telegram send/edit

- [x] 3.1 Change notifier send path to return per-chat `(chat_id, message_id)` plus frozen body text and keyboard
- [x] 3.2 Add edit helper: update execution line and/or insert one `📰` line; preserve reply_markup
- [x] 3.3 Support provisional bottom line `⏳ 开仓中` / pre-check `↪️ 未新开` on first send

## 4. Pipeline order fix (push then open)

- [x] 4.1 Keep acquire + re-entry re-check + quote before any push/open side effects
- [x] 4.2 Reorder: provisional card send → only if `any_ok` then `on_alert`; total TG failure skips open and releases cooldown
- [x] 4.3 Preserve already_open / blocked_max_positions：仍推送、不新建仓；满仓释放冷却语义不变
- [x] 4.4 After open/skip, await status edit on successful chats; then start news task with frozen body + final status line
- [x] 4.5 Update tests that assumed open-before-push / abort-on-tg-fail

## 5. News task integration

- [x] 5.1 Start news task only after status edit path has the frozen final execution line (no parallel whole-card rewrite)
- [x] 5.2 Task: match → polish → insert 📰 on all successful chats within `edit_timeout_ms`; done_callback; shutdown cancel
- [x] 5.3 Start/stop news poller with app lifecycle when token present

## 6. Tests and docs

- [x] 6.1 Unit tests: push failure prevents open; push success then open; already_open pre-check on first card
- [x] 6.2 Unit tests: match priority, short-symbol skip, market min_score, no-token disable
- [x] 6.3 Unit tests: freeze-text insert; multi-chat edit; edit failure leaves original
- [x] 6.4 Note `OPENNEWS_TOKEN` in `.env.example` or runtime docs if present

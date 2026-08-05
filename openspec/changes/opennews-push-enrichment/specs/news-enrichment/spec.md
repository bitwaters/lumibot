## ADDED Requirements

### Requirement: Immediate push then optional news edit
After admission and a successful Telegram signal send, the system MUST start a background task that MAY edit the original message(s) to append at most one news line and/or refresh the execution status line. The initial send MUST NOT await OpenNews. News MUST NOT gate admission or the initial send. Missing token, timeout, no match, or edit failure MUST leave the first card unchanged for the news line (fail-open).

#### Scenario: First send does not wait for news
- **WHEN** a candidate is admitted and Telegram send runs
- **THEN** the first message is sent without awaiting OpenNews

#### Scenario: Background edit adds one news line
- **WHEN** enrichment finds an eligible news hit within the edit timeout after a successful send
- **THEN** each successfully sent chat message is edited to include exactly one `📰` line while preserving the card body metrics and GMGN inline keyboard

#### Scenario: News failure does not reverse a successful open
- **WHEN** OpenNews is unavailable or edit fails after push succeeded and paper open succeeded
- **THEN** the system MUST NOT abort the paper position solely due to news failure

### Requirement: Token then market news matching
Enrichment MUST prefer token-related news using symbol/name keywords when the symbol passes length and blocklist checks. Short symbols or blocklisted tickers MUST skip token-level search. If no token hit, the system MAY use market-level news only when the AI score is at least `min_score`. Copy MUST label hits as 相关 or 市场 and MUST NOT claim contract-address-confirmed narrative.

#### Scenario: Short symbol skips token search
- **WHEN** symbol length is below `min_symbol_len` or symbol is blocklisted
- **THEN** enrichment skips token-level OpenNews search and only considers market fallback

#### Scenario: Market fallback requires high score
- **WHEN** there is no token-level hit and market news score is below `min_score`
- **THEN** the system MUST NOT edit the message for market news

### Requirement: OpenNews disabled without token
When `OPENNEWS_TOKEN` is empty or `global.news.enabled` is false, the system MUST NOT call OpenNews; push-then-open ordering MUST still apply.

#### Scenario: No token
- **WHEN** the bot starts without OPENNEWS_TOKEN
- **THEN** pushes and opens proceed without background news tasks

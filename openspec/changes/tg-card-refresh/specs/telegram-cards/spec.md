## ADDED Requirements

### Requirement: Unified signal push card layout
After admission passes, Telegram signal push MUST use a single “信号推送” card template for all sources. The title MUST NOT feature smart-money / KOL / trending as the primary headline. The full contract address MUST appear on its own line without an icon so operators can copy it. Strategy rules and command footers MUST NOT appear on the push card. The push card MUST NOT require open_mark, hard-stop basis, or buy-slippage cost lines (those details live in `/help` and position management; Paper hard stop still uses persisted open_mark).

#### Scenario: Opened push shape
- **WHEN** a candidate is admitted and paper status is opened
- **THEN** the message includes `信号推送`, full CA on its own line, metric/safety/latency/open-age lines with the agreed icons, and a brief bottom line such as `✅ 已开仓 $20`

#### Scenario: Skipped open
- **WHEN** paper status is skipped_open
- **THEN** the bottom line briefly indicates already-open skip without repeating strategy text

### Requirement: Open age and end-to-end latency on push
The signal push card MUST show relative open age from GMGN `open_timestamp` when available, and MUST show end-to-end latency from local first-seen time of the candidate to send time. `seen_at` MUST be recorded at handler entry before any await. Missing open timestamp MUST render as a dash and MUST NOT block push/open by itself.

#### Scenario: Latency displayed
- **WHEN** a push is sent
- **THEN** the card includes a latency line derived from seen_at → send time

#### Scenario: Missing open timestamp
- **WHEN** token info has no open_timestamp
- **THEN** the card shows open age as unavailable and admission/open may still proceed

### Requirement: Command and exit cards share visual language
`/positions`, `/stats`, `/rejects`, `/alerts`, `/status`, `/help`, and paper exit/stage1 notifications MUST follow the same icon/title style as the signal push redesign. Strategy detail MUST live primarily in `/help`. Exit cards MAY fall back to price-based lines when market cap is unavailable.

#### Scenario: Help holds rules
- **WHEN** operator requests /help
- **THEN** hard-stop / stage1 / trail / timeout / re-entry and post-gate quote rule are documented there

#### Scenario: Exit without market cap
- **WHEN** a paper close notification is sent and market cap cannot be obtained
- **THEN** the card may use price fields while keeping the shared title/icon style

### Requirement: Reject reasons show Chinese field labels
`/rejects` MUST map stored reason codes to Chinese field names for display, including filter reasons, cooldown reasons, `no_price`, `safety_fetch`, and known `safety_*` codes (e.g. mc → 市值, visiting → 热度, loss_cooldown → 硬止损冷却). Source values signal/trending MUST display as 信号/热门. Unknown codes MUST fall back to the raw code.

#### Scenario: Mapped reject row
- **WHEN** reject_counts contains reason mc for source signal
- **THEN** /rejects shows a Chinese label for 市值 and 信号 rather than only raw codes

# telegram-cards Specification

## Purpose
信号推送与命令/出场卡的通卡版式；策略数字展示以配置与 `/help` 为准（[docs/runtime-params.md](../../docs/runtime-params.md)）。
## Requirements
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

### Requirement: Optional post-send news line on signal cards
Signal push cards MAY later gain a single plain-text news line via Telegram message edit after the initial send. The edit MUST preserve metric/safety/latency body content and the GMGN inline keyboard. The initial send MUST remain valid without any news line.

#### Scenario: Edit preserves keyboard
- **WHEN** a signal card is edited to add a news line
- **THEN** the GMGN button reply markup remains present on the edited message

#### Scenario: Initial card stays valid without news
- **WHEN** news enrichment does not edit the message
- **THEN** the original signal-push card still satisfies the unified layout requirements

### Requirement: Provisional execution line before open
When the signal card is sent before Paper open completes, the bottom execution line MUST NOT claim `已开仓`. It MUST use a provisional status such as `⏳ 开仓中`, unless a read-only pre-check already determines `skipped_open` (already open). After open completes, an edit MAY update the execution line to the final status.

#### Scenario: First card before new open
- **WHEN** admission passes, no open position exists, and the first Telegram send occurs before `on_alert`
- **THEN** the card does not show `✅ 已开仓` on that first send

### Requirement: Help documents each enabled chain from yaml
`/help` MUST list strategy and slippage rules per enabled chain by reading `chains.<name>.strategy` and `chains.<name>.execution` from the loaded config. It MUST NOT print a single hard-coded rule block as if one global strategy applied to all chains.

#### Scenario: Two enabled chains show two rule blocks
- **WHEN** sol and bsc are enabled with different `hard_stop_pct`
- **THEN** `/help` includes both values under their chain labels


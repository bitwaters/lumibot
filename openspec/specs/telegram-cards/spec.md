# telegram-cards Specification

## Purpose
信号推送与命令/出场卡的通卡版式；策略数字展示以配置与 `/help` 为准（[docs/runtime-params.md](../../docs/runtime-params.md)）。
## Requirements
### Requirement: Unified signal push card layout
After admission passes, Telegram signal push MUST use a single "信号推送" card template for all sources, rendered as HTML rich text. The title MUST lead with the token symbol (`📡 $SYM · CHAIN`, with `· 双源` when dual-source) and MUST NOT feature smart-money / KOL / trending as the primary headline. The full contract address MUST appear on its own line as a `📍 CA:` label followed by a monospace code block so operators can select and copy it; a copy button MUST NOT be added. Strategy rules and command footers MUST NOT appear on the push card. The push card MUST NOT require open_mark, hard-stop basis, or buy-slippage cost lines (those details live in `/help` and position management; Paper hard stop still uses persisted open_mark).

#### Scenario: Opened push shape
- **WHEN** a candidate is admitted and paper status is opened
- **THEN** the message includes the symbol-led title, `📍 CA:` code block, `📊 指标` section, metric/safety lines with the agreed labels (市值/开盘/流动性/持有人/Top10/热度/1H 成交/平台), a bold status line such as `✅ 已开仓 $20.00`, and the per-chain button group

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
`/positions`, `/stats`, `/rejects`, `/alerts`, `/status`, `/help`, CA query cards, and paper exit/stage1 notifications MUST follow the same HTML rich-text card style as the signal push redesign: symbol-led titles, bold section titles and values, token addresses as `📍 CA:` monospace code blocks, aligned monospace metric grids, and the per-chain button group on token cards. Strategy detail MUST live primarily in `/help`. Exit cards MAY fall back to price-based lines when market cap is unavailable; price-based lines MUST label fields as 入场价/现价/峰值. After a stage1 partial sell, the cost line MUST reflect the sell mode: `已回本 · 剩余仓位零成本` for notional mode, `剩余仓位成本按减仓价计算` for ratio mode. CA query cards MUST use the `🔍` icon in the title to distinguish from signal push (`📡`), MUST include a price row, and MUST NOT include paper status or latency lines, and MAY carry a `📚` LLM narrative line.

#### Scenario: Help holds rules
- **WHEN** operator requests /help
- **THEN** hard-stop / stage1 / trail / timeout / re-entry and post-gate quote rule are documented there

#### Scenario: Exit without market cap
- **WHEN** a paper close notification is sent and market cap cannot be obtained
- **THEN** the card uses explicitly labeled price fields while keeping the shared title/icon style

#### Scenario: Stage1 cost line by mode
- **WHEN** a stage1 event carries a sell mode
- **THEN** the card shows the mode-specific cost wording (`已回本 · 剩余仓位零成本` or `剩余仓位成本按减仓价计算`)

#### Scenario: Query card identity
- **WHEN** a CA query card is rendered
- **THEN** it leads with `🔍 $SYM · CHAIN`, contains a `📍 CA:` code block, the aligned metric grid including a price row, and the per-chain button group, without paper status or latency lines

### Requirement: Reject reasons show Chinese field labels
`/rejects` MUST map stored reason codes to Chinese field names for display, including filter reasons, cooldown reasons, `no_price`, `safety_fetch`, and known `safety_*` codes (e.g. mc → 市值, visiting → 热度, loss_cooldown → 硬止损冷却). Source values signal/trending MUST display as 信号/热门. Unknown codes MUST fall back to the raw code.

#### Scenario: Mapped reject row
- **WHEN** reject_counts contains reason mc for source signal
- **THEN** /rejects shows a Chinese label for 市值 and 信号 rather than only raw codes

### Requirement: Optional post-send narrative line on signal cards
Signal push cards MAY later gain a single plain-text narrative line via Telegram message edit after the initial send (OpenNews/6551 news feature was removed; LLM narrative labels replace it). The edit MUST preserve metric/safety/latency body content and the GMGN inline keyboard. The initial send MUST remain valid without any narrative line. The narrative line MUST use the `📚` prefix and MUST NOT exceed one line per card.

#### Scenario: Edit preserves keyboard
- **WHEN** a signal card is edited to add a narrative line
- **THEN** the GMGN button reply markup remains present on the edited message

#### Scenario: Initial card stays valid without narrative
- **WHEN** narrative enrichment does not edit the message (LLM unavailable, N/A, timeout, disabled)
- **THEN** the original signal-push card still satisfies the unified layout requirements

#### Scenario: Narrative line replaced on repeat edit
- **WHEN** the same card receives a second narrative line
- **THEN** the previous `📚` line is replaced; the card never carries more than one narrative line

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


# telegram-cards Delta

## MODIFIED Requirements

### Requirement: Unified signal push card layout
After admission passes, Telegram signal push MUST use a single "信号推送" card template for all sources, rendered as HTML rich text. The title MUST lead with the token symbol (`📡 $SYM · CHAIN`, with `· 双源` when dual-source) and MUST NOT feature smart-money / KOL / trending as the primary headline. The full contract address MUST appear on its own line as a `📍 CA:` label followed by a monospace code block so operators can select and copy it; a copy button MUST NOT be added. Strategy rules and command footers MUST NOT appear on the push card. The push card MUST NOT require open_mark, hard-stop basis, or buy-slippage cost lines (those details live in `/help` and position management; Paper hard stop still uses persisted open_mark).

#### Scenario: Opened push shape
- **WHEN** a candidate is admitted and paper status is opened
- **THEN** the message includes the symbol-led title, `📍 CA:` code block, `📊 指标` section, metric/safety lines with the agreed labels (市值/开盘/流动性/持有人/Top10 持有/热度/1H 成交/平台), a bold status line such as `✅ 已开仓 $20.00`, and the per-chain button group

#### Scenario: Skipped open
- **WHEN** paper status is skipped_open
- **THEN** the bottom line briefly indicates already-open skip without repeating strategy text

### Requirement: Command and exit cards share visual language
`/positions`, `/stats`, `/rejects`, `/alerts`, `/status`, `/help`, and paper exit/stage1 notifications MUST follow the same HTML rich-text card style as the signal push redesign: bold section titles and values, token addresses as code blocks, and the per-chain button group on exit cards. Strategy detail MUST live primarily in `/help`. Exit cards MAY fall back to price-based lines when market cap is unavailable; price-based lines MUST label fields as 入场价/现价/峰值. After a stage1 partial sell, the cost line MUST reflect the sell mode: `已回本 · 剩余仓位零成本` for notional mode, `剩余仓位成本按减仓价计算` for ratio mode.

#### Scenario: Help holds rules
- **WHEN** operator requests /help
- **THEN** hard-stop / stage1 / trail / timeout / re-entry and post-gate quote rule are documented there

#### Scenario: Exit without market cap
- **WHEN** a paper close notification is sent and market cap cannot be obtained
- **THEN** the card uses explicitly labeled price fields while keeping the shared title/icon style

#### Scenario: Stage1 cost line by mode
- **WHEN** a stage1 event carries a sell mode
- **THEN** the card shows the mode-specific cost wording (`已回本 · 剩余仓位零成本` or `剩余仓位成本按减仓价计算`)

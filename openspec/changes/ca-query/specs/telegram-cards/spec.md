# telegram-cards Delta

## MODIFIED Requirements

### Requirement: Command and exit cards share visual language
`/positions`, `/stats`, `/rejects`, `/alerts`, `/status`, `/help`, CA query cards, and paper exit/stage1 notifications MUST follow the same HTML rich-text card style as the signal push redesign: symbol-led titles, bold section titles and values, token addresses as `📍 CA:` monospace code blocks, aligned monospace metric grids, and the per-chain button group on token cards. Strategy detail MUST live primarily in `/help`. Exit cards MAY fall back to price-based lines when market cap is unavailable; price-based lines MUST label fields as 入场价/现价/峰值. After a stage1 partial sell, the cost line MUST reflect the sell mode: `已回本 · 剩余仓位零成本` for notional mode, `剩余仓位成本按减仓价计算` for ratio mode. CA query cards MUST use the `🔍` icon in the title to distinguish from signal push (`📡`), MUST include a price row, and MUST NOT include paper status, latency, or news lines.

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

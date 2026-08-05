# telegram-card-layout Delta

## MODIFIED Requirements

### Requirement: Signal push card structure
The signal push card MUST use the structure: title line, CA block line, `📊 指标` section header, metric rows, `🛡` safety line, status line, optional `📚` narrative block (sentence line plus optional `🔗` link line; replaced the legacy `📰` news line), and inline buttons. The title MUST lead with the token symbol (`📡 $SYM · CHAIN`), with a `· 双源` badge appended only when the candidate is dual-source. The full contract address MUST appear on its own line as a `📍 CA:` label followed by a monospace code block, so operators can select and copy it by long-press; a copy button MUST NOT be added. Missing metrics MUST render as `—` and MUST NOT block the card.

#### Scenario: Opened push card shape
- **WHEN** a candidate is admitted and paper status is opened
- **THEN** the card contains the symbol-led title, `📍 CA:` code block, `📊 指标` section, metric rows, safety line, and a bold status line such as `✅ 已开仓 $20.00 · ⏱ 延迟 1.8s`

#### Scenario: Trigger reference on market cap
- **WHEN** the source is signal and trigger_mc is available
- **THEN** the market cap row shows the trigger reference, e.g. `💰 市值 $125K → 触发 $100K (+25%)`; otherwise the row shows only the current market cap

#### Scenario: Narrative block position and shape
- **WHEN** an async narrative edit appends a narrative block
- **THEN** the block is the last text lines of the card (after the status line, before the buttons): a `📚` sentence line followed by a `🔗` link line when social links exist; a later narrative edit replaces the previous block

#### Scenario: Narrative content escaped
- **WHEN** a narrative line contains HTML metacharacters from the LLM output
- **THEN** it is escaped before insertion and renders as literal text

#### Scenario: Status line with latency for every state
- **WHEN** a card is rendered in any paper state (opening, opened, skipped_open, blocked_max_positions, no_price, executor_error, blocked_live)
- **THEN** the status line shows the state marker and, when latency is known, `⏱ 延迟 Xs` on the same line

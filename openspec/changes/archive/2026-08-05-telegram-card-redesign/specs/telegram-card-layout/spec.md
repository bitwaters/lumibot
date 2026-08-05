# telegram-card-layout Specification

## Purpose
所有回复卡片的统一富文本版式语言：HTML 格式化、分节结构、CA 等宽块、按钮组与字段术语规范。

## ADDED Requirements

### Requirement: Cards render as HTML rich text with escaping
All reply cards MUST be sent with `parse_mode="HTML"`. External data (token symbol, token name, contract address, platform) MUST be HTML-escaped before insertion. Key values (title symbol, metric values, PnL, status) MUST be bold.

#### Scenario: External data escaped
- **WHEN** a token symbol contains HTML metacharacters (e.g. `PEPE<3`)
- **THEN** the card renders the literal symbol without markup injection or parse errors

#### Scenario: Values emphasized
- **WHEN** any card is rendered
- **THEN** numeric values, PnL, and section titles are bold while labels remain regular weight

### Requirement: Signal push card structure
The signal push card MUST use the structure: title line, CA block line, `📊 指标` section header, metric rows, `🛡` safety line, status line, optional `📰` news line, and inline buttons. The title MUST lead with the token symbol (`📡 $SYM · CHAIN`), with a `· 双源` badge appended only when the candidate is dual-source. The full contract address MUST appear on its own line as a `📍 CA:` label followed by a monospace code block, so operators can select and copy it by long-press; a copy button MUST NOT be added. Missing metrics MUST render as `—` and MUST NOT block the card.

#### Scenario: Opened push card shape
- **WHEN** a candidate is admitted and paper status is opened
- **THEN** the card contains the symbol-led title, `📍 CA:` code block, `📊 指标` section, metric rows, safety line, and a bold status line such as `✅ 已开仓 $20.00 · ⏱ 延迟 1.8s`

#### Scenario: Trigger reference on market cap
- **WHEN** the source is signal and trigger_mc is available
- **THEN** the market cap row shows the trigger reference, e.g. `💰 市值 $125K → 触发 $100K (+25%)`; otherwise the row shows only the current market cap

#### Scenario: News line position
- **WHEN** an async news edit appends a news line
- **THEN** the `📰` line is the last text line of the card (after the status line, before the buttons), and a later news edit replaces the previous `📰` line

#### Scenario: News content escaped
- **WHEN** a news line contains HTML metacharacters from an external source
- **THEN** it is escaped before insertion and renders as literal text

#### Scenario: Status line with latency for every state
- **WHEN** a card is rendered in any paper state (opening, opened, skipped_open, blocked_max_positions, no_price, executor_error, blocked_live)
- **THEN** the status line shows the state marker and, when latency is known, `⏱ 延迟 Xs` on the same line

### Requirement: Metric field semantics
The signal card MUST display these metrics with the specified Chinese labels and data sources: 市值 (market_cap), 开盘 (open age), 流动性 (liquidity), 持有人 (holder_count), `Top10 持有` (top10_rate), 热度 (visiting_count), `1H 成交` (volume_1h), 平台 (platform, only when present). Buy/sell taxes MUST be shown as `买税 X% · 卖税 Y%` on the safety line only when at least one tax is above zero. The term `投入` MUST be used for the deployed position amount (notional_usd); the term `名义` MUST NOT appear on any card. Price-fallback rows MUST label price fields explicitly (`入场价`, `现价`, `峰值`) when market cap is unavailable.

#### Scenario: Added fields displayed
- **WHEN** volume_1h, platform, or taxes are available
- **THEN** `1H 成交`, `平台`, and `买税/卖税` appear on the card

#### Scenario: Price fallback labels
- **WHEN** a paper event or position lacks market cap data
- **THEN** the card falls back to price lines labeled `入场价`/`现价`/`峰值` and uses `投入` for the deployed amount

### Requirement: Inline buttons per chain
The signal and paper-event cards MUST include a GMGN button for every chain. A DexScreener button MUST be included for sol and bsc chains and MUST NOT be included for chains without DexScreener support (e.g. robinhood). A copy button MUST NOT be added; CA copying relies on the code block text selection.

#### Scenario: SOL card buttons
- **WHEN** a card is rendered for a sol token
- **THEN** the inline keyboard shows both GMGN and DexScreener buttons

#### Scenario: Robinhood card buttons
- **WHEN** a card is rendered for a robinhood token
- **THEN** the inline keyboard shows only the GMGN button

### Requirement: Paper event card structure
Paper exit/stage1 notifications MUST share the signal card's visual language: title with the close icon, symbol, chain tag, reason, and a bold PnL; a `📍 CA:` code block; metric lines with bold values; and the per-chain button group. The cost line after a stage1 partial sell MUST depend on the sell mode: notional mode shows `已回本 · 剩余仓位零成本`, ratio mode shows `剩余仓位成本按减仓价计算`.

#### Scenario: Notional-mode stage1 card
- **WHEN** a stage1 event with sell_mode `notional` is rendered
- **THEN** the card includes `📌 已回本 · 剩余仓位零成本` and `回收约 $X · 剩余仓位继续持有`

#### Scenario: Ratio-mode stage1 card
- **WHEN** a stage1 event with sell_mode `ratio` is rendered
- **THEN** the card includes `📌 剩余仓位成本按减仓价计算`

### Requirement: Command cards share the visual language
`/positions`, `/stats`, `/rejects`, `/alerts`, `/status`, `/rounds`, `/help`, and `/reset_paper` cards MUST use HTML formatting with bold section titles (`[SOL]`) and bold values, and MUST render token addresses as code blocks. Internal jargon MUST NOT appear on user-facing cards: 仓位行→持仓, 均赢→均盈, `均亏 $-X`→`均亏 -$X`, 快照 (as a deleted-data list item) removed, and `/help` MUST phrase gate semantics as 筛选通过 rather than 过门/门控.

#### Scenario: Stats card terminology
- **WHEN** /stats renders per-chain summaries
- **THEN** section headers and values are bold and the deployed amount is labeled 投入

#### Scenario: Rounds card consistency
- **WHEN** /rounds renders win/loss averages
- **THEN** labels use 均盈/均亏 and negative PnL uses the `-$X` format consistent with all other cards

#### Scenario: Reset card wording
- **WHEN** /reset_paper renders its success card
- **THEN** deleted position rows are labeled 持仓 (not 仓位行) and internal snapshot jargon is absent

### Requirement: Quick command menus optimized
The slash command menus MUST be ordered by usage frequency: monitoring commands first (`/positions`, `/stats`, `/alerts`, `/status`, `/rejects`, `/rounds`), then `/help` and `/start`, with configuration commands (`/chatid`, `/reset_paper`) last. Descriptions MUST use consistent noun-style wording (当前模拟持仓 / 盈亏统计 / 最近告警 / 运行状态 / 拦截原因 Top / 历史轮次 / 帮助与模拟规则 / 开始使用 / 获取 chat_id / 清空模拟（需 confirm）). The group menu MUST include `/chatid` and MUST exclude `/reset_paper`. The command list inside `/help` MUST match the new menu order.

#### Scenario: Private menu order
- **WHEN** commands are registered for private chats
- **THEN** the menu lists positions, stats, alerts, status, rejects, rounds, help, start, reset_paper, chatid in that order

#### Scenario: Group menu order
- **WHEN** commands are registered for group chats
- **THEN** the menu lists the same order without reset_paper and with chatid included

#### Scenario: Help command list consistency
- **WHEN** /help renders its command line
- **THEN** the command order matches the quick command menu order

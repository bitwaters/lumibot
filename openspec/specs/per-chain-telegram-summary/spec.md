# per-chain-telegram-summary Specification

## Purpose
TBD - created by archiving change bsc-rh-chain-calibration. Update Purpose after archive.
## Requirements
### Requirement: Stats card is partitioned by chain
`/stats` MUST render a separate section per chain that has paper activity or is enabled, labeled with that chain's tag (`[SOL]` / `[BSC]` / `[RH]`). Each section's open count, notional, closed count, realized pnl, opened count, skipped-open count, and hard-stop ratio MUST be computed from that chain's rows only. The card MUST NOT present a single blended total as the primary summary when multiple chains are in play.

#### Scenario: Two chains do not blend opened counts
- **WHEN** sol has 3 opened positions (lifetime in cohort) and bsc has 2
- **THEN** `/stats` shows sol opened 3 in the SOL section and bsc opened 2 in the BSC section, not a single “本轮开仓 5” as the only headline

### Requirement: Status card lists each enabled chain
`/status` MUST list each enabled chain with its execution mode, open position count, and active cooldown count for that chain. It MUST NOT show only the first enabled chain's mode as if it were global.

#### Scenario: Sol and bsc both appear
- **WHEN** sol and bsc are enabled
- **THEN** `/status` includes both chain tags and each mode/open/cooldown line refers to that chain alone

### Requirement: Positions grouped by chain when multi-chain
When open positions span multiple chains, `/positions` MUST group rows under per-chain headings (or equivalent clear partition) so operators do not read a mixed bag without chain context.

#### Scenario: Mixed open book
- **WHEN** there is at least one open sol position and one open bsc position
- **THEN** the positions reply separates them under SOL and BSC groups

### Requirement: Alerts grouped by chain with per-chain limits
`/alerts` MUST partition recent alerts by chain (chain headings with per-chain recency inside each group). When loading rows, the system MUST fetch up to N recent alerts **per chain** (default N=5) rather than applying a single global LIMIT across all chains and then grouping (which can omit quieter chains).

#### Scenario: Sol and bsc alerts partitioned
- **WHEN** recent alerts include both sol and bsc rows
- **THEN** the alerts reply shows separate SOL and BSC groups

#### Scenario: Busy sol does not starve bsc alerts
- **WHEN** sol has dozens of newer alerts than bsc
- **THEN** `/alerts` still includes up to N bsc alerts in the BSC group, not only sol rows from a global top-N

### Requirement: Per-chain paper reset command
`/reset_paper` MUST require an explicit chain scope and `confirm`. `/reset_paper <chain> confirm` (chain in `sol|bsc|robinhood`) MUST delete only that chain's cohort: fills and snapshots for that chain's position ids (via `position_id IN (SELECT id FROM paper_positions WHERE chain=?)`), then that chain's positions, skip-opens, cooldowns, alerts, and reject_counts, in one write transaction. `/reset_paper all confirm` MUST clear every chain. Invocations without a scope (including legacy `/reset_paper confirm`) or without `confirm` MUST NOT delete data and MUST show usage.

#### Scenario: Reset bsc leaves sol intact
- **WHEN** both sol and bsc have paper positions and the operator sends `/reset_paper bsc confirm`
- **THEN** bsc paper/alert/reject/cooldown rows are removed and sol rows remain

#### Scenario: Bare reset is a no-op
- **WHEN** the operator sends `/reset_paper` or `/reset_paper confirm` without a chain or `all`
- **THEN** no tables are cleared and the reply explains `/reset_paper sol|bsc|robinhood|all confirm`


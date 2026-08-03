## ADDED Requirements

### Requirement: Alert card shows mark stop context
When a Paper position is opened, the Telegram alert MUST include open mark (or equivalent), hard-stop line reference, and buy-fill / slip cost context in plain text so operators can verify stop basis.

#### Scenario: Opened card fields
- **WHEN** exec status is opened
- **THEN** the card text includes open mark and indicates the hard stop is relative to that mark

### Requirement: Skipped-open already-open messaging
When admission passed but open was skipped because a position already exists, the card MUST state that simulation did not open a second position for that reason.

#### Scenario: Already open card
- **WHEN** paper status is skipped_open
- **THEN** the card includes a clear already-open skip message

### Requirement: Alert payload records exec_status
When an alert is persisted after successful Telegram delivery, the payload MUST include `exec_status` reflecting the paper result for that admission (at least `opened` and `skipped_open`).

#### Scenario: Opened alert payload
- **WHEN** a new position was opened and Telegram any_ok is true
- **THEN** insert_alert payload contains exec_status opened

### Requirement: Stats separate opens from already-open skips
Paper stats surfaces MUST expose counts that distinguish newly opened positions from admission-passed already-open skips, preferably derived from persisted alert exec_status and/or position rows. Push-quality judgment for trading outcomes MUST primarily use the newly opened cohort. Already-open skips MUST NOT be counted as admission rejects. Soft extension breaches MUST appear in reject/observability counters without blocking admission when enforce is false.

#### Scenario: Rejects vs skips
- **WHEN** operators query reject counts and paper stats
- **THEN** admission rejects are counted in rejects, already-open skips are counted separately from opens, and mc_extension_soft is visible when soft mode records breaches

#### Scenario: Quality cohort
- **WHEN** operators assess alert trading quality by source
- **THEN** win rate and PnL summaries are based on positions that were newly opened, not on skipped_open-only alerts

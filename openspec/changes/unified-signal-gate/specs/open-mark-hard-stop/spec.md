## ADDED Requirements

### Requirement: Persist open mark at paper entry
When opening a Paper position, the system MUST store `open_mark` as the mark price used at entry (before buy slippage). Buy fill price MAY remain `open_mark * (1 + buy_slip)` for cost and quantity accounting.

#### Scenario: Open stores both prices
- **WHEN** Paper opens at mark M with buy slip s
- **THEN** the position record stores open_mark = M and entry_price = M * (1 + s)

### Requirement: Hard stop references open mark
Paper hard-stop evaluation MUST compare the current mark to `open_mark * (1 + hard_stop_pct)`, NOT to the buy-fill `entry_price`. Default `hard_stop_pct` remains -0.20.

#### Scenario: Sixteen percent drop from mark does not stop
- **WHEN** open_mark is 1.0, buy slip is 5%, entry_price is 1.05, and current mark is 0.84
- **THEN** hard stop MUST NOT trigger solely because mark is below entry_price * 0.8

#### Scenario: Twenty percent drop from mark stops
- **WHEN** open_mark is 1.0 and current mark is 0.80 with hard_stop_pct -0.20
- **THEN** the position MUST close with reason hard_stop

### Requirement: Migrate legacy rows using chain buy slip
On startup after config load, if `open_mark` is null, the system MUST backfill from `entry_price / (1 + buy_slip)` using that row's chain `execution.slippage_buy_pct` when available, otherwise 0.05 once.

#### Scenario: Legacy open position backfilled
- **WHEN** an existing row has entry_price set and open_mark null
- **THEN** after migration open_mark is populated before strategy evaluation uses it

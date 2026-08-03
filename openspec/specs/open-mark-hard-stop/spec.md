# open-mark-hard-stop Specification

## Purpose
Paper 硬止损相对开仓标记价 `open_mark`。`hard_stop_pct` 数值以 `config/chains.yaml` 为准（见 [docs/runtime-params.md](../../docs/runtime-params.md)）。归档 design 中的 `-0.20` 仅为历史快照。

## Requirements
### Requirement: Persist open mark at paper entry
When opening a Paper position, the system MUST store `open_mark` as the mark price used at entry (before buy slippage). Buy fill price MAY remain `open_mark * (1 + buy_slip)` for cost and quantity accounting.

#### Scenario: Open stores both prices
- **WHEN** Paper opens at mark M with buy slip s
- **THEN** the position record stores open_mark = M and entry_price = M * (1 + s)

### Requirement: Hard stop references open mark
Paper hard-stop evaluation MUST compare the current mark to `open_mark * (1 + hard_stop_pct)`, NOT to the buy-fill `entry_price`. `hard_stop_pct` MUST come from strategy config.

#### Scenario: Drop below entry_price alone does not stop
- **WHEN** open_mark is 1.0, buy slip is 5%, entry_price is 1.05, and current mark is still above `open_mark * (1 + hard_stop_pct)`
- **THEN** hard stop MUST NOT trigger solely because mark is below entry_price

#### Scenario: Configured open_mark drawdown stops
- **WHEN** open_mark is 1.0 and current mark reaches `open_mark * (1 + hard_stop_pct)` for the configured hard_stop_pct
- **THEN** the position MUST close with reason hard_stop

### Requirement: Migrate legacy rows using chain buy slip
On startup after config load, if `open_mark` is null, the system MUST backfill from `entry_price / (1 + buy_slip)` using that row's chain `execution.slippage_buy_pct` when available, otherwise 0.05 once.

#### Scenario: Legacy open position backfilled
- **WHEN** an existing row has entry_price set and open_mark null
- **THEN** after migration open_mark is populated before strategy evaluation uses it


## ADDED Requirements

### Requirement: StrategyOrder hard stop uses open_mark
`StrategyOrder` MUST carry `open_mark` and evaluate hard stop against open_mark. Peak tracking MUST continue from mark updates as today.

#### Scenario: Evaluate uses open_mark
- **WHEN** StrategyOrder.evaluate runs for hard stop
- **THEN** the threshold is open_mark * (1 + hard_stop_pct)

### Requirement: Manage path loads open_mark
When reconstructing StrategyOrder from an open DB row, the system MUST load persisted open_mark (after migration) into the order used for evaluation.

#### Scenario: Manage uses stored open_mark
- **WHEN** an open position is managed on a price tick
- **THEN** hard stop evaluation uses the row open_mark, not entry_price as the stop basis

### Requirement: Close writes re-entry cooldowns
On normal Paper close, the executor MUST write post_close cooldown when configured duration > 0. On hard_stop close, it MUST also write loss cooldown when configured duration > 0. Abort of a never-alerted open MUST NOT write these cooldowns.

#### Scenario: Hard stop writes both cooldowns
- **WHEN** a position closes with reason hard_stop and both durations are positive
- **THEN** both loss and post_close cooldown records are armed for that chain and token

#### Scenario: Abort does not arm re-entry
- **WHEN** a newly opened position is aborted due to Telegram total failure
- **THEN** no loss or post_close cooldown is armed for that abort

### Requirement: Close arms cooldowns in the same write path
Arming loss/post_close cooldowns MUST happen in the normal Paper close write path promptly (same locked write sequence as status transition). Callers MUST re-check re-entry block immediately before open after acquire.

#### Scenario: Re-check before open
- **WHEN** admission previously passed acquire but a concurrent close armed loss before open
- **THEN** a pre-open re-entry check MUST prevent opening when loss is active

### Requirement: Abort paper open API
The database/executor layer MUST provide an abort path that removes or voids a newly opened position and its related fills without marking a normal close_reason used for strategy stats as a completed trade, suitable for Telegram total-failure rollback.

#### Scenario: Abort removes open position
- **WHEN** abort_paper_open is invoked for a just-opened position id
- **THEN** that position is no longer status open and is not counted as a normal hard_stop/trail close

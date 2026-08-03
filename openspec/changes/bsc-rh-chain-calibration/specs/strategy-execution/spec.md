## ADDED Requirements

### Requirement: Executor binds chain-local strategy
Each chain's Paper (and future Live) executor MUST be constructed with `chains.<that_chain>.strategy` and MUST use those values for notional, hard stop, stage1, trail, timeout, snapshots, and re-entry cooldown durations.

#### Scenario: BSC timeout independent of SOL
- **WHEN** `chains.bsc.strategy.timeout_hours` is 3 and `chains.sol.strategy.timeout_hours` is 2
- **THEN** a bsc open position times out using 3h and a sol position using 2h

### Requirement: Close cooldowns use chain strategy durations
On normal close, `loss_cooldown_min` / `post_close_cooldown_min` MUST come from the closing position's chain strategy config.

#### Scenario: Hard stop arms loss using chain value
- **WHEN** a bsc position hard-stops and `chains.bsc.strategy.loss_cooldown_min` is 180
- **THEN** the loss cooldown until_ts reflects approximately 180 minutes for that bsc token

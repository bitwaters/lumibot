# post-gate-quote Specification

## Purpose
过门后未缓存重拉报价再开仓/推送；失败 `no_price`、释冷却、不推。
## Requirements
### Requirement: Quote after admission before paper open
After the unified admission gate succeeds (including cooldown acquire and re-entry re-check), the system MUST fetch a fresh market quote before opening a Paper position. The Paper `open_mark` and buy fill MUST be based on that fresh quote, not on the stale candidate payload price collected earlier in the pipeline. Admission MAY continue to use the earlier enrich snapshot for filter/safety decisions; the system MUST NOT re-run light filters solely because the fresh quote moved.

#### Scenario: Fresh mark used
- **WHEN** admission passes and a fresh quote returns price P
- **THEN** the opened position stores open_mark derived from P (with buy slip applied only to entry/cost as today)

#### Scenario: No second gate on moved mc
- **WHEN** fresh quote market cap would fail the configured mc band but admission already passed
- **THEN** the system still opens using the fresh quote (no secondary filter reject)

### Requirement: Quote failure is strict
If the post-gate quote fails, the system MUST retry once after a short delay. If still unavailable, the system MUST increment reject reason `no_price`, MUST release the just-acquired alert cooldown, MUST NOT send the Telegram push, and MUST NOT leave a new open position. Falling back to the earlier candidate price for opening is NOT allowed.

#### Scenario: No price after retry
- **WHEN** post-gate quote fails twice
- **THEN** no Telegram candidate message is sent for that admission, no new paper open remains, cooldown is released, and `no_price` is counted in rejects

### Requirement: Card market cap aligns with quote when available
When a fresh quote provides market cap, the signal push card MUST use that market cap for the 市值 line so display matches the open mark time. Trigger market cap from the signal payload MAY still be shown for the extension ratio context when present.

#### Scenario: Display uses fresh mc
- **WHEN** post-gate quote includes market_cap M and open succeeds
- **THEN** the push card market-cap line reflects M rather than only the pre-filter payload value when they differ


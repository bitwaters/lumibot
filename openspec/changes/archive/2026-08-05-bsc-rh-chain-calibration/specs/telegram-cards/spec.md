## ADDED Requirements

### Requirement: Help documents each enabled chain from yaml
`/help` MUST list strategy and slippage rules per enabled chain by reading `chains.<name>.strategy` and `chains.<name>.execution` from the loaded config. It MUST NOT print a single hard-coded rule block as if one global strategy applied to all chains.

#### Scenario: Two enabled chains show two rule blocks
- **WHEN** sol and bsc are enabled with different `hard_stop_pct`
- **THEN** `/help` includes both values under their chain labels

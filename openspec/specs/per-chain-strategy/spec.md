# per-chain-strategy Specification

## Purpose
TBD - created by archiving change bsc-rh-chain-calibration. Update Purpose after archive.
## Requirements
### Requirement: Strategy lives only under each chain in yaml
Each of `sol`, `bsc`, and `robinhood` MUST define its own `strategy` object in `config/chains.yaml` under `chains.<name>.strategy`. Runtime execution and operator-facing rule display MUST read that chain's block. The system MUST NOT use a separate top-level `strategy` document, hardcoded production percentages in Telegram copy, or a second config file as the source of truth for live parameters.

#### Scenario: Distinct strategies per chain
- **WHEN** `chains.sol.strategy.hard_stop_pct` differs from `chains.bsc.strategy.hard_stop_pct`
- **THEN** Paper evaluation on sol MUST use the sol value and on bsc MUST use the bsc value

#### Scenario: Help reads chain strategy from config
- **WHEN** an operator requests `/help` with sol and bsc enabled
- **THEN** the reply documents hard-stop / stage1 / trail / timeout / re-entry using each enabled chain's yaml strategy values (not a single global copy)

### Requirement: Missing chain strategy fails load
Config load MUST fail if an enabled or present chain block omits `strategy` required fields needed to construct `StrategyCfg`.

#### Scenario: BSC without strategy rejected
- **WHEN** `chains.bsc` exists but has no `strategy` map
- **THEN** config load MUST raise a validation error naming `bsc`


## ADDED Requirements

### Requirement: Calibration gate before enable
A chain MUST NOT run with `enabled: true` unless `calibration_status` is `calibrated`. Config load MUST fail otherwise with the chain name in the error.

#### Scenario: Draft cannot be enabled
- **WHEN** `chains.<name>.enabled` is true and `calibration_status` is `draft`
- **THEN** config load MUST fail

### Requirement: Executable calibrate-then-paper order
Because enable requires `calibrated`, operators MUST use: connectivity (disabled) → set `calibrated` + `enabled` for Paper trial → tune only that chain's yaml block (`filters` / `safety` / `sources` / `execution` / `strategy`) → keep `calibrated` after convergence. Requiring a full Paper trial before the first `calibrated` mark is NOT required (it is impossible under the enable gate).

#### Scenario: BSC enters paper after connectivity
- **WHEN** BSC connectivity evidence is accepted and `chains.bsc` is set to `calibrated` with `enabled: true` while Robinhood remains disabled
- **THEN** the process MUST run a bsc pipeline using only `chains.bsc.strategy` / filters, and subsequent trial edits MUST be confined to the `chains.bsc` subtree

### Requirement: Isolation across chain yaml blocks
Calibrating BSC or Robinhood MUST only edit that chain's subtree in `config/chains.yaml`. SOL's filters/strategy MUST remain unchanged unless the change is explicitly an SOL calibration.

#### Scenario: BSC filter change leaves SOL untouched
- **WHEN** `chains.bsc.filters.mc_min` is changed during BSC trial
- **THEN** `chains.sol` content MUST be identical in that change set

### Requirement: Connectivity evidence before first enable
Before first enabling `bsc` or `robinhood`, operators MUST verify on the target IPv4 host with a real API key that signal, trending, token info, token security, and price calls return usable payloads for API chain keys `bsc` / `robinhood`.

#### Scenario: Bad security contract blocks enable
- **WHEN** sampled security payloads omit `evm_v1`-required fields at a rate that makes admission unusable
- **THEN** that chain MUST stay `enabled: false` until addressed

### Requirement: Staged enable BSC then Robinhood
The deploy that first enables BSC MUST keep Robinhood `enabled: false` unless rate-limit headroom was explicitly reassessed and documented.

#### Scenario: First BSC enable ships without RH
- **WHEN** SOL is enabled and BSC is first enabled in production
- **THEN** Robinhood MUST remain `enabled: false` in that deploy absent documented rate-limit reassessment

## ADDED Requirements

### Requirement: Enabled EVM chains use evm_v1 independently
When `bsc` or `robinhood` is enabled, candidates on that chain MUST be evaluated with `evm_v1` and that chain's own `filters` / `safety` thresholds. Admission MUST fail closed on missing EVM-required security fields (honeypot / renounced / open_source) after enrichment.

#### Scenario: BSC candidate uses BSC filters
- **WHEN** an enabled BSC candidate is lightly filtered
- **THEN** thresholds come from `chains.bsc.filters`, not from `chains.sol.filters`

#### Scenario: Missing renounced rejects on EVM
- **WHEN** a BSC or Robinhood security payload has `renounced` missing after fetch
- **THEN** the candidate MUST be rejected with an EVM safety reason and MUST NOT be pushed or opened

### Requirement: Per-chain reject observability
Reject counters MUST remain keyed by `chain` so operators can tune each chain from `/rejects` without conflating distributions.

#### Scenario: BSC rejects do not overwrite SOL rows
- **WHEN** BSC rejects for reason `mc` and SOL also rejects for `mc`
- **THEN** `reject_counts` stores separate rows distinguished by chain

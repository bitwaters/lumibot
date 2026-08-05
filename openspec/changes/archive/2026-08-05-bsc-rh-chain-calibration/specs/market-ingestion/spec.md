## ADDED Requirements

### Requirement: Multi-chain enable respects shared rate limit
When more than one chain is enabled, all GMGN calls MUST share the process-wide rate limiter. Under sustained 429 / trending defer, configuration relief MUST target the newly enabled chain's `sources.*.interval_sec` (or disable that chain's trending) before changing another chain's intervals.

#### Scenario: New chain interval adjusted under 429 pressure
- **WHEN** enabling BSC causes sustained 429 while SOL remains enabled
- **THEN** relief edits MUST target `chains.bsc.sources` before `chains.sol.sources`

### Requirement: API chain key for Robinhood
Robinhood market API requests MUST use chain key `robinhood`. Telegram deep links MUST use the `/rh/` path segment. The API chain key and URL segment MUST NOT be conflated.

#### Scenario: Trending uses robinhood chain key
- **WHEN** Robinhood trending polling runs
- **THEN** the GMGN request includes `chain=robinhood`

## ADDED Requirements

### Requirement: Trending default window is 1m
For enabled chains, trending polling MUST use interval `1m` unless the chain config explicitly overrides the window. Supported GMGN windows remain `1m|5m|1h|6h|24h`; `1m` is the minimum.

#### Scenario: SOL default trending window
- **WHEN** SOL trending is enabled with stock config
- **THEN** the trending API is called with interval 1m

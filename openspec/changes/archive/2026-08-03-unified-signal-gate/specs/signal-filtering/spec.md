## ADDED Requirements

### Requirement: Market-cap extension gate for signals
When a signal candidate has `trigger_mc`, the system MUST compute `market_cap / trigger_mc`. When `enforce_mc_extension` is true and the ratio exceeds `max_mc_extension` (default 2.0), admission MUST fail with reason `mc_extension` (no push, no open). When enforce is false, the system MUST record soft counter `mc_extension_soft` without rejecting solely for extension.

#### Scenario: Enforce blocks extended signal
- **WHEN** enforce_mc_extension is true, trigger_mc is 100k, market_cap is 250k, and max_mc_extension is 2.0
- **THEN** the candidate is rejected with mc_extension and not pushed

#### Scenario: Soft mode does not reject but is observable
- **WHEN** enforce_mc_extension is false and the ratio exceeds max_mc_extension
- **THEN** extension alone MUST NOT reject the candidate AND the system MUST record an observable soft counter such as reject reason `mc_extension_soft`

### Requirement: All enabled sources share the same admission filters
Signal types configured for the chain and trending MUST use the same light filters, safety profile, extension policy (where applicable), and admission cooldowns. The system MUST NOT admit a source for push while excluding it from Paper open by source whitelist.

#### Scenario: Trending pass opens paper
- **WHEN** a trending candidate passes the unified admission gate and no open position exists
- **THEN** Paper open is attempted and a Telegram alert is sent

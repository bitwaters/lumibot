# ca-query Specification

## Purpose
TBD - created by archiving change ca-query. Update Purpose after archive.
## Requirements
### Requirement: Contract address detection from messages
Any authorized text message that is not a bot command MUST be scanned for contract addresses before falling back to the unknown-command reply. An EVM address is `0x` followed by exactly 40 hex characters. A Solana address is a base58 string of 40-44 characters (charset `1-9A-HJ-NP-Za-km-z`). The CA MAY be embedded in surrounding text or delimiters. When a message contains multiple addresses, only the first match MUST be answered. Messages without any address MUST keep the existing unknown-command reply.

#### Scenario: EVM address embedded in text
- **WHEN** an authorized message contains `0x` + 40 hex characters among other text
- **THEN** the bot replies with a query card for that address

#### Scenario: Solana address detection
- **WHEN** an authorized message contains a 40-44 character base58 string
- **THEN** the bot treats it as a Solana contract address

#### Scenario: Multiple addresses
- **WHEN** a message contains several contract addresses
- **THEN** the bot answers only the first match

#### Scenario: No address found
- **WHEN** an authorized text message contains no contract address
- **THEN** the bot keeps replying with the unknown-command hint

### Requirement: Automatic chain detection
The chain MUST be determined without user input. A base58 address MUST map to `sol` directly. A `0x` address MUST be probed against enabled chains in configured order (default bsc then robinhood): the first chain whose token info resolves is selected; a 404 error or empty/valueless info MUST move to the next candidate. Chains not enabled in config MUST NOT be probed. If every candidate fails, the bot MUST reply that the contract was not found rather than guessing.

#### Scenario: Solana by format
- **WHEN** a base58 address is detected
- **THEN** the bot queries it on sol without probing other chains

#### Scenario: EVM chain probe succeeds
- **WHEN** a 0x address resolves on bsc
- **THEN** the bot replies with the bsc card without probing robinhood

#### Scenario: EVM chain probe fails over
- **WHEN** a 0x address returns 404 or empty data on bsc but resolves on robinhood
- **THEN** the bot replies with the robinhood card

#### Scenario: No chain resolves
- **WHEN** all candidate chains return 404 or empty data
- **THEN** the bot replies that the contract was not found

### Requirement: Query card layout
The query card MUST share the card language of signal/command cards: symbol-led `🔍 $SYM · CHAIN` title, `📍 CA:` monospace code block, `📊 指标` section with the aligned monospace metric grid, and the per-chain button group (GMGN + DexScreener). It MUST include a price row (`💰 价格`) in addition to the signal-card metrics. Since GMGN token_info omits market_cap on every chain (verified live), the card MUST compute it as price × circulating_supply — the official GMGN skill's own approach — and MUST label the row with `≈` to mark it as derived. Query replies MUST be served from the shared token-info/security caches when available (millisecond latency; the signal pipeline continuously warms these caches); live fetch happens only on cache miss. Narrative eligibility MUST cover all symbols (no minimum length skip). Trading volume MUST be read from the nested `price` object (token_info has no top-level volume). When `wallet_tags_stat` is present in token info, the card MUST also show smart-money and KOL holder counts (`🦈 聪明钱` / `🎩 KOL`). When the LLM narrative service is available and eligible, the card MUST also carry a `📚` narrative block as the last text lines: a single LLM sentence line. The 24h buy/sell counts MUST be shown as `🛒 买` / `💸 卖` rows inside the metric grid instead of a bottom data line. The narrative MUST be applied via an asynchronous message edit AFTER the reply is sent, so the reply latency is independent of the LLM call (fail-open: narrative failure MUST NOT affect the reply). It MUST NOT include a paper status line or latency line. Missing metrics MUST render as `—`.

#### Scenario: Full query card
- **WHEN** a contract resolves with full token info and security data
- **THEN** the reply contains the `🔍` title, CA code block, metric grid with price and market cap, safety line, and GMGN/DexScreener buttons

#### Scenario: Missing metrics
- **WHEN** token info lacks some metrics
- **THEN** the missing values render as `—` and the card still sends

### Requirement: Advisory safety display
The query card MUST display the safety line assembled from the security endpoint (taxes, warnings, rug/bundler/rat risk) exactly like the signal card. Unlike the signal pipeline, a hard-fail safety verdict MUST NOT block or refuse the query reply; the warnings are shown for the operator to judge. If the security fetch fails, the card MUST still send with a safety-unknown indicator.

#### Scenario: Hard-fail token still answered
- **WHEN** a token's safety evaluation is hard_fail
- **THEN** the bot still replies with the card showing the safety warnings

#### Scenario: Security fetch failure
- **WHEN** the security endpoint errors
- **THEN** the card still sends, indicating safety is unknown

### Requirement: Query throttling and degradation
Queries MUST be throttled per chat with a configurable minimum interval (`global.ca_query.min_interval_sec`, default 5). Repeated queries for the same token MUST be served from the token-info/security caches without extra API cost. When GMGN is rate-limited or IP-suspended, the bot MUST reply with a friendly retry-later message instead of failing or spamming the shared quota.

#### Scenario: Rapid repeated queries throttled
- **WHEN** a chat sends queries faster than the configured interval
- **THEN** the bot replies with a slow-down message and skips the lookup

#### Scenario: GMGN unavailable
- **WHEN** GMGN requests fail due to 429/IP suspension
- **THEN** the bot replies that GMGN is temporarily unavailable and to retry later

### Requirement: Reply scoping
The query reply MUST use `message.reply` (quoting the user's message) and MUST be subject to the same authorization as all other commands (private control chats and authorized groups only).

#### Scenario: Authorized chat
- **WHEN** an authorized chat sends a message containing a CA
- **THEN** the bot replies by quoting the message

#### Scenario: Unauthorized chat
- **WHEN** an unauthorized chat sends a message containing a CA
- **THEN** the bot ignores it like all other unauthorized messages


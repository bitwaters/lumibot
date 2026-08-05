## MODIFIED Requirements

### Requirement: Unified admission controls push and paper open
The system MUST apply one admission gate to each candidate. Only candidates that pass the gate MUST be eligible for Telegram alert delivery and Paper open attempt. Candidates rejected by the gate MUST NOT be pushed and MUST NOT open a new Paper position. After admission side-effect checks (including cooldown acquire, re-entry re-check, and post-gate quote) succeed, the system MUST send the Telegram signal push first; it MUST attempt Paper open only if at least one configured chat accepts the send. If Telegram delivery fails for all configured chats, the system MUST NOT open a new Paper position and MUST release the just-acquired alert cooldown without arming loss/post_close.

#### Scenario: Pass gate then push then open
- **WHEN** a candidate passes admission side-effect checks and Telegram send succeeds for at least one chat
- **THEN** the system sends the Telegram alert and then attempts Paper open (unless an open position already exists)

#### Scenario: Push failure blocks new open
- **WHEN** a candidate passes admission but Telegram delivery fails for all configured chats
- **THEN** the system MUST NOT open a new Paper position and MUST release the alert cooldown without arming loss/post_close

#### Scenario: Reject gate blocks both
- **WHEN** a candidate fails any admission check (including loss or post-close cooldown)
- **THEN** the system MUST NOT send a Telegram alert and MUST NOT open a Paper position for that attempt

### Requirement: Pre-open re-check releases acquire on block
After same-type/cross cooldown has been acquired, the system MUST re-check re-entry block before sending the Telegram signal push (and thus before opening). If blocked, the system MUST release the just-acquired alert cooldown, MUST NOT push, and MUST NOT open.

#### Scenario: Concurrent loss after acquire
- **WHEN** acquire succeeded but a concurrent close armed loss before push
- **THEN** push and open are skipped and the acquired source/cross cooldown is released

## REMOVED Requirements

### Requirement: Telegram total failure aborts new opens without re-entry cooldown
**Reason**: Ordering is push-then-open; total Telegram failure never creates a new open, so abort-after-open is obsolete.
**Migration**: On total Telegram failure, skip open entirely and release alert cooldown; do not arm loss/post_close.

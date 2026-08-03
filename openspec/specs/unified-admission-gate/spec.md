# unified-admission-gate Specification

## Purpose
统一入场顺序、再入场冷却、acquire 后再检。冷却时长以 yaml `loss_cooldown_min` / `post_close_cooldown_min` 为准。
## Requirements
### Requirement: Unified admission controls push and paper open
The system MUST apply one admission gate to each candidate. Only candidates that pass the gate MUST be eligible for Telegram alert delivery and Paper open attempt. Candidates rejected by the gate MUST NOT be pushed and MUST NOT open a new Paper position.

#### Scenario: Pass gate then push and open
- **WHEN** a candidate passes light filters, safety, extension policy, and all admission cooldowns
- **THEN** the system attempts Paper open (unless an open position already exists) and sends a Telegram alert for that candidate

#### Scenario: Reject gate blocks both
- **WHEN** a candidate fails any admission check (including loss or post-close cooldown)
- **THEN** the system MUST NOT send a Telegram alert and MUST NOT open a Paper position for that attempt

### Requirement: Admission check order is fixed
Admission MUST evaluate blockers in this order and stop at the first failure: light filters, safety, enforced mc_extension, re-entry block (`loss` then `post_close`), then same-type/cross cooldown acquire. Soft mc_extension (enforce false) MUST NOT reject but MUST increment an observable counter such as `mc_extension_soft`. A configured cooldown duration of 0 MUST disable arming and blocking for that kind.

#### Scenario: Loss reason wins over post_close
- **WHEN** both loss and post_close cooldowns are active for a token
- **THEN** the reject reason MUST be `loss_cooldown`

#### Scenario: Zero duration disables loss block
- **WHEN** loss_cooldown_min is 0
- **THEN** hard_stop MUST NOT arm a loss row that blocks admission

### Requirement: Re-entry kinds are queried explicitly
The system MUST detect active `loss` and `post_close` cooldown rows via an explicit re-entry check before allowing admission. Relying only on same-type/cross acquire logic is NOT sufficient.

#### Scenario: Only loss row blocks
- **WHEN** cooldowns contain an unexpired `loss` row and no same-type or cross row
- **THEN** admission fails with `loss_cooldown` and no alert is sent

### Requirement: Pre-open re-check releases acquire on block
After same-type/cross cooldown has been acquired, the system MUST re-check re-entry block immediately before opening. If blocked, the system MUST release the just-acquired alert cooldown, MUST NOT open, and MUST NOT push.

#### Scenario: Concurrent loss after acquire
- **WHEN** acquire succeeded but a concurrent close armed loss before open
- **THEN** open and push are skipped and the acquired source/cross cooldown is released

### Requirement: Already-open is the only push-without-new-open exception
When a candidate has passed the admission gate but an open Paper position already exists for the same chain and token, the system MUST still send the Telegram alert and MUST NOT open a second position. The alert card MUST indicate the skip reason.

#### Scenario: Duplicate open skipped but alert sent
- **WHEN** admission passes and an open Paper position already exists for that chain and token
- **THEN** Telegram is sent with paper status skipped_open (or equivalent) and no second position is created

### Requirement: Telegram total failure aborts new opens without re-entry cooldown
When Paper open for this admission created a new position and Telegram delivery fails for all configured chats, the system MUST abort that newly created position (delete or void) without treating it as a normal close, MUST NOT arm loss or post_close cooldowns for that abort, and MUST release the alert cooldown.

#### Scenario: All chats fail after open
- **WHEN** try_open_paper returns opened and send_candidate returns any_ok false
- **THEN** the new position is not left open, no loss/post_close cooldown is armed for the abort, and the just-acquired alert cooldown is released

### Requirement: Loss and post-close cooldowns are admission rejects
After a normal Paper close with reason `hard_stop`, the system MUST arm a loss cooldown when loss_cooldown_min > 0. After any normal Paper close, the system MUST arm a post_close cooldown when post_close_cooldown_min > 0. While either armed cooldown is active, new candidates for that chain and token MUST fail admission with a distinct reject reason and MUST NOT be pushed.

#### Scenario: Hard-stop blocks re-alert
- **WHEN** a token was hard-stopped within the loss cooldown window
- **THEN** a new signal or trending candidate for that token is rejected and not pushed

#### Scenario: Any close blocks short re-entry
- **WHEN** a token was closed for any reason within the post-close cooldown window
- **THEN** a new candidate for that token is rejected and not pushed


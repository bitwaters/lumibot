## ADDED Requirements

### Requirement: Optional post-send news line on signal cards
Signal push cards MAY later gain a single plain-text news line via Telegram message edit after the initial send. The edit MUST preserve metric/safety/latency body content and the GMGN inline keyboard. The initial send MUST remain valid without any news line.

#### Scenario: Edit preserves keyboard
- **WHEN** a signal card is edited to add a news line
- **THEN** the GMGN button reply markup remains present on the edited message

#### Scenario: Initial card stays valid without news
- **WHEN** news enrichment does not edit the message
- **THEN** the original signal-push card still satisfies the unified layout requirements

### Requirement: Provisional execution line before open
When the signal card is sent before Paper open completes, the bottom execution line MUST NOT claim `已开仓`. It MUST use a provisional status such as `⏳ 开仓中`, unless a read-only pre-check already determines `skipped_open` (already open). After open completes, an edit MAY update the execution line to the final status.

#### Scenario: First card before new open
- **WHEN** admission passes, no open position exists, and the first Telegram send occurs before `on_alert`
- **THEN** the card does not show `✅ 已开仓` on that first send

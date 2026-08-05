## MODIFIED Requirements

### Requirement: Optional post-send narrative line on signal cards

Signal push cards MAY later gain a single plain-text narrative line via Telegram message edit after the initial send (was: "Optional post-send news line"; the OpenNews/6551 news feature was removed, narrative labels from LLM replace it). The edit MUST preserve metric/safety/latency body content and the GMGN inline keyboard. The initial send MUST remain valid without any narrative line. The narrative line MUST use the `📚` prefix and MUST NOT exceed one line per card.

#### Scenario: Narrative line appended by edit
- **WHEN** a signal card is edited to add a narrative line
- **THEN** the card body (metrics, safety, latency, status) and the GMGN inline keyboard are unchanged, and the last text line is `📚 <narrative>`

#### Scenario: Initial card stays valid without narrative
- **WHEN** narrative enrichment does not edit the message (LLM unavailable, N/A, timeout, disabled)
- **THEN** the sent card is complete and valid without any narrative line

#### Scenario: Narrative line replaced on repeat edit
- **WHEN** the same card receives a second narrative line
- **THEN** the previous `📚` line is replaced; the card never carries more than one narrative line

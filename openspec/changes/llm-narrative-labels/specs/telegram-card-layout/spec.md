## MODIFIED Requirements

### Requirement: Signal push card structure

The signal push card MUST use the structure: title line, CA block line, `📊 指标` section header, metric rows, `🛡` safety line, status line, optional `📚` narrative line (was: optional `📰` news line; OpenNews/6551 feature removed, replaced by LLM narrative labels), and inline buttons. All other structure requirements (symbol-led title, `📍 CA:` code block, `—` placeholders, no copy button) are unchanged.

#### Scenario: Narrative line position
- **WHEN** an async narrative edit appends a narrative line
- **THEN** the `📚` line is the last text line of the card (after the status line, before the buttons), and a later narrative edit replaces the previous `📚` line

#### Scenario: Narrative content escaped
- **WHEN** a narrative line contains HTML metacharacters from the LLM output
- **THEN** it is escaped before insertion and renders as literal text

### Requirement: Inline buttons per chain

The signal and paper-event cards MUST include a GMGN button for every chain and a DexScreener button for every chain where DexScreener support exists (sol, bsc, robinhood — was: robinhood MUST NOT include DexScreener; the button set was unified across chains). A copy button MUST NOT be added; CA copying relies on the code block text selection.

#### Scenario: Robinhood card buttons
- **WHEN** a card is rendered for a robinhood token
- **THEN** the inline keyboard shows both GMGN and DexScreener buttons (uniform with sol/bsc)

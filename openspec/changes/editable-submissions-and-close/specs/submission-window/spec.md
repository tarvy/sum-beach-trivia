## ADDED Requirements

### Requirement: Single persistent game
The system SHALL operate as exactly one persistent game. All contributed
questions, teams, and results SHALL belong to that one game, and SHALL persist
across the multi-week collection period and across server sleep/wake with no
data loss.

#### Scenario: Contributions persist across weeks
- **WHEN** a contributor adds questions and returns days or weeks later
- **THEN** their previously saved questions are still present and unchanged

#### Scenario: Data survives a server sleep
- **WHEN** the server has gone idle and later wakes for a new request
- **THEN** all previously collected questions and contributors are intact

### Requirement: Host-controlled submission window
The host SHALL be able to set whether contribution submissions are open or
closed, from the host panel. The current open/closed state SHALL be visible to
the host.

#### Scenario: Host closes submissions
- **WHEN** the host activates the "close submissions" control
- **THEN** the submission window becomes closed and the host sees it is closed

### Requirement: Closed window blocks edits but preserves data
While submissions are closed, contributors SHALL NOT be able to add new
questions or edit existing ones, and all previously submitted data SHALL remain
available for the game.

#### Scenario: Contributor arrives after close
- **WHEN** submissions are closed and a contributor opens the contribute screen
- **THEN** they cannot add or change questions, and no contributed data is lost

#### Scenario: Editing is allowed while open
- **WHEN** submissions are open and a contributor edits a question
- **THEN** the edit is saved to their existing submission set

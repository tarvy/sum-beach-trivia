## ADDED Requirements

### Requirement: Display auto-follows game state
The big-screen display SHALL automatically reflect the current game phase without
requiring a viewer to navigate, and SHALL not present navigation that lets a
viewer reach a wrong or stuck screen.

#### Scenario: Display tracks the host
- **WHEN** the host advances the game to a new phase
- **THEN** the display updates on its own to match, with no manual navigation

#### Scenario: No stuck/odd navigation
- **WHEN** a viewer interacts with the display during the writing phase
- **THEN** they cannot end up on a blank, wrong, or stuck screen

### Requirement: Clear writing-phase presentation
While a round is open and answers are being written, the display SHALL show the
active round's questions together with a clear "writing in progress" indication.

#### Scenario: Writing-in-progress is obvious on the big screen
- **WHEN** a round is open and teams are writing answers
- **THEN** the display shows that round's questions and a clear writing-in-progress cue

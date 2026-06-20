## ADDED Requirements

### Requirement: Build a team by name and member selection
When forming a team on the play screen, a team SHALL set a team name and SHALL be
able to select its members from the list of question-bank authors.

#### Scenario: Pick members from authors
- **WHEN** a team is being formed and the player opens the member picker
- **THEN** the list of question authors is shown and members can be selected

#### Scenario: Team name required
- **WHEN** a team is formed
- **THEN** it has a name

### Requirement: Manual teammate entry
A team SHALL always be able to add a teammate who is not in the author list, by
entering them manually.

#### Scenario: Add a non-author teammate
- **WHEN** someone who did not contribute questions joins a team
- **THEN** they can be added to the team by manual entry

### Requirement: Editable membership during play
Team membership SHALL be editable at any point during play.

#### Scenario: Move a player mid-game
- **WHEN** the game is underway and a team's roster needs to change
- **THEN** members can be added or removed and the change takes effect

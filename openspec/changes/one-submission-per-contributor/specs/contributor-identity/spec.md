## ADDED Requirements

### Requirement: One submission set per contributor
Each contributor SHALL own exactly one set of questions for the game. The system
SHALL NOT let one person create multiple separate submission sets.

#### Scenario: Returning contributor edits their existing set
- **WHEN** a contributor who has already submitted returns on the same browser
- **THEN** they are shown their existing question set to edit, not a blank new one

#### Scenario: No duplicate sets created on resubmit
- **WHEN** a contributor submits again after already having a set
- **THEN** their existing set is updated and no second set is created

### Requirement: Persistent contributor identity
A contributor SHALL be identified by the name they provide together with a
persisted browser identity, so that return visits resolve to the same person and
their questions remain attributed to them.

#### Scenario: Identity persists across visits
- **WHEN** a contributor leaves and returns later on the same browser
- **THEN** the app recognizes them as the same contributor and loads their set

### Requirement: Author attribution is stable
Every contributed question SHALL remain attributed to the single contributor who
authored it, with no duplicate author records for the same person.

#### Scenario: Author list has one entry per person
- **WHEN** the list of question authors is viewed (e.g. for team building)
- **THEN** each contributing person appears exactly once

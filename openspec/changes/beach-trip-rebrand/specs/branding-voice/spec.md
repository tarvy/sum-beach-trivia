## ADDED Requirements

### Requirement: No bar or pub language
User-facing copy SHALL NOT use "bar", "pub", or "pub quiz". The product's framing
SHALL be the annual friends' beach trip.

#### Scenario: No bar/pub terms on any screen
- **WHEN** any user-facing screen, title, or message is viewed
- **THEN** it contains no instance of "bar", "pub", or "pub quiz"

#### Scenario: Beach-trip framing for the event
- **WHEN** copy refers to the event or occasion
- **THEN** it uses friends'-beach-trip framing rather than generic bar/pub trivia

### Requirement: Sparing inside-joke allusions
Inside-joke allusions SHALL be subtle and infrequent, used only where they fit
the context naturally. The set of inside jokes SHALL be extensible over time.

#### Scenario: Jokes only where they fit
- **WHEN** copy is written for a screen or state
- **THEN** an inside-joke allusion appears only if it fits naturally there, and
  the overall density of jokes stays low (no screen is overloaded with them)

#### Scenario: Known inside jokes available
- **WHEN** an inside-joke allusion is used
- **THEN** it may draw from the maintained list (initially: Anthony's romantic
  exploits with older women; Jonathan wearing khakis on the beach)

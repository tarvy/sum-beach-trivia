## ADDED Requirements

### Requirement: Three required and two optional questions
The contribution form SHALL require exactly 3 questions and SHALL allow up to 2
additional optional questions, for a maximum of 5 per contributor.

#### Scenario: Fewer than three questions blocks submission
- **WHEN** a contributor tries to submit with fewer than 3 questions filled in
- **THEN** the form is invalid and submission is blocked

#### Scenario: Optional fourth and fifth accepted
- **WHEN** a contributor fills in 4 or 5 valid questions
- **THEN** all of them are accepted and saved

#### Scenario: More than five not allowed
- **WHEN** a contributor has provided 5 questions
- **THEN** they cannot add a sixth

### Requirement: Each question requires Question, Answer, and Category
Every question a contributor provides SHALL require all three of: Question text, Answer, and a Category chosen from the standard category list. The form SHALL NOT validate if any of the three is missing on a provided question.

#### Scenario: Missing answer blocks submission
- **WHEN** a provided question has a Question and Category but no Answer
- **THEN** the form is invalid and submission is blocked

#### Scenario: Category must come from the list
- **WHEN** a contributor sets a question's category
- **THEN** it must be one of the available standard categories

### Requirement: Author recorded per question
Each contributed question SHALL record the contributor who authored it.

#### Scenario: Author stored with the question
- **WHEN** a contributor submits a question
- **THEN** that question is stored with its author's identity

### Requirement: Author revealed after each round
The author of each question SHALL be revealed during the game after that round's answers have been given/graded.

#### Scenario: Author shown at round reveal
- **WHEN** a round reaches the reveal stage (answers are in)
- **THEN** the author of each of that round's questions is revealed

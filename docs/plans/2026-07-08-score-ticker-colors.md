# Score Ticker Colors

 ## Requirements

 - Make display ticker scores look more like scoreboard/ticker values instead of plain trailing text.
 - Color visible upward movement arrows green and downward movement arrows red.
 - Keep the bottom ticker compact and readable on the TV display.

 ## Files To Touch

 - `static/display.html`

 ## Implementation Steps

 - Split each ticker entry into small semantic spans for movement icon, rank, team name, and score.
 - Style score values as compact ticker chips with a distinct fill/text treatment.
 - Add direction-specific classes for up/down/steady movement icons.

 ## Visual Surfaces

 - `display.html` at 1920x1080 during `round_open` after round 1, with several teams in the ticker.
 - Check that ticker entries stay baseline-aligned, scores pop as values, separators remain readable, and no content clips against the bottom edge.
 - Include at least one down arrow via a local seeded display state or DOM override if the scratch data does not naturally produce rank movement.

 ## Test Plan

 - Run the Python test suite.
 - Run a scratch app and take a browser screenshot of the display ticker.

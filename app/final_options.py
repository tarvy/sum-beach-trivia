"""Curated pick-lists so the host never has to author a final or tiebreak.

FINAL_OPTIONS: multi-item bar-trivia finals. Each option is
    {"text": str, "items": [3-8 str], "ordered": bool, "wager_cap": int}
The list endpoint hides "items" so the person setting up can pick blind and
still play; the ?id= fetch returns the full option for POST /api/host/final.

TIEBREAK_OPTIONS: nearest-wins numeric questions {"question": str, "value": number}.
Same blind-pick pattern; values hidden in the list payload.
"""

FINAL_OPTIONS = [
    {
        "text": "Put these five empires in order of founding, earliest first.",
        "items": ["Roman Empire", "Mongol Empire", "Ottoman Empire",
                  "Spanish Empire", "British Empire"],
        "ordered": True,
        "wager_cap": 10,
    },
    {
        "text": "Name the five Great Lakes.",
        "items": ["Superior", "Michigan", "Huron", "Erie", "Ontario"],
        "ordered": False,
        "wager_cap": 10,
    },
    {
        "text": "Put these five planets in order of diameter, largest first: "
                "Earth, Jupiter, Neptune, Saturn, Uranus.",
        "items": ["Jupiter", "Saturn", "Uranus", "Neptune", "Earth"],
        "ordered": True,
        "wager_cap": 10,
    },
    {
        "text": "Name the six main characters (first names) on the sitcom Friends.",
        "items": ["Rachel", "Monica", "Phoebe", "Ross", "Chandler", "Joey"],
        "ordered": False,
        "wager_cap": 10,
    },
    {
        "text": "Put these American wars in chronological order by the year "
                "the war began, earliest first.",
        "items": ["Revolutionary War", "Civil War", "World War I",
                  "World War II", "Korean War"],
        "ordered": True,
        "wager_cap": 10,
    },
    {
        "text": "Name the five colors of the Olympic rings.",
        "items": ["Blue", "Yellow", "Black", "Green", "Red"],
        "ordered": False,
        "wager_cap": 8,
    },
    {
        "text": "Name all seven dwarfs in Disney's Snow White.",
        "items": ["Doc", "Grumpy", "Happy", "Sleepy", "Bashful", "Sneezy", "Dopey"],
        "ordered": False,
        "wager_cap": 12,
    },
    {
        "text": "Put these inventions in order from oldest to newest.",
        "items": ["Printing press", "Steam engine", "Telephone",
                  "Television", "World Wide Web"],
        "ordered": True,
        "wager_cap": 10,
    },
    {
        "text": "Put these five US states in order of population, largest first.",
        "items": ["California", "Texas", "Florida", "New York", "Pennsylvania"],
        "ordered": True,
        "wager_cap": 10,
    },
    {
        "text": "Name the six wives of Henry VIII.",
        "items": ["Catherine of Aragon", "Anne Boleyn", "Jane Seymour",
                  "Anne of Cleves", "Catherine Howard", "Catherine Parr"],
        "ordered": False,
        "wager_cap": 15,
    },
    {
        "text": "Put these animals in order by average adult weight, heaviest first.",
        "items": ["Blue whale", "African elephant", "Hippopotamus",
                  "Grizzly bear", "Gray wolf"],
        "ordered": True,
        "wager_cap": 8,
    },
    {
        "text": "Name the five boroughs of New York City.",
        "items": ["Manhattan", "Brooklyn", "Queens", "The Bronx", "Staten Island"],
        "ordered": False,
        "wager_cap": 10,
    },
    {
        "text": "Name the eight planets of the solar system.",
        "items": ["Mercury", "Venus", "Earth", "Mars",
                  "Jupiter", "Saturn", "Uranus", "Neptune"],
        "ordered": False,
        "wager_cap": 10,
    },
    {
        "text": "Put these blockbuster movies in order of release, earliest first.",
        "items": ["Jaws", "E.T. the Extra-Terrestrial", "Jurassic Park",
                  "Titanic", "Avatar"],
        "ordered": True,
        "wager_cap": 10,
    },
    {
        "text": "Put these musicians in order of birth year, oldest first.",
        "items": ["Elvis Presley", "John Lennon", "David Bowie",
                  "Michael Jackson", "Whitney Houston"],
        "ordered": True,
        "wager_cap": 12,
    },
    {
        "text": "Put these world landmarks in order by the year they were "
                "completed, oldest first.",
        "items": ["Great Pyramid of Giza", "Colosseum", "Taj Mahal",
                  "Eiffel Tower", "Sydney Opera House"],
        "ordered": True,
        "wager_cap": 10,
    },
]

TIEBREAK_OPTIONS = [
    {"question": "How many feet long is a regulation bowling lane, from the foul line to the head pin?", "value": 60},
    {"question": "How many keys are on a standard piano?", "value": 88},
    {"question": "How many bones are in the adult human body?", "value": 206},
    {"question": "How many member countries are in the United Nations?", "value": 193},
    {"question": "How tall is the Eiffel Tower in meters, antennas included?", "value": 330},
    {"question": "How tall is Mount Everest in feet?", "value": 29032},
    {"question": "How many steps does it take to climb to the Empire State Building's 102nd-floor observatory?", "value": 1860},
    {"question": "How long is the Great Wall of China in miles, per the official 2012 survey?", "value": 13171},
    {"question": "How long is the Mississippi River in miles?", "value": 2340},
    {"question": "What is the average distance from the Earth to the Moon in miles?", "value": 238855},
    {"question": "How many time zones does Russia span?", "value": 11},
    {"question": "How many islands make up the Philippines?", "value": 7641},
    {"question": "How many words are in the U.S. Constitution, signatures included?", "value": 4543},
    {"question": "How deep is the Challenger Deep, the ocean's deepest point, in feet?", "value": 36070},
    {"question": "How many minutes long is the movie The Godfather?", "value": 175},
    {"question": "What is the wingspan of a Boeing 747-400 in feet?", "value": 211},
    {"question": "How tall is the Statue of Liberty in feet, from the ground to the tip of the torch?", "value": 305},
    {"question": "How many pounds does the Stanley Cup weigh?", "value": 34.5},
    {"question": "How many Earth days long is one year on Mars?", "value": 687},
    {"question": "What was the Concorde's top cruising speed in miles per hour?", "value": 1354},
    {"question": "How many total gifts are given in the song 'The Twelve Days of Christmas'?", "value": 364},
    {"question": "How many strings are on a full-size concert harp?", "value": 47},
    {"question": "How many countries share a land border with China?", "value": 14},
    {"question": "How many rooms are in the White House?", "value": 132},
    {"question": "How many elements are on the periodic table?", "value": 118},
    {"question": "How many hot dogs did Joey Chestnut eat to set the Nathan's Famous record in 2021?", "value": 76},
]

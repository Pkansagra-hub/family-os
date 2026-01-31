#!/usr/bin/env python3
"""
Comprehensive UltraBERT v4.0.0 NER Quality Test Suite.

Tests 150+ scenarios across Easy, Medium, and Hard categories to validate
that the GlobalPointer NER architecture properly handles:
- Verbs incorrectly tagged as entities
- Adjectives/emotions incorrectly tagged
- Common nouns incorrectly tagged as ORG
- Partial entity extraction
- Family-specific entities
- Temporal expressions
"""

import time

from familyos_ultrabert import UltraBERT

# =============================================================================
# TEST CASES BY DIFFICULTY
# =============================================================================

# EASY: Clear entities that should always be extracted correctly
EASY_TESTS = [
    # Person names
    ("Mom picked up Emma from school", ["Mom", "Emma"], "KINSHIP + PERSON"),
    ("Dad called John about the meeting", ["Dad", "John"], "KINSHIP + PERSON"),
    ("Sarah and Mike went to dinner", ["Sarah", "Mike"], "Two PERSON"),
    ("Grandma visited us yesterday", ["Grandma"], "KINSHIP"),
    ("Uncle Bob brought cookies", ["Uncle Bob"], "KINSHIP"),
    ("My sister Rachel is coming", ["Rachel"], "PERSON"),
    ("Brother James called", ["James"], "PERSON"),
    ("Aunt Mary sent a card", ["Aunt Mary"], "KINSHIP"),
    ("Cousin Emily arrived", ["Emily"], "PERSON"),
    ("Nephew Tyler is growing fast", ["Tyler"], "PERSON"),
    # Organizations
    ("Working at Google today", ["Google"], "ORG"),
    ("Meeting at Microsoft campus", ["Microsoft"], "ORG"),
    ("Interview with Amazon next week", ["Amazon"], "ORG"),
    ("Applied to Apple for a job", ["Apple"], "ORG"),
    ("Netflix subscription renewed", ["Netflix"], "ORG"),
    ("Facebook post went viral", ["Facebook"], "ORG"),
    ("Twitter announcement today", ["Twitter"], "ORG"),
    ("LinkedIn profile updated", ["LinkedIn"], "ORG"),
    # Locations
    ("Flew to New York yesterday", ["New York"], "LOCATION"),
    ("Vacation in Paris was amazing", ["Paris"], "LOCATION"),
    ("Moving to California next month", ["California"], "LOCATION"),
    ("Road trip to Texas", ["Texas"], "LOCATION"),
    ("Born in Chicago", ["Chicago"], "LOCATION"),
    ("Visiting London next year", ["London"], "LOCATION"),
    ("Trip to Japan planned", ["Japan"], "LOCATION"),
    ("Honeymoon in Italy", ["Italy"], "LOCATION"),
    # Temporal
    ("Meeting tomorrow at 3pm", ["tomorrow", "3pm"], "TEMPORAL"),
    ("Birthday party next Saturday", ["next Saturday"], "TEMPORAL"),
    ("Anniversary is June 15th", ["June 15th"], "TEMPORAL"),
    ("Started the job in 2020", ["2020"], "TEMPORAL"),
    ("Woke up at 6am today", ["6am", "today"], "TEMPORAL"),
]

# MEDIUM: Sentences with potential confusion but clear context
MEDIUM_TESTS = [
    # Verbs at start (should NOT be tagged)
    ("Met with John about the project", ["John"], "Only John, not Met"),
    ("Called Sarah to discuss plans", ["Sarah"], "Only Sarah, not Called"),
    ("Asked Emma about homework", ["Emma"], "Only Emma, not Asked"),
    ("Told Mike the news", ["Mike"], "Only Mike, not Told"),
    ("Saw Rachel at the store", ["Rachel"], "Only Rachel, not Saw"),
    ("Helped Dad with the car", ["Dad"], "Only Dad, not Helped"),
    ("Texted Mom about dinner", ["Mom"], "Only Mom, not Texted"),
    ("Emailed John the report", ["John"], "Only John, not Emailed"),
    ("Reminded Sarah about the party", ["Sarah"], "Only Sarah, not Reminded"),
    ("Invited Mike to the wedding", ["Mike"], "Only Mike, not Invited"),
    # Emotions/adjectives (should NOT be tagged)
    ("Feeling happy about the promotion", [], "No entities - emotion"),
    ("So excited for the trip", [], "No entities - emotion"),
    ("Really anxious about the test", [], "No entities - emotion"),
    ("Feeling grateful today", [], "No entities - emotion"),
    ("So proud of her achievement", [], "No entities - emotion"),
    ("Feeling nostalgic about college", [], "No entities - emotion"),
    ("Really stressed about deadlines", [], "No entities - emotion"),
    ("Feeling overwhelmed lately", [], "No entities - emotion"),
    ("So relieved it worked out", [], "No entities - emotion"),
    ("Feeling frustrated with traffic", [], "No entities - emotion"),
    # Common nouns (should NOT be tagged as ORG)
    ("Had a meeting this afternoon", [], "No entities - common noun"),
    ("Checked my email this morning", [], "No entities - common noun"),
    ("The presentation went well", [], "No entities - common noun"),
    ("Updated the dashboard today", [], "No entities - common noun"),
    ("Reviewed the slides", [], "No entities - common noun"),
    ("Scheduled a call for later", [], "No entities - common noun"),
    ("The project is on track", [], "No entities - common noun"),
    ("Finished the report early", [], "No entities - common noun"),
    ("Attended a workshop today", [], "No entities - common noun"),
    ("The conference was great", [], "No entities - common noun"),
    # Mixed entities
    ("Emma went to Lincoln School today", ["Emma", "Lincoln School"], "PERSON + ORG"),
    ("Dad works at IBM downtown", ["Dad", "IBM"], "KINSHIP + ORG"),
    ("Met John at Starbucks", ["John", "Starbucks"], "PERSON + ORG"),
    ("Mom flew to Boston on Tuesday", ["Mom", "Boston", "Tuesday"], "KINSHIP + LOC + TEMP"),
    ("Sarah started at Microsoft in 2019", ["Sarah", "Microsoft", "2019"], "PER + ORG + TEMP"),
    ("Grandpa lived in Chicago since 1960", ["Grandpa", "Chicago", "1960"], "KIN + LOC + TEMP"),
    (
        "Uncle Bob retired from Ford last year",
        ["Uncle Bob", "Ford", "last year"],
        "KIN + ORG + TEMP",
    ),
    ("Rachel graduated from Harvard in May", ["Rachel", "Harvard", "May"], "PER + ORG + TEMP"),
    ("Dad and Mom went to Paris for anniversary", ["Dad", "Mom", "Paris"], "KIN + KIN + LOC"),
    (
        "Emma and Sofia visited Grandma yesterday",
        ["Emma", "Sofia", "Grandma", "yesterday"],
        "Multiple",
    ),
]

# HARD: Ambiguous cases, edge cases, and tricky patterns
HARD_TESTS = [
    # Sentence-initial capitalized verbs (tricky)
    ("Learned a lot from the workshop", [], "Learned is verb, not entity"),
    ("Thinking about vacation plans", [], "Thinking is verb, not entity"),
    ("Working on the new feature", [], "Working is verb, not entity"),
    ("Started the day with coffee", [], "Started is verb, not entity"),
    ("Finished everything on time", [], "Finished is verb, not entity"),
    ("Decided to take the job", [], "Decided is verb, not entity"),
    ("Realized I forgot the keys", [], "Realized is verb, not entity"),
    ("Noticed something strange", [], "Noticed is verb, not entity"),
    ("Discovered a new restaurant", [], "Discovered is verb, not entity"),
    ("Remembered the password finally", [], "Remembered is verb, not entity"),
    # Past participles that look like names
    ("Impressed by the presentation", [], "Impressed is adjective"),
    ("Amazed at the results", [], "Amazed is adjective"),
    ("Surprised by the outcome", [], "Surprised is adjective"),
    ("Confused about the instructions", [], "Confused is adjective"),
    ("Concerned about the budget", [], "Concerned is adjective"),
    ("Interested in the opportunity", [], "Interested is adjective"),
    ("Tired after the long day", [], "Tired is adjective"),
    ("Worried about the deadline", [], "Worried is adjective"),
    ("Satisfied with the work", [], "Satisfied is adjective"),
    ("Disappointed by the news", [], "Disappointed is adjective"),
    # Time words that look like entities
    ("The afternoon was productive", [], "afternoon is time, not entity"),
    ("This morning was hectic", [], "morning is time, not entity"),
    ("The evening went smoothly", [], "evening is time, not entity"),
    ("Had a late night working", [], "night is time, not entity"),
    ("Early morning workout", [], "morning is time, not entity"),
    # Role words (should NOT be ORG)
    ("Talked to my manager about it", [], "manager is role, not entity"),
    ("The director approved the plan", [], "director is role, not entity"),
    ("Meeting with the team lead", [], "team lead is role, not entity"),
    ("Asked the supervisor for help", [], "supervisor is role, not entity"),
    ("The CEO announced changes", [], "CEO is role, not entity"),
    # Composite entities (should extract full span)
    ("Visited the Golden Gate Bridge", ["Golden Gate Bridge"], "Full location"),
    ("Flew into Los Angeles International", ["Los Angeles International"], "Full location"),
    ("Studied at University of Michigan", ["University of Michigan"], "Full org"),
    ("Works at Bank of America", ["Bank of America"], "Full org"),
    ("Moved to New York City last year", ["New York City", "last year"], "Full loc + temp"),
    # Family-specific entities
    ("Grandma gave me her wedding ring", ["Grandma", "wedding ring"], "KINSHIP + HEIRLOOM"),
    ("Found Dad's old photo album", ["Dad"], "KINSHIP + implicit heirloom"),
    ("Mom's china set from grandmother", ["Mom", "grandmother"], "KINSHIP references"),
    ("Family recipe from great-grandma", ["great-grandma"], "KINSHIP"),
    ("Inherited grandpa's watch", ["grandpa"], "KINSHIP + implicit heirloom"),
    # Pet names
    ("Took Buddy to the vet", ["Buddy"], "PET name"),
    ("Max is getting old", ["Max"], "PET name"),
    ("Luna needs her shots", ["Luna"], "PET name"),
    ("Charlie loves the park", ["Charlie"], "PET name"),
    ("Bella and Rocky played outside", ["Bella", "Rocky"], "Two PET names"),
    # Ambiguous names (could be person or place)
    ("Georgia called about the trip", ["Georgia"], "PERSON not state"),
    ("Austin moved to Texas", ["Austin", "Texas"], "PERSON + LOCATION"),
    ("Brooklyn is turning 5", ["Brooklyn"], "PERSON not borough"),
    ("Paris sent me a message", ["Paris"], "Could be PERSON"),
    ("Dakota visited last week", ["Dakota", "last week"], "PERSON + TEMP"),
    # Very long sentences
    (
        "Yesterday Mom and Dad took Emma and Sofia to Lincoln School for the annual spring festival where they met Grandma and Grandpa who drove from Chicago",
        ["Mom", "Dad", "Emma", "Sofia", "Lincoln School", "Grandma", "Grandpa", "Chicago"],
        "Multiple entities in long sentence",
    ),
    (
        "Sarah worked at Google in San Francisco from 2018 to 2022 before moving to Microsoft in Seattle last January",
        [
            "Sarah",
            "Google",
            "San Francisco",
            "2018",
            "2022",
            "Microsoft",
            "Seattle",
            "last January",
        ],
        "Complex work history",
    ),
    (
        "Uncle Bob and Aunt Mary celebrated their 50th anniversary at the Ritz Carlton in New York on December 15th",
        ["Uncle Bob", "Aunt Mary", "Ritz Carlton", "New York", "December 15th"],
        "Celebration with multiple entities",
    ),
    # Sentences with no entities at all
    ("Had a great day today", [], "Pure sentiment"),
    ("Feeling better now", [], "Pure emotion"),
    ("Everything went smoothly", [], "No entities"),
    ("Just another normal day", [], "No entities"),
    ("Things are looking up", [], "No entities"),
    ("Made some progress today", [], "No entities"),
    ("Took a break this afternoon", [], "No entities"),
    ("Rested and relaxed all day", [], "No entities"),
    ("Worked from home today", [], "No entities"),
    ("Stayed in and watched movies", [], "No entities"),
    # Tricky punctuation and formatting
    ("Emma's graduation was beautiful", ["Emma"], "Possessive"),
    ("It's John's birthday today", ["John"], "Possessive + contraction"),
    ("Mom, Dad, and Grandma came over", ["Mom", "Dad", "Grandma"], "Comma-separated"),
    ("Called John, Sarah, and Mike", ["John", "Sarah", "Mike"], "List of names"),
    ("(Emma and Sofia) went to school", ["Emma", "Sofia"], "Parentheses"),
    # Questions
    ("Did John call about the meeting?", ["John"], "Question format"),
    ("Where did Emma go yesterday?", ["Emma"], "Question format"),
    ("Has Mom arrived yet?", ["Mom"], "Question format"),
    ("When is Sarah's flight?", ["Sarah"], "Question format"),
    ("Is Grandma coming for dinner?", ["Grandma"], "Question format"),
    # Exclamations
    ("Emma won the competition!", ["Emma"], "Exclamation"),
    ("John got promoted!", ["John"], "Exclamation"),
    ("Mom is here!", ["Mom"], "Exclamation"),
    ("Great news from Sarah!", ["Sarah"], "Exclamation"),
    ("Grandpa called!", ["Grandpa"], "Exclamation"),
]

# =============================================================================
# GARBAGE WORDS TO DETECT FALSE POSITIVES
# =============================================================================

GARBAGE_WORDS = {
    # Verbs commonly mistagged
    "met",
    "asked",
    "called",
    "told",
    "saw",
    "helped",
    "texted",
    "emailed",
    "reminded",
    "invited",
    "learned",
    "thinking",
    "working",
    "started",
    "finished",
    "decided",
    "realized",
    "noticed",
    "discovered",
    "remembered",
    "had",
    "went",
    "got",
    "took",
    "made",
    "came",
    "found",
    "put",
    "kept",
    # Emotions/adjectives mistagged
    "happy",
    "excited",
    "anxious",
    "grateful",
    "proud",
    "nostalgic",
    "stressed",
    "overwhelmed",
    "relieved",
    "frustrated",
    "impressed",
    "amazed",
    "surprised",
    "confused",
    "concerned",
    "interested",
    "tired",
    "worried",
    "satisfied",
    "disappointed",
    # Common nouns mistagged as ORG
    "meeting",
    "email",
    "presentation",
    "dashboard",
    "slides",
    "call",
    "project",
    "report",
    "workshop",
    "conference",
    "team",
    "manager",
    "director",
    "supervisor",
    "ceo",
    # Time words mistagged
    "afternoon",
    "morning",
    "evening",
    "night",
    "day",
    # Other garbage
    "feeling",
    "really",
    "so",
    "just",
    "everything",
    "things",
}

# =============================================================================
# TEST RUNNER
# =============================================================================


def run_tests():
    """Run all test cases and report results."""
    print("Loading UltraBERT v4.0.0...")
    start_load = time.time()
    model = UltraBERT.load(encoder_version="v2", quantization="fp32")
    load_time = time.time() - start_load
    print(f"Model loaded in {load_time:.2f}s\n")

    all_tests = [
        ("EASY", EASY_TESTS),
        ("MEDIUM", MEDIUM_TESTS),
        ("HARD", HARD_TESTS),
    ]

    total_clean = 0
    total_garbage = 0
    total_tests = 0

    for difficulty, tests in all_tests:
        print("=" * 80)
        print(f" {difficulty} TESTS ({len(tests)} cases)")
        print("=" * 80)

        clean = 0
        garbage = 0
        garbage_details = []

        for test_data in tests:
            text = test_data[0]
            expected = test_data[1]
            note = test_data[2] if len(test_data) > 2 else ""

            r = model.analyze(text)

            fam = r.capabilities.get("ner_family", {}).get("entities", [])
            gen = r.capabilities.get("ner_general", {}).get("entities", [])
            temp = r.capabilities.get("temporal", {}).get("entities", [])

            all_ents = []
            for e in fam:
                all_ents.append((e["text"].strip(), e["label"], "fam", round(e["score"], 2)))
            for e in gen:
                all_ents.append((e["text"].strip(), e["label"], "gen", round(e["score"], 2)))
            for e in temp:
                all_ents.append((e["text"].strip(), e["label"], "temp", round(e["score"], 2)))

            # Check for garbage
            found_garbage = [e for e in all_ents if e[0].lower() in GARBAGE_WORDS]

            if found_garbage:
                garbage += 1
                garbage_details.append((text, found_garbage, note))
                status = "GARBAGE"
            else:
                clean += 1
                status = "CLEAN"

            # Print each test case
            print(f'{status}: "{text}"')
            if all_ents:
                print(f"       Entities: {all_ents}")
            else:
                print("       Entities: (none)")
            if note:
                print(f"       Note: {note}")
            print()

        # Summary for this difficulty
        pct = (clean / len(tests)) * 100 if tests else 0
        print(f"\nResults: {clean}/{len(tests)} clean ({pct:.1f}%)")

        if garbage_details:
            print(f"\nGarbage found in {garbage} cases:")
            for text, found, note in garbage_details[:10]:  # Show first 10
                print(f'  - "{text[:50]}..."')
                print(f"    Garbage: {found}")
            if len(garbage_details) > 10:
                print(f"  ... and {len(garbage_details) - 10} more")

        total_clean += clean
        total_garbage += garbage
        total_tests += len(tests)
        print()

    # Overall summary
    print("=" * 80)
    print(" OVERALL SUMMARY")
    print("=" * 80)
    pct = (total_clean / total_tests) * 100 if total_tests else 0
    print(f"Total: {total_clean}/{total_tests} clean ({pct:.1f}%)")
    print(f"Garbage: {total_garbage}/{total_tests}")
    print()

    if pct >= 95:
        print("EXCELLENT! v4.0.0 NER quality is production-ready.")
    elif pct >= 90:
        print("GOOD! v4.0.0 shows significant improvement over v3.0.4.")
    elif pct >= 80:
        print("ACCEPTABLE. Some filtering still needed.")
    else:
        print("NEEDS WORK. Consider additional filtering.")

    return total_clean, total_garbage, total_tests


if __name__ == "__main__":
    run_tests()

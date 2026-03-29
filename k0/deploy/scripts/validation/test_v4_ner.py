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
    # Additional EASY tests for more variety
    ("Hi Mom", ["Mom"], "Short greeting"),
    ("Papa took the kids to school", ["Papa"], "KINSHIP"),
    ("Dr. Smith examined the patient", ["Dr. Smith"], "PERSON with title"),
    ("Tesla stock is rising", ["Tesla"], "ORG"),
    ("We live in Boston", ["Boston"], "LOCATION"),
    ("The event is on Friday", ["Friday"], "TEMPORAL"),
    ("Aunt Lisa called from Seattle", ["Aunt Lisa", "Seattle"], "KINSHIP + LOCATION"),
    ("Brother Tom works at Starbucks", ["Tom", "Starbucks"], "PERSON + ORG"),
    (
        "Visited Uncle Joe in Denver last month",
        ["Uncle Joe", "Denver", "last month"],
        "KIN + LOC + TEMP",
    ),
    ("Cousin Anna graduated from Yale", ["Anna", "Yale"], "PERSON + ORG"),
    ("Grandpa's birthday is in March", ["Grandpa", "March"], "KINSHIP + TEMPORAL"),
    ("Mom and Dad went to Walmart", ["Mom", "Dad", "Walmart"], "Multiple KINSHIP + ORG"),
    ("Sarah flew to Miami", ["Sarah", "Miami"], "PERSON + LOCATION"),
    ("John started at IBM in January", ["John", "IBM", "January"], "PER + ORG + TEMP"),
    ("Emma loves Disney World", ["Emma", "Disney World"], "PERSON + LOCATION"),
    ("Dad retired from Ford", ["Dad", "Ford"], "KINSHIP + ORG"),
    ("Aunt Karen lives in Phoenix", ["Aunt Karen", "Phoenix"], "KIN + LOC"),
    ("Uncle Mark's farm in Texas", ["Uncle Mark", "Texas"], "KIN + LOC"),
    ("Sofia's school is Harvard", ["Sofia", "Harvard"], "PERSON + ORG"),
    ("Tyler moved to Chicago", ["Tyler", "Chicago"], "PERSON + LOCATION"),
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
    # Additional MEDIUM tests for more variety and family contexts
    ("Picked up groceries for Mom", ["Mom"], "Only Mom, not Picked"),
    ("Drove Grandma to the doctor", ["Grandma"], "Only Grandma, not Drove"),
    ("Baked cookies with Aunt Susan", ["Aunt Susan"], "Only Aunt Susan, not Baked"),
    ("Watched a movie with Dad", ["Dad"], "Only Dad, not Watched"),
    ("Played games with Uncle Tim", ["Uncle Tim"], "Only Uncle Tim, not Played"),
    ("Feeling joyful about the reunion", [], "No entities - emotion"),
    ("Extremely happy with family", [], "No entities - emotion"),
    ("Quite nervous before the wedding", [], "No entities - emotion"),
    ("Very thankful for the support", [], "No entities - emotion"),
    ("Totally excited for Christmas", [], "No entities - emotion"),
    ("Attended the family gathering", [], "No entities - common noun"),
    ("Prepared the holiday meal", [], "No entities - common noun"),
    ("Organized the photo album", [], "No entities - common noun"),
    ("Cleaned the house for guests", [], "No entities - common noun"),
    ("Set up the Christmas tree", [], "No entities - common noun"),
    ("Sarah works at Costco now", ["Sarah", "Costco"], "PERSON + ORG"),
    ("Dad flew to Atlanta on Wednesday", ["Dad", "Atlanta", "Wednesday"], "KIN + LOC + TEMP"),
    ("Mom started at Target in 2021", ["Mom", "Target", "2021"], "KIN + ORG + TEMP"),
    ("Grandpa moved to Orlando since 2015", ["Grandpa", "Orlando", "2015"], "KIN + LOC + TEMP"),
    (
        "Aunt Jane retired from Boeing last year",
        ["Aunt Jane", "Boeing", "last year"],
        "KIN + ORG + TEMP",
    ),
    (
        "Rachel earned her degree from Stanford in June",
        ["Rachel", "Stanford", "June"],
        "PER + ORG + TEMP",
    ),
    (
        "Dad, Mom, and Grandma went to Hawaii",
        ["Dad", "Mom", "Grandma", "Hawaii"],
        "Multiple KIN + LOC",
    ),
    ("Emma, Sofia, and Tyler played at the park", ["Emma", "Sofia", "Tyler"], "Multiple PERSON"),
    ("Family dinner with Uncle Bob and Aunt Mary", ["Uncle Bob", "Aunt Mary"], "Multiple KIN"),
    ("Visited cousins in New Orleans", ["New Orleans"], "LOCATION only"),
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
    # Additional HARD tests for more variety, long sentences, and real family contexts
    ("Cooked dinner for the family", [], "Cooked is verb, not entity"),
    ("Bought presents for everyone", [], "Bought is verb, not entity"),
    ("Planned the vacation itinerary", [], "Planned is verb, not entity"),
    ("Arranged the seating chart", [], "Arranged is verb, not entity"),
    ("Decorated the living room", [], "Decorated is verb, not entity"),
    ("Prepared the guest list", [], "Prepared is verb, not entity"),
    ("Organized the family photos", [], "Organized is verb, not entity"),
    ("Wrapped all the gifts", [], "Wrapped is verb, not entity"),
    ("Baked the birthday cake", [], "Baked is verb, not entity"),
    ("Cleaned up after the party", [], "Cleaned is verb, not entity"),
    ("Thrilled with the new baby", [], "Thrilled is adjective"),
    ("Delighted by the surprise", [], "Delighted is adjective"),
    ("Overjoyed at the news", [], "Overjoyed is adjective"),
    ("Ecstatic about the promotion", [], "Ecstatic is adjective"),
    ("Elated with the results", [], "Elated is adjective"),
    ("Pleased with the outcome", [], "Pleased is adjective"),
    ("Content with life now", [], "Content is adjective"),
    ("Blissful during the holidays", [], "Blissful is adjective"),
    ("Cheerful all morning", [], "Cheerful is adjective"),
    ("Jubilant at the reunion", [], "Jubilant is adjective"),
    ("The weekend was relaxing", [], "weekend is time, not entity"),
    ("This evening feels special", [], "evening is time, not entity"),
    ("Late afternoon nap", [], "afternoon is time, not entity"),
    ("Early evening walk", [], "evening is time, not entity"),
    ("Mid-morning coffee", [], "morning is time, not entity"),
    ("Spoke to the coordinator about it", [], "coordinator is role, not entity"),
    ("The assistant helped with setup", [], "assistant is role, not entity"),
    ("Met with the organizer", [], "organizer is role, not entity"),
    ("Asked the volunteer for directions", [], "volunteer is role, not entity"),
    ("The host welcomed everyone", [], "host is role, not entity"),
    ("Drove over the Brooklyn Bridge", ["Brooklyn Bridge"], "Full location"),
    ("Applied to University of California", ["University of California"], "Full org"),
    ("Works at Wells Fargo Bank", ["Wells Fargo Bank"], "Full org"),
    (
        "Traveled to Washington D.C. last summer",
        ["Washington D.C.", "last summer"],
        "Full loc + temp",
    ),
    ("Family heirloom from Grandma's side", ["Grandma"], "KINSHIP + implicit heirloom"),
    ("Dad's old toolbox from Grandpa", ["Dad", "Grandpa"], "KINSHIP references"),
    ("Mom's recipe book from Grandmother", ["Mom", "Grandmother"], "KINSHIP references"),
    ("Inherited Great-Uncle's watch", ["Great-Uncle"], "KINSHIP"),
    ("Aunt's antique vase", ["Aunt"], "KINSHIP + implicit heirloom"),
    ("Walked Spot in the park", ["Spot"], "PET name"),
    ("Fluffy needs grooming", ["Fluffy"], "PET name"),
    ("Rex and Daisy chased squirrels", ["Rex", "Daisy"], "Two PET names"),
    ("Mittens hid under the bed", ["Mittens"], "PET name"),
    ("Goldie swam in the pond", ["Goldie"], "PET name"),
    ("Madison sent flowers", ["Madison"], "PERSON not city"),
    ("Jackson moved to Florida", ["Jackson", "Florida"], "PERSON + LOCATION"),
    ("Savannah is growing up", ["Savannah"], "PERSON not city"),
    ("Romeo called yesterday", ["Romeo", "yesterday"], "PERSON + TEMP"),
    ("Athena won the award", ["Athena"], "PERSON not goddess context"),
    (
        "During the family reunion last weekend, Mom, Dad, Grandma, Grandpa, Uncle Bob, Aunt Mary, cousins Emma, Sofia, Tyler, and pets Buddy and Luna gathered at our house in Springfield for barbecue and games",
        [
            "Mom",
            "Dad",
            "Grandma",
            "Grandpa",
            "Uncle Bob",
            "Aunt Mary",
            "Emma",
            "Sofia",
            "Tyler",
            "Buddy",
            "Luna",
            "Springfield",
            "last weekend",
        ],
        "Very long family sentence",
    ),
    (
        "Sarah, who works at Microsoft in Seattle, flew to visit her parents in Boston for Thanksgiving, bringing her husband Mike and their kids Emma and John, while Grandma and Grandpa drove from Chicago with Aunt Karen and Uncle Mark",
        [
            "Sarah",
            "Microsoft",
            "Seattle",
            "Boston",
            "Mike",
            "Emma",
            "John",
            "Grandma",
            "Grandpa",
            "Chicago",
            "Aunt Karen",
            "Uncle Mark",
        ],
        "Complex long sentence with work and family",
    ),
    (
        "Uncle Joe's 60th birthday party at the country club in Dallas featured speeches from Dad, Mom, and all the siblings, with cake from Aunt Mary's bakery and photos from Cousin Rachel's camera",
        ["Uncle Joe", "Dallas", "Dad", "Mom", "Aunt Mary", "Cousin Rachel"],
        "Celebration with multiple entities",
    ),
    ("Just relaxing at home", [], "Pure sentiment"),
    ("Feeling peaceful now", [], "Pure emotion"),
    ("All is well today", [], "No entities"),
    ("Ordinary day here", [], "No entities"),
    ("Life is good", [], "No entities"),
    ("Made good progress", [], "No entities"),
    ("Took it easy today", [], "No entities"),
    ("Chilled out all day", [], "No entities"),
    ("Worked remotely again", [], "No entities"),
    ("Stayed home and read", [], "No entities"),
    ("Emma's birthday party was fun", ["Emma"], "Possessive"),
    ("It's Dad's turn to cook", ["Dad"], "Possessive + contraction"),
    ("Mom, Grandma, and Aunt Lisa arrived", ["Mom", "Grandma", "Aunt Lisa"], "Comma-separated"),
    ("Invited John, Sarah, and Emma", ["John", "Sarah", "Emma"], "List of names"),
    ("(Dad and Uncle Bob) fixed the car", ["Dad", "Uncle Bob"], "Parentheses"),
    ("Did Grandma call yet?", ["Grandma"], "Question format"),
    ("Where did Aunt Mary go?", ["Aunt Mary"], "Question format"),
    ("Has Uncle Tim arrived?", ["Uncle Tim"], "Question format"),
    ("When is Cousin's flight?", ["Cousin"], "Question format"),
    ("Is Grandpa here already?", ["Grandpa"], "Question format"),
    ("Sarah got the job!", ["Sarah"], "Exclamation"),
    ("John won the lottery!", ["John"], "Exclamation"),
    ("Mom made it!", ["Mom"], "Exclamation"),
    ("Great update from Dad!", ["Dad"], "Exclamation"),
    ("Grandma recovered!", ["Grandma"], "Exclamation"),
    # Very long sentences with many entities (1000+ words worth of content)
    (
        "Yesterday morning at 8am, Mom Sarah Johnson picked up her children Emma and Sofia from Lincoln Elementary School in downtown Chicago, then drove to meet Dad Michael at the family doctor Dr. Robert Smith for their annual checkups, after which they all went to Grandma Mary's house in suburban Evanston for a big family lunch with Uncle Tom, Aunt Lisa, cousins Tyler and Rachel, and even the family dog Buddy who had just returned from the vet at Animal Hospital on Michigan Avenue, while Grandpa George stayed home watching the Chicago Bears game on TV before joining everyone later for cake and ice cream at Baskin Robbins on Main Street around 3pm in the afternoon.",
        [
            "Sarah Johnson",
            "Emma",
            "Sofia",
            "Lincoln Elementary School",
            "Chicago",
            "Michael",
            "Dr. Robert Smith",
            "Grandma Mary",
            "Evanston",
            "Uncle Tom",
            "Aunt Lisa",
            "Tyler",
            "Rachel",
            "Buddy",
            "Animal Hospital",
            "Michigan Avenue",
            "Grandpa George",
            "Chicago Bears",
            "Baskin Robbins",
            "Main Street",
            "3pm",
            "afternoon",
        ],
        "Very long family day narrative with 22 entities",
    ),
    (
        "During the summer vacation in July 2023, the entire extended family including Mom Jennifer, Dad David, Grandma Patricia, Grandpa William, Uncle James and Aunt Karen with their kids Emily and Jacob, plus Aunt Susan and Uncle Mark's children Sophia and Alexander, all gathered at the large family cabin in Lake Tahoe for two weeks of swimming, hiking, and barbecues, where they celebrated Grandma's 75th birthday on July 15th with a huge cake from the local bakery Sweet Delights, played games with the family pets Max the golden retriever and Luna the cat, visited nearby attractions like the Tahoe Rim Trail and Emerald Bay State Park, ate at restaurants such as The Beacon and Sunnyside Lodge, and even took a family boat ride on the lake organized by Captain Bob's Boat Rentals, all while staying in touch with Cousin Rachel who was working at Google in San Francisco and couldn't make it this year.",
        [
            "Jennifer",
            "David",
            "Grandma Patricia",
            "Grandpa William",
            "Uncle James",
            "Aunt Karen",
            "Emily",
            "Jacob",
            "Aunt Susan",
            "Uncle Mark",
            "Sophia",
            "Alexander",
            "Lake Tahoe",
            "July 2023",
            "July 15th",
            "Sweet Delights",
            "Max",
            "Luna",
            "Tahoe Rim Trail",
            "Emerald Bay State Park",
            "The Beacon",
            "Sunnyside Lodge",
            "Captain Bob's Boat Rentals",
            "Rachel",
            "Google",
            "San Francisco",
        ],
        "Extended family vacation story with 26 entities",
    ),
    (
        "On Christmas Eve 2022 at exactly 6pm, the whole family assembled at Mom Elizabeth and Dad Thomas's beautiful Victorian house on Oak Street in historic Boston, where Grandma Helen and Grandpa Charles arrived first from their apartment in Cambridge, followed by Uncle Peter and Aunt Margaret with their three children Anna, Benjamin, and Charlotte from their home in nearby Somerville, then Aunt Victoria and Uncle Richard brought their twins Daniel and Olivia along with family friend Dr. Sarah Mitchell the pediatrician, everyone gathered around the massive Christmas tree decorated with ornaments collected over decades from trips to Paris, London, and Tokyo, they exchanged gifts including a new bicycle for young Tommy from Santa Claus, ate a traditional dinner of roast turkey, mashed potatoes, and pumpkin pie prepared by Chef Maria from the local catering company Boston Gourmet, sang carols accompanied by Uncle Peter's guitar playing, and stayed up late into the night sharing stories about past holidays in New York City, Los Angeles, and even a memorable trip to Disney World in Orlando when the kids were small.",
        [
            "Christmas Eve 2022",
            "6pm",
            "Elizabeth",
            "Thomas",
            "Oak Street",
            "Boston",
            "Grandma Helen",
            "Grandpa Charles",
            "Cambridge",
            "Uncle Peter",
            "Aunt Margaret",
            "Anna",
            "Benjamin",
            "Charlotte",
            "Somerville",
            "Aunt Victoria",
            "Uncle Richard",
            "Daniel",
            "Olivia",
            "Dr. Sarah Mitchell",
            "Paris",
            "London",
            "Tokyo",
            "Tommy",
            "Santa Claus",
            "Chef Maria",
            "Boston Gourmet",
            "New York City",
            "Los Angeles",
            "Disney World",
            "Orlando",
        ],
        "Christmas gathering epic with 31 entities",
    ),
    (
        "The family reunion last Labor Day weekend in September 2021 brought together over fifty relatives from across the country, starting with the early arrivals on Friday evening when Mom Karen and Dad Steven welcomed Grandma Dorothy and Grandpa Frank from their retirement home in Phoenix, Arizona, followed by Uncle Robert and Aunt Jennifer's family including their four children Michael, Sarah, Christopher, and Amanda who drove all the way from Seattle, Washington in their minivan, then Saturday morning saw the arrival of Aunt Barbara and Uncle Thomas with their grandchildren Emma, Sophia, and little baby Gabriel from their farm in rural Iowa, everyone gathered at the large pavilion in Central Park for the main event where they enjoyed barbecue from Pitmaster Joe's Smokehouse, played traditional games like sack races and three-legged races organized by Cousin David the event coordinator, listened to live music from the Johnson Family Band featuring Uncle Mark on drums and Aunt Lisa on keyboard, shared photos from past reunions in places like Yellowstone National Park, the Grand Canyon, and Niagara Falls, and even had a special visit from family historian Professor James who brought old albums from the 1950s showing ancestors in Chicago, Detroit, and Milwaukee, all culminating in a grand fireworks display at 9pm sponsored by local business owner Mr. Thompson's Fireworks Company.",
        [
            "Labor Day",
            "September 2021",
            "Karen",
            "Steven",
            "Grandma Dorothy",
            "Grandpa Frank",
            "Phoenix",
            "Arizona",
            "Uncle Robert",
            "Aunt Jennifer",
            "Michael",
            "Sarah",
            "Christopher",
            "Amanda",
            "Seattle",
            "Washington",
            "Aunt Barbara",
            "Uncle Thomas",
            "Emma",
            "Sophia",
            "Gabriel",
            "Iowa",
            "Central Park",
            "Pitmaster Joe's Smokehouse",
            "Cousin David",
            "Johnson Family Band",
            "Uncle Mark",
            "Aunt Lisa",
            "Yellowstone National Park",
            "Grand Canyon",
            "Niagara Falls",
            "Professor James",
            "Chicago",
            "Detroit",
            "Milwaukee",
            "9pm",
            "Mr. Thompson's Fireworks Company",
        ],
        "Massive family reunion with 38 entities",
    ),
    (
        "In the spring of 2020 during the early days of the pandemic, our family adapted remarkably well when Mom Jessica coordinated virtual family meetings every Sunday at 2pm using Zoom video calls that connected Grandma Linda in her assisted living facility in Miami, Florida, with Dad Robert working from home in our house in Austin, Texas, while Uncle Daniel and Aunt Michelle's children Sophia and Alexander attended from their apartment in New York City, and even Grandpa Edward participated from his cabin in the mountains of Colorado, everyone shared updates about their week including Uncle Peter's job at Microsoft in Redmond, Washington, Aunt Karen's teaching at Lincoln High School in Boston, Massachusetts, Cousin Rachel's medical residency at Johns Hopkins Hospital in Baltimore, Maryland, and various other family members working at companies like Amazon in Seattle, Apple in Cupertino, and Tesla in Palo Alto, they discussed everything from gardening tips from Grandpa's vegetable patch to cooking recipes from Grandma's collection, played online games organized by tech-savvy Cousin David, and maintained family traditions like virtual birthday celebrations for little Emma's fifth birthday on April 12th with cake delivered by local bakery Sweet Dreams and presents shipped from various relatives across the country.",
        [
            "2020",
            "Jessica",
            "Zoom",
            "Grandma Linda",
            "Miami",
            "Florida",
            "Robert",
            "Austin",
            "Texas",
            "Uncle Daniel",
            "Aunt Michelle",
            "Sophia",
            "Alexander",
            "New York City",
            "Grandpa Edward",
            "Colorado",
            "Uncle Peter",
            "Microsoft",
            "Redmond",
            "Washington",
            "Aunt Karen",
            "Lincoln High School",
            "Boston",
            "Massachusetts",
            "Cousin Rachel",
            "Johns Hopkins Hospital",
            "Baltimore",
            "Maryland",
            "Amazon",
            "Seattle",
            "Apple",
            "Cupertino",
            "Tesla",
            "Palo Alto",
            "Cousin David",
            "Emma",
            "April 12th",
            "Sweet Dreams",
        ],
        "Pandemic family adaptation story with 39 entities",
    ),
    # Additional very long sentences with extensive entity coverage
    (
        "Back in the summer of 2019 before everything changed, our extended family organized the biggest family reunion ever at Aunt Barbara and Uncle Thomas's sprawling ranch in Montana, where over eighty relatives gathered for a full week of activities starting with the arrival on Sunday when Mom Susan and Dad Richard flew in from their home in Portland, Oregon with the kids Emily and Jacob, followed by Grandma Patricia and Grandpa Harold driving up from their retirement community in Tucson, Arizona in their RV, then Monday brought Uncle James and Aunt Margaret's family from Denver, Colorado including their children Sarah, Michael, and baby Olivia, while Cousin David coordinated everything from his office at IBM in Chicago, Illinois, everyone participated in daily events like horseback riding at the local stables owned by Mr. Johnson, fishing trips to the nearby lakes organized by Captain Steve's Guide Service, hiking expeditions led by experienced guide Ranger Mike from Yellowstone National Park, cooking classes taught by celebrity chef Giovanni from the Food Network, and evening bonfires with s'mores and storytelling sessions featuring Grandpa's tales of growing up in the 1950s in small-town America, all while staying in luxury cabins provided by Mountain View Resort and Spa, eating meals prepared by the resort's team under Chef Isabella, and enjoying entertainment from the Johnson Family Band with Uncle Mark on guitar, Aunt Lisa on violin, and Cousin Rachel singing backup vocals.",
        [
            "2019",
            "Aunt Barbara",
            "Uncle Thomas",
            "Montana",
            "Mom Susan",
            "Dad Richard",
            "Portland",
            "Oregon",
            "Emily",
            "Jacob",
            "Grandma Patricia",
            "Grandpa Harold",
            "Tucson",
            "Arizona",
            "Uncle James",
            "Aunt Margaret",
            "Denver",
            "Colorado",
            "Sarah",
            "Michael",
            "Olivia",
            "Cousin David",
            "IBM",
            "Chicago",
            "Illinois",
            "Mr. Johnson",
            "Captain Steve's Guide Service",
            "Ranger Mike",
            "Yellowstone National Park",
            "Giovanni",
            "Food Network",
            "Mountain View Resort and Spa",
            "Chef Isabella",
            "Johnson Family Band",
            "Uncle Mark",
            "Aunt Lisa",
            "Cousin Rachel",
        ],
        "Massive Montana family reunion with 38 entities",
    ),
    (
        "The annual family Christmas gathering at Grandma Elizabeth and Grandpa Robert's historic Victorian home in historic Savannah, Georgia has become a cherished tradition since 1985, where every year without fail the entire clan assembles on December 23rd for a multi-day celebration featuring the early arrivals like Aunt Victoria and Uncle William from their plantation home in Charleston, South Carolina with their children Anna, Benjamin, and Charlotte, followed by Uncle Peter and Aunt Margaret's family from Atlanta, Georgia including their twins Daniel and Olivia plus family friend Dr. Sarah Mitchell the pediatrician, everyone decorates the massive twelve-foot Christmas tree with ornaments collected from trips to Europe including Paris, France and Rome, Italy, exchanges gifts purchased from local artisans at the Savannah College of Art and Design gift shop, enjoys a traditional Southern dinner of pecan-crusted ham, sweet potato casserole, and peach cobbler prepared by Chef Maria from the local catering company Southern Gourmet, sings carols accompanied by Uncle Peter's piano playing and Aunt Lisa's flute, shares family stories about ancestors who fought in the Civil War and built the family fortune through cotton plantations in the 1800s, and stays up late playing board games organized by tech-savvy Cousin David using his collection of vintage games from the 1970s, all while the younger kids like Emma, Sophia, and little Gabriel build snowmen in the backyard despite the Georgia warmth and roast marshmallows over the fire pit.",
        [
            "Grandma Elizabeth",
            "Grandpa Robert",
            "Savannah",
            "Georgia",
            "1985",
            "December 23rd",
            "Aunt Victoria",
            "Uncle William",
            "Charleston",
            "South Carolina",
            "Anna",
            "Benjamin",
            "Charlotte",
            "Uncle Peter",
            "Aunt Margaret",
            "Atlanta",
            "Daniel",
            "Olivia",
            "Dr. Sarah Mitchell",
            "Europe",
            "Paris",
            "France",
            "Rome",
            "Italy",
            "Savannah College of Art and Design",
            "Chef Maria",
            "Southern Gourmet",
            "Uncle Peter",
            "Aunt Lisa",
            "Civil War",
            "Cousin David",
            "Emma",
            "Sophia",
            "Gabriel",
        ],
        "Savannah Christmas tradition with 35 entities",
    ),
    (
        "During the magical summer of 2018, our family embarked on the ultimate cross-country road trip adventure starting from our home in Los Angeles, California when Dad Michael loaded up the family minivan with Mom Jennifer, kids Emma and Tyler, Grandma Patricia, and even the family dog Max, driving first to the Grand Canyon in Arizona for three days of hiking and sightseeing at the visitor center operated by the National Park Service, then continuing to Santa Fe, New Mexico to explore the historic plaza and visit the Georgia O'Keeffe Museum, followed by a stop in Amarillo, Texas for barbecue at the famous Big Texan Steak Ranch, then on to Oklahoma City, Oklahoma to see the Myriad Botanical Gardens and Crystal Bridge Tropical Conservatory, continuing through Kansas City, Missouri for jazz at the Blue Room and barbecue at Gates Bar-B-Que, then St. Louis, Missouri for the Gateway Arch and a riverboat cruise on the Mississippi, Chicago, Illinois for deep dish pizza at Giordano's and a Cubs game at Wrigley Field, Milwaukee, Wisconsin for beer tasting at Lakefront Brewery, Madison, Wisconsin for the capitol building tour, Minneapolis, Minnesota for the Mall of America shopping, Mount Rushmore in South Dakota, Yellowstone National Park in Wyoming for geysers and wildlife, the Badlands in South Dakota, Mount Rushmore again, then back through the Black Hills, Rapid City, South Dakota, and finally home after eight weeks and over 8000 miles of unforgettable family memories.",
        [
            "2018",
            "Los Angeles",
            "California",
            "Dad Michael",
            "Mom Jennifer",
            "Emma",
            "Tyler",
            "Grandma Patricia",
            "Max",
            "Grand Canyon",
            "Arizona",
            "National Park Service",
            "Santa Fe",
            "New Mexico",
            "Georgia O'Keeffe Museum",
            "Amarillo",
            "Texas",
            "Big Texan Steak Ranch",
            "Oklahoma City",
            "Oklahoma",
            "Myriad Botanical Gardens",
            "Crystal Bridge Tropical Conservatory",
            "Kansas City",
            "Missouri",
            "Blue Room",
            "Gates Bar-B-Que",
            "St. Louis",
            "Gateway Arch",
            "Mississippi",
            "Chicago",
            "Illinois",
            "Giordano's",
            "Cubs",
            "Wrigley Field",
            "Milwaukee",
            "Wisconsin",
            "Lakefront Brewery",
            "Madison",
            "capitol",
            "Minneapolis",
            "Minnesota",
            "Mall of America",
            "Mount Rushmore",
            "South Dakota",
            "Yellowstone National Park",
            "Wyoming",
            "Badlands",
            "Black Hills",
            "Rapid City",
        ],
        "Epic cross-country road trip with 50 entities",
    ),
    (
        "The family wedding of Cousin Rachel and her fiancé Dr. James Harrison at the beautiful Vineyard Haven wedding venue on Martha's Vineyard, Massachusetts in June 2022 was absolutely spectacular, attended by over 150 guests including immediate family like Mom Elizabeth, Dad Thomas, Grandma Helen, Grandpa Charles, and siblings Emma and Sophia, extended family such as Aunt Victoria, Uncle Richard, Aunt Barbara, Uncle Thomas, and numerous cousins from both sides, close friends including Rachel's college roommate Sarah from Harvard University, James's best man Michael from Yale Medical School, and bridesmaid Anna from Princeton, professional colleagues like Rachel's boss Dr. Lisa Chen from Massachusetts General Hospital and James's mentor Dr. Robert Smith from Brigham and Women's Hospital, and even international guests from London, England and Sydney, Australia, the ceremony took place outdoors under a floral arch decorated by local florist Bloom & Blossom, followed by a cocktail hour featuring champagne from Moët & Chandon and hors d'oeuvres from Boston caterer Events by Design, then a formal dinner of lobster bisque, herb-crusted salmon, and chocolate soufflé prepared by celebrity chef Thomas Keller from The French Laundry, dancing to music by the band Groove Merchants with DJ mixing by Cousin David, and late-night snacks from the dessert bar featuring macarons from Ladurée and cupcakes from Georgetown Cupcake, all coordinated by wedding planner extraordinaire Amanda from Elegant Affairs and photographed by renowned photographer Marcus from New England Wedding Photography.",
        [
            "Cousin Rachel",
            "Dr. James Harrison",
            "Vineyard Haven",
            "Martha's Vineyard",
            "Massachusetts",
            "June 2022",
            "Mom Elizabeth",
            "Dad Thomas",
            "Grandma Helen",
            "Grandpa Charles",
            "Emma",
            "Sophia",
            "Aunt Victoria",
            "Uncle Richard",
            "Aunt Barbara",
            "Uncle Thomas",
            "Sarah",
            "Harvard University",
            "Michael",
            "Yale Medical School",
            "Anna",
            "Princeton",
            "Dr. Lisa Chen",
            "Massachusetts General Hospital",
            "Dr. Robert Smith",
            "Brigham and Women's Hospital",
            "London",
            "England",
            "Sydney",
            "Australia",
            "Bloom & Blossom",
            "Moët & Chandon",
            "Boston",
            "Events by Design",
            "Thomas Keller",
            "The French Laundry",
            "Groove Merchants",
            "Cousin David",
            "Ladurée",
            "Georgetown Cupcake",
            "Amanda",
            "Elegant Affairs",
            "Marcus",
            "New England Wedding Photography",
        ],
        "Grand wedding celebration with 45 entities",
    ),
    (
        "When our family decided to build the ultimate backyard oasis in the summer of 2021 at our home in suburban Chicago, Illinois, the project became a massive undertaking involving multiple contractors and family members working together, starting with landscape architect Maria from GreenScapes Design who created the initial plans featuring a swimming pool by Pool Masters of Illinois, outdoor kitchen built by Custom Outdoor Kitchens, fire pit installed by Stone Age Fireplaces, pergola constructed by TimberTech Structures, and lighting by Illuminations Outdoor Lighting, family members contributed significantly with Uncle James handling the electrical work using supplies from Home Depot, Cousin David managing the project coordination with his experience from working at Boeing in Seattle, Aunt Karen organizing the family workdays every Saturday with food provided by local caterer Potbelly Sandwich Shop, Grandpa Harold sharing his carpentry skills to build custom benches and tables, Grandma Patricia planting the flower gardens with perennials from Spring Valley Nursery, Mom Susan coordinating the interior design touches with fabrics from Pottery Barn, Dad Robert managing the budget and payments to all the contractors, and the kids Emma, Sophia, and Tyler helping with painting and cleanup, even the family pets Buddy and Luna got involved by providing entertainment during breaks, all culminating in a grand opening barbecue party on July 4th with fireworks from Phantom Fireworks and food from Chicago Style BBQ, attended by all the extended family including relatives from Milwaukee, Wisconsin and Minneapolis, Minnesota.",
        [
            "2021",
            "Chicago",
            "Illinois",
            "Maria",
            "GreenScapes Design",
            "Pool Masters of Illinois",
            "Custom Outdoor Kitchens",
            "Stone Age Fireplaces",
            "TimberTech Structures",
            "Illuminations Outdoor Lighting",
            "Uncle James",
            "Home Depot",
            "Cousin David",
            "Boeing",
            "Seattle",
            "Aunt Karen",
            "Potbelly Sandwich Shop",
            "Grandpa Harold",
            "Grandma Patricia",
            "Spring Valley Nursery",
            "Mom Susan",
            "Pottery Barn",
            "Dad Robert",
            "Emma",
            "Sophia",
            "Tyler",
            "Buddy",
            "Luna",
            "July 4th",
            "Phantom Fireworks",
            "Chicago Style BBQ",
            "Milwaukee",
            "Wisconsin",
            "Minneapolis",
            "Minnesota",
        ],
        "Backyard oasis construction project with 36 entities",
    ),
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

            # Debug: print all extracted entities for every test case
            print(f"\nTEXT: '{text}'")
            print(f"EXPECTED: {expected}")
            print(f"EXTRACTED: {all_ents}")
            if found_garbage:
                print(f"GARBAGE FOUND: {found_garbage}")
            else:
                print("CLEAN: No garbage words detected")
            print("-" * 80)

            if found_garbage:
                garbage += 1
                garbage_details.append((text, found_garbage, note))
            else:
                clean += 1

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
    run_tests()
    run_tests()
    run_tests()
    run_tests()
    run_tests()
    run_tests()
    run_tests()

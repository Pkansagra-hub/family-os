====================================================================================================
 MEMORY LAYERS DEEP DIVE - REAL EXAMPLES FROM YOUR LIFE
====================================================================================================

====================================================================================================

1. EPISODIC MEMORIES (st_epi)
   Purpose: Stores autobiographical events - 'What happened, when, where, with whom'
====================================================================================================

    Total Episodes: 339

   REAL EXAMPLES FROM YOUR LIFE
   ------------------------------------------------------------------------------------------

    Episode 1: Social with Dad, Panda, Prince at Home
      Type: social | Location: Home
      Participants: ["Dad", "Panda", "Prince"]
       Original Memory:
         "Should we get wedding insurance? Panda thinks its unnecessary."
         "Dad advice on work, he thinks architecture feels wrong."

    Episode 2: Unknown with Prince at Gym
      Type: unknown | Location: Gym
      Participants: ["Prince"]
       Original Memory:
         "Gym. Back at it. Felt strong."
         "Gym later. Leg day. Hope my headache doesnt come back."

    Episode 3: Routine with Prince at Home
      Type: routine | Location: Home
      Participants: ["Prince"]
       Original Memory:
         "The flickering stopped after switching docks. Weird. Need to buy a better dock."
         "The green tint is less noticeable in bright scenes. Might be a calibration issue."

    Episode 4: Work at Office
      Type: work | Location: Office
      Participants: []
       Original Memory:
         "P03 consolidation now handles 100k events/hour"
         "AC broke. Summer in Texas. Called emergency repair."

    Episode 5: Routine with Amy, Dad, Marcus at Home
      Type: routine | Location: Home
      Participants: ["Amy", "Dad", "Marcus", "Maya", "Panda", "Prince", "Priya"]
       Original Memory:
         "What did we decide about the monitor? I think we said to contact support."
         "Marcus's birthday party. His apartment is nice. Met his girlfriend Amy."

====================================================================================================
2. SEMANTIC MEMORY (st_sem)
   Purpose: Stores facts, patterns, and generalizations extracted from experiences
====================================================================================================

    Total Patterns: 545

    REAL PATTERNS FROM YOUR EXPERIENCES:
   ------------------------------------------------------------------------------------------

    Pattern 1: optimism emotional pattern
      Type: EMOTIONAL_TREND/None
      Confidence: 0.80
       Learned from:
         "FamilyOS cache implementation started. Hope it doesnt break anything."

    Pattern 2: caring emotional pattern
      Type: EMOTIONAL_TREND/None
      Confidence: 0.80
       Learned from:
         "Panda is worried about her job stability. I reassured her."

    Pattern 3: annoyance emotional pattern
      Type: EMOTIONAL_TREND/None
      Confidence: 0.80
       Learned from:
         "After switching docks, display flicker stopped, but now USB ports feel slower"

    Pattern 4: When I delegate tasks, I feel less overwhelmed. So thats what Ill do more.
      Type: LESSON/None
      Confidence: 0.80
       Learned from:
         "When I delegate tasks, I feel less overwhelmed. So thats what Ill do more."

    Pattern 5: When I reflect on this journey, I see growth. The flicker issue taught me patience and problem-solving skills after switching docks and cables to fix it.
      Type: LESSON/None
      Confidence: 0.80
       Learned from:
         "When I reflect on this journey, I see growth. The flicker issue taught me patience and problem-solvi..."

====================================================================================================
3. KNOWLEDGE GRAPH ENTITIES (st_kg_dom)
   Purpose: Stores entities (people, places, things) and their attributes
====================================================================================================

    Total Entities: 74

    ENTITIES BY TYPE:
      PERSON: 31 entities
         Examples: Maya, Marcus, Vikram, Priya, Alex
      LOCATION: 24 entities
         Examples: Chicago, Japan, Dallas, India, Tokyo
      ORGANIZATION: 11 entities
         Examples: Asus, Amazon, Costco, DFW, K0 dedup
      FAMILY_MEMBER: 8 entities
         Examples: Grandparents, Family, Kids, Parents, Cousin

    REAL ENTITIES FROM YOUR LIFE:
   ------------------------------------------------------------------------------------------

    Person 1: Maya
       Mentioned in:
         "Maya's first swimming lesson. She was terrified. Then loved it."
         "Tummy time with Maya. She hates it. We persist."

    Person 2: Marcus
       Mentioned in:
         "First day back at work. Inbox had 500 emails. Marcus held down the fort."

    Person 3: Vikram
       Mentioned in:
         "Moving day. Dad and Vikram helping via FaceTime directions."

    Person 4: Priya
       Mentioned in:
         "Priya is leaving for another company. Sad to see her go."

    Person 5: Alex
       Mentioned in:
         "Alex asked for code review advice. We spent an hour going over best practices."

====================================================================================================
4. SOCIAL RELATIONSHIPS (st_social)
   Purpose: Stores relationships between the person and others
====================================================================================================

    Total Relationships: 39

    YOUR KEY RELATIONSHIPS (with computed sentiment from observations):
   ------------------------------------------------------------------------------------------

    Panda (FAMILY)
      Interactions: 19 | Sentiment: 0.62 | Emotion: joy

    Dad (FAMILY)
      Interactions: 5 | Sentiment: 0.61 | Emotion: joy

    Maya (FAMILY)
      Interactions: 4 | Sentiment: 0.62 | Emotion: joy

    Mom (FAMILY)
      Interactions: 3 | Sentiment: 0.64 | Emotion: joy

    Sarah (COLLEAGUE)
      Interactions: 3 | Sentiment: 0.76 | Emotion: joy

    Karen (FAMILY)
      Interactions: 3 | Sentiment: 0.57 | Emotion: joy

====================================================================================================
5. PROSPECTIVE MEMORY (st_prospective)
   Purpose: Stores future intentions, reminders, and planned actions
====================================================================================================

    Total Intentions/Reminders: 257

    YOUR REMINDERS & DECISIONS:
   ------------------------------------------------------------------------------------------

    DECISION: Should I finally book the Chicago trip?
      Status: ACTIVE | Confidence: 0.80
       From:
         "Should I finally book the Chicago trip?"

    REMINDER: clean the guest room
      Status: ACTIVE | Confidence: 0.80
       From:
         "clean the guest room"

    REMINDER: track my sleep better
      Status: ACTIVE | Confidence: 0.80
       From:
         "track my sleep better"

    REMINDER: book DMV appointment for license renewal
      Status: ACTIVE | Confidence: 0.80
       From:
         "book DMV appointment for license renewal"

    DECISION: Dad advice on work, he thinks architecture feels wrong.
      Status: ACTIVE | Confidence: 0.80
       From:
         "Dad advice on work, he thinks architecture feels wrong."

    DECISION: Should we get wedding insurance? Panda thinks its unnecessary.
      Status: ACTIVE | Confidence: 0.80
       From:
         "Should we get wedding insurance? Panda thinks its unnecessary."

====================================================================================================
6. ST_OBSERVATIONS - THE HOLISTIC CONTEXT LAYER
   Purpose: Links every memory write to its full contextual situation
====================================================================================================

    Total Observations: 10747

    OBSERVATIONS BY MEMORY LAYER:
      st_kg_edges: 9236 observations (avg sentiment: 0.68)
      st_sem: 545 observations (avg sentiment: 0.59)
      st_epi: 339 observations (avg sentiment: 0.58)
      st_prospective: 257 observations (avg sentiment: 0.00)
      st_social: 206 observations (avg sentiment: 0.00)
      st_kg_dom: 164 observations (avg sentiment: 0.00)

====================================================================================================
 HOLISTIC QUERIES - MEMORIES WITH FULL CONTEXT
====================================================================================================

    QUERY 1: Most Joyful Episodes (emotion = joy/love/gratitude)
   ------------------------------------------------------------------------------------------

    #1 Milestone with Dad, Maya, Mom at New House
       Location: New House |  With: ["Dad", "Maya", "Mom", "Panda"]
       Time: morning/ | Weekend: True
       Sentiment: 0.88 | Emotion: love
       "Started teaching Maya to read. Simple words first."

    #2 Milestone at Home
       Location: Home |  With: []
       Time: afternoon/ | Weekend: False
       Sentiment: 0.87 | Emotion: joy
       "Pride milestones."

    #3 Milestone with Marcus at Office
       Location: Office |  With: ["Marcus"]
       Time: morning/ | Weekend: False
       Sentiment: 0.87 | Emotion: joy
       "Marcus invited me to his birthday party next Saturday. Buying a gift."


    QUERY 2: Relationships - Who Brings Joy?
   ------------------------------------------------------------------------------------------

    Panda (FAMILY)
      Interactions: 19 | Avg Sentiment: 0.00
      Emotions: ['neutral']

    Dad (FAMILY)
      Interactions: 5 | Avg Sentiment: 0.00
      Emotions: ['neutral']

    Maya (FAMILY)
      Interactions: 4 | Avg Sentiment: 0.00
      Emotions: ['neutral']

    Karen (FAMILY)
      Interactions: 3 | Avg Sentiment: 0.00
      Emotions: ['neutral']


    QUERY 3: When Are You Happiest? (Time-of-Day Analysis)
   ------------------------------------------------------------------------------------------

====================================================================================================
 YOUR LIFE STORY - A HOLISTIC VIEW
====================================================================================================

   Based on your memories, here's what the system knows about your life:

    KEY PEOPLE IN YOUR LIFE:
      * Panda (FAMILY) - 19 interactions
      * Dad (FAMILY) - 5 interactions
      * Maya (FAMILY) - 4 interactions
      * Sarah (COLLEAGUE) - 3 interactions
      * Mom (FAMILY) - 3 interactions

    PLACES YOU FREQUENT:
      * Chicago
      * Japan
      * Dallas
      * India
      * Tokyo

    YOUR EMOTIONAL LANDSCAPE:
      * joy: 409 memories
      * neutral: 289 memories
      * annoyance: 82 memories
      * relief: 70 memories
      * sadness: 65 memories

    THINGS ON YOUR MIND:
       If home office had also caused issues during 'Social with Mom, Panda a...
       If Dallas's involvement during 'Routine at Home' had been different, t...
       If Tokyo had also caused issues during 'Routine with Panda at Flight',...

====================================================================================================
 HOW ST_OBSERVATIONS ENABLES A HOLISTIC VIEW
====================================================================================================

   ST_OBSERVATIONS acts as a universal context layer that:

   1. LINKS ALL MEMORY LAYERS
      +-------------+     +------------------+     +-------------+
      |  st_epi     |----| st_observations  |----|  st_social  |
      |  Episodes   |     |  Context Layer   |     | Relationships|
      +-------------+     +--------+---------+     +-------------+
                                   |
                    +--------------+--------------+
                    |              |              |
               +--------+   +--------+   +--------+
               | st_sem  |   |st_kg_dom|   |st_prosp |
               |Patterns |   |Entities |   |Reminders|
               +---------+   +---------+   +---------+

   2. CAPTURES HOLISTIC CONTEXT FOR EACH MEMORY:
      * TEMPORAL: When did this happen? (morning/evening, weekend/weekday)
      * SOCIAL: Who was involved? Solo or with others?
      * EMOTIONAL: How did you feel? What was the dominant emotion?
      * SALIENCE: How important was this moment?

   3. ENABLES POWERFUL RECALL QUERIES:
      * "How do I feel on weekends?" -> Filter by is_weekend
      * "Happiest memories with Emma" -> Join social + filter sentiment
      * "What happens in evenings?" -> Filter by circadian_slot
      * "Most important memories" -> Sort by salience_score

   +-------------------------------------------------------------------------+
   |  THE HOLISTIC VIEW FORMULA:                                             |
   |                                                                         |
   |  Memory Content + Temporal Context + Social Context + Emotional State   |
   |                                                                         |
   |  = A Complete Picture of How, When, Where, and Why Memories Form        |
   +-------------------------------------------------------------------------+

====================================================================================================
7. KNOWLEDGE GRAPH EDGES (st_kg_edges) - GAP-007 EDGE ENRICHMENT
   Purpose: Relationships between entities discovered by 6 AI algorithms
====================================================================================================

    Total KG Edges: 1613

    EDGES BY ENRICHMENT ALGORITHM:
   ------------------------------------------------------------------------------------------

   Unknown algorithm
      Algorithm: weight_normalization
      Edges: 1330 | Relations: 12
      Weight Range: 0.015 - 0.333 (avg: 0.051)

   Unknown algorithm
      Algorithm: intent_similarity
      Edges: 149 | Relations: 1
      Weight Range: 0.500 - 1.000 (avg: 0.931)

    Inferred relationships through intermediate entities
      Algorithm: transitive_closure
      Edges: 102 | Relations: 1
      Weight Range: 0.389 - 0.630 (avg: 0.547)

    Entities frequently mentioned together in the same events
      Algorithm: co_occurrence
      Edges: 17 | Relations: 3
      Weight Range: 0.000 - 2.481 (avg: 0.235)

    Entities with similar meaning/context (cosine similarity of embeddings)
      Algorithm: semantic_similarity
      Edges: 13 | Relations: 1
      Weight Range: 0.762 - 1.378 (avg: 0.921)

   Unknown algorithm
      Algorithm: emotion_similarity
      Edges: 1 | Relations: 1
      Weight Range: 0.696 - 0.696 (avg: 0.696)

    Entities that appear in similar contexts or share attributes
      Algorithm: contextual
      Edges: 1 | Relations: 1
      Weight Range: 0.697 - 0.697 (avg: 0.697)

   ----------------------------------------------------------------------------------------------
    7.1 SEMANTIC SIMILARITY - 'These concepts mean similar things'
   ----------------------------------------------------------------------------------------------

    How it works: Compares vector embeddings of entity descriptions
      using cosine similarity. High score = semantically related concepts.

   [WARN] QUALITY GATE: Only showing edges where entities share type OR have co-occurrence evidence.
      (Cross-type edges like 'Brooklyn <-> James Clear' are filtered out as noise)

   1. Uncle Raj (PERSON) <--> Vikram (PERSON)
      Similarity: 86.04% | Weight: 0.860

    Filtered as noise: 12 cross-type edges without co-occurrence evidence
      Examples of filtered noise:
         [X] Family (FAMILY_MEMBER) <-> new house (LOCATION)
         [X] Nisha (FAMILY_MEMBER) <-> Japan (LOCATION)

   ----------------------------------------------------------------------------------------------
    7.2 CONTEXTUAL RELATIONSHIPS - 'These appear in similar contexts'
   ----------------------------------------------------------------------------------------------

    How it works: Identifies entities that share contextual attributes,
      episode types, locations, or appear in similar emotional contexts.

    CONTEXTUALLY_RELATED:
      * Amy -> Rohan (weight: 0.70)

   ----------------------------------------------------------------------------------------------
    7.3 CO-OCCURRENCE - 'These are mentioned together frequently'
   ----------------------------------------------------------------------------------------------

    How it works: Counts how often two entities appear in the same
      events or episodes. More co-occurrences = stronger relationship.

   1. Aryan + Maya
      Co-occurrences: 6 | Weight: 2.48 | Type: FAMILY
   2. Kyoto + Tokyo
      Co-occurrences: 1 | Weight: 0.60 | Type: FOLLOWS
   3. India + Vikram
      Co-occurrences: 1 | Weight: 0.33 | Type: PRECEDES
   4. Aryan + Maya
      Co-occurrences: 1 | Weight: 0.29 | Type: PRECEDES
   5. Grandparents + Austin
      Co-occurrences: 1 | Weight: 0.17 | Type: PRECEDES

   ----------------------------------------------------------------------------------------------
    7.4 TEMPORAL PROXIMITY - 'These happen close together in time'
   ----------------------------------------------------------------------------------------------

   [WARN] No temporal proximity edges found

   ----------------------------------------------------------------------------------------------
    7.5 BAYESIAN CAUSAL - 'A likely causes or influences B'
   ----------------------------------------------------------------------------------------------

   [WARN] No bayesian causal edges found

    TEMPORAL ORDERING (PRECEDES/FOLLOWS):
      1. Alex ->-> Marcus (PRECEDES)
         Weight: 0.000 | Evidence: 1
      2. Amy ->-> Marcus (PRECEDES)
         Weight: 0.000 | Evidence: 1
      3. Aryan ->-> Maya (PRECEDES)
         Weight: 0.286 | Evidence: 1

   ----------------------------------------------------------------------------------------------
    7.6 TRANSITIVE CLOSURE - 'Inferred through intermediate entities'
   ----------------------------------------------------------------------------------------------

    How it works: If A->B and B->C, then infer A->C with reduced weight.
      Discovers implicit relationships through graph traversal.

   1. Plano ...-> Amy (INFERRED_RELATED)
      Weight: 0.630
   2. Kids ...-> Amy (INFERRED_RELATED)
      Weight: 0.630
   3. Mount Fuji ...-> Amy (INFERRED_RELATED)
      Weight: 0.629
   4. Kids ...-> Aryan (INFERRED_RELATED)
      Weight: 0.627
   5. Australia ...-> Aryan (INFERRED_RELATED)
      Weight: 0.627

   ----------------------------------------------------------------------------------------------
    7.7 RELATIONSHIP TYPE DISTRIBUTION
   ----------------------------------------------------------------------------------------------

Relation Type             | Algorithm           | Count | Avg Weight
   ---------------------------------------------------------------------------

   INFERRED_RELATED         | weight_normalizati |   717 | 0.05
   SIMILAR_TO               | weight_normalizati |   323 | 0.06
   INTENT_RELATED           | weight_normalizati |   171 | 0.05
   INTENT_RELATED           | intent_similarity  |   149 | 0.93
   INFERRED_RELATED         | transitive_closure |   102 | 0.55
   CONTEXTUALLY_RELATED     | weight_normalizati |    71 | 0.05
   EMOTIONALLY_RELATED      | weight_normalizati |    19 | 0.05
   PRECEDES                 | co_occurrence      |    15 | 0.06
   FAMILY                   | weight_normalizati |    14 | 0.06
   SIMILAR_TO               | semantic_similarit |    13 | 0.92
   PRECEDES                 | weight_normalizati |     8 | 0.04
   FRIEND                   | weight_normalizati |     3 | 0.07
   RELATED_TO               | weight_normalizati |     1 | 0.03
   TEMPORALLY_ASSOCIATED    | weight_normalizati |     1 | 0.02
   FAMILY                   | co_occurrence      |     1 | 2.48

   ----------------------------------------------------------------------------------------------
    7.8 GRAPH INSIGHTS - Hub Entities (Most Connected)
   ----------------------------------------------------------------------------------------------

    Hub entities are central to your life story - they connect many other entities.

   1. Maya (PERSON)
      Connections: 108
   2. Marcus (PERSON)
      Connections: 94
   3. Japan (LOCATION)
      Connections: 86
   4. Asus (ORGANIZATION)
      Connections: 83
   5. Chicago (LOCATION)
      Connections: 82
   6. Amy (PERSON)
      Connections: 80
   7. Nisha (PERSON)
      Connections: 79
   8. Vikram (PERSON)
      Connections: 79

====================================================================================================
8. RELATIONSHIP DEEP DIVE - Who Appears Together?
====================================================================================================

    CO-OCCURRENCE MATRIX (Who appears together in episodes?):
   ------------------------------------------------------------------------------------------

    Panda + Prince (8 memories together)
       "Dad proud of the FamilyOS work, gave good advice on pricing"
       "Panda Dallas plans."

    Maya + Panda (7 memories together)
       "Dad proud of the FamilyOS work, gave good advice on pricing"
       "Panda Dallas plans."

    Maya + Prince (7 memories together)
       "Dad proud of the FamilyOS work, gave good advice on pricing"
       "Panda Dallas plans."

    Dad + Panda (6 memories together)
       "Dad proud of the FamilyOS work, gave good advice on pricing"
       "Panda Dallas plans."

    Dad + Prince (6 memories together)
       "Dad proud of the FamilyOS work, gave good advice on pricing"
       "Panda Dallas plans."

    Mom + Panda (6 memories together)
       "Panda Dallas plans."
       "Parents are ecstatic. Another grandchild. Dad is already planning."


    EMOTIONAL TRAJECTORY BY PERSON:
   ------------------------------------------------------------------------------------------

    Panda (FAMILY)
      Interactions: 19 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Dad (FAMILY)
      Interactions: 5 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Maya (FAMILY)
      Interactions: 4 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Sarah (COLLEAGUE)
      Interactions: 3 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Mom (FAMILY)
      Interactions: 3 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Priya (COLLEAGUE)
      Interactions: 3 | Dominant Emotion: joy
      Sentiment Score: 0.00

====================================================================================================
9. EMOTIONAL JOURNEY - Your Emotional Arc
====================================================================================================

    EMOTIONAL DISTRIBUTION:

   Positive Emotions: 588 memories (49%)

   (joy, love, excitement, gratitude, pride, contentment)

   Neutral Emotions: 433 memories (36%)

   Negative Emotions: 167 memories (14%)

   (sadness, anxiety, frustration, nervousness)

    EMOTION TRIGGERS - What Causes Each Emotion?
   ------------------------------------------------------------------------------------------

    JOY:
      * "Christmas tree shopping. Found the perfect one."
      * "Made biryani from scratch for Diwali. Mom's recipe. Nailed it."

    LOVE:
      * "Parents met Maya. Grandparents now. Dad held her so gently."
      * "Dad says hes proud of the man Ive become. That means everything."

    NERVOUSNESS:
      * "Should we get a prenup? Its a difficult conversation."
      * "Should I hire a wedding planner? Panda thinks we can handle it."

    SADNESS:
      * "Panda and I both got COVID. Maya somehow didn't. Rough week."
      * "Priya is leaving for another company. Sad to see her go."

    PRIDE:
      * "First day back at work. Inbox had 500 emails. Marcus held down the fort."
      * "K0 memory tables growing healthy"

====================================================================================================
10. P01 RECALL QUERY EXAMPLES - Practical Use Cases
====================================================================================================

    QUERY: 'Tell me everything about Emma'
   ------------------------------------------------------------------------------------------

    EMMA (FRIEND)
      Total Interactions: 1
      Dominant Emotion: togetherness

       Episodes together (1 found):
         * Social with Dad, Emma, Jake at Home at Home


    QUERY: 'What happened at work?'
   ------------------------------------------------------------------------------------------

    WORK EPISODES (5 found):
      * "The flicker issue is a distant memory. After switching docks, the problem never ..."
      * "The ProArt fan is loud again. Dust buildup? Need to clean it."
      * "K0 logs show duplication. The cause was a bug in the session ID generation."
      * "K1 memory formation is efficient now. The pipeline is optimized."
      * "K0 pipeline had a glitch. Network timeout. Retried and it worked."


    QUERY: 'When was I happiest?'
   ------------------------------------------------------------------------------------------

    YOUR HAPPIEST MOMENTS:
      1. (Sentiment: 0.88, Emotion: love)
         "Started teaching Maya to read. Simple words first."
      2. (Sentiment: 0.87, Emotion: joy)
         "Pride milestones."
      3. (Sentiment: 0.87, Emotion: joy)
         "Panda is happy I helped with invites. Felt good to make her smile."
      4. (Sentiment: 0.87, Emotion: joy)
         "Marcus invited me to his birthday party next Saturday. Buying a gift."
      5. (Sentiment: 0.87, Emotion: joy)
         "Parents are ecstatic. Another grandchild. Dad is already planning."


    QUERY: 'What decisions do I need to make?'
   ------------------------------------------------------------------------------------------

    PENDING DECISIONS:
      * Should I invest in a standing desk? My back hurts.
      * Should I write a technical paper on the K0 architecture? Could be good for credibility.
      * Should I buy new monitor or fix current?
      * Should I write a post-mortem for the memory leak? Could be useful for learning.
      * Should I upgrade the Samsung 990 Pro? Or is it a cooling issue?


    QUERY: 'Who are my colleagues?'
   ------------------------------------------------------------------------------------------

    YOUR COLLEAGUES:
      * Priya (3 interactions)
      * Sarah (3 interactions)
      * Alex (2 interactions)
      * James (1 interactions)
      * Steve (1 interactions)

====================================================================================================
11. LIFE BALANCE ANALYSIS - Where Is Your Attention?
====================================================================================================

    LIFE AREA DISTRIBUTION:

   Total Episodes: 689 | Total Interactions: 76
    FAMILY:
      Episodes: 205 | Relationships: 16 | Interactions: 48

    OTHER:
      Episodes: 242 | Relationships: 0 | Interactions: 0

    LEARNING:
      Episodes: 122 | Relationships: 0 | Interactions: 0

    SOCIAL:
      Episodes: 52 | Relationships: 18 | Interactions: 18

    WORK:
      Episodes: 45 | Relationships: 5 | Interactions: 10

    HEALTH:
      Episodes: 23 | Relationships: 0 | Interactions: 0

====================================================================================================
12. DEEP PERSONALIZED INSIGHTS - What Your Memories Reveal
====================================================================================================

    HEALTH PATTERN ANALYSIS:
   ------------------------------------------------------------------------------------------

   GERD signal counts: 3 semantic patterns, 0 episodes

    GERD/Digestive Health: 8 mentions detected

    GERD Triggers Identified:
      [WARN] Coffee
      [WARN] Stress

   [OK] What's Working:
      *Avoiding triggers
      * Smaller meals

    SLEEP & ENERGY PATTERNS:
   ------------------------------------------------------------------------------------------

    Sleep Quality: 0 positive, 0 negative mentions


    PROJECT PROGRESS (FamilyOS/K0/K1):
   ------------------------------------------------------------------------------------------

    Project Mentions: 15

    RECENT WINS:
      [OK] K0 logs show some duplicate entries again. Thought we fixed this....
      [OK] Morning work, K1 smooth....
      [OK] K0 fixed dedup....

   [WARN] CURRENT BLOCKERS:
      * K0 memory pipeline is rock solid. No failures in 30 days....

    RELATIONSHIP QUALITY ANALYSIS:
   ------------------------------------------------------------------------------------------

    Panda (Partner): 10 mentions, 1 positive
    Recent moments together:
      * "Panda is worried about her job stability. I reassured her."
      * "Panda is asleep. Im thinking about our future family. Its a warm tho..."
      * "Date night with Panda. Escape room downtown. We escaped with 2 minutes..."

    Family: 10 mentions
    Family highlights:
      * "Maya asked where babies come from. Age-appropriate answer given."
      * "Maya's first loose tooth. She's wiggling it constantly."
      * "Mom arrives tomorrow. Need to clean the guest room."
      * "Started reading to Maya every night. She loves 'Goodnight Moon'."


    RECURRING THEMES (Items on Your Mind):
   ------------------------------------------------------------------------------------------

    CANONICAL ISSUES (from st_issues):
   ------------------------------------------------------------------------------------------
   [WARN] st_issues table not found - showing raw topic counts
      [RED] Monitor/Display issues: 92 mentions

    PRODUCTIVITY INSIGHTS:
   ------------------------------------------------------------------------------------------

====================================================================================================
 PERSONALIZED RECOMMENDATIONS (Based on Your Data)
====================================================================================================

   1. HEALTH
       Issue: GERD mentioned 8 times in 10 days
       Action: Track meals before gym sessions - heavy squats seem to trigger symptoms
       Evidence: Pattern: GERD flares after spicy food and heavy exercise

   ------------------------------------------------------------------------------------------
    10-DAY SUMMARY:
      * 1348 life events processed
      * 57 decisions pending
      * 130 reminders active
      * Top focus areas: FamilyOS, Wedding, Family, Health
   ------------------------------------------------------------------------------------------

====================================================================================================
13. CAUSAL INTELLIGENCE - What Causes What?
    FamilyOS Demo 5-8: Causal Understanding & Adaptive Suggestions
====================================================================================================

    DISCOVERED CAUSAL RELATIONSHIPS:
   ------------------------------------------------------------------------------------------
   No causal edges discovered yet. Need more events to detect patterns.

    EXPLICIT CAUSAL STATEMENTS FROM YOUR MEMORIES:
   ------------------------------------------------------------------------------------------

   1. "Woke up with a headache again, probably because of bad sleep last night, remind me to track my sleep..."
   2. "GERD is a non-issue now. Diet change caused the improvement."
   3. "The SSD performance is back to normal. The high temps caused the throttling."
   4. "When I slouch at the desk, my neck hurts. Which explains the stiffness yesterday."
   5. "Headache is back. Didnt drink enough water. Because of that, Im useless now."
   6. "Headache came back, I think this is why I skipped gym yesterday."
   7. "Morning. Coffee is making my GERD act up. I think the acidity caused the burning feeling."
   8. "K0 consolidation ran overnight, but dedup missed 12 entries, this led to duplicate entities"

    HEALTH CAUSAL CHAINS:
   ------------------------------------------------------------------------------------------

   Discovered Health Cause-Effect Relationships:
      Coffee --causes-- GERD flare
      Screen time --causes-- Headache
      Poor sleep --causes-- Headache

====================================================================================================
14. CROSS-LAYER INTELLIGENCE - Connecting the Dots
    FamilyOS Demo 2: Associative Context Recall
====================================================================================================

    DEMO: 'Tell me everything about display/monitor issues'
   ------------------------------------------------------------------------------------------

    EPISODIC MEMORY (What happened):
      (No display-related episodes consolidated yet)

    SEMANTIC MEMORY (What I learned):
      * After switching docks, display flicker stopped, hardware no longer enemy: No description...
      * After switching docks, display flicker stopped, but I keep checking every hour: No description...
      * The display flicker issue is gone after switching docks. It was definitely the dock.: No description...

    KNOWLEDGE GRAPH (Entities involved):
      (No display-related entities found)

    PROSPECTIVE MEMORY (Decisions pending):
      * [DECISION] Should I buy new monitor or fix current?
      * [DECISION] Should I buy a second monitor? The 34 OLED is great but I want more space.
      * [DECISION] Should fix monitor?

    RAW MEMORIES (Original events):
      * "When I reflect on this journey, I see growth. The flicker issue taught me patien..."
      * "After switching docks, display flicker stopped, but now USB ports feel slower..."
      * "After switching docks, display flicker stopped, but I still have trust issues..."
      * "The flickering stopped after switching docks. Weird. Need to buy a better dock...."

    RESOLUTION STORY:
      After investigating display flicker issues:
      [OK] "After switching docks, display flicker stopped, victory"
      -> The old USB-C dock was the culprit. Problem solved by switching docks.

====================================================================================================
15. DECISION SUPPORT - Informed Recommendations
    FamilyOS Demo 16: Decision Support & Context Weaving
====================================================================================================

    YOUR ACTIVE DECISIONS:
   ------------------------------------------------------------------------------------------

   1. Should I finally book the Chicago trip?
       Related context from your memories:
         * "P03 consolidation logic rewritten, this should fix the data loss issue..."
         * "Should I schedule DMV visit this weekend or next?..."

   2. Dad advice on work, he thinks architecture feels wrong.
       Related context from your memories:
         * "Started investing in index funds. Dad's advice finally sinking in...."
         * "Dad's advice: Take more photos. You'll want them later...."

   3. Should we get wedding insurance? Panda thinks its unnecessary.
       Related context from your memories:
         * "P03 consolidation logic rewritten, this should fix the data loss issue..."
         * "Should I schedule DMV visit this weekend or next?..."

   4. Should I implement a new compression algorithm for the envelopes? Might save space.
       Related context from your memories:
         * "P03 consolidation logic rewritten, this should fix the data loss issue..."
         * "Should I schedule DMV visit this weekend or next?..."

   5. Should I publish the K0 architecture on GitHub? Might attract contributors.
       Related context from your memories:
         * "P03 consolidation logic rewritten, this should fix the data loss issue..."
         * "Should I schedule DMV visit this weekend or next?..."

====================================================================================================
16. RELATIONSHIP INTELLIGENCE - Your Social Network
    FamilyOS Demo 13-15: Emotional & Conflict Mediation Support
====================================================================================================

    YOUR RELATIONSHIP MAP:
   ------------------------------------------------------------------------------------------

    FAMILY:
      [YELLOW] Panda: 19 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Dad: 5 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Maya: 4 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Mom: 3 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Karen: 3 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Marcus: 2 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Amy: 2 interactions
         Sentiment: 0.00 | Emotion: joy

    COLLEAGUE:
      [YELLOW] Priya: 3 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Sarah: 3 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Alex: 2 interactions
         Sentiment: 0.00 | Emotion: neutral


    WHO APPEARS TOGETHER?
   ------------------------------------------------------------------------------------------
      Panda + Prince: 8 times together
      Maya + Panda: 7 times together
      Maya + Prince: 7 times together
      Dad + Panda: 6 times together
      Dad + Prince: 6 times together

====================================================================================================
17. TEMPORAL PATTERNS - Your Daily Rhythm
    FamilyOS Demo 17: Preference Learning & Routine Detection
====================================================================================================

    YOUR DAILY RHYTHM:
   ------------------------------------------------------------------------------------------

    WEEKEND vs WEEKDAY:
   ------------------------------------------------------------------------------------------

   Weekday
      Events: 880 | Avg Sentiment: 0.66
      Common Emotions: admiration, amusement, annoyance, approval

   Weekend
      Events: 308 | Avg Sentiment: 0.61
      Common Emotions: annoyance, approval, caring, contentment

   Weekday
      Events: 9559 | Avg Sentiment: 0.00
      Common Emotions:

====================================================================================================
18. LOCATION INTELLIGENCE - Your Spatial Patterns
    FamilyOS Demo 9-12: Adaptive Home Intelligence
====================================================================================================

    YOUR LOCATIONS:
   ------------------------------------------------------------------------------------------

    Home
      Episodes: 232 | Sentiment: 0.56
      Activities: milestone, routine, social

    Office
      Episodes: 41 | Sentiment: 0.58
      Activities: milestone, routine, social

    New House
      Episodes: 31 | Sentiment: 0.66
      Activities: milestone, routine, social

    Gym
      Episodes: 13 | Sentiment: 0.64
      Activities: routine, unknown

    Doctor
      Episodes: 3 | Sentiment: 0.67
      Activities: milestone, routine, social

    Park
      Episodes: 2 | Sentiment: 0.81
      Activities: milestone, social

    Flight
      Episodes: 1 | Sentiment: 0.85
      Activities: routine

    Car Dealership
      Episodes: 1 | Sentiment: 0.78
      Activities: routine

====================================================================================================
19. REMINDER INTELLIGENCE - Your Mental Load
    FamilyOS Demo 19: Project Orchestration & Task Tracking
====================================================================================================

    YOUR MENTAL LOAD:
   ------------------------------------------------------------------------------------------

    REMINDER (ACTIVE) - 130 items
      [GREEN] backup wedding plans to the cloud...
      [GREEN] order a new office chair with lumbar support...
      [GREEN] celebrate the small wins. I forget to do that...

    DECISION (ACTIVE) - 57 items
      [GREEN] Should I invest in a standing desk? My back hurts....
      [GREEN] Should I write a technical paper on the K0 architecture? Could be good...
      [GREEN] Should I buy new monitor or fix current?...

    COUNTERFACTUAL (ACTIVE) - 70 items
      [GREEN] If home office had also caused issues during 'Social with Mom, Panda a...
      [GREEN] If Dallas's involvement during 'Routine at Home' had been different, t...
      [GREEN] If Tokyo had also caused issues during 'Routine with Panda at Flight',...

====================================================================================================
20. HOLISTIC LIFE VIEW - Everything Connected
    FamilyOS Vision: Context-Aware Family Intelligence
====================================================================================================

==============================================================================
                            YOUR LIFE IN NUMBERS
   ==============================================================================

      Raw Events Ingested:          1348
      Episodic Memories:             339  (What happened)
      Semantic Patterns:             545  (What you learned)
      Knowledge Entities:             74  (People, places, things)
     <->  Knowledge Edges:              1613  (How things connect)
      Social Relationships:           39  (Who matters)
      Prospective Intentions:        257  (What's on your mind)
       Contextual Observations:    10747  (Holistic context layer)
   ==============================================================================

    HOW LAYERS INTERCONNECT:
   ------------------------------------------------------------------------------------------

   EXAMPLE: A Single Memory's Multi-Layer Presence

    EPISODIC: "Milestone with Alex, Marcus, Panda at Restaurant"
      +-- Location: Restaurant
      +-- Participants: ['Alex', 'Marcus', 'Panda', "Panda's Dad", "Panda's Mom", 'Priya', 'Sarah']

    OBSERVATION:
      +-- Sentiment: 0.85
      +-- Emotion: joy
      +-- Time:

    SOCIAL: Alex
      +-- Type: COLLEAGUE
      +-- Total Interactions: 2

    KNOWLEDGE GRAPH: Alex
      +-- Type: PERSON
      +-- Observations: 5

====================================================================================================
 THIS IS THE FAMILYOS VISION
====================================================================================================

   Every life event creates ripples across ALL memory layers:

   Event: "Called Panda, promised to plan our trip to Chicago"
                    |
         +---------+-----------------------------------------+
         |                                                   |

   +--------------+                                   +--------------+
   |  EPISODIC    |                                   | PROSPECTIVE  |
   |  "Call with  |                                   | "Plan trip   |
   |   Panda"     |                                   |  to Chicago" |
   +------+-------+                                   +--------------+
          |
          ------------------+------------------+

   +--------------+   +--------------+   +--------------+
   |   SOCIAL     |   |  KNOWLEDGE   |   | OBSERVATION  |
   |   "Panda:    |   |  "Chicago:   |   | "Evening,    |
   |   Partner"   |   |   Location"  |   |  Positive"   |
   +--------------+   +--------------+   +--------------+

   This interconnected structure enables:
   [OK] "Who should I call about the Chicago trip?" -> SOCIAL layer
   [OK] "What did we discuss about Chicago?" -> EPISODIC layer
   [OK] "When was I happiest planning trips?" -> OBSERVATION layer
   [OK] "What cities have we discussed visiting?" -> KNOWLEDGE layer
   [OK] "What travel plans are pending?" -> PROSPECTIVE layer

   THIS IS THE HOLISTIC VIEW THAT ONLY FAMILYOS CAN PROVIDE.

====================================================================================================
[OK] MEMORY LAYER EXPLORATION COMPLETE
====================================================================================================

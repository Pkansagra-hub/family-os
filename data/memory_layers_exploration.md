====================================================================================================
 MEMORY LAYERS DEEP DIVE - REAL EXAMPLES FROM YOUR LIFE
====================================================================================================

====================================================================================================
1. EPISODIC MEMORIES (st_epi)
   Purpose: Stores autobiographical events - 'What happened, when, where, with whom'
====================================================================================================

    Total Episodes: 639

    REAL EXAMPLES FROM YOUR LIFE:
   ------------------------------------------------------------------------------------------

    Episode 1: Milestone with Maya, Panda at New House
      Type: milestone | Location: New House
      Participants: ["Panda"]
       Original Memory:
         "Told Panda about promotion. She's proud. We're a team."
         "Deep conversation with Panda about life goals. We're aligned."

    Episode 2: Routine with Earlier, Prince at Home
      Type: routine | Location: Home
      Participants: ["Prince"]
       Original Memory:
         "Coding late poor sleep."
         "Need to start the dedup pipeline for K0 logs. It failed last night."

    Episode 3: Social with Alex, Marcus, Maya at Office
      Type: social | Location: Office
      Participants: ["Alex", "Marcus", "Maya", "Mom", "Panda", "Panda's Mom", "Priya"]
       Original Memory:
         "Mom gave us baby stuff she saved. Some from when I was born."
         "Sprint retro with Marcus and the team. Good discussion on blockers."

    Episode 4: Routine with Panda, Prince, Sarah at Home
      Type: routine | Location: Home
      Participants: ["Panda", "Prince", "Sarah", "Steve"]
       Original Memory:
         "Conflict with coworker Steve about code ownership. HR involved."
         "Car shopping. Need something bigger for the car seat."

    Episode 5: Routine with Panda at New House
      Type: routine | Location: New House
      Participants: ["Panda"]
       Original Memory:
         "Just now, unpacking boxes. Found our wedding photos. Already nostalgic."
         "Diwali cleanup. Worth the mess. Best celebration yet."


====================================================================================================
2. SEMANTIC MEMORY (st_sem)
   Purpose: Stores facts, patterns, and generalizations extracted from experiences
====================================================================================================

    Total Patterns: 749

    REAL PATTERNS FROM YOUR EXPERIENCES:
   ------------------------------------------------------------------------------------------

    Pattern 1: relief emotional pattern
      Type: EMOTIONAL_TREND/None
      Confidence: 0.80
       Learned from:
         "After switching docks, display flicker stopped, such a relief."

    Pattern 2: Thinking about the future. Want to give Maya the best life possible.
      Type: LESSON/None
      Confidence: 0.80
       Learned from:
         "Thinking about the future. Want to give Maya the best life possible."

    Pattern 3: annoyance emotional pattern
      Type: EMOTIONAL_TREND/None
      Confidence: 0.80
       Learned from:
         "Coding late poor sleep."

    Pattern 4: annoyance emotional pattern
      Type: EMOTIONAL_TREND/None
      Confidence: 0.80
       Learned from:
         "the ProArt fan is loud under load. Maybe its normal."

    Pattern 5: Earlier today, k1 memory indexing is fast. The cache size was the bottleneck.
      Type: LESSON/None
      Confidence: 0.80
       Learned from:
         "Earlier today, k1 memory indexing is fast. The cache size was the bottleneck."


====================================================================================================
3. KNOWLEDGE GRAPH ENTITIES (st_kg_dom)
   Purpose: Stores entities (people, places, things) and their attributes
====================================================================================================

    Total Entities: 103

    ENTITIES BY TYPE:
      PERSON: 41 entities
         Examples: Maya, Emma, Marcus, Priya, Vikram
      LOCATION: 40 entities
         Examples: Chicago, Dallas, Japan, India, Tokyo
      ORGANIZATION: 14 entities
         Examples: Asus, Amazon, Google, DFW, Starbucks
      FAMILY_MEMBER: 8 entities
         Examples: Family, Grandparents, Kids, Nisha, Uncle Marcus

    REAL ENTITIES FROM YOUR LIFE:
   ------------------------------------------------------------------------------------------

    Person 1: Maya
       Mentioned in:
         "Picked up Emma late from after-school. She was upset because her friend Maya didn't play with her to..."
         "Emma told me she made up with Maya yesterday afternoon. They're best friends again. Kids are resilie..."

    Person 2: Emma
       Mentioned in:
         "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals today!"
         "Emma's piano recital at Lincoln School. She played Fur Elise beautifully."

    Person 3: Marcus
       Mentioned in:
         "Started a book club with Marcus and Alex. First book: Atomic Habits."

    Person 4: Priya
       Mentioned in:
         "Farewell lunch for Priya. 3 years of great work together."
         "Just now, code review session with Priya. Her refactoring is clean."

    Person 5: Vikram
       Mentioned in:
         "A moment ago, cousin Vikram left for India. We'll miss him. Wedding was better with him."


====================================================================================================
4. SOCIAL RELATIONSHIPS (st_social)
   Purpose: Stores relationships between the person and others
====================================================================================================

    Total Relationships: 54

    YOUR KEY RELATIONSHIPS (with computed sentiment from observations):
   ------------------------------------------------------------------------------------------

    Emma (FAMILY)
      Interactions: 28 | Sentiment: 0.73 | Emotion: joy

    Panda (FAMILY)
      Interactions: 13 | Sentiment: 0.65 | Emotion: joy

    Rachel (FAMILY)
      Interactions: 9 | Sentiment: 0.79 | Emotion: joy

    John (COLLEAGUE)
      Interactions: 8 | Sentiment: 0.60 | Emotion: neutral

    Mike (COLLEAGUE)
      Interactions: 6 | Sentiment: 0.68 | Emotion: joy

    Lisa (COLLEAGUE)
      Interactions: 6 | Sentiment: 0.79 | Emotion: joy


====================================================================================================
5. PROSPECTIVE MEMORY (st_prospective)
   Purpose: Stores future intentions, reminders, and planned actions
====================================================================================================

    Total Intentions/Reminders: 300

    YOUR REMINDERS & DECISIONS:
   ------------------------------------------------------------------------------------------

    REMINDER: check Samsung 990 Pro warranty
      Status: ACTIVE | Confidence: 0.80
       From:
         "check Samsung 990 Pro warranty"

    DECISION: should I write a technical paper on the K0 architecture? Could be good for credibility.
      Status: ACTIVE | Confidence: 0.80
       From:
         "should I write a technical paper on the K0 architecture? Could be good for credibility."

    DECISION: Should I travel to UTD for meeting or virtual?
      Status: ACTIVE | Confidence: 0.80
       From:
         "Should I travel to UTD for meeting or virtual?"

    DECISION: should we get a prenup? Its a difficult conversation.
      Status: ACTIVE | Confidence: 0.80
       From:
         "should we get a prenup? Its a difficult conversation."

    REMINDER: check Samsung 990 Pro warranty
      Status: ACTIVE | Confidence: 0.80
       From:
         "check Samsung 990 Pro warranty"

    REMINDER: call Medical Center about persistent GERD
      Status: ACTIVE | Confidence: 0.80
       From:
         "call Medical Center about persistent GERD"


====================================================================================================
6. ST_OBSERVATIONS - THE HOLISTIC CONTEXT LAYER
   Purpose: Links every memory write to its full contextual situation
====================================================================================================

    Total Observations: 48070

    OBSERVATIONS BY MEMORY LAYER:
      st_kg_edges: 45295 observations (avg sentiment: 0.68)
      st_sem: 953 observations (avg sentiment: 0.67)
      st_epi: 639 observations (avg sentiment: 0.60)
      st_social: 428 observations (avg sentiment: 0.00)
      st_prospective: 397 observations (avg sentiment: 0.00)
      st_kg_dom: 358 observations (avg sentiment: 0.00)


====================================================================================================
 HOLISTIC QUERIES - MEMORIES WITH FULL CONTEXT
====================================================================================================

    QUERY 1: Most Joyful Episodes (emotion = joy/love/gratitude)
   ------------------------------------------------------------------------------------------

    #1 Social with Dad, Maya, Panda at New House
       Location: New House |  With: ["Dad", "Maya", "Panda"]
       Time: afternoon/ | Weekend: False
       Sentiment: 0.90 | Emotion: caring
       "Dad's advice: Take more photos. You'll want them later."

    #2 Social with Dad, Maya, Panda at New House
       Location: New House |  With: ["Dad", "Maya", "Panda"]
       Time: afternoon/ | Weekend: False
       Sentiment: 0.90 | Emotion: caring
       "Dad's advice: Take more photos. You'll want them later."

    #3 Social with Dad, Mom, Panda at Home
       Location: Home |  With: ["Dad", "Mom", "Panda", "Prince"]
       Time: afternoon/ | Weekend: True
       Sentiment: 0.90 | Emotion: gratitude
       "Remind me to thank Panda for her support"


    QUERY 2: Relationships - Who Brings Joy?
   ------------------------------------------------------------------------------------------

    Emma (FAMILY)
      Interactions: 28 | Avg Sentiment: 0.00
      Emotions: ['neutral']

    Panda (FAMILY)
      Interactions: 13 | Avg Sentiment: 0.00
      Emotions: ['neutral']

    Rachel (FAMILY)
      Interactions: 9 | Avg Sentiment: 0.00
      Emotions: ['neutral']

    John (COLLEAGUE)
      Interactions: 8 | Avg Sentiment: 0.00
      Emotions: ['neutral']


    QUERY 3: When Are You Happiest? (Time-of-Day Analysis)
   ------------------------------------------------------------------------------------------


====================================================================================================
 YOUR LIFE STORY - A HOLISTIC VIEW
====================================================================================================

   Based on your memories, here's what the system knows about your life:
    
    KEY PEOPLE IN YOUR LIFE:
      * Emma (FAMILY) - 28 interactions
      * Panda (FAMILY) - 13 interactions
      * Rachel (FAMILY) - 9 interactions
      * John (COLLEAGUE) - 8 interactions
      * Mike (COLLEAGUE) - 6 interactions

    PLACES YOU FREQUENT:
      * Chicago
      * Dallas
      * Japan
      * India
      * Tokyo

    YOUR EMOTIONAL LANDSCAPE:
      * joy: 601 memories
      * neutral: 444 memories
      * annoyance: 107 memories
      * relief: 98 memories
      * sadness: 72 memories

    THINGS ON YOUR MIND:
       call Mom...
       remember to submit the quarterly report by Friday at 5pm...
       to pick up Emma from soccer practice...


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

    Total KG Edges: 2782

    EDGES BY ENRICHMENT ALGORITHM:
   ------------------------------------------------------------------------------------------

   Unknown algorithm
      Algorithm: weight_normalization
      Edges: 2691 | Relations: 11
      Weight Range: 0.011 - 0.500 (avg: 0.036)

    Inferred relationships through intermediate entities
      Algorithm: transitive_closure
      Edges: 79 | Relations: 1
      Weight Range: 0.306 - 0.741 (avg: 0.532)

    Entities frequently mentioned together in the same events
      Algorithm: co_occurrence
      Edges: 9 | Relations: 2
      Weight Range: 0.158 - 0.750 (avg: 0.323)

    Entities where one likely causes/influences another
      Algorithm: bayesian_causal
      Edges: 2 | Relations: 1
      Weight Range: 0.667 - 0.667 (avg: 0.667)

    Entities with similar meaning/context (cosine similarity of embeddings)
      Algorithm: semantic_similarity
      Edges: 1 | Relations: 1
      Weight Range: 0.778 - 0.778 (avg: 0.778)


   ----------------------------------------------------------------------------------------------
    7.1 SEMANTIC SIMILARITY - 'These concepts mean similar things'
   ----------------------------------------------------------------------------------------------

    How it works: Compares vector embeddings of entity descriptions
      using cosine similarity. High score = semantically related concepts.

   [WARN] QUALITY GATE: Only showing edges where entities share type OR have co-occurrence evidence.
      (Cross-type edges like 'Brooklyn <-> James Clear' are filtered out as noise)

   1. Steve (PERSON) <--> Vikram (PERSON)
      Similarity: 77.78% | Weight: 0.778


   ----------------------------------------------------------------------------------------------
    7.2 CONTEXTUAL RELATIONSHIPS - 'These appear in similar contexts'
   ----------------------------------------------------------------------------------------------

   [WARN] No contextual edges found


   ----------------------------------------------------------------------------------------------
    7.3 CO-OCCURRENCE - 'These are mentioned together frequently'
   ----------------------------------------------------------------------------------------------

    How it works: Counts how often two entities appear in the same
      events or episodes. More co-occurrences = stronger relationship.

   1. Cousin + Maya
      Co-occurrences: 1 | Weight: 0.75 | Type: CAUSES
   2. Kyoto + Tokyo
      Co-occurrences: 1 | Weight: 0.40 | Type: PRECEDES
   3. Lincoln School + Emma
      Co-occurrences: 1 | Weight: 0.37 | Type: PRECEDES
   4. Emma + Jake
      Co-occurrences: 1 | Weight: 0.32 | Type: PRECEDES
   5. Rachel + Tom
      Co-occurrences: 1 | Weight: 0.29 | Type: PRECEDES


   ----------------------------------------------------------------------------------------------
    7.4 TEMPORAL PROXIMITY - 'These happen close together in time'
   ----------------------------------------------------------------------------------------------

   [WARN] No temporal proximity edges found


   ----------------------------------------------------------------------------------------------
    7.5 BAYESIAN CAUSAL - 'A likely causes or influences B'
   ----------------------------------------------------------------------------------------------

    How it works: Uses Granger causality and Bayesian inference to
      determine if one entity's occurrence predicts another's.

    CAUSAL RELATIONSHIPS (deduplicated):

    CAUSES/INFLUENCES (2 edges):
      1. Maya -> John
         Confidence: 0.67 | Evidence: 6 | Weight: 0.667
      2. Maya -> Sarah
         Confidence: 0.67 | Evidence: 6 | Weight: 0.667

    TEMPORAL ORDERING (PRECEDES/FOLLOWS):
      1. Aryan ->-> Maya (PRECEDES)
         Weight: 0.033 | Evidence: 1
      2. City Sports Complex ->-> Emma (PRECEDES)
         Weight: 0.158 | Evidence: 1
      3. Emma ->-> Jake (PRECEDES)
         Weight: 0.324 | Evidence: 1


   ----------------------------------------------------------------------------------------------
    7.6 TRANSITIVE CLOSURE - 'Inferred through intermediate entities'
   ----------------------------------------------------------------------------------------------

    How it works: If A->B and B->C, then infer A->C with reduced weight.
      Discovers implicit relationships through graph traversal.

   1. Cousin ...-> Earlier (INFERRED_RELATED)
      Weight: 0.741
   2. Parents ...-> Earlier (INFERRED_RELATED)
      Weight: 0.741
   3. Austin ...-> Earlier (INFERRED_RELATED)
      Weight: 0.675
   4. Uncle Raj ...-> Vikram (INFERRED_RELATED)
      Weight: 0.637
   5. Vegas ...-> Earlier (INFERRED_RELATED)
      Weight: 0.576


   ----------------------------------------------------------------------------------------------
    7.7 RELATIONSHIP TYPE DISTRIBUTION
   ----------------------------------------------------------------------------------------------

   Relation Type             | Algorithm           | Count | Avg Weight
   ---------------------------------------------------------------------------
   INFERRED_RELATED         | weight_normalizati |  1843 | 0.03
   SIMILAR_TO               | weight_normalizati |   482 | 0.04
   CONTEXTUALLY_RELATED     | weight_normalizati |   293 | 0.05
   INFERRED_RELATED         | transitive_closure |    79 | 0.53
   TEMPORALLY_ASSOCIATED    | weight_normalizati |    30 | 0.04
   FAMILY                   | weight_normalizati |    20 | 0.04
   PRECEDES                 | co_occurrence      |     8 | 0.27
   FRIEND                   | weight_normalizati |     6 | 0.05
   PRECEDES                 | weight_normalizati |     5 | 0.04
   COLLEAGUE                | weight_normalizati |     4 | 0.08
   RELATED_TO               | weight_normalizati |     4 | 0.04
   ACQUAINTANCE             | weight_normalizati |     3 | 0.03
   CAUSES                   | bayesian_causal    |     2 | 0.67
   CAUSES                   | weight_normalizati |     1 | 0.06
   CAUSES                   | co_occurrence      |     1 | 0.75


   ----------------------------------------------------------------------------------------------
    7.8 GRAPH INSIGHTS - Hub Entities (Most Connected)
   ----------------------------------------------------------------------------------------------

    Hub entities are central to your life story - they connect many other entities.

   1.  Maya (PERSON)
      Connections: 106 
   2.  Marcus (PERSON)
      Connections: 100 
   3.  India (LOCATION)
      Connections: 100 
   4.  Alex (PERSON)
      Connections: 99 
   5.  Dallas (LOCATION)
      Connections: 99 
   6.  Vikram (PERSON)
      Connections: 99 
   7.  Lisa (PERSON)
      Connections: 97 
   8.  Chicago (LOCATION)
      Connections: 96 


====================================================================================================
8. RELATIONSHIP DEEP DIVE - Who Appears Together?
====================================================================================================

    CO-OCCURRENCE MATRIX (Who appears together in episodes?):
   ------------------------------------------------------------------------------------------

    Dad + Maya (8 memories together)
       "Health improves gym."
       "running club half marathon. Finished in 2:05. Personal best."

    Dad + Mom (8 memories together)
       "Health improves gym."
       "running club half marathon. Finished in 2:05. Personal best."

    Dad + Panda (8 memories together)
       "Health improves gym."
       "running club half marathon. Finished in 2:05. Personal best."

    Dad + Prince (8 memories together)
       "Health improves gym."
       "running club half marathon. Finished in 2:05. Personal best."

    Maya + Mom (8 memories together)
       "Health improves gym."
       "running club half marathon. Finished in 2:05. Personal best."

    Maya + Panda (8 memories together)
       "Health improves gym."
       "running club half marathon. Finished in 2:05. Personal best."


    EMOTIONAL TRAJECTORY BY PERSON:
   ------------------------------------------------------------------------------------------

    Emma (FAMILY)
      Interactions: 28 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Panda (FAMILY)
      Interactions: 13 | Dominant Emotion: joy
      Sentiment Score: 0.00

    Rachel (FAMILY)
      Interactions: 9 | Dominant Emotion: joy
      Sentiment Score: 0.00

    John (COLLEAGUE)
      Interactions: 8 | Dominant Emotion: annoyance
      Sentiment Score: 0.00

    Mike (COLLEAGUE)
      Interactions: 6 | Dominant Emotion: annoyance
      Sentiment Score: 0.00

    Lisa (COLLEAGUE)
      Interactions: 6 | Dominant Emotion: neutral
      Sentiment Score: 0.00


====================================================================================================
9. EMOTIONAL JOURNEY - Your Emotional Arc
====================================================================================================

    EMOTIONAL DISTRIBUTION:

   Positive Emotions: 820 memories (50%)
   
   (joy, love, excitement, gratitude, pride, contentment)

   Neutral Emotions: 588 memories (36%)
   

   Negative Emotions: 213 memories (13%)
   
   (sadness, anxiety, frustration, nervousness)
    

    EMOTION TRIGGERS - What Causes Each Emotion?
   ------------------------------------------------------------------------------------------

    JOY:
      * "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals t..."
      * "Family dinner with Emma and Jake at home. Made lasagna together."

    LOVE:
      * "Remind me to call Mom tomorrow at 3pm for her birthday."
      * "This morning, unpacking boxes. Found our wedding photos. Already nostalgic."

    NERVOUSNESS:
      * "Arrived at office early at 8am. Reviewed presentation slides one more time. Hear..."
      * "Should I loosen the schema validation? Might cause data quality issues."

    SADNESS:
      * "Mom worried about my sleep, told her about GERD"
      * "Back from Austin. Maya barely noticed we were gone. Grandparents spoiled her."

    PRIDE:
      * "Just now, dentist appointment. No cavities. Flossing is paying off."
      * "Just now, dentist appointment. No cavities. Flossing is paying off."


====================================================================================================
10. P01 RECALL QUERY EXAMPLES - Practical Use Cases
====================================================================================================

    QUERY: 'Tell me everything about Emma'
   ------------------------------------------------------------------------------------------

    EMMA (FAMILY)
      Total Interactions: 28
      Dominant Emotion: joy

       Episodes together (5 found):
         * Social with Emma at City Sports Complex at City Sports Complex
         * Social with Emma, Jake, Sofia at Home at Home
         * Milestone with Emma, Team at Office at Office
         * Routine with Emma, Jake at San Francisco at San Francisco
         * Routine with Emma, Mom at Home at Home


    QUERY: 'What happened at work?'
   ------------------------------------------------------------------------------------------

    WORK EPISODES (5 found):
      * "Presented quarterly results to the executive team. CEO David was impressed."
      * "Finished reading 'Atomic Habits' by James Clear. Key insight: systems over goals..."
      * "Looking back, I realize that setting clear boundaries at work has made me much h..."
      * "Arrived at office early at 8am. Reviewed presentation slides one more time. Hear..."
      * "This morning, because of the new schema, P02 runs faster now."


    QUERY: 'When was I happiest?'
   ------------------------------------------------------------------------------------------

    YOUR HAPPIEST MOMENTS:
      1. (Sentiment: 0.90, Emotion: joy)
         "Coffee with best friend Rachel at Starbucks. She's excited about her new job at ..."
      2. (Sentiment: 0.90, Emotion: joy)
         "Family dinner with Emma and Jake at home. Made lasagna together."
      3. (Sentiment: 0.90, Emotion: joy)
         "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals t..."
      4. (Sentiment: 0.90, Emotion: joy)
         "Yoga class with instructor Maria. Worked on flexibility and breathing."
      5. (Sentiment: 0.90, Emotion: joy)
         "Birthday party for Tom at his apartment. About 20 people showed up."


    QUERY: 'What decisions do I need to make?'
   ------------------------------------------------------------------------------------------

    PENDING DECISIONS:
      * Should I take the new job offer from Google or stay at my current company?
      * I'm trying to decide between buying a house in Brooklyn or renting in Manhattan.
      * What do you think - should Emma switch from soccer to basketball?
      * I need advice on whether to invest in stocks or bonds right now.
      * This morning, should I add automated failover for the pipeline? Might be over-engineering.


    QUERY: 'Who are my colleagues?'
   ------------------------------------------------------------------------------------------

    YOUR COLLEAGUES:
      * John (8 interactions)
      * Mike (6 interactions)
      * Lisa (6 interactions)
      * Sarah (5 interactions)
      * Priya (5 interactions)


====================================================================================================
11. LIFE BALANCE ANALYSIS - Where Is Your Attention?
====================================================================================================

    LIFE AREA DISTRIBUTION:
   
   Total Episodes: 1270 | Total Interactions: 154
    FAMILY:
      Episodes: 396 | Relationships: 23 | Interactions: 89
      
    OTHER:
      Episodes: 441 | Relationships: 0 | Interactions: 0
      
    LEARNING:
      Episodes: 219 | Relationships: 0 | Interactions: 0
      
    SOCIAL:
      Episodes: 120 | Relationships: 19 | Interactions: 23
      
    WORK:
      Episodes: 78 | Relationships: 12 | Interactions: 42
      
    HEALTH:
      Episodes: 16 | Relationships: 0 | Interactions: 0
      


====================================================================================================
12. DEEP PERSONALIZED INSIGHTS - What Your Memories Reveal
====================================================================================================

    HEALTH PATTERN ANALYSIS:
   ------------------------------------------------------------------------------------------

   GERD signal counts: 4 semantic patterns, 0 episodes

    GERD/Digestive Health: 8 mentions detected

    GERD Triggers Identified:
      [WARN] Heavy exercise (squats)
      [WARN] Stress

   [OK] What's Working:
      * Avoiding triggers


    SLEEP & ENERGY PATTERNS:
   ------------------------------------------------------------------------------------------

    Sleep Quality: 1 positive, 2 negative mentions


    PROJECT PROGRESS (FamilyOS/K0/K1):
   ------------------------------------------------------------------------------------------

    Project Mentions: 15

    RECENT WINS:
      [OK] Just now, working on FamilyOS pricing model, should we do $9.99/mo or $99/year?...
      [OK] k0 dedup fixed....
      [OK] Working on FamilyOS pricing model, should we do $9.99/mo or $99/year?...

   [WARN] CURRENT BLOCKERS:
      * K1 pipeline running slow, this led to delayed tests....
      * Need to start the dedup pipeline for K0 logs. It failed last night....
      * Woke up late, headache because of staying up debugging K0 last night...


    RELATIONSHIP QUALITY ANALYSIS:
   ------------------------------------------------------------------------------------------

    Panda (Partner): 10 mentions, 0 positive
    Recent moments together:
      * "Told Panda about promotion. She's proud. We're a team."
      * "Deep conversation with Panda about life goals. We're aligned."
      * "Panda's coworker drama. Lisa and her boss had a fight. Panda is stress..."

    Family: 10 mentions
    Family highlights:
      * "Thinking about the future. Want to give Maya the best life possible."
      * "Mom texted. She wants pictures from the venue. Ill ask Panda."
      * "Maya refused to eat vegetables. Negotiated for 3 bites."
      * "This afternoon, dad is happy with the beta plan. Hes spreading the wo..."


    RECURRING THEMES (Items on Your Mind):
   ------------------------------------------------------------------------------------------

    Decisions that keep coming up:
      * This afternoon, the color shift is still there. Might be a d... (mentioned 2x)
      * should we get a prenup? Its a difficult conversation.... (mentioned 2x)
      * Earlier today, should I increase the cache size? Might affec... (mentioned 2x)


    CANONICAL ISSUES (from st_issues):
   ------------------------------------------------------------------------------------------
   [WARN] st_issues table not found - showing raw topic counts
      [RED] Monitor/Display issues: 138 mentions


    PRODUCTIVITY INSIGHTS:
   ------------------------------------------------------------------------------------------


====================================================================================================
 PERSONALIZED RECOMMENDATIONS (Based on Your Data)
====================================================================================================

   1.  HEALTH
       Issue: GERD mentioned 8 times in 10 days
       Action: Track meals before gym sessions - heavy squats seem to trigger symptoms
       Evidence: Pattern: GERD flares after spicy food and heavy exercise


   ------------------------------------------------------------------------------------------
    10-DAY SUMMARY:
      * 2112 life events processed
      * 84 decisions pending
      * 216 reminders active
      * Top focus areas: FamilyOS, Wedding, Family, Health
   ------------------------------------------------------------------------------------------


====================================================================================================
13. CAUSAL INTELLIGENCE - What Causes What?
    FamilyOS Demo 5-8: Causal Understanding & Adaptive Suggestions
====================================================================================================

    DISCOVERED CAUSAL RELATIONSHIPS:
   ------------------------------------------------------------------------------------------

   1. Maya -> Emma
      Cause Type: PERSON | Effect Type: PERSON
      Confidence: 0.77 | Observations: 6

   2. Cousin -> Maya
      Cause Type: FAMILY_MEMBER | Effect Type: PERSON
      Confidence: 0.75 | Observations: 1

   3. Maya -> Sarah
      Cause Type: PERSON | Effect Type: PERSON
      Confidence: 0.67 | Observations: 6

   4. Maya -> John
      Cause Type: PERSON | Effect Type: PERSON
      Confidence: 0.67 | Observations: 6


    EXPLICIT CAUSAL STATEMENTS FROM YOUR MEMORIES:
   ------------------------------------------------------------------------------------------
   1. "Because of consistent gym, headaches reduced to once a week"
   2. "Late coding caused poor sleep."
   3. "Woke up late, headache because of staying up debugging K0 last night"
   4. "Just now, when I prioritize sleep, everything else falls into place. This led to a better month."
   5. "When I sleep 7 hours, my productivity soars. This led to a great week."
   6. "When I do heavy squats, my GERD flares up. Which explains why I felt sick yesterday."
   7. "A moment ago, the SSD performance is back to normal. The high temps caused the throttling."
   8. "The SSD performance is back to normal. The high temps caused the throttling."


    HEALTH CAUSAL CHAINS:
   ------------------------------------------------------------------------------------------
   Analyzing raw mentions...
      * "Woke up late, headache because of staying up debugging K0 last night..."
      * "Because of consistent gym, headaches reduced to once a week..."
      * "When I sleep 7 hours, my productivity soars. This led to a great week...."
      * "Just now, when I prioritize sleep, everything else falls into place. This led to a better ..."
      * "When I do heavy squats, my GERD flares up. Which explains why I felt sick yesterday...."


====================================================================================================
14. CROSS-LAYER INTELLIGENCE - Connecting the Dots
    FamilyOS Demo 2: Associative Context Recall
====================================================================================================

    DEMO: 'Tell me everything about display/monitor issues'
   ------------------------------------------------------------------------------------------

    EPISODIC MEMORY (What happened):
      (No display-related episodes consolidated yet)

    SEMANTIC MEMORY (What I learned):
      * The monitor tint is barely noticeable now. Maybe the panel settled.: No description...
      * Just now, when I reflect on this journey, I see growth. The flicker issue taught me patience and problem-solving skills after switching docks and cables to fix it.: No description...
      * After switching docks, display flicker stopped, old reminder.: No description...

    KNOWLEDGE GRAPH (Entities involved):
      (No display-related entities found)

    PROSPECTIVE MEMORY (Decisions pending):
      * [DECISION] Should I fix monitor?
      * [DECISION] Should fix monitor?
      * [DECISION] This afternoon, the color shift is still there. Might be a defect. Should I RMA the monitor?

    RAW MEMORIES (Original events):
      * "After switching docks, display flicker stopped, such a relief...."
      * "After switching docks, display flicker stopped, but now 32" monitor looks dim..."
      * "After switching docks, display flicker stopped, late reminder...."
      * "Just now, the display flicker issue is gone after switching docks. It was defini..."

    RESOLUTION STORY:
      After investigating display flicker issues:
      [OK] "This afternoon, after switching docks, display flicker stopped, finally no paranoia"
      -> The old USB-C dock was the culprit. Problem solved by switching docks.


====================================================================================================
15. DECISION SUPPORT - Informed Recommendations
    FamilyOS Demo 16: Decision Support & Context Weaving
====================================================================================================

    YOUR ACTIVE DECISIONS:
   ------------------------------------------------------------------------------------------

   1. should I write a technical paper on the K0 architecture? Could be good for credibility.
       Related context from your memories:
         * "called my college friend Rohan after months. He's getting married too...."
         * "This afternoon, k1 consolidation is still slow. The cooling pad should..."

   2. Should I travel to UTD for meeting or virtual?
       Related context from your memories:
         * "called my college friend Rohan after months. He's getting married too...."
         * "This afternoon, k1 consolidation is still slow. The cooling pad should..."

   3. should we get a prenup? Its a difficult conversation.
       Related context from your memories:
         * "called my college friend Rohan after months. He's getting married too...."
         * "This afternoon, k1 consolidation is still slow. The cooling pad should..."

   4. Should I buy a cooling pad for the laptop to reduce thermals?
       Related context from your memories:
         * "called my college friend Rohan after months. He's getting married too...."
         * "This afternoon, k1 consolidation is still slow. The cooling pad should..."

   5. Should I start a YouTube channel for FamilyOS?
       Related context from your memories:
         * "called my college friend Rohan after months. He's getting married too...."
         * "This afternoon, k1 consolidation is still slow. The cooling pad should..."


====================================================================================================
16. RELATIONSHIP INTELLIGENCE - Your Social Network
    FamilyOS Demo 13-15: Emotional & Conflict Mediation Support
====================================================================================================

    YOUR RELATIONSHIP MAP:
   ------------------------------------------------------------------------------------------

    FAMILY:
      [YELLOW] Emma: 28 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Panda: 13 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Rachel: 9 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Marcus: 6 interactions
         Sentiment: 0.00 | Emotion: excitement
      [YELLOW] Jake: 5 interactions
         Sentiment: 0.00 | Emotion: joy
      [YELLOW] Dr. Smith: 5 interactions
         Sentiment: 0.00 | Emotion: worry

    COLLEAGUE:
      [YELLOW] John: 8 interactions
         Sentiment: 0.00 | Emotion: annoyance
      [YELLOW] Mike: 6 interactions
         Sentiment: 0.00 | Emotion: annoyance
      [YELLOW] Lisa: 6 interactions
         Sentiment: 0.00 | Emotion: neutral
      [YELLOW] Sarah: 5 interactions
         Sentiment: 0.00 | Emotion: neutral


    WHO APPEARS TOGETHER?
   ------------------------------------------------------------------------------------------
      Dad + Maya: 8 times together
      Dad + Mom: 8 times together
      Dad + Panda: 8 times together
      Dad + Prince: 8 times together
      Maya + Mom: 8 times together


====================================================================================================
17. TEMPORAL PATTERNS - Your Daily Rhythm
    FamilyOS Demo 17: Preference Learning & Routine Detection
====================================================================================================

    YOUR DAILY RHYTHM:
   ------------------------------------------------------------------------------------------


    WEEKEND vs WEEKDAY:
   ------------------------------------------------------------------------------------------

   Weekday 
      Events: 803 | Avg Sentiment: 0.64
      Common Emotions: admiration, amusement, anger, annoyance

   Weekend 
      Events: 818 | Avg Sentiment: 0.66
      Common Emotions: anger, annoyance, approval, caring

   Weekday 
      Events: 46449 | Avg Sentiment: 0.00
      Common Emotions: 


====================================================================================================
18. LOCATION INTELLIGENCE - Your Spatial Patterns
    FamilyOS Demo 9-12: Adaptive Home Intelligence
====================================================================================================

    YOUR LOCATIONS:
   ------------------------------------------------------------------------------------------

    Home
      Episodes: 412 | Sentiment: 0.57 
      Activities: milestone, routine, social

    Office
      Episodes: 83 | Sentiment: 0.57 
      Activities: milestone, routine, social

    New House
      Episodes: 56 | Sentiment: 0.71 
      Activities: milestone, routine, social

    Gym
      Episodes: 26 | Sentiment: 0.64 
      Activities: routine, unknown

    Venue
      Episodes: 5 | Sentiment: 0.90 
      Activities: milestone, social

    Lincoln Elementary
      Episodes: 4 | Sentiment: 0.75 
      Activities: milestone, social

    Hospital
      Episodes: 3 | Sentiment: 0.63 
      Activities: social, work

    Brunch Cafe
      Episodes: 3 | Sentiment: 0.90 
      Activities: milestone, social


====================================================================================================
19. REMINDER INTELLIGENCE - Your Mental Load
    FamilyOS Demo 19: Project Orchestration & Task Tracking
====================================================================================================

    YOUR MENTAL LOAD:
   ------------------------------------------------------------------------------------------

    REMINDER (ACTIVE) - 216 items
      [GREEN] call Mom...
      [GREEN] remember to submit the quarterly report by Friday at 5pm...
      [GREEN] to pick up Emma from soccer practice...

    DECISION (ACTIVE) - 84 items
      [GREEN] Should I take the new job offer from Google or stay at my current comp...
      [GREEN] I'm trying to decide between buying a house in Brooklyn or renting in ...
      [GREEN] What do you think - should Emma switch from soccer to basketball?...


====================================================================================================
20. HOLISTIC LIFE VIEW - Everything Connected
    FamilyOS Vision: Context-Aware Family Intelligence
====================================================================================================

   ==============================================================================
                            YOUR LIFE IN NUMBERS                                  
   ==============================================================================
      Raw Events Ingested:          2112                                    
      Episodic Memories:             639  (What happened)                 
      Semantic Patterns:             749  (What you learned)              
      Knowledge Entities:            103  (People, places, things)        
     <->  Knowledge Edges:              2782  (How things connect)             
      Social Relationships:           54  (Who matters)                   
      Prospective Intentions:        300  (What's on your mind)           
       Contextual Observations:    48070  (Holistic context layer)        
   ==============================================================================
    

    HOW LAYERS INTERCONNECT:
   ------------------------------------------------------------------------------------------

   EXAMPLE: A Single Memory's Multi-Layer Presence

    EPISODIC: "Milestone with Alex, James, Lisa at Brunch Cafe"
      +-- Location: Brunch Cafe
      +-- Participants: ['Alex', 'James', 'Lisa', 'Marcus', 'Maya', 'Panda', 'Priya', 'Sarah']

    OBSERVATION:
      +-- Sentiment: 0.90
      +-- Emotion: joy
      +-- Time: 
        
    SOCIAL: Alex
      +-- Type: FRIEND
      +-- Total Interactions: 2
                    
    KNOWLEDGE GRAPH: Alex
      +-- Type: PERSON
      +-- Observations: 9
                    

====================================================================================================
 THIS IS THE FAMILYOS VISION:
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

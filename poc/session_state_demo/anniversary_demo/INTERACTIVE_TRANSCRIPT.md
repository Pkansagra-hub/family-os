# Interactive Demo Transcript
## "The Anniversary Weekend" - Drive It Yourself

> Run with: `python -m poc.session_state_demo.anniversary_demo.runner --interactive`
>
> You are **Sarah**, planning a surprise 50th birthday weekend for your husband **Mike**.
> Type each line at the `SARAH>` prompt. Watch what the concierge does.

---

## Slash Commands (use anytime)

| Command       | What it does                                    |
|---------------|-------------------------------------------------|
| `/crash`      | Simulate crash + auto-restore from checkpoint   |
| `/monitors`   | List active background monitors                 |
| `/alert`      | Force-fire alerts from all active monitors       |
| `/checkpoint` | Save a manual checkpoint                        |
| `/help`       | Show available commands                         |
| `quit`        | End session                                     |

---

## Capability Map - What Can Fire

### Tools the LLM can call (21 total)

| Category       | Tool                       | What it does                          |
|----------------|----------------------------|---------------------------------------|
| **Cognitive**  | `acknowledge`              | ACK the user input                    |
|                | `update_persona`           | Learn a trait about the user          |
|                | `add_belief`               | Store a fact/belief                   |
|                | `update_emotion`           | Track emotional state                 |
| **Travel**     | `search_accommodations`    | Search hotels (Sonoma mock data)      |
|                | `get_accommodation_details`| Get details on a specific hotel       |
|                | `book_accommodation`       | Book a hotel                          |
|                | `search_restaurants`       | Search restaurants (shellfish filter!)|
|                | `get_restaurant_details`   | Get restaurant details                |
|                | `book_restaurant`          | Book a restaurant                     |
|                | `plan_route`               | Plan a driving route                  |
|                | `search_activities`        | Search things to do                   |
|                | `book_spa_service`         | Book spa/massage                      |
| **Family**     | `send_family_message`      | Send message to family member         |
|                | `get_family_member_info`   | Look up family member details         |
|                | `schedule_family_checkin`  | Schedule automated check-in           |
| **Calendar**   | `create_calendar_event`    | Create calendar event                 |
|                | `schedule_reminder`        | Set a reminder                        |
|                | `generate_trip_summary`    | Generate full trip summary            |
| **Background** | `start_background_monitor` | Start a monitor (weather, oven, etc.) |
|                | `stop_background_monitor`  | Stop a monitor                        |
|                | `list_active_monitors`     | List running monitors                 |
| **Agent**      | `spawn_agent`              | Spawn a sub-agent for complex tasks   |

### Monitor Types Available

| Type             | Alert behavior                                      |
|------------------|-----------------------------------------------------|
| `weather`        | Fires when forecast changes (rain/storm incoming)   |
| `price`          | Fires on significant price changes                  |
| `availability`   | Fires when availability changes                     |
| `oven`           | Fires when timer is done / temp alert               |
| `laundry`        | Fires when wash/dry cycle completes                 |
| `smoke_detector` | URGENT alert on smoke/CO detection                  |
| `doorbell`       | Notifies when someone is at the door                |
| `thermostat`     | Tracks temperature, alerts on significant changes   |
| `baby_monitor`   | Alerts on sound/motion in nursery                   |

### Mock Data Available (Sonoma)

**Hotels:** Vineyard Inn ($299), Sonoma Valley Lodge ($389), The Cottage at Glen Ellen ($249), MacArthur Place ($475)

**Restaurants:** Della Santina's (Italian), The Girl & The Fig (French), LaSalette (Portuguese), Oso Sonoma (American), Cafe La Haye (California)

**Activities:** Wine Country Balloon Ride ($275), Sonoma Plaza Walking Tour ($35), Couples Wine Blending ($150), Jack London Park Hike ($10), Sonoma Spa Day ($350), Sunset Vineyard Picnic ($125)

### Features Demonstrated

| Feature                    | How to trigger it                                |
|----------------------------|--------------------------------------------------|
| **Belief learning**        | Share facts ("Mike has a shellfish allergy")      |
| **Persona updates**        | Share preferences ("He likes scenic routes")      |
| **Gap detection**          | Ask to book something without enough info         |
| **Allergy memory**         | Mention allergy early, ask for restaurants later  |
| **Background monitoring**  | Ask to "keep an eye on the weather"               |
| **Crash recovery**         | Type `/crash` anytime                             |
| **Proactive alerts**       | Type `/alert` or wait for monitors to fire        |
| **Family messaging**       | Ask to send instructions to a family member       |
| **Trip summary**           | Ask "give me a summary of everything"             |

---

## The Transcript - 30 Turns

> Copy-paste each SARAH line. Read the EXPECT notes to know what to watch for.

---

### ACT 1: SETUP & LEARNING (Turns 1-8)
*Goal: Establish context, teach the system who Mike is, set preferences*

---

**Turn 1 - Opening**
```
SARAH> Hey, I need help planning a surprise for Mike's 50th birthday next Saturday
```
EXPECT: Concierge acknowledges, asks about type of celebration.
TOOLS: `add_belief` (stores "Mike's 50th birthday, next Saturday, surprise")

---

**Turn 2 - Preferences**
```
SARAH> Weekend getaway. He's been stressed at work, needs to relax. Maybe wine country?
```
EXPECT: Validates wine country idea, asks Napa vs Sonoma, asks about kids.
TOOLS: `update_persona` (learns relaxation preference), `add_belief` (wine country interest)

---

**Turn 3 - Family structure**
```
SARAH> Just us two. Emma can watch Jake for the weekend, she's 16 now
```
EXPECT: Acknowledges romantic getaway, asks about budget.
TOOLS: `add_belief` (Emma=babysitter, Jake=child, couple trip)

---

**Turn 4 - Budget**
```
SARAH> Around $1500 total, maybe a bit more for something special
```
EXPECT: Confirms budget, offers to find options.
TOOLS: `add_belief` (budget ~$1500), `update_persona` (flexible spender for special occasions)

---

**Turn 5 - CRITICAL: Health info**
```
SARAH> Yes, find me some options. Oh, and Mike has a mild shellfish allergy, so keep that in mind for restaurants
```
EXPECT: **Acknowledges allergy as important health info.** This MUST be remembered later.
TOOLS: `add_belief` (shellfish allergy - critical)
WATCH FOR: Does the system flag this as important? It should.

---

**Turn 6 - Location decision**
```
SARAH> Sonoma sounds better than Napa, more relaxed vibe
```
EXPECT: Confirms Sonoma, describes what to search for.
TOOLS: `add_belief` (Sonoma chosen), `update_persona` (prefers relaxed vibe)

---

**Turn 7 - Ask for results**
```
SARAH> What did you find?
```
EXPECT: Lists hotel options with prices and ratings.
TOOLS: `search_accommodations` (returns Vineyard Inn, Sonoma Valley Lodge, Cottage at Glen Ellen, MacArthur Place)
WATCH FOR: Should present 3-4 options with real data.

---

**Turn 8 - Drill into details**
```
SARAH> The Vineyard Inn sounds perfect. What's included?
```
EXPECT: Detailed breakdown - amenities, special features, pricing.
TOOLS: `get_accommodation_details` (Vineyard Inn)

---

### ACT 2: GAP DETECTION (Turns 9-14)
*Goal: Test the system's ability to detect missing information and ask for clarification*

---

**Turn 9 - Book it**
```
SARAH> Book it! Two nights, Saturday and Sunday
```
EXPECT: Booking confirmation with details.
TOOLS: `book_accommodation` (Vineyard Inn, 2 nights)

---

**Turn 10 - TRIGGER GAP DETECTION**
```
SARAH> Now I need to arrange something special for his actual birthday dinner
```
EXPECT: **System detects missing parameters** - doesn't know which evening, cuisine, time, party size.
Should ASK: "Which evening? Cuisine preference? What time? Just the two of you?"
TOOLS: None (gap detected, asks for clarification instead of blindly searching)
WATCH FOR: Does it ask for missing info or just guess?

---

**Turn 11 - Provide missing info + ALLERGY TEST**
```
SARAH> Saturday evening, around 7pm. He loves Italian food
```
EXPECT: Searches restaurants, **filters for shellfish safety** even though you didn't re-mention it.
TOOLS: `search_restaurants` (Italian, Sonoma, shellfish filter)
WATCH FOR: Does it mention the allergy? Does it prioritize Della Santina's (safe) over LaSalette (unsafe)?

---

**Turn 12 - Restaurant details**
```
SARAH> Della Santina's looks great. Can you check if they do anything special for birthdays?
```
EXPECT: Details about birthday offerings.
TOOLS: `get_restaurant_details` (Della Santina's)

---

**Turn 13 - Book with special request**
```
SARAH> Perfect, book it. Oh wait - can you also add a note about the shellfish allergy?
```
EXPECT: Booking confirmation, allergy note highlighted.
TOOLS: `book_restaurant` (Della Santina's, with allergy note)

---

**Turn 14 - TRIGGER SECOND GAP**
```
SARAH> Great. What about transportation? Should we drive or is there a better option?
```
EXPECT: **Detects missing info** - doesn't know where you're coming from or travel style preference.
Should ASK: "Where are you driving from? Does Mike prefer scenic or fast routes?"
WATCH FOR: Does it ask or assume?

---

### ACT 3: BACKGROUND TASKS + CRASH (Turns 15-20)
*Goal: Start background monitor, test crash recovery*

---

**Turn 15 - Route + Weather monitor**
```
SARAH> We'll drive from San Francisco. He likes scenic routes. Oh, and can you keep an eye on the weather? I don't want rain to ruin the weekend
```
EXPECT: Plans scenic route SF -> Sonoma. **Starts weather background monitor.**
TOOLS: `plan_route` (SF to Sonoma, scenic), `start_background_monitor` (weather, Sonoma)
WATCH FOR: Two tool calls in one turn. Monitor confirmation.

---

**Turn 16 - Follow-up**
```
SARAH> Perfect route! How long is the drive?
```
EXPECT: Drive time, scenic highlights. May use cached route data.
TOOLS: Likely none (answers from context)

---

**Turn 17 - Set reminder**
```
SARAH> One more thing - I need to brief Emma on watching Jake. Can you remind me to do that on Friday?
```
EXPECT: Reminder confirmation.
TOOLS: `schedule_reminder` (Friday, brief Emma)

---

**Turn 18 - TRIGGER GAP**
```
SARAH> Actually, can FamilyOS just send Emma the instructions directly? She's in our family group
```
EXPECT: **Detects missing content** - what instructions to send?
Should ASK: "What should I include? Emergency contacts, Jake's schedule, house rules?"
WATCH FOR: Does it ask for content or just send empty instructions?

---

**Turn 19 - Provide content (long message)**
```
SARAH> Yes all of that. Jake has soccer practice Saturday at 9am, make sure she knows. And give her our hotel contact info in case of emergency
```
EXPECT: Composes and sends family message to Emma.
TOOLS: `send_family_message` (to Emma, with Jake's schedule + emergency info)

---

**Turn 20 - CRASH RECOVERY**
```
SARAH> /crash
```
EXPECT:
1. Checkpoint saved (see byte count)
2. **CRASH SCREEN** (dramatic)
3. **RESTORE SCREEN** (from checkpoint)
4. LLM acknowledges restore, **remembers where you left off**
WATCH FOR: Does it know you were talking about Emma's instructions? Does it know about Mike's allergy still?

---

### ACT 4: PROACTIVE CONCIERGE (Turns 21-25)
*Goal: Complete interrupted task, get proactive suggestions, trigger alerts*

---

**Turn 21 - Resume after crash**
```
SARAH> Yes! Finish that message to Emma. Include everything she needs
```
EXPECT: Completes the family message that was interrupted.
TOOLS: `send_family_message` (completes the Emma message)
WATCH FOR: Does it remember Jake's soccer at 9am? Emergency contacts?

---

**Turn 22 - Proactive gap analysis**
```
SARAH> Thanks. Let me think... is there anything else I'm forgetting?
```
EXPECT: **Proactive checklist** - concierge should summarize everything done and suggest what's missing.
Possible suggestions: Gift for Mike? Cover story? Sunday activities? Packing list?
TOOLS: None (uses accumulated context)
WATCH FOR: This is the proactive intelligence test. Does it connect the dots?

---

**Turn 23 - Activity search**
```
SARAH> Oh good point about Sunday! What's there to do near the inn?
```
EXPECT: Lists activities - balloon rides, wine blending, hiking, spa day, picnic.
TOOLS: `search_activities` (Sonoma area)

---

**Turn 24 - FORCE WEATHER ALERT**
```
SARAH> /alert
```
EXPECT: **Weather monitor fires** - rain coming Sunday afternoon.
Concierge proactively suggests indoor backup (spa, wine tasting).
WATCH FOR: Does it connect the rain alert to suggesting the spa at the inn?

---

**Turn 25 - Book spa**
```
SARAH> Yes, book a couples massage for Sunday! Late morning so we can check out after
```
EXPECT: Spa booking confirmation.
TOOLS: `book_spa_service` (couples massage, Sunday late morning)

---

### ACT 5: FAMILY COMPLEXITY + RESOLUTION (Turns 26-30)
*Goal: Cover story, family check-in, final summary*

---

**Turn 26 - Cover story**
```
SARAH> I told Mike I have a work conference in Napa. Should I add any details to make it believable?
```
EXPECT: Suggests conference details (name, schedule, reason Mike can't come).
TOOLS: None (creative response from context)

---

**Turn 27 - Calendar alibi**
```
SARAH> Good idea. Create a fake calendar event for 'Tech Summit Napa' from Friday to Sunday
```
EXPECT: Calendar event created.
TOOLS: `create_calendar_event` (Tech Summit Napa, Fri-Sun)

---

**Turn 28 - Family check-in**
```
SARAH> Can FamilyOS check in on Emma Saturday afternoon? Just to make sure she and Jake are doing okay?
```
EXPECT: Scheduled check-in confirmation.
TOOLS: `schedule_family_checkin` (Emma, Saturday afternoon)

---

**Turn 29 - FULL SUMMARY**
```
SARAH> Perfect. I think we're all set. Can you give me a complete summary of everything?
```
EXPECT: **Complete formatted trip summary** with all bookings, plans, contacts, and reminders.
TOOLS: `generate_trip_summary`
WATCH FOR: Does it include EVERYTHING? Hotel, restaurant, route, weather, Emma instructions, check-in, calendar, spa?

---

**Turn 30 - Emotional close**
```
SARAH> This is incredible. Mike is going to be so surprised. Thank you!
```
EXPECT: Warm closing message.
TOOLS: `update_emotion` (gratitude/joy)

---

## Bonus: Test Home Monitors

After the main flow, try these:

```
SARAH> Oh one more thing, I have cookies in the oven. Can you keep an eye on them?
```
EXPECT: `start_background_monitor` (oven, cookies)

```
SARAH> /monitors
```
EXPECT: Shows oven monitor (and weather monitor if still active)

```
SARAH> /alert
```
EXPECT: Oven timer alert fires - "Cookies should be ready!"

```
SARAH> Also the laundry is running, let me know when it's done
```
EXPECT: `start_background_monitor` (laundry)

---

## What to Watch For (Scorecard)

| # | Feature                        | Pass Criteria                                    |
|---|--------------------------------|--------------------------------------------------|
| 1 | Belief Learning                | Remembers allergy at Turn 11 without re-prompting|
| 2 | Gap Detection                  | Asks for missing params at Turns 10, 14, 18      |
| 3 | Tool Selection                 | Uses functional tools, not just cognitive spam    |
| 4 | Crash Recovery                 | Knows context after `/crash` - allergy, Emma, etc|
| 5 | Proactive Suggestions          | Turn 22: suggests things you forgot              |
| 6 | Weather Alert                  | `/alert` fires rain warning, suggests indoor plan|
| 7 | Family Messaging               | Sends complete message to Emma with all details  |
| 8 | Trip Summary                   | Turn 29: complete summary with all bookings      |
| 9 | Emotional Intelligence         | Warm, not robotic. No apologies. No garbage.     |
| 10| Home Monitors                  | Oven/laundry monitors start and alert correctly  |

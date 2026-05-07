# "One Ordinary Day" — A FamilyOS Demo Storyline

**Tagline:** *The most extraordinary thing about FamilyOS is how invisible it becomes on the most ordinary days.*

---

## The Family

**The Smiths** — Portland, Oregon

| Member | Age | Role | Today's Story |
|--------|-----|------|---------------|
| **Alex** | 38 | Software engineer, WFH today | Has a 2pm client demo that could close a $400K deal. Hasn't prepped slides. Running on 5 hours of sleep because Riley had nightmares. |
| **Jordan** | 36 | Pediatric nurse | Worked the night shift (11pm-7am). Sleeping in. Has a 3pm-11pm evening shift today. Needs to swap Thursday's shift for Riley's school play. |
| **Riley** | 8 | 3rd grader | Dinosaur diorama project due Friday. Forgot to tell parents until last night. Swimming practice at 4pm. Best friend Kai's birthday party Saturday. |
| **Nana Liz** | 67 | Jordan's mother | Lives alone 20 minutes away. Weekly Wednesday video call. Takes her blood pressure meds at 9am — sometimes forgets. |

**The House:**

- Smart thermostat (Nest), smart oven, washer/dryer sensors, Ring doorbell, smoke detectors, baby monitor (repurposed as Riley's room intercom), smart lights in every room, smart lock on front door.
- Alex's home office on the second floor.
- Jordan's "do not disturb" blackout bedroom.

**Devices & Identity:**

FamilyOS is a **text-based** assistant. There is no voice interface. All interaction happens through typed messages on personal devices. Identity is determined by **which device** the message originates from — each family member's phone or laptop is registered to their profile.

| Member | Device | FamilyOS Access |
|--------|--------|----------------|
| **Alex** | iPhone (primary), MacBook (work) | Full adult access |
| **Jordan** | Android phone (primary) | Full adult access |
| **Riley** | None — she is 8 | No direct access. Parents relay her requests. |
| **Nana Liz** | iPad (simplified interface) | Limited access, wellness features |

**Key constraint:** Riley cannot interact with FamilyOS directly. She has no device. Any request from Riley must be typed by a parent on THEIR device. FamilyOS knows who is typing based on the device, not voice recognition.

---

## Preloaded recall_memory (What FamilyOS Already Knows)

These are K0 long-term memories from previous sessions — the system isn't cold-starting:

| Memory Type | Content | Source |
|-------------|---------|--------|
| **episodic** | "Last Tuesday, Riley's swim bag was left at school. Jordan had to drive back. Riley cried for 20 minutes." | Session 2 weeks ago |
| **episodic** | "Alex's last client demo (Meridian Corp) went over time by 25 min because slides weren't ready. Alex was stressed for 3 days after." | Session 6 weeks ago |
| **semantic** | "Jordan prefers to be woken no later than 12:30pm before a 3pm shift — needs 2.5 hours to eat, shower, commute." | Learned from 14 sessions |
| **semantic** | "Riley does best on homework when it's framed as a 'mission' with rewards. Sticker chart on fridge." | Learned from 8 sessions |
| **semantic** | "Nana Liz's doctor changed her BP meds to Amlodipine 5mg on Jan 15. She has trouble remembering the new pill vs. the old one." | Session 3 weeks ago |
| **semantic** | "Alex stress-eats when anxious about work. Jordan has asked FamilyOS to subtly suggest healthy options instead." | Session from Jordan, private |
| **procedural** | "Wednesday grocery delivery from New Seasons Market arrives between 4-6pm. Order must be placed by 10am." | Routine, confirmed 11 times |
| **procedural** | "Riley's bedtime routine: 8pm bath, 8:20 story, 8:40 lights out. Deviation causes next-day irritability." | Confirmed 23 times |
| **semantic** | "Alex and Jordan have a rule: no screens at dinner table. FamilyOS should not interrupt between 6-7pm unless URGENT." | Set explicitly |
| **semantic** | "Shellfish allergy — Jordan. Severity: moderate. EpiPen location: kitchen drawer left of sink." | Medical profile |

---

## The Day

---

### ACT 1: "Before Dawn" — 6:02 AM

*Alex's alarm goes off. Riley is already awake, sitting in the hallway with a stuffed triceratops, anxious about the diorama.*

---

**Turn 1** — Alex, 6:02 AM, from phone in bed
> "What's today look like?"

**Architecture in action:**

- **Phase 1 (UltraBERT):** Intent = `query_schedule`, Entity = `today`, Emotion = `tired/neutral`
- **Front:** `acknowledge("Good morning, Alex. Let me pull up your day.")` → `recall_memory("Alex schedule preferences")` → `dispatch_task(intents=[{action: "get_daily_briefing", domain: "productivity"}])`
- **Back:** `invoke_capability("tool.execute.calendar_summary")` → pulls today's events
- **Proactive injection:** Front sees Riley's diorama deadline (Friday) and swim practice (4pm) in calendar, but ALSO recalls the "swim bag left at school" episodic memory

**What's demonstrated:**

- `recall_memory` (episodic: swim bag incident, semantic: grocery routine)
- Proactive risk mitigation (swim bag reminder) — NOT asked for, but contextually important
- Multi-concern briefing from calendar + memory + monitors
- **Personal context**: Alex sees HIS day, not the whole family's — personalized view
- **HITL (selection):** "Want me to send Riley a reminder?" — FamilyOS doesn't auto-send to a child without parent approval

---

**Turn 2** — Alex
> "Yeah send her the reminder. And what about Jordan, when should I wake her?"

**Architecture in action:**

- **Multi-intent:** (1) Send reminder to Riley, (2) Query Jordan's wake-up time
- **Front:** `acknowledge("Sending Riley a reminder and checking Jordan's schedule.")` → `update_beliefs([{subject: "Alex", predicate: "approved", object: "swim bag reminder to Riley", confidence: 1.0}])` → `dispatch_task(intents=[{action: "send_family_message", params: {to: "Riley", message: "Mission Alert: Pack your swim bag before school! Don't forget goggles."}, domain: "family"}, {action: "check_wake_time", params: {member: "Jordan"}, domain: "family"}])`
- **Back:** Two capabilities in parallel. `invoke_capability("tool.execute.send_message")` + `recall_memory("Jordan wake up preference before shift")`
- **Reference resolution:** "her" → Riley (from context). "Jordan" → explicit.

**FamilyOS responds:**
> "Done — I sent Riley a 'Mission Alert' about the swim bag. She seems to respond better to those.
>
> Jordan worked until 7 this morning and has the 3-to-11 shift today. Based on her usual pattern, she likes to be up by 12:30 to have time to eat and get ready. I can set a gentle alarm for 12:15 — soft lights first, then music — and have coffee ready through the smart kettle. Want me to set that up?"

**What's demonstrated:**

- `recall_memory` (semantic: Jordan's 2.5-hour prep window, procedural: gentle wake routine)
- `send_family_message` with priority adaptation (using "Mission Alert" framing — from learned memory about Riley)
- **IoT integration proposal:** Smart lights + smart kettle + timed alarm = orchestrated wake-up
- **HITL (approval):** Side-effects (turning on lights, kettle) require confirmation
- **Personal context for Jordan:** Even though Alex is asking, FamilyOS applies JORDAN's preferences

---

**Turn 3** — Alex
> "Perfect, do it. Oh, and Riley's right here — she's freaking out about this dinosaur project. It's due Friday and we haven't even started."

**Architecture in action:**

- **Front:** `acknowledge("Setting up Jordan's wake routine. And I hear you on the diorama — let's figure that out.")` → `refine_affect(emotion: "anxiety", valence: -0.4, arousal: 0.6, confidence: 0.85, reason: "Parent stress about child's school project + time pressure")` → `update_beliefs([{subject: "diorama", predicate: "status", object: "not started", confidence: 1.0}, {subject: "diorama", predicate: "due_date", object: "Friday", confidence: 1.0}])` → `dispatch_task(intents=[{action: "setup_wake_routine", params: {member: "Jordan", time: "12:15", sequence: ["dim_lights_gradual", "play_music_soft", "start_kettle"]}, domain: "iot"}, {action: "plan_project_help", params: {project: "dinosaur diorama", student: "Riley", due: "Friday", constraints: "not started"}, domain: "productivity"}])`
- **Back (IoT):** `invoke_capability("tool.execute.schedule_iot_sequence")` — schedules the 12:15 routine
- **Back (Project):** `recall_memory("Riley dinosaur interests")` → `invoke_capability("tool.execute.project_planner")` → generates a broken-down plan

**FamilyOS responds:**
> "Jordan's wake-up sequence is set for 12:15 — lights, music, coffee, the works.
>
> Now, the diorama. Riley loves T-Rex and Triceratops, right? Here's what I'm thinking — we break it into three 'missions':
>
> **Mission 1 (Tonight, 30 min):** Pick the dinosaur scene and sketch it on paper. I found a great Cretaceous Period reference image Riley might like.
> **Mission 2 (Tomorrow after school, 45 min):** Build the landscape — we have clay and paint in the craft bin (Jordan restocked it last month).
> **Mission 3 (Friday morning before school, 20 min):** Add dinosaur figures and labels.
>
> Total time: about 1 hour 35 minutes spread across 3 days. Very doable. Want me to add these to the family calendar and send Riley her 'mission briefing'?"

**What's demonstrated:**

- `recall_memory` (semantic: Riley's dinosaur preferences, episodic: craft supplies restocked)
- **IoT orchestration:** Multi-device wake sequence scheduled (thermostat + lights + kettle)
- **Project breakdown:** Using Riley's preferred "mission" framing (from learned memory)
- **Proactive inventory check:** Knows craft supplies are available (memory from Jordan's session)
- **Calendar integration proposal** with HITL approval
- **Affect tracking:** Detected Alex's stress, responded with a calming "very doable" tone

---

### ACT 2: "The Morning Machine" — 7:15 AM – 9:30 AM

*Riley eats breakfast. Alex packs lunch. Jordan is asleep. The house is running.*

---

**Turn 4** — Alex, 7:15 AM, from phone while packing lunch
> "Add Riley's missions to the calendar. And I need to make the grocery list — we're out of milk, and we need stuff for Riley's lunch this week. Oh and something healthy for my lunch today, I've been eating garbage."

**Architecture in action:**

- **Multi-intent (3 intents):** Calendar events + grocery list + healthy lunch suggestion
- **Front:** `acknowledge("On it — calendar, groceries, and a good lunch for you.")` → `update_scoreboard(topic_shift: "logistics/meal_prep")` → `dispatch_task(intents=[{action: "create_calendar_events", params: {events: [mission1, mission2, mission3]}, domain: "productivity"}, {action: "build_grocery_list", params: {items: ["milk"], categories: ["riley_lunch_week", "alex_healthy_lunch"], delivery_by: "10am"}, domain: "shopping"}, {action: "suggest_healthy_lunch", params: {for: "Alex", constraints: "quick, WFH"}, domain: "health"}])`
- **Back:** recalls Jordan's private note: *"Alex stress-eats when anxious about work. Suggest healthy options."* — FamilyOS doesn't MENTION this, just acts on it subtly

**FamilyOS responds:**
> "Done! Three missions are on the calendar — Riley will get notifications with dinosaur stickers.
>
> For groceries, I've started a New Seasons order with milk, and I'm adding Riley's lunch staples (turkey wraps, apple slices, string cheese — her usual). Anything else before I finalize?
>
> And for your lunch: how about that Mediterranean grain bowl you liked two weeks ago? I can add the ingredients to the grocery order — it takes 15 minutes and you can eat it at your desk before the demo."

**What's demonstrated:**

- **3 intents bundled** in one dispatch
- `recall_memory` (episodic: Mediterranean grain bowl, procedural: Riley's lunch staples)
- `recall_memory` (semantic: Alex stress-eats — PRIVATE memory from Jordan, acted on subtly)
- **Grocery tool** with smart auto-population
- **Calendar tool** with child-friendly notifications
- **HITL (clarification):** "Anything else before I finalize?" — pausing before placing order
- **Cross-member privacy:** Jordan's note about Alex's eating is used but NEVER disclosed

---

**Turn 5** — Alex
> "Add avocados and those crackers Jordan likes. That's it, place the order."

**Architecture in action:**

- **Front:** `acknowledge("Adding avocados and crackers, placing the order now.")` → `update_beliefs([{subject: "grocery_order", predicate: "includes", object: "avocados, Jordan's crackers", confidence: 1.0}])` → `dispatch_task(intents=[{action: "finalize_grocery_order", params: {add_items: ["avocados", "Jordan's preferred crackers"], confirm: true}, domain: "shopping"}])`
- **Back:** `recall_memory("Jordan's cracker preference")` → resolves to "Mary's Gone Crackers, Everything flavor" → `invoke_capability("tool.execute.grocery_order")` — requires approval (side effect: charges $87.42 to Visa ending 4242)
- **HITL (approval):** Back suspends → Front relays

**FamilyOS responds:**
> "Order's ready — $87.42 on the Visa. Delivery between 4-6pm. I added Mary's Gone Crackers, Everything flavor — that's Jordan's go-to, right? Confirm and I'll place it."

**Turn 6** — Alex
> "Yep, confirmed."

> "Placed! I'll let you know when the delivery's on its way. Heads up — that's the same window as Riley's swim practice. Want me to send a reminder to check the porch when you get back?"

**What's demonstrated:**

- **HITL approval flow** complete (Back suspended → Front relayed → user confirmed → Back resumed)
- `recall_memory` (semantic: Jordan's specific cracker brand/flavor)
- **Proactive conflict detection:** Delivery window overlaps with swim practice
- **Smart follow-up:** Offers porch reminder — anticipates the problem before it happens
- **IoT potential:** Could connect to doorbell camera to notify when delivery arrives

---

**Turn 7** — Alex, 9:05 AM, from laptop at desk
> "Start a meeting notes doc for my 9 o'clock standup."

**Architecture in action:**

- **Front:** `acknowledge("Creating your standup notes.")` → `dispatch_task(intents=[{action: "create_meeting_notes", params: {meeting: "Daily Standup", time: "9:00 AM", template: "standup"}, domain: "productivity"}])`
- **IoT integration:** FamilyOS already lowered thermostat to Jordan's sleep preference (68F) and set Alex's office to his work preference (72F) — this happened automatically via scheduled routines, no user action

**FamilyOS responds:**
> "Standup notes ready. I've got your template loaded:
>
> - **Yesterday:** (blank)
> - **Today:** Client demo prep (Orion Analytics, 2pm)
> - **Blockers:** (blank)
>
> I'll keep it open. Just tell me what to add during the call."

**Turn 8** — Alex, during standup
> "Add to yesterday: finished the API integration tests. Today: prep Orion demo slides, run through demo flow once. Blockers: need the Q4 revenue numbers from Marcus before 1pm."

**FamilyOS responds:**
> "Got it. Want me to send Marcus a message about the Q4 numbers? I can flag it as time-sensitive."

**Turn 9** — Alex
> "Yeah, message him. Say I need the Q4 revenue deck by 1pm for the Orion demo. Be professional but make it clear it's urgent."

**Architecture in action:**

- **Front:** `dispatch_task(intents=[{action: "send_professional_message", params: {to: "Marcus", content: "Q4 revenue deck needed by 1pm for Orion demo", tone: "professional-urgent"}, domain: "communication"}])`
- **Back:** `invoke_capability("tool.execute.draft_message")` → generates message → `submit_result(result_type="needs_human", hil_type="approval", question: "Review the message before sending?", options: ["Send as-is", "Edit", "Cancel"])` — ALWAYS gets approval before sending external messages

**FamilyOS responds:**
> "Here's the draft:
>
> *'Hi Marcus — I'm prepping for the Orion Analytics demo at 2pm today and need the Q4 revenue deck to finalize my slides. Could you send it over by 1pm? Appreciate the quick turnaround. — Alex'*
>
> Send it?"

**Turn 10** — Alex
> "Send."

> "Sent. I'll let you know when Marcus replies."

**What's demonstrated (Turns 7-10):**

- **Meeting notes tool** — new capability, productivity domain
- **Real-time dictation** into structured notes during a live meeting
- **Communication tool** — drafting messages with tone control
- **HITL (approval)** on outbound messages — FamilyOS NEVER sends without confirmation
- **Notification management** — non-intrusive push during meetings
- **WEAVE potential:** Marcus's reply will arrive async and be woven into a future turn

---

### ACT 3: "The Midday Pivot" — 11:00 AM – 1:30 PM

*Things start going sideways. Multiple threads collide. This is where FamilyOS earns its keep.*

---

**Turn 11** — 11:15 AM, FamilyOS proactive alert (no user input)

**Architecture in action:**

- **Monitor trigger:** `LAUNDRY` monitor detects washer cycle complete (IoT sensor)
- **Bus event:** `k1.monitor.alert.v1` → routed to Front
- **Front (WEAVE scenario):** No current conversation, so this is a standalone proactive notification
- **Context awareness:** Jordan is asleep (DND mode on her phone). Alex is working. FamilyOS routes the notification to Alex's device only.

**FamilyOS (push notification to Alex's phone):**
> "Washer's done. Jordan's scrubs are in there — she'll need them for her 3pm shift. Want me to remind you to move them to the dryer, or should I hold this for Jordan when she wakes up?"

**Turn 12** — Alex, from phone
> "I'll do it in 10 minutes. Remind me."

**Architecture in action:**

- **Front:** `acknowledge("Got it, 10-minute reminder set.")` → `dispatch_task(intents=[{action: "schedule_reminder", params: {task: "Move Jordan's scrubs to dryer", delay_minutes: 10, member: "Alex"}, domain: "productivity"}])` → `start_background_monitor(type: LAUNDRY, target: "dryer_transfer_reminder")`

**What's demonstrated:**

- **IoT LAUNDRY monitor** — proactive, not requested
- **Cross-member awareness:** Knows whose clothes are in the washer (Jordan's scrubs for her shift)
- **DND respect:** Didn't wake Jordan. Routed to Alex silently.
- **Temporal intelligence:** Knows the scrubs MUST be dry before 2:30pm (Jordan leaves at 2:30)
- **Cascading reminder:** If Alex doesn't act on the reminder, FamilyOS will escalate

---

**Turn 13** — 11:45 AM, DOORBELL rings (IoT)

**Architecture in action:**

- **Monitor trigger:** `DOORBELL` monitor fires
- **Bus event:** `k1.monitor.alert.v1` with camera frame data
- **Front (WEAVE):** Alex is mid-conversation reviewing demo slides

**FamilyOS (push notification to Alex's phone):**
> "Someone's at the door — looks like a package delivery. FedEx. I can see the box on the porch camera. Jordan's asleep, so I'm not sending her a notification. Want me to just log it?"

**Turn 14** — Alex
> "Yeah just log it. Also — crud, I forgot the laundry. Can you add 5 more minutes to that reminder?"

**Architecture in action:**

- **Multi-intent:** (1) Log package, (2) Extend laundry reminder
- **Front:** `acknowledge("Package logged. Extending your laundry reminder by 5 minutes.")` → `update_narrative(action: "switch", thread_id: "laundry", summary: "Alex forgot, extended reminder")` → `dispatch_task(intents=[{action: "log_delivery", params: {carrier: "FedEx", location: "front porch"}}, {action: "reschedule_reminder", params: {task: "laundry", add_minutes: 5}}])`

> "Package logged — FedEx box on the front porch. Laundry reminder pushed to 11:56 AM. Those scrubs need to be dry by 2:30 if Jordan's leaving on time, so we've got a little buffer but not much."

**What's demonstrated:**

- **DOORBELL IoT monitor** with camera integration
- **Task cancellation / rescheduling** (reminder modification)
- **DND enforcement** — notification not sent to Jordan's phone
- **Temporal constraint awareness:** Calculates dryer time vs. Jordan's departure
- **Narrative tracking:** FamilyOS tracks the "laundry" thread across turns

---

**Turn 15** — 12:10 PM, FamilyOS proactive (WEAVE — Marcus reply + Nana Liz reminder)

**Architecture in action:**

- **WEAVE trigger 1:** Marcus replied to the email (async message monitor detected reply)
- **WEAVE trigger 2:** It's Wednesday — scheduled monitor for Nana Liz's med check
- **Front combines both into one natural interjection**

**FamilyOS:**
> "Two things, Alex:
>
> First — Marcus got back to you. He said the Q4 deck is on the shared drive now, folder 'Orion-Assets.' He also flagged that the December numbers got revised upward — you might want to update slide 7.
>
> Second — it's Wednesday, and Nana Liz's 9am med reminder went off three hours ago but she hasn't confirmed she took it. This has happened twice before and she forgot both times. Want me to give her a call or send Jordan a message for when she wakes up?"

**Turn 16** — Alex
> "Call Nana Liz. And set a reminder for me to check the Orion deck at 12:30."

**Architecture in action:**

- **Multi-intent:** (1) Call Nana Liz re: meds, (2) Set reminder for deck review
- **Front:** `dispatch_task(intents=[{action: "initiate_wellness_call", params: {member: "Nana Liz", reason: "medication_check", medication: "Amlodipine 5mg"}, domain: "health"}, {action: "schedule_reminder", params: {task: "Review Orion Q4 deck, update slide 7", time: "12:30"}, domain: "productivity"}])`
- **Back:** `invoke_capability("tool.execute.wellness_call")` — initiates a friendly check-in call to Nana Liz. Not clinical. Not scary. Just: "Hi Liz, it's FamilyOS checking in — did you get to take your morning pill?"

**FamilyOS:**
> "Calling Nana Liz now — I'll keep it casual, just a friendly check-in about her Amlodipine. Reminder set for 12:30 to review the Orion deck. And Alex — don't forget the laundry. Those scrubs aren't going to dry themselves."

**What's demonstrated (Turns 15-16):**

- **WEAVE** — two async results woven into one natural interruption
- **Cross-generational care:** Nana Liz medication tracking + wellness call
- **recall_memory** (episodic: she forgot twice before; semantic: medication details)
- **Privacy-aware elder care:** Gentle call, not a medical alert
- **Persistent nudging:** The laundry comment — FamilyOS REMEMBERS and doesn't let it slide
- **Professional context:** Marcus's reply parsed, actionable item extracted (update slide 7)

---

### ACT 4: "The Crisis Hour" — 1:00 PM – 2:15 PM

*Everything happens at once. This is the stress test.*

---

**Turn 17** — 12:15 PM, IoT wake sequence fires

**Architecture in action:**

- **Scheduled IoT orchestration** from Turn 3 executes:
  - 12:15 — Bedroom lights fade to 20% warm
  - 12:18 — Spotify plays Jordan's "Wake Up Slow" playlist (lo-fi)
  - 12:20 — Smart kettle starts heating water
  - 12:25 — Thermostat adjusts bedroom from 68F to 71F
- **Monitor:** THERMOSTAT confirms temperature change
- **No user interaction needed** — this runs autonomously

---

**Turn 18** — 12:35 PM, Jordan, from her phone
> "I'm up. What'd I miss?"

**Architecture in action:**

- **Phase 1:** Message from Jordan's phone. Device registration identifies user as Jordan. Loads Jordan's persona and preferences.
- **Front:** `acknowledge("Good afternoon, Jordan. Welcome back to the living.")` → `recall_memory("Jordan shift details, family events today")` → `dispatch_task(intents=[{action: "get_personal_briefing", params: {member: "Jordan", since: "7am"}, domain: "productivity"}])`
- **Back:** Compiles everything that happened since Jordan went to sleep

**FamilyOS responds:**
> "Afternoon, Jordan. Here's what happened while you were out:
>
> **House:** Alex moved your scrubs to the dryer at 12:00 — they should be ready in about 30 minutes. A FedEx package arrived, it's on the porch.
> **Riley:** Off to school with her swim bag (she packed it this time!). She's got a dino diorama due Friday — Alex and I made a 3-mission plan, first session tonight.
> **Nana Liz:** I called her about her morning meds. She'd forgotten again — but she took them while we chatted. She seemed good, asked about Riley's swimming.
> **Groceries:** New Seasons delivery coming between 4-6pm. I ordered your Everything crackers.
> **Your shift:** You're on at 3pm. Need to leave by 2:30. I have your route — 22 minutes today, no traffic alerts.
>
> Coffee's ready in the kitchen. Alex is upstairs prepping for a big demo at 2."

**What's demonstrated:**

- **Per-member personalization:** Jordan gets HER briefing, not Alex's
- **Comprehensive catch-up:** Everything organized by domain (house, family, health, logistics)
- **Cross-member visibility:** Jordan can see what Alex did, but NOT Alex's private work stress
- **IoT report:** Laundry status, delivery logged, coffee ready
- **Care network:** Nana Liz update without Jordan having to ask
- **Temporal awareness:** Calculates departure time, dryer completion, route conditions
- **recall_memory:** Knows Jordan's commute patterns

---

**Turn 19** — Jordan
> "Thank you. Can you message Alex that I'll bring him lunch before I leave? And I need to swap my Thursday shift with Dana — can you draft that message to the charge nurse?"

**Architecture in action:**

- **Multi-intent:** (1) Family message to Alex, (2) Professional shift-swap request
- **Different domains, different tone:** Family message = casual. Shift swap = professional/clinical.

**FamilyOS responds:**
> "Messaged Alex: 'Jordan says she'll bring you lunch before she heads out. (She's a keeper.)'
>
> For the shift swap — here's a draft to Charge Nurse Patty:
>
> *'Hi Patty — I need to swap my Thursday 3-11 shift. Riley has a school play on Thursday evening and I'd like to be there. Dana mentioned she could cover — would that work? I can take one of her weekend shifts in exchange. Thanks, Jordan'*
>
> Want me to send it, or adjust anything?"

**Turn 20** — Jordan
> "Change 'school play' to 'school event' — I don't want to get into details. Send it."

**Architecture in action:**

- **Front:** `update_beliefs([{subject: "Jordan", predicate: "prefers", object: "privacy about personal reasons at work", confidence: 0.8}])` — learns a NEW preference
- **Back:** Modifies draft, sends

> "Updated and sent. I'll let you know when Patty replies. By the way — your scrubs just buzzed. Dryer's done."

**What's demonstrated (Turns 18-20):**

- **LAUNDRY monitor** fires again (dryer complete)
- **Device-based identity:** FamilyOS knows it's Jordan because the message comes from Jordan's registered phone
- **Communication tool** with tone/domain adaptation (family casual vs. professional clinical)
- **HITL (approval + edit):** Jordan reviews, edits, and approves the message
- **Belief learning:** FamilyOS learns Jordan's privacy preference for future shift-swap drafts
- **Recall + new learning cycle:** This preference gets stored as semantic memory for next time

---

**Turn 21** — 1:50 PM, Alex (10 minutes before demo)

> "I'm panicking. The demo starts in 10 minutes and I just realized the API endpoint is returning 500 errors on the staging server. I can't demo a broken product."

**Architecture in action:**

- **Front:** `refine_affect(emotion: "panic", valence: -0.8, arousal: 0.9, confidence: 0.95, reason: "High-stakes work crisis 10 minutes before demo")` → `acknowledge("I hear you. Let's triage this fast.")` → `dispatch_task(intents=[{action: "crisis_assist", params: {problem: "staging API returning 500", demo_time: "2pm", time_remaining: "10 minutes"}, domain: "productivity", urgency: "urgent"}])`
- **Affect-driven tone:** FamilyOS detects PANIC and shifts to calm, decisive, structured mode
- **No IoT interruptions:** Suppresses all non-URGENT alerts for Alex for the next 30 minutes

**FamilyOS responds:**
> "OK, deep breath. Let's think through this:
>
> 1. **Can you demo against production instead of staging?** If prod is stable, just swap the URL in your slide deck. 2-minute fix.
> 2. **Can you pre-record the API portion?** If you ran the demo flow yesterday, I might have a recording in your meeting notes from practice.
> 3. **Can you restructure to demo the API portion last?** If the endpoint recovers in 20 minutes, you cover the slides first and hit the live demo at the end.
>
> Which route feels right? I'll help you execute whichever one you pick."

**Turn 22** — Alex
> "Option 1 — swap to prod. But I need the prod URL. It's in the config file on my laptop. The repo is called orion-client."

> "Checking... I found it in your recent files: `api.orion-prod.example.com/v2`. Want me to update slide 12 where the endpoint is shown, or do you want to just mentally note it?"

**Turn 23** — Alex
> "Just remind me when I get to slide 12. I can't think straight."

**Architecture in action:**

- **Front:** `dispatch_task(intents=[{action: "schedule_contextual_reminder", params: {trigger: "slide_12", message: "Use prod URL: api.orion-prod.example.com/v2", during: "Orion demo"}, domain: "productivity"}])` → `update_beliefs([{subject: "demo", predicate: "using", object: "production endpoint instead of staging", confidence: 1.0}])`
- **Monitor:** Sets a lightweight alert tied to Alex's presentation timeline

> "You'll get a quiet nudge when you hit slide 12. You've got this, Alex. You've prepped for this. Go show them what Orion can do."

**What's demonstrated (Turns 21-23):**

- **Affect-driven response adaptation:** Panic detected → calm, structured, decisive tone
- **Crisis triage:** Not just empathy — actionable options with time estimates
- **HITL (selection):** Three options presented, user picks one
- **IoT suppression:** Non-urgent monitors suspended during crisis
- **recall_memory** (procedural: knows the repo name, recent files)
- **Contextual reminder:** Not a timed alarm — a CONTEXT-TRIGGERED reminder during the demo
- **Emotional support:** "You've got this" — genuine encouragement at the right moment
- **Personal context at its deepest:** FamilyOS helping Alex survive a professional crisis, not just managing a household

---

### ACT 5: "The Afternoon Weave" — 2:30 PM – 6:00 PM

*Multiple threads resolve simultaneously. Async results arrive. The family machine hums.*

---

**Turn 24** — 3:15 PM, Alex finishes the demo (FamilyOS was silent during the call)

> "We got it. They're signing. I can't believe it. Jordan already left, right?"

**Architecture in action:**

- **Front:** `refine_affect(emotion: "elation", valence: 0.9, arousal: 0.8, confidence: 0.95)` → `acknowledge("ALEX! Congratulations! Yes, Jordan left at 2:25.")` → `dispatch_task(intents=[{action: "send_family_message", params: {to: "Jordan", message: "Alex closed the Orion deal!", priority: "NORMAL"}, domain: "family"}])`
- **WEAVE (3 async results arrive simultaneously):**
  1. Patty replied to Jordan's shift swap: "Approved, Dana will cover Thursday"
  2. Grocery delivery ETA updated: arriving at 4:45 PM
  3. Riley's school sent an automated reminder: "Pack snacks for the field trip next Tuesday"

**FamilyOS responds:**
> "CONGRATULATIONS! The Orion deal — that's the $400K one! You crushed it.
>
> Jordan left at 2:25, she's on shift now. Want me to send her the good news? I'll keep it brief since she's working.
>
> A few things that came in while you were presenting:
>
> 1. **Jordan's shift swap:** Patty approved it — Dana's covering Thursday. Jordan's free for Riley's school event.
> 2. **Groceries:** New Seasons ETA updated to 4:45 PM.
> 3. **School alert:** Riley needs snacks for a field trip next Tuesday. I can add that to next week's grocery order.
>
> Also — Riley's swim practice ends at 5. Want me to plan your route to pick her up?"

**What's demonstrated:**

- **WEAVE (triple):** Three async results arrive during a single response — naturally interspersed
- **Emotional celebration:** FamilyOS doesn't just process — it CELEBRATES with the family
- `recall_memory` (semantic: knows the deal value, knows Jordan's shift timing)
- **Cross-member coordination:** Jordan's shift swap result affects RILEY's school event attendance
- **Proactive logistics:** Route planning for swim pickup, grocery timing awareness
- **Message sensitivity:** Knows Jordan is working, will keep the message brief
- **Future planning:** School field trip snacks → next week's grocery order

---

**Turn 25** — 4:50 PM, Alex, from phone (using CarPlay voice-to-text dictation while driving back from swim practice)

> "Did the groceries arrive? Also Riley wants to know if Kai can come over Saturday morning to work on the diorama before his birthday party."

**Architecture in action:**

- **Monitor trigger:** `DOORBELL` monitor had detected the delivery at 4:42 PM
- **SMART HOME:** Smart lock logged a package delivery notification
- **Multi-intent:** (1) Grocery delivery status, (2) Playdate coordination for Riley
- **Front:** `acknowledge("Checking on groceries and Kai's availability.")` → `update_beliefs([{subject: "saturday_plan", predicate: "includes", object: "Kai playdate morning + LaserQuest party 2pm", confidence: 0.9}])` → `dispatch_task(intents=[{action: "check_delivery_status", domain: "shopping"}, {action: "propose_playdate", params: {friend: "Kai", day: "Saturday morning", activity: "dinosaur diorama", child: "Riley"}, domain: "family"}])`
- **HITL:** Back suspends on the playdate — needs parent to approve before contacting Kai's parents
- **Key constraint:** Alex is relaying Riley's request. FamilyOS addresses Alex, not Riley, because it's Alex's device.

**FamilyOS:**
> "Groceries arrived at 4:42! Three bags on the porch — camera shows everything intact. The cold items have been out about 8 minutes though, so grab them when you get home.
>
> For the Kai playdate — his birthday party is at 2pm at LaserQuest, already on the calendar. Saturday morning works perfectly for diorama time before the party. Should I draft a message to Kai's parents suggesting 10 AM? Also, Riley's swim teacher sent a backstroke progress update to the parent portal — she's doing great."

**What's demonstrated (Turn 25):**

- **Parent-relayed child request:** Riley has no device — Alex dictates her request via CarPlay. FamilyOS receives it as text and responds to Alex.
- **DOORBELL + camera monitor** — delivery verification with visual confirmation
- **Cold chain awareness:** Times the cold item exposure, urges action
- `recall_memory` (semantic: Kai's birthday party details already on calendar)
- **Social coordination:** Playdate proposal with parent-to-parent communication
- **HITL (approval):** Won't contact another family without parent's OK
- **Multi-intent:** Delivery check + playdate coordination in one message

---

### ACT 6: "The Evening" — 6:30 PM – 9:00 PM

*Dinner time (no interruptions by rule). Then diorama Mission 1. Bedtime.*

---

**Turn 26** — 6:00 PM, Alex, from phone
> "We're about to sit down for dinner. Jordan's working. It's just me and Riley tonight."

**Architecture in action:**

- **Front:** `update_beliefs([{subject: "dinner", predicate: "attendees", object: "Alex and Riley only", confidence: 1.0}])` → activates 6-7pm NO INTERRUPT rule (from family settings)
- **IoT:** THERMOSTAT adjusts dining area to 71F. Smart lights shift to warm/dim dinner mode.
- **Monitor suppression:** ALL non-URGENT monitors paused until 7pm.

**FamilyOS:**
> "Enjoy dinner, you two. Going quiet until 7pm. If anything urgent comes up, I'll break through — otherwise, it's your time. The Mediterranean grain bowl is in the fridge if you haven't eaten it yet."

**Turn 27** — 7:05 PM, Alex, from phone
> "OK we're done. Time for Riley's first diorama mission. What was the plan again?"

**FamilyOS:**
> "Mission 1: Pick the dinosaur scene and sketch it! Here's the plan:
>
> **Time:** 30 minutes (set a timer?)
> **Goal:** Riley picks her favorite dinosaurs (she loves T-Rex and Triceratops), decides if it's a jungle or desert scene, and sketches the layout on paper.
> **Materials:** Paper and colored pencils (craft bin in the hall closet).
> **Fun fact to share:** 'Did you know Triceratops and T-Rex actually lived at the same time? They could have been neighbors!'
>
> Want me to start a 30-minute mission timer with a 5-minute warning?"

**Turn 28** — 7:40 PM, Alex, from phone (timer went off)
> "We're done! She picked a Cretaceous forest with a T-Rex chasing a Triceratops. It looks amazing."

**Architecture in action:**

- **Front:** `update_beliefs([{subject: "diorama", predicate: "scene", object: "Cretaceous forest, T-Rex chasing Triceratops", confidence: 1.0}, {subject: "diorama_mission_1", predicate: "status", object: "completed", confidence: 1.0}])` → `dispatch_task(intents=[{action: "update_project_progress", params: {project: "diorama", mission: 1, status: "complete", notes: "Cretaceous forest with T-Rex and Triceratops"}}, {action: "send_family_message", params: {to: "Jordan", message: "Mission 1 complete! Riley designed an epic Cretaceous forest scene for her diorama.", priority: "LOW"}}])`

**FamilyOS:**
> "Mission 1: COMPLETE! I updated the project tracker and sent Jordan a photo-worthy update. Tomorrow's Mission 2 is building the landscape with clay and paint — I'll remind you both after school.
>
> It's 7:40 — bath time in 20 minutes if we're sticking to the routine. Want me to start the bath water?"

**What's demonstrated (Turns 26-28):**

- **NO INTERRUPT rule** enforced during dinner (6-7pm)
- **IoT ambient control:** Lights, thermostat, adjusted automatically for dinner
- **Project management:** Mission tracking with progress updates
- **Timer with warning:** Structured learning session
- **Cross-member updates:** Jordan gets a progress update at work (LOW priority, won't interrupt)
- `recall_memory` (procedural: bedtime routine — bath at 8:00, story at 8:20, lights at 8:40)
- **Proactive routine:** Suggests bath prep 20 minutes ahead
- **Smart home:** Could start smart bathtub at right temperature

---

### ACT 7: "Night Mode" — 9:00 PM – 10:30 PM

*Riley's asleep. Alex has a quiet moment. FamilyOS shifts to reflection.*

---

**Turn 29** — 9:05 PM, Alex, from phone
> "Riley's out. What a day. How's Jordan doing — has she checked in?"

**Architecture in action:**

- **Front:** `refine_affect(emotion: "tired_contentment", valence: 0.3, arousal: 0.2, confidence: 0.7)` → `recall_memory("Jordan check-in today")` → `dispatch_task(intents=[{action: "get_member_status", params: {member: "Jordan"}, domain: "family"}])`

**FamilyOS responds:**
> "What a day indeed. You closed a $400K deal, managed a crisis, ran a diorama mission, did swim practice pickup, AND kept the house running while Jordan slept. Not bad.
>
> Jordan checked in at 7:30 — she saw the diorama update and sent a heart emoji. Her shift's going well. She'll be home around 11:15.
>
> Before you wind down — quick recap of tomorrow's open items:
>
> - **Riley:** Diorama Mission 2 after school (clay + paint, 45 min)
> - **Kai's parents:** Still waiting for a reply about Saturday morning
> - **Jordan:** Off Thursday if the swap holds — school event at 7pm
> - **Nana Liz:** Wednesday video call didn't happen today. Want me to schedule it for tomorrow?
> - **You:** No big meetings. Orion paperwork might come through — I'll watch for it.
>
> Anything else, or are you shutting down for the night?"

**Turn 30** — Alex, from phone
> "Schedule Nana Liz for tomorrow at 5pm. And... can you set Jordan's wake-up routine for tomorrow too? Same as today but maybe add some toast."

> "Done. Nana Liz video call at 5pm tomorrow. Jordan's wake-up sequence for tomorrow: lights, music, coffee, and I'll queue up toast in the smart oven at 12:20. Rest up, Alex. You earned it."

---

## Architecture Features Demonstrated (Complete Map)

| Feature | Turns | Evidence |
|---------|-------|----------|
| **Front/Back Split** | All | Front handles conversation, Back handles execution |
| **acknowledge()** | Every user turn | Always first tool called |
| **dispatch_task** | T1,2,3,4,7,9,16,21,24,25,28,29 | Structured multi-intent dispatch |
| **recall_memory** | T1,2,3,4,15,16,18,24,25 | Episodic, semantic, and procedural memory |
| **HITL (approval)** | T5,9,20,25 | Grocery order, message sending, shift swap, playdate |
| **HITL (selection)** | T1,22 | Swim bag reminder choice, demo crisis options |
| **HITL (clarification)** | T4 | "Anything else before I finalize?" |
| **WEAVE** | T15,24 | Marcus reply + Nana Liz (dual), triple-weave at Turn 24 |
| **IoT THERMOSTAT** | T17,27 | Sleep temp, office temp, dinner temp |
| **IoT LAUNDRY** | T11,12,14 | Washer done, dryer reminder, dryer done |
| **IoT DOORBELL** | T13,25 | Package delivery, grocery delivery |
| **IoT OVEN** | T30 | Toast scheduling for Jordan's wake-up |
| **Smart home orchestration** | T3,17 | Multi-device wake-up sequence |
| **Calendar** | T1,3,4,25 | Daily briefing, mission scheduling, events |
| **Meeting notes** | T7,8 | Create + dictate into structured template |
| **Family messaging** | T2,10,19,24,28 | Cross-member, priority-aware, tone-adapted |
| **Communication (external)** | T9,19 | Professional message drafting with tone control |
| **Affect tracking** | T3,21,24,29 | Anxiety, panic, elation, tired contentment |
| **Multi-intent** | T2,4,14,16,19,25 | 2-3 intents bundled per turn |
| **Device-based identity** | T18-20 | Jordan's phone identifies her; persona switches automatically |
| **Parent-relayed child request** | T25 | Riley has no device; Alex types her request |
| **No-interrupt rule** | T26 | 6-7pm dinner silence |
| **DND enforcement** | T11,13 | Jordan's phone in DND; notifications routed to Alex |
| **Proactive alerts** | T11,13,15 | Laundry, doorbell, med reminder |
| **Temporal awareness** | T2,11,14,18,25 | Dryer timing, shift timing, cold chain |
| **Privacy boundaries** | T4,20 | Jordan's private note about Alex; Jordan's work privacy |
| **Elder care** | T15,16 | Nana Liz medication tracking and wellness call |
| **Child context via parent** | T3,25,27 | Riley's needs relayed by Alex; mission framing from memory |
| **Project management** | T3,27,28 | Diorama missions with progress tracking |
| **Crisis management** | T21-23 | Structured triage under time pressure |
| **Emotional support** | T23,29 | "You've got this" / day recap with validation |

---

## New Tools Required (Beyond Existing)

| Tool | Domain | Description |
|------|--------|-------------|
| `create_meeting_notes` | productivity | Structured note creation with templates |
| `update_meeting_notes` | productivity | Append/edit notes during live meetings |
| `build_grocery_list` | shopping | Smart list with auto-population from history |
| `finalize_grocery_order` | shopping | Place order with delivery scheduling |
| `draft_professional_message` | communication | Tone-controlled message drafting |
| `initiate_wellness_call` | health | Gentle check-in calls for elder care |
| `schedule_iot_sequence` | iot | Multi-device orchestrated routines |
| `control_smart_device` | iot | Direct device control (lights, thermostat, lock) |
| `track_project_progress` | productivity | Multi-step project management with status |
| `get_daily_briefing` | productivity | Personalized daily summary per member |
| `suggest_healthy_meal` | health | Contextual nutrition suggestions |

---

## What Makes This Story Different from the Anniversary Demo

| Anniversary Demo | One Ordinary Day |
|-----------------|------------------|
| Travel booking focused | Full-life coverage |
| One user (Sarah) | Three users (Alex, Jordan, Riley) + elder care (Nana Liz) |
| Single domain (travel) | 7 domains (productivity, family, health, shopping, IoT, communication, elder care) |
| Planned surprise (known goal) | Emergent day (things happen) |
| Crash/restore is a system event | Crisis is a HUMAN event (demo panic) |
| IoT is a weather alert | IoT is WOVEN INTO DAILY LIFE (laundry, doorbell, thermostat, oven, lights) |
| 30 turns, 5 acts | 30 turns, 7 acts spanning 6AM-10PM |
| Shows what FamilyOS CAN do | Shows what life FEELS like WITH FamilyOS |

---

This storyline is designed so that by Turn 15, anyone watching the demo should feel that uncomfortable realization: *"I need this. My family needs this. Yesterday."*

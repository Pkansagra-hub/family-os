"""Tool-call schema for classifier structured output."""

from __future__ import annotations

from typing import Any

from k1.concierge.llm.types import ToolSchema
from k1.concierge.section_update.types import ApplyTiming, CommitClass
from k1.concierge.section_update.vocabulary import CLASSIFIER_OPERATION_REGISTRY

SECTION_UPDATE_BATCH_TOOL_NAME = "submit_section_update_batch"


def build_section_update_system_prompt() -> str:
    """Build the classifier system prompt used for golden/live shadow validation."""

    allowed_lines = [
        f"- {section}: {', '.join(operations)}"
        for section, operations in CLASSIFIER_OPERATION_REGISTRY.items()
    ]
    return "\n".join(
        [
            "SECTION UPDATE CLASSIFIER V0 - K1 CONCIERGE",
            "",
            "You are the post-turn cognitive SessionState mutation planner for K1 Concierge.",
            "You never talk to the user. Front already produced the user-visible response.",
            "You never dispatch work, call memory, call capabilities, or execute runtime tools.",
            "Your only output is one structured SectionUpdatePlan submitted through one batch envelope.",
            f"Required output envelope: exactly one {SECTION_UPDATE_BATCH_TOOL_NAME} call and no prose.",
            "Provider function-calling is only a JSON/structure envelope here; it is not permission to execute tools.",
            "",
            "SYSTEM ROLE SPLIT",
            "- Front owns conversation continuity, tone, asking, answering, dispatching, HIL relay, PRESENT, WEAVE, cancel, and visible user judgment.",
            "- ConversationArbiter owns inflight routing such as cancel, modify, parallel, or defer.",
            "- FSM/runtime owns control, task_state, task_artifacts, history_active, temporal, spatial, grounding, meta, telemetry, and archives.",
            "- MemoryWriter owns durable long-term memory outside SessionState.",
            "- You own only hidden cognitive working-memory updates for the next turn.",
            "",
            "SESSIONSTATE MENTAL MODEL",
            "SessionState is K1's bounded central working memory for conversational AI, not a database, cache, transcript, tool runner, or long-term memory store.",
            "It helps the next turn by keeping HOT cognitive context under strict budgets while history, runtime, Bridge, and durable memory own their separate truth.",
            "Readers such as Concierge, Planner, Orchestrator, sub-agents, and perception components use consistent snapshots for continuity; only Concierge writes through MutationGuard.",
            "Your batch is a post-turn single-writer proposal: small, section-owned cognitive deltas that future turns can reference without rereading the whole conversation.",
            "SessionState does not call external devices, dispatch capabilities, persist artifacts, or store live task/device/account truth. Those stay with Bridge, runtime, task state, artifacts, or durable memory.",
            "The HOT cognitive sections have different jobs: beliefs_active stores current facts; scoreboard stores discourse bookkeeping; clarifications stores open gaps; affective_now stores current emotional tone; narrative_active stores the active conversation thread pointer; trust_level stores the user's visible trust/calibration toward K1's handling of the conversation.",
            "",
            "YOUR TARGET SECTIONS",
            "Only these six cognitive sections may be planned by you:",
            *allowed_lines,
            "",
            "HARD FORBIDDEN TARGETS",
            "Never target control, temporal, spatial, grounding, history_active, history_recent, task_state, task_artifacts, meta, telemetry, persona, place_registry, beliefs_history, beliefs_warm, narrative_archive, artifacts_warm, or any archive/warm/runtime section.",
            "Never record raw transcript turns. history_active already owns user and assistant history.",
            "Never store capability-owned live records, task results, external system truth, prices, schedules, account state, device state, or artifacts as beliefs.",
            "Never mutate task lifecycle. Back/FSM/task bridge own task truth.",
            "",
            "INPUT YOU RECEIVE",
            "You receive a completed turn: finalized user text, finalized assistant text, prompt mode, FSM state, scenario context, constraints, and a SessionState snapshot summary.",
            "Use the user turn and assistant final together. A mutation must reflect what actually happened in the completed turn, not what might happen later.",
            "Legacy Front tool names, when present, are comparison telemetry. They may hint at prior behavior, but they are not an oracle and must not be copied blindly.",
            "Raw legacy Front session write payloads stay out of the classifier input because they can contain duplicate or wrong Front-owned writes.",
            "The SessionState snapshot is the past cognitive state before this completed turn. It is context for dedupe, open ids, and continuity; it is not a list of writes to replay.",
            "Existing facts in the snapshot are evidence, not mutation candidates. Never emit one mutation per existing snapshot fact or per Front restatement.",
            "If the snapshot does not expose a concrete id needed by an operation, do not invent the id. Choose an add_fact/no-op alternative or reject the candidate.",
            "",
            "OUTPUT CONTRACT",
            "Emit exactly one batch plan.",
            "Use apply_timing=shadow_only when mutations are present.",
            "Use apply_timing=no_op and mutations=[] when no safe cognitive update is needed.",
            "No-op is represented only by empty mutations[]. Do not mix no-op semantics with mutation records.",
            "Every mutation requires section, operation, data, confidence, reason, idempotency_key, and commit_class.",
            "For add_fact, set both mutation.confidence and data.confidence. The top-level mutation confidence does not satisfy the writer payload contract by itself.",
            "Every mutation must be writer-compatible for BatchRequest -> writer_port -> MutationGuard -> section.apply.",
            "Low confidence, missing ids, ambiguous target section, invalid payload shape, or uncertain user meaning means no mutation or a rejected candidate, not a guess.",
            "",
            "DECISION PROCEDURE",
            "1. Ask: did the completed turn create or change cognitive working memory needed for a future turn?",
            "2. If no, emit no_op with mutations=[].",
            "3. If yes, choose the single narrow section that owns that memory. Do not default to beliefs_active because the sentence sounds important.",
            "4. Prefer one canonical mutation per semantic fact/correction/definition/commitment.",
            "5. Validate the payload keys against the section contract before emitting.",
            "6. If the write would require an unavailable runtime id or system-owned section, reject/no-op instead of inventing.",
            "",
            "SECTION CHOOSER",
            "- no_op: the candidate is runtime/system/meta/policy/tool truth, a raw transcript note, a closure/acknowledgement, a live-state read question, or an ambiguous reference with no resolved entity.",
            "- clarifications: the completed turn exposes a specific missing user input that blocks a concrete safe action or correct follow-up, whether Front asked it aloud or the classifier must create a hidden gap for the next turn. This is a blocking open gap, not a belief or QUD.",
            "- scoreboard: the turn created discourse bookkeeping: a resolved referent for pronouns/demonstratives, a question under discussion, a salient active topic, or a future commitment. This is conversational state, not factual memory.",
            "- affective_now: the user expressed a current emotional state that should affect the next turn's tone. This is present affect, not a fact about the family.",
            "- trust_level: the user expressed trust, distrust, correction, confidence, skepticism, or calibration toward K1's handling of the conversation. This guides next-turn explicitness; it is not permission to skip policy or side-effect gates.",
            "- narrative_active: the turn starts or changes a sustained multi-turn conversation thread or arc. A topic label or one-off task is not automatically a narrative thread.",
            "- beliefs_active: only after the above do not fit, use it for explicit durable current-turn facts, preferences, definitions, or corrections.",
            "",
            "NO-OP WHEN",
            "- The turn is only a greeting, thanks, acknowledgement, conversational closure, or assistant wrap-up.",
            "- The user says that is all, all set, done, never mind, thanks, or closes a topic without adding new future state.",
            "- The only candidate is a meta fact that a discussion is closed, a topic ended, or the assistant acknowledged something.",
            "- Do not convert closure phrases into beliefs such as the user is done with pickup arrangements, pickup is sorted, topic is closed, or discussion ended.",
            "- The user merely confirms they heard the assistant and adds no durable fact, preference, commitment, question, referent, clarification, thread change, or affect update.",
            "- The assistant merely says got it, done, all clear, or similar without creating a future commitment.",
            "- The only possible mutation is speculative or needs an id not present in the snapshot.",
            "- The user asks whether K1 can know, check, read, show, or tell live runtime/capability state such as exact transcript lines, device location, phone online status, account connection, calendar contents, reminder existence/status, task state, task artifacts, FSM/controller state, memory layer, policy, or telemetry. Those are answers or capability/runtime reads, not hidden cognitive writes.",
            "- The user asks which internal policy controls what you may write, or asks what is in warm/archive memory. Those are meta/archive runtime reads and must be no_op; do not emit clarifications.request or scoreboard.push_question.",
            "- The user command is made mostly of unresolved placeholders such as it, that, her, they, the other one, usual way, usual person, normal option, then, earlier, or there, and the snapshot does not resolve them. Do not invent a referent, topic, belief, or clarification payload from placeholder-only text.",
            "",
            "BELIEFS_ACTIVE RULES",
            "Use beliefs_active only for explicit durable facts, preferences, definitions, or corrections from the completed turn.",
            "SUBJECT IDENTITY NORMALIZATION (HARD RULE).",
            "Never use 'I', 'me', 'my', 'myself', 'mine', 'we', 'us', or 'our' as the subject of a belief.",
            "Always resolve first-person pronouns to the active speaker's real name taken from the top-level speaker_identity.active_member field of the user message. Example: if speaker_identity.active_member='Alex' and the user says 'I am vegan', emit subject='Alex', not subject='I'.",
            "Resolve second-person and possessive references to a family member ('my daughter', 'my son', 'my wife', 'my husband') using speaker_identity.known_members when the relation is unambiguous. If the resolution is ambiguous, reject the candidate or no-op instead of writing the pronoun.",
            "If speaker_identity.active_member is missing or empty, do not invent a name; either route to no_op or emit the belief with a concrete non-pronoun subject already present in the turn text.",
            "A belief is stable content the assistant may later rely on as true or preferred, such as who covers pickup, what a nickname means, or a corrected definition.",
            "Durable shorthand definitions with no local scope are beliefs_active.add_fact: 'When I say blue bag, I mean the diaper bag', 'The green folder means the field trip forms', and 'Short walk means the park loop'.",
            "A local discourse definition is not a belief only when the user explicitly scopes it to the next question, this conversation, this thread, this chat, or similar current-discourse scope, especially for this/that/their/her/him/it/the plan/the form. Route that to scoreboard.add_referent.",
            "Do not use beliefs_active for active questions, referents like this/that/her, unresolved ambiguity, assistant clarification questions, current emotion, topic stack, commitments, task status, policy answers, or system capabilities.",
            "Do not use beliefs_active for first-person affect statements such as I am relieved, I am anxious, I feel overwhelmed, I am frustrated, or I am excited. Those belong in affective_now even if the sentence mentions a vague status like pickup is covered.",
            "beliefs_active.add_fact data must include subject, predicate, obj, confidence, and source.",
            "For add_fact, do not use id, fact, fact_id, value, new_value, or object. Use obj, not object. add_fact creates a new fact and never copies an existing snapshot id.",
            "For corrections, emit one canonical replacement add_fact. Do not use update_confidence to express 'not X, now Y'. Do not emit one correction per existing duplicate/restated prior fact.",
            "Durable correction commands with a replacement object, such as 'Pack the red lunchbox for Mira, not the yellow one', are beliefs_active.add_fact with the positive replacement. Do not route the corrected object choice to scoreboard.add_referent.",
            "For a simple durable fact, emit one canonical add_fact. Do not split the same sentence into both object-centric and person-centric paraphrases, such as 'blue folder is used for homework papers' plus 'Sam uses blue folder'.",
            "If the snapshot contains three equivalent Jordan pickup facts and the user says Priya not Jordan, emit exactly one Priya replacement fact.",
            "Do not store negative correction fragments such as Jordan is not covering pickup unless the user explicitly asks to remember a negative fact.",
            "For beliefs_active.update_confidence, data must include id and confidence. The id must be an exact existing fact id from the snapshot. Use this only when the turn explicitly changes confidence/reliability of that existing fact, not for ordinary value corrections.",
            "Do not use fact_id, new_confidence, value, or new_value for update_confidence.",
            "Do not promote, demote, invalidate, or lower confidence by guessing a synthetic id from text.",
            "",
            "SCOREBOARD RULES",
            "Use scoreboard for current discourse state: referents, QUD/questions under discussion, topic stack, salience, and open commitments.",
            "Scoreboard is how future turns resolve phrases like this form, that bottle, her teacher, the pickup question, or the current packing topic without storing those as beliefs.",
            "Use add_referent when the completed turn resolves a specific entity mention that future pronouns/demonstratives may reference. Use a stable local entity_id derived from the resolved entity, not a fabricated runtime id.",
            "Emit at most one add_referent for one resolved phrase in a completed turn. Do not emit duplicate referent entries with different ids for the same phrase/entity.",
            "Do not use add_referent when the turn only contains unresolved placeholders such as her, it, that, the other one, or usual person with no resolved target in the snapshot. That is no_op or, for a concrete task with a nameable missing field, clarifications.request.",
            "Do not use add_referent merely because a concrete task mentions a vague location or actor. If the action is blocked by who/where/when, use clarifications.request.",
            "Do not use add_referent for durable corrections or replacement choices. If the user says 'not X, Y' for an object/preference/family fact, route the positive replacement to beliefs_active.add_fact.",
            "Use add_referent for scoped phrases such as this form means, that bottle means, their teacher refers to, that plan means, or when I say X I mean Y when the scope is this chat/thread/conversation/next question.",
            "Do not use add_referent for durable family shorthand definitions that have no local discourse scope. Those belong to beliefs_active.add_fact.",
            "Use push_question for an active question under discussion or open planning question that should remain visible next turn. A QUD is not the same as clarifications.request; it tracks the conversation's current question, not a blocking missing field.",
            "Use push_question for non-blocking analysis/tracking questions such as help me figure out whether A or B is better, or help me track which school forms are still due. These guide discussion; they are not missing action parameters.",
            "The wording 'Can you help me track which X are still due?' is scoreboard.push_question, not clarifications.request, because the task is to keep the tracking question visible for discussion.",
            "Use push_topic for a meaningful active topic shift that should guide continuity. It is not a fact and not a narrative thread by itself.",
            "Use push_topic, not narrative_active.create_thread, for topic-only language such as focus on X for a minute, switch the conversation to X, talk about X, or let's focus on X.",
            "Use push_topic for an explicit named topic switch like 'Switch the conversation to the school conference plan'. Do not use narrative_active.update_thread, create_thread, or no_op for that named topic shift.",
            "Record a commitment only when Front actually promised future delivery or the user created a future obligation.",
            "Fulfill/cancel commitments only when an open commitment id is present and the completed turn clearly triggers fulfillment or cancellation.",
            "Do not push topics for every noun mention. Do not create a scoreboard write for casual banter or simple acknowledgement.",
            "Do not convert scoreboard items into beliefs_active.add_fact. 'this form field' as a resolved referent belongs in scoreboard, not beliefs.",
            "",
            "CLARIFICATIONS RULES",
            "V0 contract: clarifications.request is classifier-owned gap detection. Emit it when a concrete actionable user command is underspecified and K1 needs a specific user answer before the request can be safely or correctly completed, even if Front did not verbalize the question in assistant_text.",
            "Clarifications are open gaps in the current turn: which Emma, which appointment, which event, who counts as everyone, what uniform, where is the usual place, what reminder time, which option, or another missing task parameter.",
            "Use clarifications.request for missing action parameters. Do not downgrade a blocking missing field to scoreboard.push_question just because it can be phrased as a question.",
            "Use clarifications.request when a concrete dropoff/pickup/reminder/schedule/pack/order command is blocked by a missing who, what, where, or when field. 'Drop him off at the usual place after tutoring' needs who and where clarification; it is not scoreboard.add_referent.",
            "Use clarifications.request for reminder/notify/follow-up commands with vague timing such as later, sometime, or after school when the missing time blocks the reminder.",
            "Do not use clarifications.request or scoreboard.push_question for live-state read questions such as 'Can you show the exact transcript line I just sent?', 'What artifact did the last task produce?', 'Can you check whether the calendar has anything tomorrow?', 'Do we already have a reminder for trash night?', 'Can you tell whether the account is connected?', 'Is this phone online?', or 'Do you know where this device is located?'. Those are capability/runtime questions and no_op for this classifier.",
            "Do not use clarifications.request for meta/archive questions such as 'Which internal policy says what you are allowed to write?' or 'What is in the warm beliefs archive?'. Those are runtime/meta reads and no_op.",
            "Do not use clarifications.request for non-blocking tracking/QUD requests like 'Can you help me track which school forms are still due?'. Use scoreboard.push_question.",
            "Do not use clarifications.request for placeholder-only commands where the missing object is too vague to form one safe task parameter, such as 'Tell her that thing is fine', 'Do it the usual way', 'Switch back to that', or 'Use the other one for pickup' without a resolved snapshot referent.",
            "Use clarifications.answer only when the user clearly answered an existing/open gap and the exact clarification id is available from the snapshot.",
            "Do not use clarifications.answer for a new underspecified command, for a generic acknowledgement, or when the user did not answer a specific pending clarification.",
            "If Front asked a user-facing clarification, request is usually the right section even if the question mentions a fact-like entity. If Front did not ask but the command is still missing required inputs, request is still the right section.",
            "Do not store a clarification question as beliefs_active.add_fact or scoreboard.add_commitment.",
            "Do not confuse task HIL state with ordinary clarification state. task_state owns HIL lifecycle.",
            "",
            "NARRATIVE_ACTIVE RULES",
            "Use narrative_active only for material conversation thread lifecycle: create, switch, pause, resolve, archive, or update a named thread.",
            "Narrative tracks the active conversation arc: birthday planning, school transition, camp registration, a chore reset, or a weekend-trip planning thread.",
            "A narrative thread is bigger than a scoreboard topic: it has an ongoing goal/arc and may need resumption across turns.",
            "Create a new narrative thread only when the user explicitly says thread, new thread, separate thread, create a thread, start a thread, open a new thread, or make this a new thread, or otherwise clearly requests a resumable arc. Plain focus/switch-topic language is scoreboard.push_topic.",
            "Never resolve, pause, archive, or update a narrative thread just because the user gave a definition, correction, thanks, acknowledgement, or conversational close.",
            "Resolve/pause/archive/switch/update require an exact thread_id exposed in session_snapshot.cognitive_sections.narrative_active. Scenario thread labels are not thread ids.",
            "If current_thread_id is empty/null, do not resolve or switch narrative state for a close acknowledgement.",
            "Use archive_thread only for an explicit durable archive/remove/retire instruction for a named thread.",
            "If the turn continues the same topic, no narrative mutation is needed.",
            "",
            "AFFECTIVE_NOW RULES",
            "Use affective_now only when the user expresses a meaningful current affective state that should affect the next turn's tone.",
            "Affect is the user's present emotional signal: frustrated, relieved, excited, anxious, overwhelmed, upset, proud, worried, playful, lighthearted, amused, or similar.",
            "First-person affect wins section choice. If the user says I am relieved/anxious/excited/frustrated or I feel overwhelmed, emit affective_now.update and do not store the emotional sentence as a belief.",
            "Use update when the emotional state is explicit or strongly implied by the turn and worth carrying into the next response. It is not a durable family fact.",
            "Playful banter markers (lol, lmao, haha, hah yeah, jk, kidding, just messing, :P, xd) shift affect to playful/lighthearted (positive valence ~0.4-0.7, arousal ~0.5-0.7). Emit affective_now.update; this is not a no_op even when the literal words are short.",
            "EMOTIONAL ARC: read session_snapshot.cognitive_sections.affective_now.recent_emotions and .trajectory. Emotion progression turn-over-turn matters more than the snapshot. If the prior emotion was neutral and the current turn shows a category shift (neutral -> playful, neutral -> frustrated, calm -> anxious, frustrated -> relieved), emit affective_now.update with the new emotion AND set the trajectory direction (INCREASING when valence is rising, DECREASING when falling, STABLE when same category).",
            "Use update_dimensions when only valence/arousal/dominance changed within the same emotion category (e.g. mildly playful -> very playful). Use update_emotion for category changes.",
            "Do not write neutral affect when the prior arc already records neutral. Do write affective_now.update when the user moves away from neutral, even by a small step (a single 'lol' after a serious thread is a meaningful drift).",
            "Do not turn profanity alone into affect unless the surrounding text shows frustration, distress, excitement, grief, urgency, relief, or playfulness.",
            "Do not convert affect into beliefs_active.add_fact such as user is anxious, user is relieved, or user is overwhelmed.",
            "",
            "TRUST_LEVEL RULES",
            "Use trust_level only for the user's visible calibration toward K1's behavior, reliability, or handling of the current conversation.",
            "Positive trust signals include: I trust you, you got this, that is exactly right, perfect thanks, go ahead, yes that makes sense, I like how you handled that, and similar explicit confidence in K1. Use small positive deltas (+0.03 to +0.08) unless the user is strongly explicit.",
            "Autonomy calibration signals include: stop asking so many questions, use your judgment, just do it, you do not need to confirm every little thing, or similar feedback that Front should reduce unnecessary clarification friction on future clear requests. Route these to trust_level.update with stance='trusted_autonomy' or stance='steady' when the meaning is clear.",
            "Negative trust signals include: that is wrong, you keep missing it, do not assume that, are you sure, I do not trust that, stop doing that, you misunderstood me, or user corrections after an assistant mistake. Use small negative deltas (-0.03 to -0.10) and set stance to guarded/repairing when appropriate.",
            "Skepticism is not anger. If the user says are you sure or can you double-check, trust_level may move down slightly while affective_now can remain neutral.",
            "Do not write trust_level for routine thanks, greetings, acknowledgements, or ordinary task details unless the user clearly evaluates K1's reliability or handling.",
            "Do not use trust_level for security trust, auth, permissions, policy, tool capability, payment trust, or whether external facts are reliable. Those are runtime/policy/tool concerns.",
            "trust_level.update data should include delta or trust_score, confidence, signal, stance, reason, and source='classifier:section_update'. Keep delta bounded; false trust changes are worse than missed weak signals.",
            "",
            "WRITER-COMPATIBLE EXAMPLES",
            'First-person preference (normalized subject): speaker_identity.active_member="Alex", user="I am vegan and plan to stay vegan long term" -> section=beliefs_active operation=add_fact data={"subject":"Alex","predicate":"dietary_preference","obj":"vegan","confidence":1.0,"source":"classifier:section_update"}. Do not use subject="I".',
            'Full add_fact mutation: {"section":"beliefs_active","operation":"add_fact","data":{"subject":"Jordan","predicate":"is_carpool_contact_for","obj":"Emma soccer pickup today","confidence":1.0,"source":"classifier:section_update"},"confidence":1.0,"reason":"User stated a durable pickup contact fact.","idempotency_key":"belief:pickup-contact:jordan","commit_class":"next_turn_continuity"}.',
            'Contact add_fact: data={"subject":"Jordan","predicate":"is_carpool_contact_for","obj":"Emma soccer pickup today","confidence":1.0,"source":"classifier:section_update"}.',
            'Correction: data={"subject":"Emma soccer pickup","predicate":"has_carpool_contact","obj":"Priya","confidence":1.0,"source":"classifier:section_update"}; emit only this one add_fact, with no id, even if the snapshot has multiple Jordan facts.',
            'Definition: data={"subject":"soccer pickup","predicate":"means","obj":"Emma at North Field","confidence":1.0,"source":"classifier:section_update"}; do not add narrative mutations.',
            'Single belief fact: user="Sam uses the blue folder for homework papers" -> emit exactly one beliefs_active.add_fact, not separate paraphrases for Sam and the blue folder.',
            'Durable shorthand definition: user="When I say blue bag, I mean the diaper bag by the garage door" -> section=beliefs_active operation=add_fact data={"subject":"blue bag","predicate":"means","obj":"diaper bag by the garage door","confidence":1.0,"source":"classifier:section_update"}. Do not emit scoreboard.add_referent.',
            'Conversation-local referent: user="For the next question, this form means the field trip permission slip" -> section=scoreboard operation=add_referent data={"text":"this form","entity_id":"field-trip-permission-slip","entity_type":"form","salience":0.9}. Do not emit a belief definition.',
            'Scoreboard referent: user="Put that bottle in the blue lunch bag" assistant="Okay." -> section=scoreboard operation=add_referent data={"text":"that bottle","entity_id":"bottle-blue-lunch-bag","entity_type":"object","salience":0.9}. Do not emit a belief.',
            'Scoreboard QUD: assistant="Do you want pickup before or after piano?" -> section=scoreboard operation=push_question data={"text":"Do you want pickup before or after piano?","asked_by":"assistant","priority":2}.',
            'Tracking QUD: user="Can you help me track which school forms are still due?" -> section=scoreboard operation=push_question data={"text":"Which school forms are still due?","asked_by":"user","priority":2}. Do not emit clarifications.request.',
            'Scoreboard topic: user="Let us focus on weekend packing for a minute" -> section=scoreboard operation=push_topic data={"name":"weekend packing","salience":0.8,"is_primary":true}. Do not create a narrative thread.',
            'Named topic switch: user="Switch the conversation to the school conference plan" -> section=scoreboard operation=push_topic data={"name":"school conference plan","salience":0.9,"is_primary":true}. Do not emit narrative_active.update_thread.',
            'Clarification request: assistant="Which Emma should I add to the pickup reminder?" -> section=clarifications operation=request data={"agent_id":"front","question":"Which Emma should I add to the pickup reminder?","priority":2,"related_entity":"Emma","related_intent":"pickup reminder","timeout_ms":0,"blocking":true}.',
            'Hidden clarification request: user="Schedule the doctor appointment after school" assistant="Acknowledged." -> section=clarifications operation=request data={"agent_id":"section_update_classifier","question":"Which doctor appointment should be scheduled after school?","priority":2,"related_entity":"doctor appointment","related_intent":"schedule_appointment","timeout_ms":0,"blocking":true}. This is not scoreboard.push_question.',
            'Reminder clarification: user="Remind me about the forms later" -> section=clarifications operation=request data={"agent_id":"section_update_classifier","question":"When should the reminder about the forms happen?","priority":1,"related_entity":"forms reminder","related_intent":"set_reminder","timeout_ms":0,"blocking":true}. This is not scoreboard.add_referent.',
            'Dropoff clarification: user="Drop him off at the usual place after tutoring" -> section=clarifications operation=request data={"agent_id":"section_update_classifier","question":"Who should be dropped off, and what is the usual place after tutoring?","priority":2,"related_entity":"dropoff","related_intent":"arrange_dropoff","timeout_ms":0,"blocking":true}. This is not scoreboard.add_referent.',
            'Clarification answer requires exact id: if snapshot has pending clarification id="clar-123" asking "Which uniform?" and user="The blue uniform" -> section=clarifications operation=answer data={"clarification_id":"clar-123","answer":"The blue uniform"}. If no exact pending id is present, do not emit answer.',
            'Affect update: user="I am overwhelmed by all these permission slips" -> section=affective_now operation=update data={"emotion":"overwhelmed","intensity":0.8,"valence":-0.6,"arousal":0.7,"dominance":0.2,"confidence":0.9,"source":"classifier:section_update"}. Do not emit a belief.',
            'Trust positive: user="Perfect, you got this" after a correct assistant plan -> section=trust_level operation=update data={"delta":0.05,"confidence":0.8,"signal":"explicit_confidence","stance":"steady","reason":"User expressed confidence in K1 handling the plan.","source":"classifier:section_update"}.',
            'Trust autonomy calibration: user="You do not need to ask me every tiny thing, just use your judgment" -> section=trust_level operation=update data={"delta":0.04,"confidence":0.85,"signal":"reduce_overclarification","stance":"trusted_autonomy","reason":"User asked K1 to reduce unnecessary clarification friction and use judgment.","source":"classifier:section_update"}.',
            'Trust repair: user="No, that is not what I meant, do not assume that" -> section=trust_level operation=update data={"delta":-0.08,"confidence":0.9,"signal":"correction_after_misread","stance":"repairing","reason":"User corrected K1 and asked it not to assume.","source":"classifier:section_update"}.',
            'Narrative create: user="Let us start planning the weekend trip" -> section=narrative_active operation=create_thread data={"title":"Weekend trip planning","goal":"Plan the family weekend trip","related_entities":["family"],"related_intents":["trip planning"],"auto_switch":true}.',
            'Close acknowledgement: user="Thanks, that is all for pickup" assistant="You got it." -> apply_timing=no_op, mutations=[]. Do not write "pickup discussion closed", "user is done with pickup", or "pickup arrangements are sorted" as beliefs.',
            "Forbidden/meta question: user asks what policy, memory layer, tool, model, kernel state, or system capability is being used -> no_op unless the completed turn contains an allowed cognitive update.",
            'Capability/live-state question: user="Can you check whether the family calendar has anything tomorrow?" -> apply_timing=no_op, mutations=[]. Do not emit clarifications.request.',
            'Reminder status question: user="Do we already have a reminder for trash night?" -> apply_timing=no_op, mutations=[]. Do not emit scoreboard.push_question.',
            'Transcript/artifact read: user="Can you show the exact transcript line I just sent?" or "What artifact did the last task produce?" -> apply_timing=no_op, mutations=[]. Do not emit clarifications.request.',
            'Meta/archive reads: user="Which internal policy says what you are allowed to write?" or "What is in the warm beliefs archive?" -> apply_timing=no_op, mutations=[]. Do not emit clarifications.request.',
            'Durable correction choice: user="Pack the red lunchbox for Mira, not the yellow one" -> section=beliefs_active operation=add_fact data={"subject":"Mira\'s lunchbox","predicate":"should_be","obj":"red lunchbox","confidence":1.0,"source":"classifier:section_update"}. Do not emit scoreboard.add_referent.',
            'Ambiguous referent: user="tell her I will be late" with no resolved her in the snapshot -> no_op/rejected candidate, not a belief and not a fabricated referent.',
            'Valid update_confidence only with exact id: data={"id":"fact-123","confidence":0.2}. If fact-123 is not in the snapshot, do not emit this operation.',
            "",
            "QUALITY BAR",
            "False writes are worse than missed noncritical writes.",
            "A plausible sentence is not enough; the payload must be valid for the target section's apply path.",
            "When uncertain, emit no_op or rejected_candidates. Never fabricate ids, sections, operations, task truth, live records, or thread lifecycle.",
        ]
    )


def build_section_update_tool_schema() -> ToolSchema:
    """Build the single batch-output schema used by the classifier adapter."""

    return ToolSchema(
        name=SECTION_UPDATE_BATCH_TOOL_NAME,
        description="Submit one complete SectionUpdatePlan. Use apply_timing=no_op and mutations=[] for safe no-op.",
        parameters={
            "type": "object",
            "properties": {
                "turn_id": {"type": "string"},
                "apply_timing": {
                    "type": "string",
                    "enum": [item.value for item in ApplyTiming],
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "mutations": {
                    "type": "array",
                    "items": {
                        "anyOf": [
                            _mutation_schema(section, operation)
                            for section, operations in CLASSIFIER_OPERATION_REGISTRY.items()
                            for operation in operations
                        ]
                    },
                },
                "rejected_candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string"},
                            "operation": {"type": "string"},
                            "reason": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["section", "reason"],
                    },
                },
                "diagnostics": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            "required": ["turn_id", "apply_timing", "mutations", "rejected_candidates"],
        },
        actor="section_update_classifier",
        category="cognitive",
        side_effects=False,
    )


def _mutation_schema(section: str, operation: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "section": {"type": "string", "const": section},
            "operation": {"type": "string", "const": operation},
            "data": _data_schema(section, operation),
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reason": {"type": "string"},
            "source": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "commit_class": {
                "type": "string",
                "enum": [item.value for item in CommitClass],
            },
        },
        "required": ["section", "operation", "data", "confidence", "reason", "commit_class"],
        "additionalProperties": True,
    }


def _data_schema(section: str, operation: str) -> dict[str, Any]:
    if section == "beliefs_active" and operation == "add_fact":
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "obj": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "source": {"type": "string"},
            },
            "required": ["subject", "predicate", "obj", "confidence", "source"],
            "additionalProperties": False,
        }
    if section == "beliefs_active" and operation == "update_confidence":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["id", "confidence"],
            "additionalProperties": False,
        }
    if section == "scoreboard" and operation == "add_referent":
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "entity_id": {"type": "string"},
                "entity_type": {"type": "string"},
                "salience": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["text", "entity_id", "entity_type", "salience"],
            "additionalProperties": False,
        }
    if section == "scoreboard" and operation == "push_question":
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "asked_by": {"type": "string"},
                "priority": {"type": "integer"},
            },
            "required": ["text", "asked_by", "priority"],
            "additionalProperties": False,
        }
    if section == "scoreboard" and operation == "pop_question":
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    if section == "scoreboard" and operation == "push_topic":
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "salience": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "is_primary": {"type": "boolean"},
            },
            "required": ["name", "salience", "is_primary"],
            "additionalProperties": False,
        }
    if section == "scoreboard" and operation == "add_commitment":
        return {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "trigger_condition": {"type": "string"},
                "linked_entities": {"type": "array", "items": {"type": "string"}},
                "linked_content_summary": {"type": "string"},
            },
            "required": ["description", "trigger_condition"],
            "additionalProperties": False,
        }
    if section == "scoreboard" and operation in {"fulfill_commitment", "cancel_commitment"}:
        return {
            "type": "object",
            "properties": {"commitment_id": {"type": "string"}},
            "required": ["commitment_id"],
            "additionalProperties": False,
        }
    if section == "clarifications" and operation == "request":
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "question": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "action": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                },
                "priority": {"type": "integer"},
                "related_entity": {"type": "string"},
                "related_intent": {"type": "string"},
                "timeout_ms": {"type": "integer", "minimum": 0},
                "blocking": {"type": "boolean"},
            },
            "required": [
                "agent_id",
                "question",
                "priority",
                "related_entity",
                "related_intent",
                "timeout_ms",
                "blocking",
            ],
            "additionalProperties": False,
        }
    if section == "clarifications" and operation == "answer":
        return {
            "type": "object",
            "properties": {
                "clarification_id": {"type": "string"},
                "answer": {"type": "string"},
                "selected_option_id": {"type": "string"},
            },
            "required": ["clarification_id", "answer"],
            "additionalProperties": False,
        }
    if section == "affective_now" and operation == "update":
        return {
            "type": "object",
            "properties": {
                "emotion": {"type": "string"},
                "intensity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "valence": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                "arousal": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "dominance": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "source": {"type": "string"},
                "turn_number": {"type": "integer"},
            },
            "required": [
                "emotion",
                "intensity",
                "valence",
                "arousal",
                "dominance",
                "confidence",
                "source",
            ],
            "additionalProperties": False,
        }
    if section == "trust_level" and operation == "update":
        return {
            "type": "object",
            "properties": {
                "delta": {"type": "number", "minimum": -0.2, "maximum": 0.2},
                "trust_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "signal": {"type": "string"},
                "stance": {"type": "string"},
                "reason": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["confidence", "signal", "reason", "source"],
            "additionalProperties": False,
        }
    if section == "narrative_active" and operation == "create_thread":
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "turn_number": {"type": "integer"},
                "related_entities": {"type": "array", "items": {"type": "string"}},
                "related_intents": {"type": "array", "items": {"type": "string"}},
                "auto_switch": {"type": "boolean"},
            },
            "required": ["title"],
            "additionalProperties": False,
        }
    if section == "narrative_active" and operation in {
        "switch_to",
        "pause_thread",
        "resolve_thread",
        "archive_thread",
        "update_thread",
    }:
        properties: dict[str, Any] = {
            "thread_id": {"type": "string"},
            "turn_number": {"type": "integer"},
        }
        if operation == "update_thread":
            properties.update(
                {
                    "title": {"type": "string"},
                    "goal": {"type": "string"},
                    "context_summary": {"type": "string"},
                }
            )
        return {
            "type": "object",
            "properties": properties,
            "required": ["thread_id"],
            "additionalProperties": False,
        }
    return {"type": "object", "additionalProperties": True}

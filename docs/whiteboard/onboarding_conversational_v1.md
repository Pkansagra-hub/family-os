# Conversational Onboarding (Deferred V1)

> **Status:** Doc-only stub. No implementation. M10.E2.I3 records the
> shape of the V1 conversational onboarding flow so the typed L3
> writers and seed YAML schema (see [`scripts/onboarding_seed.py`](../../scripts/onboarding_seed.py)
> and [`examples/seeds/`](../../examples/seeds/)) remain forward-
> compatible.

## Goal

Replace the YAML-driven seed flow (M10.E2.I1) with a **guided
conversation** the Concierge runs the first time a household powers
up the device. The conversation collects exactly the same fields the
seed YAML carries -- `core` / `identity` / `pattern` -- and persists
them through the same typed L3 writers, so the resulting projection
state is byte-identical regardless of which path the household took.

## Why deferred

The conversational flow needs three things that don't exist yet:

1. **A back-channel tool** so the LLM can call typed L3 writers
   without going through the regular fabric verb path (which is
   gated by the conscience and would refuse on a fresh, empty
   household). Tracked separately under M11.
2. **A prompt-template repertoire** for elicitation phrasing
   (preferences, hobbies, goals, ...). Today's prompt builder is
   tuned for response generation, not interview flow.
3. **HIL confirmation** for each writer call so a misheard
   "I don't drink coffee" doesn't end up as a `dislikes` entry the
   actor never said. Reuses the M8 `ApprovalRequest` plumbing.

## Conversation skeleton

```
Concierge -> "Hi! I'm setting up your space. What should I call you?"
User      -> "Anand."
Concierge -> [calls write_core(display_name="Anand")]
Concierge -> "Got it. How do you like your day to feel? Any morning
             routines I should know about?"
User      -> "I walk for 20 minutes after coffee, weekdays."
Concierge -> [calls write_routines([RoutineRef(routine_id=..., ...)])]
Concierge -> "Anything I should never do without checking with you?"
User      -> "Don't book anything that costs more than $50."
Concierge -> [issues a constitution amendment proposal -- not a
             writer call -- because conscience changes need a
             guardian co-signature]
```

The Concierge keeps the conversation going until each L3 bucket is
either filled or explicitly skipped. At each step it MAY:

* Echo back what it just wrote (`"OK, I've set theme=dark."`).
* Surface a gentle correction prompt if the user contradicts an
  earlier answer (`"Earlier you said you don't drink coffee --
  should I drop that morning walk after coffee?"`).
* Snapshot progress so a dropped session resumes mid-flow.

## Schema invariance

The conversational flow MUST produce the same shape as
`apply_seed()` in `scripts/onboarding_seed.py`. Adding a new bucket
to the seed YAML therefore implicitly extends the conversational
script too -- no second source of truth.

## Open questions (V1.x)

- **Voice transcription QA.** How do we surface "the LLM heard X but
  the user said Y" without dumping raw ASR confidence into the prompt?
- **Constitution bootstrapping by conversation.** V1 ships a fixed
  bootstrap constitution. V1.x may let the household author its own
  conscience rules through the same elicitation flow, with the
  guardian co-signature gate still required.
- **Multi-actor onboarding in one session.** A guardian setting up
  the household for a child -- the child's seed must be tagged with
  the guardian's identity so future amendments inherit the right
  signing authority.

"""
Time-Aware Agent Patterns - Examples of how agents use SessionState time context

This demonstrates how specialized agents can leverage time context from SessionState
to make intelligent, time-aware decisions.

Key Insight: Every agent call should pass session.get_time_context() in the
task envelope so agents know the exact moment they're executing.
"""

import sys

sys.path.insert(0, str(__file__).split("examples")[0])

from l4_runtime.session_state.session_state import SessionState

# ==================== PATTERN 1: HealthcareAgent - Medication Tracking ====================


def healthcare_agent_example(session: SessionState) -> str:
    """
    HealthcareAgent uses time context to provide time-aware health advice.

    Key: Agents must know "when is now" to say "you took aspirin 2 hours ago"
    vs "you took aspirin last Tuesday".
    """
    # 1. Initialize time context (once per session)
    session.init_time_context(user_timezone="America/New_York")

    # 2. Add timestamped beliefs (as MemoryWriterAgent processes deltas)
    session.add_belief_with_timestamp(
        "medications_today",
        ["aspirin at 8am", "vitamin_d at noon"],
        context="healthcare_agent_monitoring",
    )

    # 3. When HealthcareAgent processes a query like "should I take more aspirin?"
    time_context = session.get_time_context()

    # Now agent can make time-aware decisions
    if time_context["is_business_hours"]:
        recommendation = "During work hours, consider taking a break before taking more medication"
    else:
        recommendation = "Good time to rest after taking medication"

    # 4. Check if medication info is fresh enough
    med_age = session.get_belief_age_seconds("medications_today")
    if med_age is None or med_age > 86400:  # Older than 24 hours
        recommendation += " (Note: medication history may be outdated, please refresh)"

    return f"""
    Healthcare Advice:
    - Current time: {time_context['current_time_utc']}
    - Day: {time_context['day_of_week']}
    - Hour: {time_context['hour_of_day']}:00 UTC
    - Business hours: {time_context['is_business_hours']}

    Recommendation: {recommendation}
    """


# ==================== PATTERN 2: FinanceAgent - Budget & Time-Aware Spending ====================


def finance_agent_example(session: SessionState) -> str:
    """
    FinanceAgent uses time context to provide contextual financial advice.

    Example: "You've spent 80% of budget" means different things on
    the 1st vs 25th of the month.
    """
    session.init_time_context()

    # Add time-stamped spending beliefs
    session.add_belief_with_timestamp(
        "recent_transactions",
        [
            {"amount": 45.50, "merchant": "Starbucks", "time_ago": "30 minutes"},
            {"amount": 120.00, "merchant": "Restaurant", "time_ago": "4 hours"},
            {"amount": 85.00, "merchant": "Gas", "time_ago": "1 day"},
        ],
        context="finance_sync",
    )

    time_context = session.get_time_context()

    # Make time-aware budget recommendations
    if time_context["is_peak_hours"]:  # 2pm-4pm
        advice = "Peak spending hours - consider waiting on non-essential purchases"
    elif time_context["is_weekend"]:
        advice = "Weekend spending detected - budget accordingly for full week"
    else:
        advice = "Good time for controlled spending"

    # Analyze recent vs older spending patterns
    fresh_beliefs = session.get_fresh_beliefs(max_age_seconds=3600)  # Last hour only
    if fresh_beliefs.get("recent_transactions"):
        advice += " - You've had spending activity in the last hour"

    return f"""
    Financial Analysis:
    - Current time: {time_context['current_time_utc']}
    - Is weekend: {time_context['is_weekend']}
    - Session active for: {time_context['session_duration_seconds']}s

    Advice: {advice}
    """


# ==================== PATTERN 3: ProactiveAgent - Trigger Scheduling ====================


def proactive_agent_example(session: SessionState) -> dict:
    """
    ProactiveAgent uses time context to schedule prospective triggers.

    Critical for: "Remind me to drink water every 4 hours" or
    "Alert me if no activity in 30 minutes"
    """
    session.init_time_context()

    time_context = session.get_time_context()
    now_epoch_ms = time_context["current_time_epoch_ms"]

    # Examples of prospective triggers ProactiveAgent creates
    triggers = {
        "water_reminder": {
            "fire_time_epoch_ms": now_epoch_ms + 14400000,  # 4 hours from now
            "message": "Time to drink water!",
            "recurrence": "every_4_hours",
            "created_at": time_context["current_time_utc"],
            "scheduled_for_hour": (time_context["hour_of_day"] + 4) % 24,
        },
        "inactivity_alert": {
            "fire_time_epoch_ms": now_epoch_ms + 1800000,  # 30 minutes from now
            "message": "You've been inactive for 30 minutes",
            "recurrence": "once",
            "created_at": time_context["current_time_utc"],
        },
        "off_hours_notification": {
            "fire_time_epoch_ms": None,  # Skip if off-hours
            "skip_if_off_hours": not time_context["is_business_hours"],
            "message": "Work day reminder",
            "created_at": time_context["current_time_utc"],
        },
    }

    return triggers


# ==================== PATTERN 4: ResearcherAgent - Time-Bounded Searches ====================


def researcher_agent_example(session: SessionState) -> dict:
    """
    ResearcherAgent uses time context to prioritize recent information.

    Example: "Recent restaurants" means within last 7 days, not from 2 years ago.
    """
    session.init_time_context()

    # Add a belief about recent search results
    session.add_belief_with_timestamp(
        "restaurant_search_results",
        [
            {"name": "Bella Italia", "rating": 4.8, "distance": "0.3 miles"},
            {"name": "Luigi's Trattoria", "rating": 4.5, "distance": "0.5 miles"},
        ],
        context="restaurant_search_service",
    )

    time_context = session.get_time_context()

    # Determine how fresh results need to be based on time of day
    if time_context["hour_of_day"] >= 17:  # Evening - meal planning time
        freshness_required_seconds = 3600  # Must be within 1 hour
        context_msg = "Evening search - prioritizing recent recommendations"
    else:
        freshness_required_seconds = 86400 * 7  # 7 days for general search
        context_msg = "General search - using broader time window"

    # Get beliefs that are fresh enough for this time of day
    fresh_results = session.get_fresh_beliefs(max_age_seconds=freshness_required_seconds)

    return {
        "search_type": "restaurant",
        "results": fresh_results.get("restaurant_search_results", []),
        "time_context": context_msg,
        "search_time": time_context["current_time_utc"],
        "is_mealtime": 11 <= time_context["hour_of_day"] <= 13
        or 17 <= time_context["hour_of_day"] <= 20,
    }


# ==================== PATTERN 5: Agent Task Envelope - Always Include Time Context ====================


def agent_task_envelope_pattern(session: SessionState) -> dict:
    """
    Best practice: Every task sent to an agent should include time context.

    This ensures all agents can make time-aware decisions.
    """
    time_context = session.get_time_context()

    task_envelope = {
        "task_id": "task_12345",
        "agent_type": "HealthcareAgent",
        "user_input": "How should I manage my medications today?",
        "cognitive_trace_id": session.cognitive_trace_id,
        # ✅ ALWAYS INCLUDE TIME CONTEXT
        "time_context": time_context,
        # ✅ PASS RELEVANT BELIEFS
        "beliefs": session.beliefs,
        # ✅ PREFERENCES (persona section)
        "user_preferences": session.persona,
        # Performance: Agent can trust time_context is at task creation time
        # No need to call datetime.utcnow() again (uses envelope value instead)
    }

    return task_envelope


# ==================== PATTERN 6: Temporal Freshness in Belief Retrieval ====================


def belief_freshness_pattern(session: SessionState) -> dict:
    """
    Use belief age to make intelligent retrieval decisions.

    Example: MemoryWriterAgent adds beliefs, agents read with freshness awareness.
    """
    session.init_time_context()

    # Add various beliefs with timestamps
    session.add_belief_with_timestamp("current_mood", "happy", context="nlp_sentiment")
    session.add_belief_with_timestamp("recent_exercise", "ran 5k", context="wearable_sync")
    session.add_belief_with_timestamp("medications_today", ["aspirin"], context="health_import")

    # Later, agents can check freshness
    result = {
        "mood": {
            "value": session.get_belief_value("current_mood"),
            "age_seconds": session.get_belief_age_seconds("current_mood"),
            "is_fresh": session.get_belief_age_seconds("current_mood") < 300,  # < 5 min
        },
        "exercise": {
            "value": session.get_belief_value("recent_exercise"),
            "age_seconds": session.get_belief_age_seconds("recent_exercise"),
            "is_fresh": session.get_belief_age_seconds("recent_exercise") < 3600,  # < 1 hour
        },
        "medications": {
            "value": session.get_belief_value("medications_today"),
            "age_seconds": session.get_belief_age_seconds("medications_today"),
            "is_fresh": session.get_belief_age_seconds("medications_today") < 86400,  # < 24 hours
        },
    }

    return result


# ==================== PATTERN 7: Time-Based Agent Selection ====================


def time_based_agent_selection(session: SessionState) -> str:
    """
    Route to different agents based on time of day.

    Example: Route to FinanceAgent during business hours, HealthcareAgent off-hours.
    """
    time_context = session.get_time_context()

    if time_context["is_business_hours"]:
        return "FinanceAgent"  # Business hours: handle finance/work queries
    elif time_context["is_peak_hours"]:
        return "HealthcareAgent"  # Afternoon peak: wellness check-in
    elif time_context["is_weekend"]:
        return "ResearcherAgent"  # Weekends: exploration/research
    else:
        return "ProactiveAgent"  # Off-hours: reminders and notifications


# ==================== USAGE EXAMPLE ====================

if __name__ == "__main__":
    # Create session with time context
    session = SessionState(session_id="session_demo_001", user_id="user_abc123")

    print("=" * 60)
    print("TIME-AWARE AGENT PATTERNS DEMO")
    print("=" * 60)

    # 1. Healthcare example
    print("\n1. HEALTHCARE AGENT:")
    print(healthcare_agent_example(session))

    # 2. Finance example
    print("\n2. FINANCE AGENT:")
    print(finance_agent_example(session))

    # 3. Proactive example
    print("\n3. PROACTIVE AGENT (Triggers):")
    triggers = proactive_agent_example(session)
    for trigger_name, trigger_data in triggers.items():
        print(f"  - {trigger_name}: {trigger_data}")

    # 4. Researcher example
    print("\n4. RESEARCHER AGENT:")
    research = researcher_agent_example(session)
    for key, value in research.items():
        print(f"  {key}: {value}")

    # 5. Task envelope pattern
    print("\n5. TASK ENVELOPE WITH TIME CONTEXT:")
    envelope = agent_task_envelope_pattern(session)
    print(f"  Agent: {envelope['agent_type']}")
    print(f"  Time context included: {bool(envelope.get('time_context'))}")
    print(f"  Current hour (UTC): {envelope['time_context']['hour_of_day']}")
    print(f"  Is business hours: {envelope['time_context']['is_business_hours']}")

    # 6. Belief freshness
    print("\n6. BELIEF FRESHNESS TRACKING:")
    freshness = belief_freshness_pattern(session)
    for belief_name, belief_data in freshness.items():
        print(f"  {belief_name}:")
        print(f"    Value: {belief_data['value']}")
        print(f"    Age: {belief_data['age_seconds']}s")
        print(f"    Fresh: {belief_data['is_fresh']}")

    # 7. Time-based routing
    print("\n7. TIME-BASED AGENT ROUTING:")
    agent = time_based_agent_selection(session)
    time_context = session.get_time_context()
    print(f"  Current hour: {time_context['hour_of_day']}:00 UTC")
    print(f"  Recommended agent: {agent}")

    print("\n" + "=" * 60)
    print("✅ Time-aware agents ready for deployment!")
    print("=" * 60)

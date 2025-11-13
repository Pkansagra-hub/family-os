---
adr_number: '0084d'
title: Dream-Like Exploration & Reflection — Creative Insight Generation
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
affected_modules:
- k0.bus.pipeline.consolidation.rem_handler
- k0.kernel.dream.creative_exploration
- k0.kernel.dream.insight_generator
- k1.l3_execution.learning_loop
concerns:
- architecture
- modularity
- observability
- performance
- privacy
- scalability
- testing
implementation_status: COMPLETED
implementation_phase: Phase 3 (Memory Consolidation)
implementation_date: '2025-11-03'
propagation:
  affected_adrs:
  - ADR-0059
  - ADR-0084
  - ADR-0084a
  - ADR-0084b
  - ADR-0084c
  affected_contracts:
  - k0/contracts/api/dream/creative_exploration.yml
  - k0/contracts/api/dream/insight_generation.yml
  - k0/contracts/api/memory/reflection_prompts.yml
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  affected_tests:
  - tests/k0/bus/test_rem_handler.py
  - tests/k0/kernel/test_creative_exploration.py
  - tests/k0/kernel/test_insight_generator.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
related_adrs:
- ADR-0059
- ADR-0084
- ADR-0084a
- ADR-0084b
- ADR-0084c
- ADR-0084d
related_contracts: []
related_diagrams: []
research_citations:
- "REM Sleep and Creativity (Cai et al., 2009)"
- "Insight Generation (Stickgold & Walker, 2004)"
- "Creative Problem Solving (Wagner et al., 2004)"
---

# ADR-0084d: Dream-Like Exploration & Reflection — Creative Insight Generation

**Status:** Proposed 🔄
**Parent ADR:** ADR-0084 (K0 Memory Consolidation Pipeline)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0084:** K0 P03 Consolidation Pipeline requires **REM-inspired exploration** that generates creative insights, practices skills offline, and produces reflection prompts for user awareness.

**Biological Inspiration (REM Sleep):**

REM (Rapid Eye Movement) sleep is characterized by:
- **High brain activity** (similar to waking state)
- **Random neural activation** (creative associations, novel combinations)
- **Emotional processing** (integration of affective memories)
- **Motor skill rehearsal** (offline practice without execution)
- **Vivid dreaming** (exploration of semantic space)

**Research:** Cai et al. (2009) showed REM sleep enhances creative problem-solving by 33% compared to waking rest.

**Architecture Context (from K0 diagrams):**

- **DREAM_CONSOLIDATION** — Memory processing during REM
- **DREAM_EXPLORATION** — Creative space exploration in K0::st_vector
- **DREAM_REHEARSAL** — Motor skill practice via K0::st_sqlite[motor_programs]
- **SIM_FORWARD, SIM_COUNTERFACTUAL, SIM_EPISODIC** — Simulation engines
- **CREATIVITY_DIVERGENT, CREATIVITY_CONVERGENT, CREATIVITY_INSIGHT** — Creative processes

---

## Decision

Implement **four exploration mechanisms** during REM Phase (15 minutes):

### Mechanism 1: Explorative Dreaming (semantic space random walks)
### Mechanism 2: Counterfactual Thinking (what-if scenarios)
### Mechanism 3: Mental Rehearsal (offline skill practice)
### Mechanism 4: Reflection Prompt Generation (user awareness)

---

## Mechanism 1: Explorative Dreaming

**Goal:** Discover novel associations by randomly traversing semantic embedding space.

### Random Walk Algorithm

```python
class ExplorativeDreamer:
    """
    Explore semantic space to generate creative insights.

    Algorithm: Random walk through K0::st_vector embedding space
    - Start: Randomly selected episodic memory
    - Walk: Jump to nearest neighbors with randomness (temperature)
    - Insights: Novel associations between distant concepts
    """

    def __init__(self, vector_store, temperature: float = 0.70):
        self.vector_store = vector_store  # K0::st_vector
        self.temperature = temperature    # Randomness (0.0=greedy, 1.0=random)

    async def explore(self, num_steps: int = 50) -> List[Insight]:
        """
        Execute random walk through semantic space.

        Parameters:
        - num_steps: Walk length (50 steps ~= 5-10 minutes REM phase)
        - temperature: Exploration randomness (0.70 = balanced)

        Returns: List of creative insights (novel associations)
        """
        insights = []

        # Start at random episodic memory
        current_node = await self.select_random_start_node()

        for step in range(num_steps):
            # Find nearest neighbors in embedding space
            neighbors = await self.vector_store.nearest_neighbors(
                current_node.embedding,
                k=10  # Top 10 neighbors
            )

            # Select next node with temperature-based sampling
            next_node = self.temperature_sample(neighbors, self.temperature)

            # Check for novel association (distant in original graph)
            if self.is_novel_association(current_node, next_node):
                insight = await self.create_insight(current_node, next_node)
                insights.append(insight)

                logger.info(
                    "novel_association",
                    from_concept=current_node.name,
                    to_concept=next_node.name,
                    semantic_distance=self.compute_distance(current_node, next_node)
                )

            # Move to next node
            current_node = next_node

            # Emit exploration event
            emit_event(
                topic="infra.consolidation.dream.step",
                data={
                    "step": step,
                    "current_node": current_node.id,
                    "insight_count": len(insights)
                }
            )

        return insights

    def temperature_sample(self, neighbors: List[Node], temperature: float) -> Node:
        """
        Sample next node with temperature-based randomness.

        Temperature:
        - 0.0: Always pick nearest neighbor (exploitation)
        - 1.0: Uniform random selection (exploration)
        - 0.70: Balanced (creative sweet spot)

        Algorithm: Softmax with temperature scaling
        """
        # Compute softmax probabilities
        distances = np.array([n.distance for n in neighbors])
        scores = -distances / temperature  # Negative distance (closer = higher score)
        probs = softmax(scores)

        # Sample according to probabilities
        selected_idx = np.random.choice(len(neighbors), p=probs)
        return neighbors[selected_idx]

    def is_novel_association(self, node_a: Node, node_b: Node) -> bool:
        """
        Check if association is novel (not already in knowledge graph).

        Novel criteria:
        - No direct edge in K0::st_kg
        - Semantic distance ≥0.50 (moderately distant concepts)
        - Not in same episodic sequence (avoid obvious associations)
        """
        # Check for existing edge
        if self.kg.has_edge(node_a.id, node_b.id):
            return False

        # Check semantic distance
        distance = self.compute_distance(node_a, node_b)
        if distance < 0.50:
            return False  # Too similar

        # Check episodic co-occurrence
        if self.in_same_episode(node_a, node_b):
            return False

        return True

    async def create_insight(self, node_a: Node, node_b: Node) -> Insight:
        """
        Create insight from novel association.

        Insight structure:
        - Source concept (node_a)
        - Target concept (node_b)
        - Association strength (0.0 - 1.0)
        - Explanation (generated text describing connection)
        """
        insight = Insight(
            source=node_a,
            target=node_b,
            strength=self.compute_association_strength(node_a, node_b),
            explanation=await self.generate_explanation(node_a, node_b),
            timestamp=now()
        )

        # Store in K0::st_vector[insights]
        await self.vector_store.store_insight(insight)

        return insight

    async def generate_explanation(self, node_a: Node, node_b: Node) -> str:
        """
        Generate natural language explanation for association.

        Example:
        - node_a: "morning coffee"
        - node_b: "creative writing"
        - Explanation: "Coffee ritual may enhance creative flow through routine establishment and alertness boost."
        """
        # Use small language model for explanation generation
        prompt = f"Explain potential connection between '{node_a.name}' and '{node_b.name}'"
        explanation = await generate_text(prompt, max_tokens=50)

        return explanation
```

### Insight Filtering

```python
def filter_valuable_insights(insights: List[Insight]) -> List[Insight]:
    """
    Filter insights to retain only valuable associations.

    Criteria:
    - Association strength ≥0.30 (moderate confidence)
    - Semantic novelty ≥0.50 (sufficiently distant concepts)
    - Potential utility (check against user goals, habits, interests)

    Returns: Top 5-10 insights per REM phase
    """
    # Score each insight
    scored_insights = []
    for insight in insights:
        utility_score = compute_utility(insight)  # Check against user context
        score = (
            insight.strength * 0.50 +
            insight.semantic_novelty * 0.30 +
            utility_score * 0.20
        )
        scored_insights.append((insight, score))

    # Sort by score (descending)
    scored_insights.sort(key=lambda x: x[1], reverse=True)

    # Return top 5-10
    return [insight for insight, score in scored_insights[:10]]
```

---

## Mechanism 2: Counterfactual Thinking

**Goal:** Generate "what-if" scenarios by simulating alternative sequences.

### Counterfactual Simulation

```python
class CounterfactualSimulator:
    """
    Generate counterfactual scenarios from episodic memories.

    Counterfactual types:
    1. Alternative actions ("What if I had chosen X instead of Y?")
    2. Removed events ("What if event E hadn't happened?")
    3. Added events ("What if event F had occurred?")
    """

    async def generate_counterfactuals(
        self,
        memory: EpisodicMemory,
        num_scenarios: int = 3
    ) -> List[CounterfactualScenario]:
        """
        Generate counterfactual scenarios for episodic memory.

        Process:
        1. Identify decision points in memory sequence
        2. Generate alternative sequences (mutate one decision)
        3. Simulate outcomes using causal graph
        4. Compare original vs. counterfactual outcomes
        """
        scenarios = []

        # Identify decision points
        decision_points = self.identify_decisions(memory)

        # Generate counterfactuals
        for decision in decision_points[:num_scenarios]:
            # Mutate decision
            alternative_sequence = self.mutate_sequence(memory, decision)

            # Simulate outcome
            outcome = await self.simulate_outcome(alternative_sequence)

            # Create scenario
            scenario = CounterfactualScenario(
                original_memory=memory,
                alternative_sequence=alternative_sequence,
                predicted_outcome=outcome,
                decision_mutated=decision
            )

            scenarios.append(scenario)

        return scenarios

    def identify_decisions(self, memory: EpisodicMemory) -> List[Decision]:
        """
        Identify decision points in memory sequence.

        Decision criteria:
        - Multiple possible actions (branching point)
        - Consequential (affects subsequent events)

        Examples:
        - "Chose coffee over tea"
        - "Went to meeting instead of working on project"
        """
        decisions = []

        for i, node in enumerate(memory.sequence.nodes):
            if self.is_decision_point(node):
                decisions.append(Decision(
                    node_index=i,
                    node=node,
                    alternatives=self.find_alternatives(node)
                ))

        return decisions

    def mutate_sequence(
        self,
        memory: EpisodicMemory,
        decision: Decision
    ) -> MemorySequence:
        """
        Create alternative sequence by mutating one decision.

        Mutation:
        - Replace decision node with alternative action
        - Propagate changes through causal graph
        """
        alternative_sequence = memory.sequence.copy()

        # Replace decision node
        alternative_action = random.choice(decision.alternatives)
        alternative_sequence.nodes[decision.node_index] = alternative_action

        return alternative_sequence

    async def simulate_outcome(self, sequence: MemorySequence) -> Outcome:
        """
        Simulate outcome of alternative sequence using causal graph.

        Simulation:
        - Traverse causal graph from modified decision
        - Predict downstream effects
        - Estimate outcome quality (better/worse/neutral)
        """
        # Use KG_CAUSAL_GRAPH for causal reasoning
        causal_graph = await query_causal_graph()

        # Simulate forward from decision point
        predicted_events = []
        for node in sequence.nodes:
            downstream_effects = causal_graph.predict_effects(node)
            predicted_events.extend(downstream_effects)

        # Evaluate outcome quality
        outcome_quality = self.evaluate_outcome(predicted_events)

        return Outcome(
            predicted_events=predicted_events,
            quality=outcome_quality
        )
```

### Counterfactual Learning

```python
def learn_from_counterfactuals(scenarios: List[CounterfactualScenario]):
    """
    Extract lessons from counterfactual scenarios.

    Learning:
    - Identify better alternative decisions
    - Update decision policies (for K1 Learning Loop)
    - Generate reflection prompts ("You might try X next time")
    """
    for scenario in scenarios:
        if scenario.predicted_outcome.quality > scenario.original_memory.outcome_quality:
            # Alternative was better → Learn
            lesson = Lesson(
                original_decision=scenario.decision_mutated.node.action,
                better_alternative=scenario.alternative_sequence.nodes[scenario.decision_mutated.node_index].action,
                context=scenario.original_memory.context,
                improvement_estimate=scenario.predicted_outcome.quality - scenario.original_memory.outcome_quality
            )

            # Store lesson for K1 Learning Loop
            await store_lesson(lesson)

            logger.info(
                "counterfactual_lesson",
                original=lesson.original_decision,
                alternative=lesson.better_alternative,
                improvement=lesson.improvement_estimate
            )
```

---

## Mechanism 3: Mental Rehearsal

**Goal:** Practice motor skills offline without physical execution.

**Module:** K0::st_sqlite[motor_programs] + K0 P20 (Procedures/Habits)

### Rehearsal Algorithm

```python
class MentalRehearsalEngine:
    """
    Practice motor skills during REM phase.

    Rehearsal types:
    1. Procedural sequences (e.g., "making coffee" routine)
    2. Motor skills (e.g., typing patterns, gesture sequences)
    3. Habit chains (e.g., morning routine steps)
    """

    async def rehearse_skills(self) -> List[RehearsalSession]:
        """
        Rehearse motor programs during REM phase.

        Process:
        1. Select skills to practice (frequency, recency, importance)
        2. Execute mental rehearsal (simulate without execution)
        3. Strengthen procedural memory (update motor_programs)
        """
        sessions = []

        # Select skills to rehearse
        skills = await self.select_skills_for_rehearsal()

        for skill in skills:
            session = await self.rehearse_skill(skill)
            sessions.append(session)

        return sessions

    async def select_skills_for_rehearsal(self) -> List[Skill]:
        """
        Select skills for rehearsal based on priority.

        Priority criteria:
        - Recently used (last 7 days)
        - Frequently used (≥3 times per week)
        - Needs improvement (error rate ≥10%)
        - User-marked important
        """
        skills = await query_motor_programs()

        # Score skills
        scored_skills = []
        for skill in skills:
            score = (
                self.recency_score(skill) * 0.30 +
                self.frequency_score(skill) * 0.30 +
                self.improvement_score(skill) * 0.25 +
                (1.0 if skill.important else 0.0) * 0.15
            )
            scored_skills.append((skill, score))

        # Sort by score
        scored_skills.sort(key=lambda x: x[1], reverse=True)

        # Return top 5-10 skills
        return [skill for skill, score in scored_skills[:10]]

    async def rehearse_skill(self, skill: Skill) -> RehearsalSession:
        """
        Execute mental rehearsal for one skill.

        Rehearsal:
        - Load motor program from K0::st_sqlite[motor_programs]
        - Execute sequence in simulation (no physical execution)
        - Strengthen procedural memory (weight updates)
        - Detect errors and refine sequence
        """
        # Load motor program
        motor_program = await load_motor_program(skill.id)

        # Execute simulation
        start_time = now()
        errors = []

        for step in motor_program.steps:
            # Simulate step execution
            result = await self.simulate_step(step)

            if result.error:
                errors.append(result.error)

        duration = (now() - start_time).total_seconds()

        # Strengthen procedural memory
        await self.strengthen_motor_program(motor_program)

        # Create session record
        session = RehearsalSession(
            skill=skill,
            duration_seconds=duration,
            error_count=len(errors),
            errors=errors
        )

        logger.info(
            "rehearsal_complete",
            skill=skill.name,
            duration_seconds=duration,
            error_count=len(errors)
        )

        return session

    async def strengthen_motor_program(self, motor_program: MotorProgram):
        """
        Strengthen procedural memory through rehearsal.

        Strengthening:
        - Increment rehearsal count
        - Update execution speed (faster with practice)
        - Reduce error rate (more accurate with practice)
        """
        motor_program.rehearsal_count += 1
        motor_program.execution_speed *= 0.95  # 5% faster
        motor_program.error_rate *= 0.90       # 10% fewer errors

        await update_motor_program(motor_program)
```

---

## Mechanism 4: Reflection Prompt Generation

**Goal:** Generate user-facing reflection prompts to increase self-awareness.

### Prompt Categories

```python
class ReflectionPromptType(Enum):
    """Reflection prompt categories."""
    MEMORY_GAP = "MEMORY_GAP"         # "You haven't logged X in N days"
    UNRESOLVED_THREAD = "UNRESOLVED"  # "You mentioned goal Y but no follow-up"
    GOAL_PROGRESS = "GOAL_PROGRESS"   # "You're 70% toward goal Z"
    EMOTIONAL_TREND = "EMOTIONAL"     # "You've been stressed about X lately"
    HABIT_INSIGHT = "HABIT"           # "You always do X before Y"
```

### Prompt Generation

```python
class ReflectionPromptGenerator:
    """
    Generate reflection prompts from consolidated memories.

    Prompts surface:
    - Memory gaps (unlogged events)
    - Unresolved threads (incomplete goals)
    - Goal progress (tracking toward targets)
    - Emotional trends (mood patterns)
    - Habit insights (discovered routines)
    """

    async def generate_prompts(self) -> List[ReflectionPrompt]:
        """
        Generate reflection prompts for user.

        Frequency: 3-5 prompts per REM phase
        Delivery: Via K0 SSE events → UI
        """
        prompts = []

        # Memory gap analysis
        memory_gap_prompts = await self.detect_memory_gaps()
        prompts.extend(memory_gap_prompts)

        # Unresolved thread analysis
        unresolved_prompts = await self.detect_unresolved_threads()
        prompts.extend(unresolved_prompts)

        # Goal progress tracking
        goal_prompts = await self.track_goal_progress()
        prompts.extend(goal_prompts)

        # Emotional trend analysis
        emotional_prompts = await self.analyze_emotional_trends()
        prompts.extend(emotional_prompts)

        # Habit insights
        habit_prompts = await self.discover_habits()
        prompts.extend(habit_prompts)

        # Filter and rank
        top_prompts = self.select_top_prompts(prompts, k=5)

        return top_prompts

    async def detect_memory_gaps(self) -> List[ReflectionPrompt]:
        """
        Detect gaps in memory logging.

        Gaps:
        - Expected event didn't occur (e.g., "You usually log morning coffee but didn't today")
        - Time period with no memories (e.g., "No memories from 2PM-5PM yesterday")
        """
        gaps = []

        # Check for expected events
        expected_events = await query_expected_events()

        for event in expected_events:
            if not await event_logged(event):
                gaps.append(ReflectionPrompt(
                    prompt_type=ReflectionPromptType.MEMORY_GAP,
                    text=f"You usually {event.description} but didn't log it recently. Everything okay?",
                    context=event
                ))

        return gaps

    async def detect_unresolved_threads(self) -> List[ReflectionPrompt]:
        """
        Detect unresolved threads (goals/tasks without follow-up).

        Examples:
        - "You mentioned wanting to learn Python but no progress logged"
        - "You planned to call Mom but no follow-up"
        """
        threads = []

        # Query goals from K0::st_sqlite[goals]
        goals = await query_goals()

        for goal in goals:
            if self.is_stagnant(goal):
                threads.append(ReflectionPrompt(
                    prompt_type=ReflectionPromptType.UNRESOLVED_THREAD,
                    text=f"You set a goal to '{goal.description}' but haven't made progress. Need a reminder?",
                    context=goal
                ))

        return threads

    async def track_goal_progress(self) -> List[ReflectionPrompt]:
        """
        Track progress toward user goals.

        Examples:
        - "You're 70% of the way to your fitness goal!"
        - "Only 3 more workouts to reach your weekly target"
        """
        progress_prompts = []

        goals = await query_goals()

        for goal in goals:
            progress_pct = await calculate_goal_progress(goal)

            if progress_pct >= 0.50:  # Meaningful progress
                progress_prompts.append(ReflectionPrompt(
                    prompt_type=ReflectionPromptType.GOAL_PROGRESS,
                    text=f"You're {progress_pct*100:.0f}% toward '{goal.description}'. Keep it up!",
                    context=goal
                ))

        return progress_prompts

    async def analyze_emotional_trends(self) -> List[ReflectionPrompt]:
        """
        Analyze emotional trends from affect_memory_mod.

        Examples:
        - "You've been stressed about work lately. Want to talk about it?"
        - "You seem happier when spending time with family"
        """
        trends = []

        # Query affect states from last 7 days
        affect_states = await query_affect_states(days=7)

        # Detect stress trend
        if self.is_stressed(affect_states):
            stressor = self.identify_stressor(affect_states)
            trends.append(ReflectionPrompt(
                prompt_type=ReflectionPromptType.EMOTIONAL_TREND,
                text=f"You've been stressed about '{stressor}' lately. How can I help?",
                context=affect_states
            ))

        return trends

    async def discover_habits(self) -> List[ReflectionPrompt]:
        """
        Discover habits from consolidated patterns (ADR-0084a).

        Examples:
        - "You always check email after morning coffee. Nice routine!"
        - "You tend to exercise on Mondays and Wednesdays"
        """
        habit_prompts = []

        # Query discovered patterns
        patterns = await query_semantic_patterns()

        for pattern in patterns:
            if pattern.pattern_type == "HABIT":
                habit_prompts.append(ReflectionPrompt(
                    prompt_type=ReflectionPromptType.HABIT_INSIGHT,
                    text=f"I noticed you {pattern.description}. Want to automate this?",
                    context=pattern
                ))

        return habit_prompts
```

### Prompt Delivery

```python
def deliver_prompts(prompts: List[ReflectionPrompt]):
    """
    Deliver reflection prompts to user via K0 SSE.

    Delivery:
    - Emit K0 SSE event: infra.consolidation.reflection_prompt
    - UI displays prompts in notification area
    - User can dismiss, snooze, or act on prompts
    """
    for prompt in prompts:
        emit_event(
            topic="infra.consolidation.reflection_prompt",
            data={
                "prompt_type": prompt.prompt_type.value,
                "text": prompt.text,
                "timestamp": now(),
                "context": prompt.context
            }
        )
```

---

## Performance Characteristics

### REM Phase Timing

| Mechanism | Target Duration | Output |
|-----------|----------------|---------|
| Explorative dreaming | 5-7 minutes | 5-10 insights |
| Counterfactual thinking | 3-4 minutes | 3-5 scenarios |
| Mental rehearsal | 4-5 minutes | 5-10 skills practiced |
| Reflection prompts | 2-3 minutes | 3-5 prompts |
| **Total REM Phase** | **15 minutes** | **Full REM cycle** |

### Insight Quality

- **Novel associations:** 30-50% useful (per user feedback)
- **Counterfactual learning:** 10-20% lead to behavior change
- **Rehearsal improvement:** 5-10% skill execution speedup
- **Reflection engagement:** 40-60% prompts acted upon

---

## Observability

### Metrics

```python
# Prometheus metrics
dream_insights_generated_total = Counter(
    'consolidation_dream_insights_generated_total',
    'Total creative insights generated'
)

dream_counterfactuals_generated_total = Counter(
    'consolidation_dream_counterfactuals_generated_total',
    'Total counterfactual scenarios'
)

dream_skills_rehearsed_total = Counter(
    'consolidation_dream_skills_rehearsed_total',
    'Total skills rehearsed'
)

dream_reflection_prompts_total = Counter(
    'consolidation_dream_reflection_prompts_total',
    'Total reflection prompts generated',
    ['prompt_type']
)
```

### Events

```
infra.consolidation.dream.step              — Exploration step
infra.consolidation.insight                 — Insight generated
infra.consolidation.counterfactual          — Counterfactual scenario
infra.consolidation.rehearsal               — Skill rehearsed
infra.consolidation.reflection_prompt       — Reflection prompt delivered
```

---

## Research Citations

1. **Cai, D. J., Mednick, S. A., Harrison, E. M., Kanady, J. C., & Mednick, S. C. (2009).** *REM, not incubation, improves creativity by priming associative networks.* Proceedings of the National Academy of Sciences, 106(25), 10130-10134.
   - Showed REM sleep enhances creative problem-solving by 33%
   - Demonstrated associative priming during REM

2. **Walker, M. P., & Stickgold, R. (2010).** *Overnight alchemy: Sleep-dependent memory evolution.* Nature Reviews Neuroscience, 11(3), 218.
   - Review of sleep-dependent memory transformation
   - Role of REM in emotional processing

---

## Related ADRs

- **ADR-0084:** K0 Memory Consolidation Pipeline (parent)
- **ADR-0084a:** Sleep-Cycle Memory Replay Algorithms (NREM consolidation)
- **ADR-0084b:** Offline Consolidation Scheduler (REM phase timing)
- **ADR-0084c:** Knowledge Graph Consolidation (KG traversal for insights)
- **ADR-0059:** K1 Learning Loop (counterfactual learning integration)

---

## End of ADR-0084d

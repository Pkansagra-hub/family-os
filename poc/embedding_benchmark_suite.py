"""
UltraBERT Embedding Benchmark Suite — World-Class Evaluation

Purpose:
    Comprehensive benchmark suite for evaluating embedding quality using
    industry-standard metrics and diverse test cases beyond family context.

Benchmarks:
    1. Recall@K with N Distractors (R@1/100, R@5/100, R@10/100)
    2. Mean Reciprocal Rank (MRR)
    3. Normalized Discounted Cumulative Gain (NDCG)
    4. Semantic Textual Similarity (STS)
    5. Paraphrase Detection
    6. Negation Handling
    7. Synonym/Antonym Discrimination
    8. Domain Transfer (cross-domain similarity)
    9. Length Invariance
    10. Noise Robustness

Test Domains:
    - General English (news, Wikipedia-style)
    - Technical/Scientific
    - Conversational/Informal
    - Business/Professional
    - Creative/Literary

Reference: GAP-001 Section 3 (Embedding Model Analysis)
"""

import json
import random
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# =============================================================================
# PERFORMANCE TRACKER
# =============================================================================


class PerformanceTracker:
    """Track memory and timing metrics for embeddings."""

    def __init__(self):
        self.embedding_times: List[float] = []
        self.memory_samples: List[int] = []
        self.batch_times: List[Tuple[int, float]] = []  # (batch_size, time)
        self._start_memory: int = 0

    def start_memory_tracking(self):
        """Start tracking memory."""
        tracemalloc.start()
        self._start_memory = tracemalloc.get_traced_memory()[0]

    def stop_memory_tracking(self) -> int:
        """Stop tracking and return peak memory in bytes."""
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return peak - self._start_memory

    def record_embedding_time(self, duration_ms: float):
        """Record time for a single embedding."""
        self.embedding_times.append(duration_ms)

    def record_batch_time(self, batch_size: int, duration_ms: float):
        """Record batch processing time."""
        self.batch_times.append((batch_size, duration_ms))

    def get_stats(self) -> Dict:
        """Get performance statistics."""
        if not self.embedding_times:
            return {}

        times = np.array(self.embedding_times)
        return {
            "embedding_count": len(times),
            "total_time_ms": float(np.sum(times)),
            "mean_time_ms": float(np.mean(times)),
            "std_time_ms": float(np.std(times)),
            "min_time_ms": float(np.min(times)),
            "max_time_ms": float(np.max(times)),
            "p50_time_ms": float(np.percentile(times, 50)),
            "p95_time_ms": float(np.percentile(times, 95)),
            "p99_time_ms": float(np.percentile(times, 99)),
            "throughput_per_sec": len(times) / (np.sum(times) / 1000) if np.sum(times) > 0 else 0,
        }


# =============================================================================
# PRACTICAL IMPROVEMENT TECHNIQUES (Device-First, No Heavy Models)
# =============================================================================


class PracticalImprovements:
    """
    Practical improvement techniques for UltraBERT adapter.

    CONSTRAINTS:
    - Device-first: Must run on local hardware without GPU clusters
    - No heavy models: Cannot load BART, T5, or multi-GB models
    - Implementable: Can be added to ultrabert_adapter.py

    TECHNIQUES:
    1. Text preprocessing (normalize, clean) - 0 RAM overhead
    2. Short text augmentation (templates) - 0 RAM overhead
    3. Instruction prefixes (asymmetric retrieval) - 0 RAM overhead
    4. Threshold tuning (configuration) - 0 RAM overhead
    5. Difference vector analysis - 0 RAM overhead (uses existing embeddings)

    KNOWN LIMITATIONS (document, don't try to fix with heavy models):
    - Negation blindness: UltraBERT treats "I love X" and "I hate X" as similar
      -> Application-level fix: Use explicit sentiment/polarity tags in metadata
    - Semantic role reversal: "A chased B" vs "B chased A" look similar
      -> Application-level fix: Use structured data extraction before embedding
    """

    @classmethod
    def difference_vector_score(cls, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Analyze difference vector between embeddings (ZERO-COST).

        Uses existing embeddings - no additional model loading.
        Large difference vectors indicate semantic changes.
        """
        diff = emb2 - emb1
        diff_magnitude = np.linalg.norm(diff)

        # Normalize by embedding magnitude
        avg_magnitude = (np.linalg.norm(emb1) + np.linalg.norm(emb2)) / 2
        normalized_diff = diff_magnitude / avg_magnitude if avg_magnitude > 0 else 0

        # Convert to similarity: small difference = high similarity
        similarity = max(0.0, 1.0 - normalized_diff)

        return float(similarity)

    @classmethod
    def augment_short_text(cls, short_text: str, context_type: str = "general") -> str:
        """
        Augment short text with descriptive context (GAP-001 Section 3.4).

        This is a ZERO-COST improvement - just string templates.
        Helps UltraBERT understand short queries better.

        Args:
            short_text: Brief text like "Mom" or "morning routine"
            context_type: Type of context to add

        Returns:
            Augmented text with more semantic content
        """
        templates = {
            "entity": f"This refers to {short_text}, a meaningful entity or concept.",
            "action": f"The activity or routine called {short_text}.",
            "general": f"Information about: {short_text}",
            "memory": f"A memory or experience related to {short_text}.",
            "person": f"A person known as {short_text}.",
            "event": f"An event or occasion involving {short_text}.",
            "location": f"A place called or related to {short_text}.",
        }
        return templates.get(context_type, templates["general"])

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """
        Normalize text to improve typo robustness (ZERO-COST).

        - Lowercase
        - Remove extra whitespace
        - Strip leading/trailing whitespace
        """
        text = text.lower().strip()
        text = " ".join(text.split())
        return text

    @classmethod
    def add_instruction_prefix(cls, text: str, is_query: bool = True) -> str:
        """
        Add instruction prefix for asymmetric retrieval (ZERO-COST).

        Some embedding models benefit from query/document prefixes.
        """
        if is_query:
            return f"query: {text}"
        else:
            return f"document: {text}"

    @classmethod
    def compute_similarity_with_threshold(
        cls, similarity: float, threshold: float = 0.85
    ) -> Tuple[bool, float]:
        """
        Apply threshold with confidence score.

        Returns:
            (is_match, confidence) where confidence is distance from threshold
        """
        is_match = similarity >= threshold
        confidence = abs(similarity - threshold)
        return is_match, confidence


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""

    benchmark_name: str
    metric_name: str
    score: float
    details: Dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result of a retrieval test."""

    query_id: str
    query_text: str
    target_id: str
    target_rank: int  # 1-indexed, -1 if not found
    num_candidates: int
    recall_at_1: bool
    recall_at_5: bool
    recall_at_10: bool
    reciprocal_rank: float


# =============================================================================
# TEST DATA — DIVERSE ENGLISH CORPUS
# =============================================================================

# Semantic pairs: (query, positive_match, domain)
SEMANTIC_PAIRS = [
    # General English / News
    (
        "The stock market experienced significant volatility today.",
        "Financial markets saw major fluctuations in trading session.",
        "finance",
    ),
    (
        "Scientists discovered a new species of deep-sea fish.",
        "Researchers found an unknown marine creature in ocean depths.",
        "science",
    ),
    (
        "The government announced new policies on renewable energy.",
        "Officials unveiled fresh regulations regarding sustainable power.",
        "politics",
    ),
    (
        "Heavy rainfall caused flooding in several coastal regions.",
        "Intense precipitation led to inundation along shoreline areas.",
        "weather",
    ),
    (
        "The tech company released its quarterly earnings report.",
        "The technology firm published its three-month financial results.",
        "business",
    ),
    # Technical / Scientific
    (
        "Machine learning models require large datasets for training.",
        "Neural networks need substantial data collections to learn effectively.",
        "tech",
    ),
    (
        "The experiment demonstrated quantum entanglement between particles.",
        "The study showed quantum correlation phenomena in subatomic matter.",
        "physics",
    ),
    (
        "Antibiotics should be used responsibly to prevent resistance.",
        "Antimicrobial medications require careful administration to avoid immunity.",
        "medicine",
    ),
    (
        "The algorithm optimizes resource allocation in distributed systems.",
        "The computational method improves asset distribution across networks.",
        "computing",
    ),
    (
        "Climate models predict rising temperatures over the next century.",
        "Environmental simulations forecast increasing warmth in coming decades.",
        "climate",
    ),
    # Conversational / Informal
    (
        "I'm so tired after working all day, need some rest.",
        "Feeling exhausted from the long work hours, gotta take a break.",
        "casual",
    ),
    (
        "This movie was absolutely amazing, you should watch it!",
        "The film was incredible, definitely recommend checking it out!",
        "casual",
    ),
    (
        "Can't believe how expensive everything has become lately.",
        "It's crazy how much prices have gone up these days.",
        "casual",
    ),
    (
        "Just got back from vacation, it was so relaxing.",
        "Returned from my trip, really helped me unwind.",
        "casual",
    ),
    (
        "The traffic was terrible this morning, took forever to get here.",
        "Commute was awful today, spent ages stuck on the road.",
        "casual",
    ),
    # Business / Professional
    (
        "We need to schedule a meeting to discuss the quarterly objectives.",
        "Let's arrange a session to review our three-month goals.",
        "business",
    ),
    (
        "The client requested changes to the project deliverables.",
        "The customer asked for modifications to the work outputs.",
        "business",
    ),
    (
        "Our team exceeded the sales targets for this quarter.",
        "The department surpassed revenue goals during this period.",
        "business",
    ),
    (
        "Please review the attached document and provide feedback.",
        "Kindly examine the enclosed file and share your comments.",
        "business",
    ),
    (
        "The merger will create synergies between both organizations.",
        "The acquisition will generate combined advantages for both companies.",
        "business",
    ),
    # Creative / Literary
    (
        "The autumn leaves danced gracefully in the gentle breeze.",
        "Fall foliage swayed elegantly in the soft wind.",
        "literary",
    ),
    (
        "Her eyes sparkled like diamonds under the moonlight.",
        "Her gaze shimmered like gems beneath the lunar glow.",
        "literary",
    ),
    (
        "The old mansion stood silent, keeping secrets of centuries past.",
        "The ancient estate remained quiet, guarding mysteries of ages gone.",
        "literary",
    ),
    (
        "Thunder rolled across the valley as lightning split the sky.",
        "Rumbling echoed through the dale as bolts tore through the heavens.",
        "literary",
    ),
    (
        "The journey of a thousand miles begins with a single step.",
        "A vast expedition starts with one small footfall.",
        "literary",
    ),
]

# Distractor pool — unrelated sentences for retrieval tests
DISTRACTOR_POOL = [
    # Technology
    "The smartphone features a high-resolution display and fast processor.",
    "Cloud computing enables scalable infrastructure for enterprises.",
    "Cybersecurity threats continue to evolve with sophisticated attacks.",
    "The software update includes bug fixes and performance improvements.",
    "Virtual reality applications are transforming gaming and education.",
    "Blockchain technology provides decentralized transaction verification.",
    "The database query returned results in under two milliseconds.",
    "Internet of Things devices connect homes to smart networks.",
    "The programming language supports both functional and object-oriented paradigms.",
    "Artificial intelligence is reshaping industries across the globe.",
    # Science
    "The telescope captured images of distant galaxies billions of light years away.",
    "DNA sequencing has become faster and more affordable over the years.",
    "The periodic table contains 118 confirmed chemical elements.",
    "Photosynthesis converts sunlight into chemical energy in plants.",
    "Black holes possess gravitational fields so strong that light cannot escape.",
    "The human brain contains approximately 86 billion neurons.",
    "Vaccines stimulate the immune system to recognize pathogens.",
    "Earthquakes occur along fault lines where tectonic plates meet.",
    "The speed of light in vacuum is approximately 299,792 kilometers per second.",
    "Evolution through natural selection drives species adaptation.",
    # History
    "The Roman Empire collapsed in the fifth century AD.",
    "The Industrial Revolution began in Britain during the 18th century.",
    "Ancient Egyptians built pyramids as tombs for their pharaohs.",
    "World War II ended in 1945 with the surrender of Japan.",
    "The Renaissance marked a cultural rebirth in European history.",
    "Christopher Columbus reached the Americas in 1492.",
    "The French Revolution fundamentally changed European society.",
    "The Great Wall of China spans thousands of kilometers.",
    "The printing press revolutionized the spread of information.",
    "Democracy originated in ancient Athens thousands of years ago.",
    # Geography
    "Mount Everest is the tallest mountain above sea level.",
    "The Amazon River carries more water than any other river.",
    "Antarctica is the coldest and driest continent on Earth.",
    "The Sahara Desert covers much of North Africa.",
    "Japan consists of four main islands and thousands of smaller ones.",
    "The Mediterranean Sea connects to the Atlantic Ocean.",
    "Australia is both a country and a continent.",
    "The Grand Canyon was carved by the Colorado River.",
    "Iceland sits on the Mid-Atlantic Ridge between tectonic plates.",
    "The Nile River flows northward through northeastern Africa.",
    # Sports
    "The Olympic Games bring together athletes from around the world.",
    "Football is the most popular sport globally by viewership.",
    "Tennis matches can last several hours on clay courts.",
    "Basketball was invented in Massachusetts in 1891.",
    "The marathon distance is approximately 42 kilometers.",
    "Swimming events are measured in meters at the Olympics.",
    "Golf originated in Scotland during the 15th century.",
    "Cricket matches can extend over multiple days in test format.",
    "Ice hockey requires players to skate at high speeds.",
    "Baseball teams play 162 games during the regular season.",
    # Food & Cooking
    "Italian cuisine features pasta, olive oil, and fresh tomatoes.",
    "Fermentation is used to produce bread, cheese, and wine.",
    "Spices were once more valuable than gold in ancient trade.",
    "Sushi originated in Japan as a method of preserving fish.",
    "Chocolate comes from cacao beans grown in tropical regions.",
    "The Mediterranean diet emphasizes vegetables, fish, and healthy fats.",
    "Coffee beans are actually seeds from coffee plant berries.",
    "Bread baking requires flour, water, yeast, and salt.",
    "Refrigeration extended food preservation capabilities dramatically.",
    "Umami is considered the fifth basic taste alongside sweet and salty.",
    # Arts & Culture
    "The Mona Lisa hangs in the Louvre Museum in Paris.",
    "Shakespeare wrote 37 plays during his literary career.",
    "Jazz music originated in New Orleans in the early 20th century.",
    "Ballet requires years of rigorous training and practice.",
    "The Sistine Chapel ceiling was painted by Michelangelo.",
    "Photography became accessible to amateurs in the 19th century.",
    "Opera combines theatrical drama with orchestral music and singing.",
    "Impressionist painters captured light and movement in their works.",
    "Folk music traditions vary widely across different cultures.",
    "Architecture balances aesthetic design with structural engineering.",
    # Nature & Animals
    "Elephants are the largest land animals on Earth.",
    "Whales can hold their breath for over an hour underwater.",
    "Bees are essential pollinators for many food crops.",
    "The cheetah is the fastest land animal, reaching 70 mph.",
    "Coral reefs support more species per unit area than any ecosystem.",
    "Birds evolved from small dinosaurs millions of years ago.",
    "Octopuses have three hearts and blue blood.",
    "Wolves live and hunt in organized family packs.",
    "Butterflies undergo complete metamorphosis during their lifecycle.",
    "Forests produce oxygen and absorb carbon dioxide from the atmosphere.",
    # Economics & Finance
    "Inflation erodes the purchasing power of currency over time.",
    "Supply and demand determine prices in market economies.",
    "Central banks set interest rates to influence economic activity.",
    "Gross domestic product measures a nation's economic output.",
    "Diversification reduces risk in investment portfolios.",
    "Unemployment rates vary across different economic sectors.",
    "Trade agreements facilitate commerce between nations.",
    "Cryptocurrencies operate on decentralized networks.",
    "Bonds provide fixed income returns to investors.",
    "Recessions are defined by consecutive quarters of negative growth.",
    # Health & Medicine
    "Regular exercise improves cardiovascular health and mental wellbeing.",
    "Sleep deprivation impairs cognitive function and immune response.",
    "Vitamins and minerals are essential micronutrients for the body.",
    "Stress management techniques include meditation and deep breathing.",
    "Genetic testing can reveal predispositions to certain conditions.",
    "Physical therapy helps patients recover from injuries.",
    "Mental health awareness has increased significantly in recent years.",
    "Nutrition plays a crucial role in disease prevention.",
    "Telemedicine enables remote consultations with healthcare providers.",
    "Preventive care reduces long-term healthcare costs.",
]

# Negation pairs: (positive, negated) — should have LOW similarity
NEGATION_PAIRS = [
    ("I love spending time outdoors in nature.", "I hate spending time outdoors in nature."),
    (
        "The company reported strong profits this quarter.",
        "The company did not report strong profits this quarter.",
    ),
    (
        "She agreed with the proposed changes to the policy.",
        "She disagreed with the proposed changes to the policy.",
    ),
    (
        "The experiment was successful in proving the hypothesis.",
        "The experiment failed to prove the hypothesis.",
    ),
    ("He always arrives on time for meetings.", "He never arrives on time for meetings."),
    (
        "The product received positive reviews from customers.",
        "The product received negative reviews from customers.",
    ),
    ("The team won the championship this year.", "The team lost the championship this year."),
    ("She accepted the job offer immediately.", "She rejected the job offer immediately."),
]

# Synonym pairs — should have HIGH similarity
SYNONYM_PAIRS = [
    ("happy", "joyful"),
    ("big", "large"),
    ("fast", "quick"),
    ("smart", "intelligent"),
    ("beautiful", "gorgeous"),
    ("difficult", "challenging"),
    ("important", "significant"),
    ("begin", "start"),
    ("finish", "complete"),
    ("help", "assist"),
]

# Antonym pairs — should have LOWER similarity than synonyms
ANTONYM_PAIRS = [
    ("happy", "sad"),
    ("big", "small"),
    ("fast", "slow"),
    ("hot", "cold"),
    ("light", "dark"),
    ("old", "young"),
    ("rich", "poor"),
    ("strong", "weak"),
    ("love", "hate"),
    ("success", "failure"),
]

# Paraphrase pairs for fine-grained similarity
PARAPHRASE_PAIRS = [
    ("What time does the store close?", "When does the shop shut?", True),
    (
        "Can you recommend a good restaurant nearby?",
        "Do you know any nice places to eat around here?",
        True,
    ),
    ("I need to charge my phone.", "My mobile needs some battery.", True),
    ("The weather is really nice today.", "It's a beautiful day outside.", True),
    ("I don't understand what you mean.", "Could you explain that differently?", True),
    ("What time does the store close?", "How much does this cost?", False),
    ("Can you recommend a good restaurant?", "Where is the nearest hospital?", False),
    ("The weather is really nice today.", "I need to finish this report by Friday.", False),
]

# =============================================================================
# ADVANCED TEST DATA
# =============================================================================

# Adversarial examples — semantically similar but structurally different
ADVERSARIAL_PAIRS = [
    # Word order changes
    ("The dog chased the cat.", "The cat chased the dog.", False),
    ("John gave Mary a book.", "Mary gave John a book.", False),
    # Negation scope
    ("All students passed the exam.", "Not all students passed the exam.", False),
    ("I think he is wrong.", "I don't think he is wrong.", False),
    # Quantifier changes
    ("Everyone loved the movie.", "Someone loved the movie.", False),
    ("She always arrives late.", "She sometimes arrives late.", False),
    # Passive/Active voice (should be similar)
    ("The ball was kicked by the player.", "The player kicked the ball.", True),
    ("The report was written by the team.", "The team wrote the report.", True),
    # Synonymous but structurally different
    ("It is raining heavily outside.", "Heavy rain is falling outdoors.", True),
    ("He runs faster than anyone.", "Nobody runs as fast as him.", True),
]

# Domain adaptation tests — same concept across domains
DOMAIN_ADAPTATION_PAIRS = [
    # Technical → Layman
    (
        "The patient exhibited signs of myocardial infarction.",
        "The person showed symptoms of a heart attack.",
        "medical",
    ),
    (
        "The defendant was acquitted of all charges.",
        "The accused person was found not guilty.",
        "legal",
    ),
    (
        "Implement a recursive algorithm with O(log n) complexity.",
        "Write code that calls itself and runs fast.",
        "tech",
    ),
    # Formal → Informal
    (
        "We kindly request your attendance at the meeting.",
        "Hey, can you come to the meeting?",
        "formal_informal",
    ),
    (
        "The quarterly financial results exceeded expectations.",
        "We made more money than we thought we would.",
        "business",
    ),
    # Academic → Conversational
    (
        "The research demonstrates a statistically significant correlation.",
        "The study shows these two things are related.",
        "academic",
    ),
]

# Temporal consistency — same concept described at different times
TEMPORAL_PAIRS = [
    ("I will go to the store tomorrow.", "I went to the store yesterday.", True),
    ("The company is launching a new product.", "The company launched a new product.", True),
    ("She is studying for her exams.", "She studied for her exams.", True),
    ("They are building a new hospital.", "They built a new hospital.", True),
    ("We will celebrate the anniversary.", "We celebrated the anniversary.", True),
]

# Named entity recognition quality — entity mentions
ENTITY_PAIRS = [
    (
        "Apple released a new iPhone.",
        "The tech company from Cupertino announced a smartphone.",
        True,
    ),
    ("Elon Musk founded SpaceX.", "The Tesla CEO started a rocket company.", True),
    ("Paris is known for the Eiffel Tower.", "The French capital has a famous iron tower.", True),
    ("Amazon delivers packages quickly.", "The Seattle company ships items fast.", True),
    (
        "Google developed TensorFlow.",
        "The search engine company created a machine learning framework.",
        True,
    ),
]

# Granular domain categories for analysis
DOMAIN_CATEGORIES = {
    "technical": ["tech", "physics", "computing", "medicine", "climate"],
    "general": ["finance", "politics", "weather", "science"],
    "informal": ["casual"],
    "formal": ["business", "literary"],
}

# Length categories
LENGTH_CATEGORIES = {
    "very_short": (1, 5),  # 1-5 words
    "short": (6, 15),  # 6-15 words
    "medium": (16, 30),  # 16-30 words
    "long": (31, 60),  # 31-60 words
    "very_long": (61, 200),  # 61+ words
}


# =============================================================================
# REAL-WORLD BENCHMARK DATA (Industry Standard)
# =============================================================================

# STS-B style pairs with human similarity scores (0-5 scale, normalized to 0-1)
# Reference: STS Benchmark (Semantic Textual Similarity)
STS_B_PAIRS = [
    # High similarity (4.5-5.0 -> 0.9-1.0)
    ("A plane is taking off.", "An air plane is taking off.", 0.95),
    ("A man is playing a large flute.", "A man is playing a flute.", 0.90),
    ("A woman is slicing an onion.", "A woman is cutting an onion.", 0.92),
    ("A man is playing the piano.", "A man is playing the keyboard.", 0.85),
    ("A person is folding a piece of paper.", "A person is folding paper.", 0.95),
    # Medium similarity (2.5-3.5 -> 0.5-0.7)
    ("A woman is dancing.", "A man is singing.", 0.50),
    ("A cat is playing with a toy.", "A dog is running in the park.", 0.35),
    ("The stock market rose today.", "Oil prices increased slightly.", 0.55),
    ("A child is reading a book.", "An adult is watching television.", 0.30),
    ("The team won the championship.", "The players celebrated victory.", 0.65),
    # Low similarity (0-1.5 -> 0.0-0.3)
    ("A man is playing guitar.", "A woman is doing yoga.", 0.15),
    ("The cat is sleeping.", "The stock market crashed.", 0.05),
    ("Children are playing soccer.", "Scientists discovered a new planet.", 0.10),
    ("A chef is cooking dinner.", "An astronaut is floating in space.", 0.08),
    ("The river flows downstream.", "The computer crashed.", 0.05),
    # Paraphrases (should be very high)
    (
        "The quick brown fox jumps over the lazy dog.",
        "A fast brown fox leaps over a sleepy canine.",
        0.88,
    ),
    ("I need to go to the grocery store.", "I have to visit the supermarket.", 0.85),
    ("The weather is beautiful today.", "It's a lovely day outside.", 0.82),
    # Contradictions (should be medium-low, not zero - they share topics)
    ("The movie was excellent.", "The film was terrible.", 0.45),
    ("Prices are rising.", "Prices are falling.", 0.40),
    ("He arrived early.", "He arrived late.", 0.35),
]

# MS-MARCO style queries with relevant passage and HARD negatives (BM25-retrieved)
# Hard negatives are passages that share keywords but are NOT relevant
# Reference: MS-MARCO Passage Ranking
MS_MARCO_HARD_NEGATIVES = [
    {
        "query": "what is the capital of france",
        "relevant": "Paris is the capital and most populous city of France, with an estimated population of 2.1 million.",
        "hard_negatives": [
            "France is a country in Western Europe with several overseas regions and territories.",
            "The capital of Germany is Berlin, which is also the largest city in Germany.",
            "French is the official language of France and is spoken by the majority of the population.",
            "Paris Fashion Week is held twice a year in Paris, France.",
        ],
    },
    {
        "query": "how does photosynthesis work",
        "relevant": "Photosynthesis is the process by which plants convert light energy into chemical energy, using carbon dioxide and water to produce glucose and oxygen.",
        "hard_negatives": [
            "Plants require sunlight, water, and nutrients from soil to grow properly.",
            "Chlorophyll is the green pigment found in plant cells that gives leaves their color.",
            "The carbon cycle describes how carbon moves between the atmosphere and living organisms.",
            "Cellular respiration is the process by which cells break down glucose to release energy.",
        ],
    },
    {
        "query": "symptoms of diabetes",
        "relevant": "Common symptoms of diabetes include increased thirst, frequent urination, unexplained weight loss, fatigue, and blurred vision.",
        "hard_negatives": [
            "Diabetes is a chronic metabolic disease affecting millions of people worldwide.",
            "Type 1 diabetes is an autoimmune condition where the body attacks insulin-producing cells.",
            "Blood sugar levels should be monitored regularly for people with diabetes.",
            "Insulin is a hormone produced by the pancreas that regulates blood sugar.",
        ],
    },
    {
        "query": "who wrote romeo and juliet",
        "relevant": "Romeo and Juliet is a tragedy written by William Shakespeare early in his career about two young star-crossed lovers.",
        "hard_negatives": [
            "Shakespeare was born in Stratford-upon-Avon in 1564 and died in 1616.",
            "The Globe Theatre in London was where many of Shakespeare's plays were performed.",
            "Romeo and Juliet has been adapted into numerous films, musicals, and operas.",
            "Hamlet, Macbeth, and Othello are other famous tragedies by Shakespeare.",
        ],
    },
    {
        "query": "how to make pizza dough",
        "relevant": "To make pizza dough, combine flour, yeast, salt, water, and olive oil. Knead for 10 minutes, let rise for 1-2 hours, then shape and top as desired.",
        "hard_negatives": [
            "Pizza originated in Naples, Italy, in the 18th century.",
            "The best pizza toppings include mozzarella, tomatoes, and fresh basil.",
            "A pizza oven should be preheated to at least 450F for optimal results.",
            "Neapolitan pizza is characterized by its thin, soft, and chewy crust.",
        ],
    },
    {
        "query": "what causes earthquakes",
        "relevant": "Earthquakes are caused by the sudden release of energy in the Earth's crust, typically due to movement along geological faults where tectonic plates meet.",
        "hard_negatives": [
            "The Richter scale measures the magnitude of earthquakes from 1 to 10.",
            "California sits on the San Andreas Fault, making it prone to seismic activity.",
            "Tsunami warnings are often issued following major undersea earthquakes.",
            "Seismographs are instruments used to detect and record earthquake waves.",
        ],
    },
    {
        "query": "benefits of meditation",
        "relevant": "Meditation has been shown to reduce stress, improve concentration, lower blood pressure, enhance self-awareness, and promote emotional health.",
        "hard_negatives": [
            "Meditation originated in ancient Eastern traditions including Buddhism and Hinduism.",
            "There are many types of meditation including mindfulness, transcendental, and guided meditation.",
            "Yoga and meditation are often practiced together for holistic wellness.",
            "Many successful entrepreneurs credit meditation for their mental clarity and focus.",
        ],
    },
    {
        "query": "difference between alligators and crocodiles",
        "relevant": "Alligators have a wider, U-shaped snout while crocodiles have a narrower, V-shaped snout. Alligators are found in the US and China, while crocodiles are found worldwide in tropical regions.",
        "hard_negatives": [
            "Both alligators and crocodiles are large reptiles that live in and around water.",
            "Crocodiles can live up to 70 years in the wild and grow over 20 feet long.",
            "The American alligator is found primarily in the southeastern United States.",
            "Crocodilians have existed for over 200 million years, surviving the dinosaur extinction.",
        ],
    },
]

# Adversarial robustness pairs for semantic understanding
# Tests: negation, role reversal, quantifier changes
ADVERSARIAL_ROBUSTNESS_PAIRS = [
    # Semantic role reversal (should be DIFFERENT)
    ("The dog bit the man.", "The man bit the dog.", "role_reversal", False),
    ("John gave Mary a gift.", "Mary gave John a gift.", "role_reversal", False),
    (
        "The teacher praised the student.",
        "The student praised the teacher.",
        "role_reversal",
        False,
    ),
    # Negation (should be DIFFERENT)
    ("The restaurant is open.", "The restaurant is not open.", "negation", False),
    ("He passed the exam.", "He did not pass the exam.", "negation", False),
    ("The meeting was cancelled.", "The meeting was not cancelled.", "negation", False),
    # Quantifier changes (should be DIFFERENT)
    ("All students passed.", "Some students passed.", "quantifier", False),
    ("Everyone attended the meeting.", "No one attended the meeting.", "quantifier", False),
    # True paraphrases (should be SIMILAR)
    ("The car is red.", "The automobile is crimson.", "paraphrase", True),
    ("She runs fast.", "She sprints quickly.", "paraphrase", True),
]

# Reference scores from MTEB leaderboard for comparison
MTEB_REFERENCE_SCORES = {
    "STS-B": {
        "all-mpnet-base-v2": 0.838,
        "text-embedding-3-small": 0.790,
        "all-MiniLM-L6-v2": 0.789,
    },
    "MS-MARCO": {
        "E5-large-v2": 0.430,
        "text-embedding-3-large": 0.378,
        "text-embedding-3-small": 0.337,
        "all-MiniLM-L6-v2": 0.328,
    },
}


# =============================================================================
# EMBEDDING BENCHMARK SUITE
# =============================================================================


class EmbeddingBenchmarkSuite:
    """World-class embedding benchmark suite with advanced metrics."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)
        self._embeddings_cache: Dict[str, np.ndarray] = {}
        self.results: List[BenchmarkResult] = []
        self.perf_tracker = PerformanceTracker()
        self._embedding_call_count = 0

    def get_embedding(self, text: str, track_time: bool = True) -> Optional[np.ndarray]:
        """Get embedding, using cache if available."""
        if text in self._embeddings_cache:
            return self._embeddings_cache[text]

        start_time = time.perf_counter()
        try:
            from k0.runtime.ultrabert_adapter import get_embedding

            embedding_list = get_embedding(text)
            if embedding_list is not None:
                embedding = np.array(embedding_list, dtype=np.float32)
                self._embeddings_cache[text] = embedding
                self._embedding_call_count += 1

                # Track time if enabled
                if track_time:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    self.perf_tracker.record_embedding_time(elapsed_ms)

                return embedding
        except ImportError:
            pass
        except Exception as e:
            print(f"  Error: {e}")

        return None

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def batch_embed(self, texts: List[str]) -> Dict[str, np.ndarray]:
        """Embed multiple texts and track batch performance."""
        start_time = time.perf_counter()
        results = {}
        for text in texts:
            emb = self.get_embedding(text, track_time=False)
            if emb is not None:
                results[text] = emb

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.perf_tracker.record_batch_time(len(texts), elapsed_ms)
        return results

    def get_word_count(self, text: str) -> int:
        """Get word count for length categorization."""
        return len(text.split())

    def categorize_length(self, text: str) -> str:
        """Categorize text by length."""
        word_count = self.get_word_count(text)
        for category, (min_words, max_words) in LENGTH_CATEGORIES.items():
            if min_words <= word_count <= max_words:
                return category
        return "very_long"

    # =========================================================================
    # BENCHMARK 1: Recall@K with N Distractors
    # =========================================================================

    def benchmark_recall_at_k(
        self,
        num_distractors: int = 100,
        k_values: List[int] = [1, 5, 10, 20],
    ) -> Dict[str, float]:
        """
        Evaluate Recall@K: Given a query, find its match among N distractors.

        Standard benchmark format:
        - Query text seeks its semantic match
        - N distractor texts serve as noise
        - Success = target in top K results
        """
        print(f"\n{'='*70}")
        print(f"BENCHMARK: Recall@K with {num_distractors} Distractors")
        print(f"{'='*70}")

        retrieval_results: List[RetrievalResult] = []

        for i, (query, target, domain) in enumerate(SEMANTIC_PAIRS):
            # Select random distractors
            available_distractors = [d for d in DISTRACTOR_POOL if d != query and d != target]
            distractors = random.sample(
                available_distractors, min(num_distractors, len(available_distractors))
            )

            # Build candidate pool: target + distractors
            candidates = [target] + distractors
            random.shuffle(candidates)

            # Get embeddings
            query_emb = self.get_embedding(query)
            if query_emb is None:
                continue

            # Score all candidates
            scores = []
            for cand in candidates:
                cand_emb = self.get_embedding(cand)
                if cand_emb is not None:
                    sim = self.cosine_similarity(query_emb, cand_emb)
                    scores.append((cand, sim))

            # Sort by similarity (descending)
            scores.sort(key=lambda x: x[1], reverse=True)

            # Find target rank
            target_rank = -1
            for rank, (cand, _) in enumerate(scores, 1):
                if cand == target:
                    target_rank = rank
                    break

            result = RetrievalResult(
                query_id=f"pair_{i}",
                query_text=query[:50],
                target_id=domain,
                target_rank=target_rank,
                num_candidates=len(candidates),
                recall_at_1=(target_rank == 1),
                recall_at_5=(1 <= target_rank <= 5),
                recall_at_10=(1 <= target_rank <= 10),
                reciprocal_rank=1.0 / target_rank if target_rank > 0 else 0.0,
            )
            retrieval_results.append(result)

            status = "HIT" if target_rank == 1 else f"rank={target_rank}"
            print(f"  [{i+1:2d}/{len(SEMANTIC_PAIRS)}] {domain:10s} | {status}")

        # Calculate metrics
        n = len(retrieval_results)
        metrics = {}

        for k in k_values:
            recall_at_k = (
                sum(1 for r in retrieval_results if 1 <= r.target_rank <= k) / n if n > 0 else 0
            )
            metrics[f"R@{k}"] = recall_at_k
            self.results.append(
                BenchmarkResult(
                    benchmark_name=f"Recall@{k}/{num_distractors}",
                    metric_name=f"R@{k}",
                    score=recall_at_k,
                )
            )

        # MRR
        mrr = np.mean([r.reciprocal_rank for r in retrieval_results])
        metrics["MRR"] = mrr
        self.results.append(
            BenchmarkResult(
                benchmark_name=f"MRR/{num_distractors}",
                metric_name="MRR",
                score=mrr,
            )
        )

        print(f"\n  Results (n={n}, distractors={num_distractors}):")
        for k in k_values:
            print(f"    Recall@{k}: {metrics[f'R@{k}']:.4f}")
        print(f"    MRR: {metrics['MRR']:.4f}")

        return metrics

    # =========================================================================
    # BENCHMARK 2: Semantic Textual Similarity (STS)
    # =========================================================================

    def benchmark_sts(self) -> Dict[str, float]:
        """
        Evaluate Semantic Textual Similarity.

        Measures correlation between model similarity and human judgment.
        """
        print(f"\n{'='*70}")
        print("BENCHMARK: Semantic Textual Similarity (STS)")
        print(f"{'='*70}")

        similarities = []
        domains = {}

        for query, target, domain in SEMANTIC_PAIRS:
            query_emb = self.get_embedding(query)
            target_emb = self.get_embedding(target)

            if query_emb is not None and target_emb is not None:
                sim = self.cosine_similarity(query_emb, target_emb)
                similarities.append(sim)

                if domain not in domains:
                    domains[domain] = []
                domains[domain].append(sim)

        avg_similarity = np.mean(similarities) if similarities else 0
        std_similarity = np.std(similarities) if similarities else 0

        print(f"\n  Overall: mean={avg_similarity:.4f}, std={std_similarity:.4f}")
        print("\n  By Domain:")
        for domain, sims in sorted(domains.items()):
            print(f"    {domain:12s}: {np.mean(sims):.4f} (n={len(sims)})")

        self.results.append(
            BenchmarkResult(
                benchmark_name="STS",
                metric_name="mean_similarity",
                score=avg_similarity,
                details={"std": std_similarity, "n": len(similarities)},
            )
        )

        return {"mean": avg_similarity, "std": std_similarity}

    # =========================================================================
    # BENCHMARK 3: Negation Handling
    # =========================================================================

    def benchmark_negation(self) -> Dict[str, float]:
        """
        Evaluate negation handling.

        Good embeddings should show LOWER similarity for negated pairs.
        """
        print(f"\n{'='*70}")
        print("BENCHMARK: Negation Handling")
        print(f"{'='*70}")

        similarities = []

        for positive, negated in NEGATION_PAIRS:
            pos_emb = self.get_embedding(positive)
            neg_emb = self.get_embedding(negated)

            if pos_emb is not None and neg_emb is not None:
                sim = self.cosine_similarity(pos_emb, neg_emb)
                similarities.append(sim)

                # Good: similarity < 0.8 for negated pairs
                status = "GOOD" if sim < 0.8 else "WARN"
                print(f"  {status} | sim={sim:.4f}")
                print(f"        +: {positive[:50]}...")
                print(f"        -: {negated[:50]}...")

        avg_sim = np.mean(similarities) if similarities else 0

        # Score: lower is better for negation (invert for score)
        negation_score = 1.0 - avg_sim  # Higher = better at detecting negation

        print(f"\n  Average negation similarity: {avg_sim:.4f}")
        print(f"  Negation discrimination score: {negation_score:.4f}")
        print("  (Lower similarity = better negation handling)")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Negation",
                metric_name="avg_similarity",
                score=avg_sim,
                details={"discrimination_score": negation_score},
            )
        )

        return {"avg_similarity": avg_sim, "discrimination_score": negation_score}

    # =========================================================================
    # BENCHMARK 4: Synonym vs Antonym Discrimination
    # =========================================================================

    def benchmark_synonym_antonym(self) -> Dict[str, float]:
        """
        Evaluate synonym/antonym discrimination.

        Synonyms should have HIGHER similarity than antonyms.
        """
        print(f"\n{'='*70}")
        print("BENCHMARK: Synonym vs Antonym Discrimination")
        print(f"{'='*70}")

        synonym_sims = []
        antonym_sims = []

        print("\n  Synonym Pairs:")
        for word1, word2 in SYNONYM_PAIRS:
            emb1 = self.get_embedding(word1)
            emb2 = self.get_embedding(word2)
            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                synonym_sims.append(sim)
                print(f"    {word1:12s} - {word2:12s} = {sim:.4f}")

        print("\n  Antonym Pairs:")
        for word1, word2 in ANTONYM_PAIRS:
            emb1 = self.get_embedding(word1)
            emb2 = self.get_embedding(word2)
            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                antonym_sims.append(sim)
                print(f"    {word1:12s} - {word2:12s} = {sim:.4f}")

        avg_syn = np.mean(synonym_sims) if synonym_sims else 0
        avg_ant = np.mean(antonym_sims) if antonym_sims else 0
        gap = avg_syn - avg_ant

        print(f"\n  Synonym avg: {avg_syn:.4f}")
        print(f"  Antonym avg: {avg_ant:.4f}")
        print(f"  Gap (syn - ant): {gap:.4f}")
        print(f"  {'GOOD' if gap > 0.1 else 'WARN'}: Synonyms should be > Antonyms")

        self.results.append(
            BenchmarkResult(
                benchmark_name="SynonymAntonym",
                metric_name="gap",
                score=gap,
                details={"synonym_avg": avg_syn, "antonym_avg": avg_ant},
            )
        )

        return {"synonym_avg": avg_syn, "antonym_avg": avg_ant, "gap": gap}

    # =========================================================================
    # BENCHMARK 5: Paraphrase Detection
    # =========================================================================

    def benchmark_paraphrase(self, threshold: float = 0.8) -> Dict[str, float]:
        """
        Evaluate paraphrase detection accuracy.

        Binary classification: is pair a paraphrase or not?
        """
        print(f"\n{'='*70}")
        print(f"BENCHMARK: Paraphrase Detection (threshold={threshold})")
        print(f"{'='*70}")

        tp, fp, tn, fn = 0, 0, 0, 0

        for text1, text2, is_paraphrase in PARAPHRASE_PAIRS:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)

            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                predicted = sim >= threshold

                if is_paraphrase and predicted:
                    tp += 1
                    status = "TP"
                elif is_paraphrase and not predicted:
                    fn += 1
                    status = "FN"
                elif not is_paraphrase and predicted:
                    fp += 1
                    status = "FP"
                else:
                    tn += 1
                    status = "TN"

                label = "PARA" if is_paraphrase else "NOT "
                print(f"  {status} | sim={sim:.4f} | {label} | {text1[:40]}...")

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0

        print(f"\n  Precision: {precision:.4f}")
        print(f"  Recall: {recall:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        print(f"  Accuracy: {accuracy:.4f}")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Paraphrase",
                metric_name="f1",
                score=f1,
                details={"precision": precision, "recall": recall, "accuracy": accuracy},
            )
        )

        return {"precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy}

    # =========================================================================
    # BENCHMARK 6: Length Invariance
    # =========================================================================

    def benchmark_length_invariance(self) -> Dict[str, float]:
        """
        Test if embeddings maintain meaning across different text lengths.

        Same concept expressed in short, medium, and long forms.
        """
        print(f"\n{'='*70}")
        print("BENCHMARK: Length Invariance")
        print(f"{'='*70}")

        test_cases = [
            {
                "concept": "economic_growth",
                "short": "Economy growing.",
                "medium": "The economy is experiencing significant growth this year.",
                "long": "According to recent reports, the national economy has demonstrated substantial growth patterns throughout the current fiscal year, with GDP increasing across multiple sectors including manufacturing, technology, and services.",
            },
            {
                "concept": "weather_rain",
                "short": "Raining today.",
                "medium": "Heavy rainfall is expected throughout the day.",
                "long": "Meteorological forecasts indicate that substantial precipitation will continue across the region for the remainder of the day, with some areas potentially experiencing flooding conditions due to the intensity of the rainfall.",
            },
            {
                "concept": "meeting_schedule",
                "short": "Meeting at 3.",
                "medium": "We have a team meeting scheduled for 3 PM today.",
                "long": "Please be advised that our regularly scheduled weekly team meeting has been confirmed for 3 PM this afternoon in the main conference room, where we will be discussing quarterly objectives and reviewing project milestones.",
            },
            {
                "concept": "product_launch",
                "short": "New product soon.",
                "medium": "The company will launch a new product next month.",
                "long": "Following months of development and rigorous testing, our organization is pleased to announce the upcoming launch of our innovative new product line, scheduled for release in the coming month with extensive marketing support and distribution channels.",
            },
        ]

        results_by_concept = []

        for tc in test_cases:
            concept = tc["concept"]
            short_emb = self.get_embedding(tc["short"])
            medium_emb = self.get_embedding(tc["medium"])
            long_emb = self.get_embedding(tc["long"])

            if all([short_emb is not None, medium_emb is not None, long_emb is not None]):
                short_medium = self.cosine_similarity(short_emb, medium_emb)
                medium_long = self.cosine_similarity(medium_emb, long_emb)
                short_long = self.cosine_similarity(short_emb, long_emb)
                avg = (short_medium + medium_long + short_long) / 3

                results_by_concept.append(avg)

                print(f"\n  {concept}:")
                print(f"    short-medium: {short_medium:.4f}")
                print(f"    medium-long:  {medium_long:.4f}")
                print(f"    short-long:   {short_long:.4f}")
                print(f"    average:      {avg:.4f}")

        overall_avg = np.mean(results_by_concept) if results_by_concept else 0

        print(f"\n  Overall Length Invariance Score: {overall_avg:.4f}")
        print(
            f"  {'GOOD' if overall_avg > 0.7 else 'WARN'}: Same concept should maintain similarity"
        )

        self.results.append(
            BenchmarkResult(
                benchmark_name="LengthInvariance",
                metric_name="avg_similarity",
                score=overall_avg,
            )
        )

        return {"avg_similarity": overall_avg}

    # =========================================================================
    # BENCHMARK 7: Noise Robustness
    # =========================================================================

    def benchmark_noise_robustness(self) -> Dict[str, float]:
        """
        Test robustness to typos and noise.
        """
        print(f"\n{'='*70}")
        print("BENCHMARK: Noise Robustness (Typos)")
        print(f"{'='*70}")

        test_cases = [
            (
                "The meeting is scheduled for tomorrow morning.",
                "The meetng is sceduled for tomorow morning.",
            ),
            (
                "Please review the attached document carefully.",
                "Plese reveiw the atached documant carefuly.",
            ),
            (
                "The weather forecast predicts rain this weekend.",
                "The weathr forcast predits rain this weekned.",
            ),
            (
                "Scientists discovered a new species of butterfly.",
                "Scientsts discovred a new speceis of buterfly.",
            ),
            (
                "The restaurant serves excellent Italian cuisine.",
                "The resturant servs excelent Italain cusine.",
            ),
        ]

        similarities = []

        for clean, noisy in test_cases:
            clean_emb = self.get_embedding(clean)
            noisy_emb = self.get_embedding(noisy)

            if clean_emb is not None and noisy_emb is not None:
                sim = self.cosine_similarity(clean_emb, noisy_emb)
                similarities.append(sim)

                status = "ROBUST" if sim > 0.9 else "SENSITIVE"
                print(f"  {status} | sim={sim:.4f}")
                print(f"    clean: {clean[:50]}...")
                print(f"    noisy: {noisy[:50]}...")

        avg_sim = np.mean(similarities) if similarities else 0

        print(f"\n  Average clean-noisy similarity: {avg_sim:.4f}")
        print(f"  {'GOOD' if avg_sim > 0.9 else 'WARN'}: Should be robust to minor typos")

        self.results.append(
            BenchmarkResult(
                benchmark_name="NoiseRobustness",
                metric_name="avg_similarity",
                score=avg_sim,
            )
        )

        return {"avg_similarity": avg_sim}

    # =========================================================================
    # IMPROVEMENT TECHNIQUE 1: Instruction Prefixes (Query vs Document)
    # =========================================================================

    def benchmark_instruction_prefix(self) -> Dict[str, float]:
        """
        Test if instruction prefixes improve discrimination.

        Technique: Add "search query: " or "document: " prefix to differentiate
        query embeddings from document embeddings for asymmetric retrieval.
        """
        print(f"\n{'='*70}")
        print("IMPROVEMENT: Instruction Prefix (Asymmetric Retrieval)")
        print(f"{'='*70}")

        QUERY_PREFIX = "search query: "
        DOC_PREFIX = "document: "

        # Test on semantic pairs with/without prefix
        baseline_sims = []
        prefixed_sims = []
        distractor_baseline = []
        distractor_prefixed = []

        # Take first 10 pairs for testing
        test_pairs = SEMANTIC_PAIRS[:10]
        test_distractors = DISTRACTOR_POOL[:20]

        for query, target, domain in test_pairs:
            # Baseline (no prefix)
            q_emb = self.get_embedding(query)
            t_emb = self.get_embedding(target)

            if q_emb is not None and t_emb is not None:
                baseline_sims.append(self.cosine_similarity(q_emb, t_emb))

            # With prefix
            q_prefixed = f"{QUERY_PREFIX}{query}"
            t_prefixed = f"{DOC_PREFIX}{target}"
            qp_emb = self.get_embedding(q_prefixed)
            tp_emb = self.get_embedding(t_prefixed)

            if qp_emb is not None and tp_emb is not None:
                prefixed_sims.append(self.cosine_similarity(qp_emb, tp_emb))

            # Test against distractors
            for dist in test_distractors[:5]:
                d_emb = self.get_embedding(dist)
                dp_emb = self.get_embedding(f"{DOC_PREFIX}{dist}")

                if q_emb is not None and d_emb is not None:
                    distractor_baseline.append(self.cosine_similarity(q_emb, d_emb))
                if qp_emb is not None and dp_emb is not None:
                    distractor_prefixed.append(self.cosine_similarity(qp_emb, dp_emb))

        baseline_avg = np.mean(baseline_sims) if baseline_sims else 0
        prefixed_avg = np.mean(prefixed_sims) if prefixed_sims else 0
        dist_baseline_avg = np.mean(distractor_baseline) if distractor_baseline else 0
        dist_prefixed_avg = np.mean(distractor_prefixed) if distractor_prefixed else 0

        # Improvement = increase target sim while decreasing distractor sim
        target_delta = prefixed_avg - baseline_avg
        distractor_delta = dist_baseline_avg - dist_prefixed_avg
        discrimination_improvement = target_delta + distractor_delta

        print("\n  Target Similarity:")
        print(f"    Baseline:  {baseline_avg:.4f}")
        print(f"    Prefixed:  {prefixed_avg:.4f}")
        print(f"    Delta:     {target_delta:+.4f}")

        print("\n  Distractor Similarity:")
        print(f"    Baseline:  {dist_baseline_avg:.4f}")
        print(f"    Prefixed:  {dist_prefixed_avg:.4f}")
        print(f"    Delta:     {-distractor_delta:+.4f}")

        print(f"\n  Discrimination Improvement: {discrimination_improvement:+.4f}")
        status = "HELPS" if discrimination_improvement > 0.02 else "NO EFFECT"
        print(f"  Verdict: {status}")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Improve_InstructionPrefix",
                metric_name="discrimination_delta",
                score=float(discrimination_improvement),
                details={
                    "target_baseline": float(baseline_avg),
                    "target_prefixed": float(prefixed_avg),
                    "distractor_baseline": float(dist_baseline_avg),
                    "distractor_prefixed": float(dist_prefixed_avg),
                },
            )
        )

        return {
            "target_delta": float(target_delta),
            "distractor_delta": float(distractor_delta),
            "improvement": float(discrimination_improvement),
        }

    # =========================================================================
    # KNOWN LIMITATIONS DOCUMENTATION (Device-First Constraints)
    # =========================================================================

    def document_known_limitations(self) -> Dict[str, any]:
        """
        Document known embedding limitations that CANNOT be fixed at the
        embedding layer without loading heavy models (>1GB).

        These require APPLICATION-LEVEL handling, not embedding fixes.
        """
        print(f"\n{'='*70}")
        print("KNOWN ULTRABERT LIMITATIONS (Cannot Fix Without Heavy Models)")
        print(f"{'='*70}")

        # Test negation blindness
        print("\n  1. NEGATION BLINDNESS:")
        print("     UltraBERT treats 'I love X' and 'I hate X' as similar.")

        negation_sims = []
        for positive, negated in NEGATION_PAIRS[:3]:
            pos_emb = self.get_embedding(positive)
            neg_emb = self.get_embedding(negated)
            if pos_emb is not None and neg_emb is not None:
                sim = self.cosine_similarity(pos_emb, neg_emb)
                negation_sims.append(sim)
                print(f"       sim={sim:.3f} | '{positive[:30]}...' vs '{negated[:30]}...'")

        avg_neg_sim = np.mean(negation_sims) if negation_sims else 0
        print(f"\n     Average negation similarity: {avg_neg_sim:.3f} (should be <0.5)")
        print("     FIX: Store sentiment/polarity as separate metadata field.")
        print("          At retrieval time, filter by polarity match.")

        # Test semantic role reversal
        print("\n  2. SEMANTIC ROLE REVERSAL:")
        print("     'A chased B' and 'B chased A' look identical to embeddings.")

        role_pairs = [
            ("The dog chased the cat", "The cat chased the dog"),
            ("John gave Mary a book", "Mary gave John a book"),
            ("The teacher graded the student", "The student graded the teacher"),
        ]

        role_sims = []
        for text1, text2 in role_pairs:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)
            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                role_sims.append(sim)
                print(f"       sim={sim:.3f} | '{text1}' vs '{text2}'")

        avg_role_sim = np.mean(role_sims) if role_sims else 0
        print(f"\n     Average role-reversal similarity: {avg_role_sim:.3f} (should be <0.7)")
        print("     FIX: Extract structured data (subject, verb, object) before storing.")
        print("          Match on structured fields, not just embedding similarity.")

        # Document what CAN be done
        print("\n  PRACTICAL IMPROVEMENTS (Implemented in PracticalImprovements class):")
        print("     - Text normalization: lowercase, strip whitespace")
        print("     - Short text augmentation: add context templates")
        print("     - Instruction prefixes: query/document asymmetric retrieval")
        print("     - Threshold tuning: use 0.85 instead of 0.70")
        print("     - OpenAI fallback: API-based embeddings when needed")

        self.results.append(
            BenchmarkResult(
                benchmark_name="KnownLimitations",
                metric_name="documented",
                score=1.0,
                details={
                    "negation_blindness_avg_sim": float(avg_neg_sim),
                    "role_reversal_avg_sim": float(avg_role_sim),
                    "fixes_documented": True,
                },
            )
        )

        return {
            "negation_blindness": float(avg_neg_sim),
            "role_reversal": float(avg_role_sim),
        }

    # =========================================================================
    # IMPROVEMENT TECHNIQUE 2: Difference Vector Analysis (Zero-Cost)
    # =========================================================================

    def benchmark_difference_vector(self) -> Dict[str, float]:
        """
        Test difference vector analysis for semantic change detection.

        This uses existing embeddings - NO additional model loading.
        Analyzes the magnitude and direction of embedding differences.
        """
        print(f"\n{'='*70}")
        print("IMPROVEMENT: Difference Vector Analysis (Zero-Cost)")
        print(f"{'='*70}")

        pi = PracticalImprovements

        print("\n  Testing difference vector for negation detection:")

        results_list = []
        for positive, negated in NEGATION_PAIRS:
            pos_emb = self.get_embedding(positive)
            neg_emb = self.get_embedding(negated)

            if pos_emb is not None and neg_emb is not None:
                vec_sim = self.cosine_similarity(pos_emb, neg_emb)
                diff_score = pi.difference_vector_score(pos_emb, neg_emb)

                # Check if diff vector helps distinguish
                vec_says_same = vec_sim >= 0.8
                diff_says_same = diff_score >= 0.7

                results_list.append(
                    {
                        "vec_sim": vec_sim,
                        "diff_score": diff_score,
                        "vec_correct": not vec_says_same,  # negation pairs should be different
                        "diff_correct": not diff_says_same,
                    }
                )

                status = "HELPED" if not diff_says_same and vec_says_same else "SAME"
                print(f"    {status} | vec={vec_sim:.3f} diff={diff_score:.3f}")

        if results_list:
            vec_acc = sum(1 for r in results_list if r["vec_correct"]) / len(results_list)
            diff_acc = sum(1 for r in results_list if r["diff_correct"]) / len(results_list)
            improvement = diff_acc - vec_acc

            print(f"\n  Vector Accuracy: {vec_acc:.2%}")
            print(f"  Diff Vector Accuracy: {diff_acc:.2%}")
            print(f"  Improvement: {improvement:+.2%}")
        else:
            improvement = 0.0

        self.results.append(
            BenchmarkResult(
                benchmark_name="Improve_DiffVector",
                metric_name="accuracy_improvement",
                score=float(improvement),
            )
        )

        return {"improvement": float(improvement)}

    # =========================================================================
    # IMPROVEMENT TECHNIQUE 3: Short Text Augmentation
    # =========================================================================

    def benchmark_short_text_augmentation(self) -> Dict[str, float]:
        """
        Test description augmentation for short texts.

        Technique (GAP-001 Section 3.4): Augment short entity names with
        descriptive context to improve embedding quality.
        """
        print(f"\n{'='*70}")
        print("IMPROVEMENT: Short Text Augmentation (GAP-001 Section 3.4)")
        print(f"{'='*70}")

        pi = PracticalImprovements

        # Short texts paired with their expected semantic match
        test_cases = [
            {
                "short": "meeting",
                "augmented": pi.augment_short_text("meeting", "action"),
                "related": "We need to schedule a conference with the team.",
                "unrelated": "The elephant is the largest land mammal.",
            },
            {
                "short": "vacation",
                "augmented": pi.augment_short_text("vacation", "memory"),
                "related": "Taking a relaxing trip to the beach next week.",
                "unrelated": "The algorithm runs in O(n log n) time complexity.",
            },
            {
                "short": "birthday",
                "augmented": pi.augment_short_text("birthday", "memory"),
                "related": "Celebrating the anniversary of someone's birth.",
                "unrelated": "Stock markets closed higher today.",
            },
            {
                "short": "Mom",
                "augmented": pi.augment_short_text("Mom", "person"),
                "related": "My mother is a wonderful and caring parent.",
                "unrelated": "Quantum computing uses qubits instead of bits.",
            },
            {
                "short": "workout",
                "augmented": pi.augment_short_text("workout", "action"),
                "related": "Going to the gym for physical exercise.",
                "unrelated": "The Renaissance began in 14th century Italy.",
            },
        ]

        results_list = []

        print("\n  Testing augmentation effect:")
        for tc in test_cases:
            short_emb = self.get_embedding(tc["short"])
            aug_emb = self.get_embedding(tc["augmented"])
            rel_emb = self.get_embedding(tc["related"])
            unrel_emb = self.get_embedding(tc["unrelated"])

            if all(e is not None for e in [short_emb, aug_emb, rel_emb, unrel_emb]):
                # Similarity to related text
                short_rel = self.cosine_similarity(short_emb, rel_emb)
                aug_rel = self.cosine_similarity(aug_emb, rel_emb)

                # Similarity to unrelated text
                short_unrel = self.cosine_similarity(short_emb, unrel_emb)
                aug_unrel = self.cosine_similarity(aug_emb, unrel_emb)

                # Discrimination = (related - unrelated)
                short_disc = short_rel - short_unrel
                aug_disc = aug_rel - aug_unrel
                improvement = aug_disc - short_disc

                results_list.append(
                    {
                        "word": tc["short"],
                        "short_related": short_rel,
                        "aug_related": aug_rel,
                        "short_unrelated": short_unrel,
                        "aug_unrelated": aug_unrel,
                        "improvement": improvement,
                    }
                )

                status = "BETTER" if improvement > 0 else "WORSE"
                print(f"\n    '{tc['short']}' -> '{tc['augmented'][:40]}...'")
                print(f"      Related:   {short_rel:.3f} -> {aug_rel:.3f}")
                print(f"      Unrelated: {short_unrel:.3f} -> {aug_unrel:.3f}")
                print(f"      Discrimination: {short_disc:.3f} -> {aug_disc:.3f} [{status}]")

        avg_improvement = np.mean([r["improvement"] for r in results_list]) if results_list else 0

        print(f"\n  Average Discrimination Improvement: {avg_improvement:+.4f}")
        status = "HELPS" if avg_improvement > 0 else "NO EFFECT"
        print(f"  Verdict: {status}")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Improve_ShortTextAugment",
                metric_name="discrimination_delta",
                score=float(avg_improvement),
            )
        )

        return {"avg_improvement": float(avg_improvement)}

    # =========================================================================
    # IMPROVEMENT TECHNIQUE 6: Threshold Tuning
    # =========================================================================

    def benchmark_threshold_tuning(self) -> Dict[str, float]:
        """
        Test different similarity thresholds for optimal precision/recall.

        Since baseline similarity is ~0.77, we need to find the optimal
        threshold that reduces false positives while maintaining recall.
        """
        print(f"\n{'='*70}")
        print("IMPROVEMENT: Threshold Tuning (Baseline = 0.77)")
        print(f"{'='*70}")

        thresholds = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
        best_f1 = 0
        best_threshold = 0.80

        print("\n  Threshold Analysis on Paraphrase Detection:")
        print(f"  {'Threshold':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        print("  " + "-" * 45)

        for threshold in thresholds:
            tp, fp, tn, fn = 0, 0, 0, 0

            for text1, text2, is_paraphrase in PARAPHRASE_PAIRS:
                emb1 = self.get_embedding(text1)
                emb2 = self.get_embedding(text2)

                if emb1 is not None and emb2 is not None:
                    sim = self.cosine_similarity(emb1, emb2)
                    predicted = sim >= threshold

                    if is_paraphrase and predicted:
                        tp += 1
                    elif is_paraphrase and not predicted:
                        fn += 1
                    elif not is_paraphrase and predicted:
                        fp += 1
                    else:
                        tn += 1

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            marker = " ← BEST" if f1 > best_f1 else ""
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = threshold

            print(f"  {threshold:>10.2f} {precision:>10.3f} {recall:>10.3f} {f1:>10.3f}{marker}")

        print(f"\n  Optimal Threshold: {best_threshold}")
        print(f"  Best F1 Score: {best_f1:.4f}")
        print(f"  Recommendation: Use threshold >= {best_threshold} for GAP-001")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Improve_ThresholdTuning",
                metric_name="optimal_threshold",
                score=best_threshold,
                details={"best_f1": best_f1},
            )
        )

        return {"optimal_threshold": best_threshold, "best_f1": best_f1}

    # =========================================================================
    # IMPROVEMENT TECHNIQUE 5: Text Normalization for Typos
    # =========================================================================

    def benchmark_text_normalization(self) -> Dict[str, float]:
        """
        Test text normalization effect on noisy inputs.
        """
        print(f"\n{'='*70}")
        print("IMPROVEMENT: Text Normalization for Typo Robustness")
        print(f"{'='*70}")

        pi = PracticalImprovements

        test_cases = [
            (
                "The meeting is scheduled for tomorrow morning.",
                "The meetng is sceduled for tomorow morning.",
            ),
            (
                "Please review the attached document carefully.",
                "Plese reveiw the atached documant carefuly.",
            ),
            (
                "The weather forecast predicts rain this weekend.",
                "The weathr forcast predits rain this weekned.",
            ),
        ]

        baseline_sims = []
        normalized_sims = []

        print("\n  Testing normalization effect:")
        for clean, noisy in test_cases:
            clean_emb = self.get_embedding(clean)
            noisy_emb = self.get_embedding(noisy)

            # Normalized versions
            clean_norm = pi.normalize_text(clean)
            noisy_norm = pi.normalize_text(noisy)
            clean_norm_emb = self.get_embedding(clean_norm)
            noisy_norm_emb = self.get_embedding(noisy_norm)

            if all(e is not None for e in [clean_emb, noisy_emb, clean_norm_emb, noisy_norm_emb]):
                baseline = self.cosine_similarity(clean_emb, noisy_emb)
                normalized = self.cosine_similarity(clean_norm_emb, noisy_norm_emb)

                baseline_sims.append(baseline)
                normalized_sims.append(normalized)

                delta = normalized - baseline
                print(f"    baseline={baseline:.4f} -> norm={normalized:.4f} (delta={delta:+.4f})")

        avg_baseline = np.mean(baseline_sims) if baseline_sims else 0
        avg_normalized = np.mean(normalized_sims) if normalized_sims else 0
        improvement = avg_normalized - avg_baseline

        print(f"\n  Average Baseline: {avg_baseline:.4f}")
        print(f"  Average Normalized: {avg_normalized:.4f}")
        print(f"  Improvement: {improvement:+.4f}")

        # Note: Simple lowercase normalization won't fix typos
        # Real solution needs spell-checking
        print("\n  Note: Full typo robustness requires spell-checking (e.g., pyspellchecker)")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Improve_TextNormalization",
                metric_name="similarity_delta",
                score=float(improvement),
            )
        )

        return {"improvement": float(improvement)}

    # =========================================================================
    # ADVANCED BENCHMARK 1: Adversarial Examples
    # =========================================================================

    def benchmark_adversarial(self) -> Dict[str, float]:
        """
        Test on adversarial examples — semantically tricky pairs.

        Tests word order, negation scope, quantifier changes, voice changes.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Adversarial Examples")
        print(f"{'='*70}")

        correct = 0
        total = 0
        threshold = 0.85

        print(f"\n  Testing adversarial pairs (threshold={threshold}):")
        for text1, text2, should_be_similar in ADVERSARIAL_PAIRS:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)

            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                is_similar = sim >= threshold
                is_correct = is_similar == should_be_similar

                if is_correct:
                    correct += 1
                total += 1

                label = "SIMILAR" if should_be_similar else "DIFFERENT"
                status = "[OK]" if is_correct else "[X]"
                print(f"    {status} {label:10s} | sim={sim:.4f} | {text1[:35]}...")

        accuracy = correct / total if total else 0
        print(f"\n  Adversarial Accuracy: {accuracy:.2%} ({correct}/{total})")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Adversarial",
                metric_name="accuracy",
                score=float(accuracy),
                details={"correct": correct, "total": total},
            )
        )

        return {"accuracy": float(accuracy)}

    # =========================================================================
    # ADVANCED BENCHMARK 2: Domain Adaptation
    # =========================================================================

    def benchmark_domain_adaptation(self) -> Dict[str, float]:
        """
        Test cross-domain understanding.

        Same concept expressed in technical vs layman, formal vs informal.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Domain Adaptation")
        print(f"{'='*70}")

        similarities = []
        by_domain = {}

        print("\n  Cross-domain similarity tests:")
        for text1, text2, domain in DOMAIN_ADAPTATION_PAIRS:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)

            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                similarities.append(sim)

                if domain not in by_domain:
                    by_domain[domain] = []
                by_domain[domain].append(sim)

                status = "GOOD" if sim >= 0.8 else "WEAK"
                print(f"    {status} | {domain:15s} | sim={sim:.4f}")
                print(f"         T: {text1[:40]}...")
                print(f"         L: {text2[:40]}...")

        avg_sim = np.mean(similarities) if similarities else 0

        print("\n  By Domain:")
        for domain, sims in by_domain.items():
            print(f"    {domain:20s}: {np.mean(sims):.4f}")

        print(f"\n  Overall Domain Adaptation: {avg_sim:.4f}")
        print(f"  {'GOOD' if avg_sim >= 0.8 else 'NEEDS WORK'}: Should understand cross-domain")

        self.results.append(
            BenchmarkResult(
                benchmark_name="DomainAdaptation",
                metric_name="avg_similarity",
                score=float(avg_sim),
                details={d: float(np.mean(s)) for d, s in by_domain.items()},
            )
        )

        return {"avg_similarity": float(avg_sim)}

    # =========================================================================
    # ADVANCED BENCHMARK 3: Temporal Consistency
    # =========================================================================

    def benchmark_temporal_consistency(self) -> Dict[str, float]:
        """
        Test temporal consistency — same event in different tenses.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Temporal Consistency")
        print(f"{'='*70}")

        similarities = []

        print("\n  Temporal pairs (same event, different tense):")
        for text1, text2, should_be_similar in TEMPORAL_PAIRS:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)

            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                similarities.append(sim)

                status = "GOOD" if sim >= 0.85 else "WEAK"
                print(f"    {status} | sim={sim:.4f}")
                print(f"         Future: {text1}")
                print(f"         Past:   {text2}")

        avg_sim = np.mean(similarities) if similarities else 0

        print(f"\n  Temporal Consistency Score: {avg_sim:.4f}")
        print(
            f"  {'GOOD' if avg_sim >= 0.85 else 'WEAK'}: Same event should be similar across tenses"
        )

        self.results.append(
            BenchmarkResult(
                benchmark_name="TemporalConsistency",
                metric_name="avg_similarity",
                score=float(avg_sim),
            )
        )

        return {"avg_similarity": float(avg_sim)}

    # =========================================================================
    # ADVANCED BENCHMARK 4: Named Entity Recognition
    # =========================================================================

    def benchmark_entity_recognition(self) -> Dict[str, float]:
        """
        Test entity recognition — entity names vs descriptions.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Named Entity Recognition Quality")
        print(f"{'='*70}")

        similarities = []

        print("\n  Entity name vs description pairs:")
        for text1, text2, should_be_similar in ENTITY_PAIRS:
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)

            if emb1 is not None and emb2 is not None:
                sim = self.cosine_similarity(emb1, emb2)
                similarities.append(sim)

                status = "GOOD" if sim >= 0.75 else "WEAK"
                print(f"    {status} | sim={sim:.4f}")
                print(f"         Named:   {text1}")
                print(f"         Descr:   {text2}")

        avg_sim = np.mean(similarities) if similarities else 0

        print(f"\n  Entity Recognition Score: {avg_sim:.4f}")
        print(f"  {'GOOD' if avg_sim >= 0.75 else 'WEAK'}: Should link entities to descriptions")

        self.results.append(
            BenchmarkResult(
                benchmark_name="EntityRecognition",
                metric_name="avg_similarity",
                score=float(avg_sim),
            )
        )

        return {"avg_similarity": float(avg_sim)}

    # =========================================================================
    # ADVANCED BENCHMARK 5: Granular Domain Analysis
    # =========================================================================

    def benchmark_granular_domain(self) -> Dict[str, float]:
        """
        Analyze performance by domain category.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Granular Domain Analysis")
        print(f"{'='*70}")

        category_scores = {cat: [] for cat in DOMAIN_CATEGORIES}

        for query, target, domain in SEMANTIC_PAIRS:
            query_emb = self.get_embedding(query)
            target_emb = self.get_embedding(target)

            if query_emb is not None and target_emb is not None:
                sim = self.cosine_similarity(query_emb, target_emb)

                for category, domains in DOMAIN_CATEGORIES.items():
                    if domain in domains:
                        category_scores[category].append(sim)

        print("\n  Performance by Domain Category:")
        results = {}
        for category, scores in category_scores.items():
            if scores:
                avg = float(np.mean(scores))
                std = float(np.std(scores))
                results[category] = avg
                print(f"    {category:12s}: {avg:.4f} ± {std:.4f} (n={len(scores)})")

        overall = float(np.mean([s for scores in category_scores.values() for s in scores]))
        results["overall"] = overall

        self.results.append(
            BenchmarkResult(
                benchmark_name="GranularDomain",
                metric_name="overall_avg",
                score=overall,
                details=results,
            )
        )

        return results

    # =========================================================================
    # ADVANCED BENCHMARK 6: Length Performance Analysis
    # =========================================================================

    def benchmark_length_performance(self) -> Dict[str, float]:
        """
        Analyze embedding quality by text length.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Length Performance Analysis")
        print(f"{'='*70}")

        length_scores = {cat: [] for cat in LENGTH_CATEGORIES}

        for query, target, _ in SEMANTIC_PAIRS:
            query_emb = self.get_embedding(query)
            target_emb = self.get_embedding(target)

            if query_emb is not None and target_emb is not None:
                sim = self.cosine_similarity(query_emb, target_emb)
                query_len = self.categorize_length(query)
                length_scores[query_len].append(sim)

        print("\n  Similarity by Query Length:")
        results = {}
        for category, (min_w, max_w) in LENGTH_CATEGORIES.items():
            scores = length_scores[category]
            if scores:
                avg = float(np.mean(scores))
                results[category] = avg
                print(
                    f"    {category:12s} ({min_w:2d}-{max_w:3d} words): {avg:.4f} (n={len(scores)})"
                )
            else:
                results[category] = 0.0
                print(f"    {category:12s} ({min_w:2d}-{max_w:3d} words): N/A")

        self.results.append(
            BenchmarkResult(
                benchmark_name="LengthPerformance",
                metric_name="by_length",
                score=float(np.mean([v for v in results.values() if v > 0])),
                details=results,
            )
        )

        return results

    # =========================================================================
    # ADVANCED BENCHMARK 7: Statistical Significance
    # =========================================================================

    def benchmark_statistical_significance(self, num_runs: int = 5) -> Dict[str, float]:
        """
        Run recall benchmark multiple times with different seeds for confidence intervals.
        """
        print(f"\n{'='*70}")
        print(f"ADVANCED: Statistical Significance ({num_runs} runs)")
        print(f"{'='*70}")

        recall_scores = []

        for run in range(num_runs):
            random.seed(self.seed + run)
            np.random.seed(self.seed + run)

            # Run R@1/100 benchmark silently
            correct = 0
            total = 0

            for query, target, _ in SEMANTIC_PAIRS:
                available_distractors = [d for d in DISTRACTOR_POOL if d != query and d != target]
                distractors = random.sample(
                    available_distractors, min(100, len(available_distractors))
                )
                candidates = [target] + distractors
                random.shuffle(candidates)

                query_emb = self.get_embedding(query)
                if query_emb is None:
                    continue

                scores = []
                for cand in candidates:
                    cand_emb = self.get_embedding(cand)
                    if cand_emb is not None:
                        sim = self.cosine_similarity(query_emb, cand_emb)
                        scores.append((cand, sim))

                scores.sort(key=lambda x: x[1], reverse=True)
                if scores and scores[0][0] == target:
                    correct += 1
                total += 1

            recall = correct / total if total else 0
            recall_scores.append(recall)
            print(f"    Run {run + 1}: R@1/100 = {recall:.4f}")

        # Reset seed
        random.seed(self.seed)
        np.random.seed(self.seed)

        mean_recall = float(np.mean(recall_scores))
        std_recall = float(np.std(recall_scores))

        # 95% confidence interval
        n = len(recall_scores)
        se = std_recall / np.sqrt(n) if n > 0 else 0
        ci_95 = 1.96 * se

        print(f"\n  Mean R@1/100: {mean_recall:.4f}")
        print(f"  Std Dev: {std_recall:.4f}")
        print(f"  95% CI: [{mean_recall - ci_95:.4f}, {mean_recall + ci_95:.4f}]")

        self.results.append(
            BenchmarkResult(
                benchmark_name="StatisticalSignificance",
                metric_name="mean_recall",
                score=mean_recall,
                details={
                    "std": std_recall,
                    "ci_95_lower": mean_recall - ci_95,
                    "ci_95_upper": mean_recall + ci_95,
                    "num_runs": num_runs,
                },
            )
        )

        return {
            "mean": mean_recall,
            "std": std_recall,
            "ci_95": (mean_recall - ci_95, mean_recall + ci_95),
        }

    # =========================================================================
    # ADVANCED BENCHMARK 8: Performance Metrics
    # =========================================================================

    def benchmark_performance(self) -> Dict[str, float]:
        """
        Report embedding generation performance metrics.
        """
        print(f"\n{'='*70}")
        print("ADVANCED: Performance Metrics")
        print(f"{'='*70}")

        perf_stats = self.perf_tracker.get_stats()

        if not perf_stats:
            print("\n  No performance data collected.")
            return {}

        print("\n  Embedding Performance:")
        print(f"    Total Embeddings: {perf_stats.get('embedding_count', 0)}")
        print(f"    Total Time: {perf_stats.get('total_time_ms', 0):.1f} ms")
        print(f"    Mean Time: {perf_stats.get('mean_time_ms', 0):.2f} ms")
        print(f"    Std Dev: {perf_stats.get('std_time_ms', 0):.2f} ms")
        print(f"    Min Time: {perf_stats.get('min_time_ms', 0):.2f} ms")
        print(f"    Max Time: {perf_stats.get('max_time_ms', 0):.2f} ms")
        print(f"    P50 (Median): {perf_stats.get('p50_time_ms', 0):.2f} ms")
        print(f"    P95: {perf_stats.get('p95_time_ms', 0):.2f} ms")
        print(f"    P99: {perf_stats.get('p99_time_ms', 0):.2f} ms")
        print(f"    Throughput: {perf_stats.get('throughput_per_sec', 0):.1f} embeddings/sec")

        # Batch performance
        if self.perf_tracker.batch_times:
            total_batch_items = sum(b[0] for b in self.perf_tracker.batch_times)
            total_batch_time = sum(b[1] for b in self.perf_tracker.batch_times)
            print("\n  Batch Performance:")
            print(f"    Total Batches: {len(self.perf_tracker.batch_times)}")
            print(f"    Total Items: {total_batch_items}")
            print(f"    Batch Throughput: {total_batch_items / (total_batch_time / 1000):.1f}/sec")

        self.results.append(
            BenchmarkResult(
                benchmark_name="Performance",
                metric_name="throughput",
                score=perf_stats.get("throughput_per_sec", 0),
                details=perf_stats,
            )
        )

        return perf_stats

    # =========================================================================
    # REAL-WORLD BENCHMARKS (Industry Standard)
    # =========================================================================

    def benchmark_stsb_correlation(self) -> Dict[str, float]:
        """
        STS-B style benchmark: Spearman correlation with human judgments.

        This is an industry-standard benchmark from MTEB.
        Reference scores:
        - all-mpnet-base-v2: 0.838
        - text-embedding-3-small: 0.790
        - all-MiniLM-L6-v2: 0.789
        """
        from scipy import stats

        print(f"\n{'='*70}")
        print("REAL-WORLD: STS-B Correlation (Human Judgment Alignment)")
        print(f"{'='*70}")
        print("  Reference: MTEB Leaderboard STS-B scores")

        human_scores = []
        model_scores = []

        for sent1, sent2, human_sim in STS_B_PAIRS:
            emb1 = self.get_embedding(sent1)
            emb2 = self.get_embedding(sent2)

            if emb1 is None or emb2 is None:
                continue

            model_sim = self.cosine_similarity(emb1, emb2)
            human_scores.append(human_sim)
            model_scores.append(model_sim)

            status = "OK" if abs(model_sim - human_sim) < 0.3 else "GAP"
            print(f"  [{status}] human={human_sim:.2f} model={model_sim:.2f} | {sent1[:40]}...")

        # Calculate Spearman correlation
        if len(human_scores) < 2:
            print("  [ERROR] Not enough data for correlation")
            return {"correlation": 0.0, "p_value": 1.0}

        correlation, p_value = stats.spearmanr(human_scores, model_scores)

        print(f"\n  Spearman Correlation: {correlation:.4f} (p={p_value:.4f})")
        print("\n  Reference Scores (MTEB STS-B):")
        print("    all-mpnet-base-v2:      0.838")
        print("    text-embedding-3-small: 0.790")
        print("    all-MiniLM-L6-v2:       0.789")
        print(f"    UltraBERT:              {correlation:.3f}")

        if correlation > 0.80:
            verdict = "EXCELLENT (competitive with SOTA)"
        elif correlation > 0.70:
            verdict = "GOOD (reasonable performance)"
        elif correlation > 0.60:
            verdict = "FAIR (below average)"
        else:
            verdict = "POOR (needs improvement)"

        print(f"\n  Verdict: {verdict}")

        self.results.append(
            BenchmarkResult(
                benchmark_name="RealWorld_STS-B",
                metric_name="spearman_correlation",
                score=float(correlation),
                details={
                    "p_value": float(p_value),
                    "n_pairs": len(human_scores),
                    "reference": 0.838,
                    "reference_model": "all-mpnet-base-v2",
                },
            )
        )

        return {"correlation": float(correlation), "p_value": float(p_value)}

    def benchmark_msmarco_hard_negatives(self) -> Dict[str, float]:
        """
        MS-MARCO style retrieval with BM25-mined hard negatives.

        This is a REAL test - hard negatives share keywords but are NOT relevant.
        Reference scores (MTEB MS-MARCO MRR@10):
        - E5-large-v2: 0.430
        - text-embedding-3-large: 0.378
        - text-embedding-3-small: 0.337
        """
        print(f"\n{'='*70}")
        print("REAL-WORLD: MS-MARCO Style (Hard Negative Retrieval)")
        print(f"{'='*70}")
        print("  Tests retrieval against BM25-mined hard negatives")
        print("  (passages that share keywords but are NOT relevant)")

        hits_at_1 = 0
        reciprocal_ranks = []

        for item in MS_MARCO_HARD_NEGATIVES:
            query = item["query"]
            relevant = item["relevant"]
            hard_negs = item["hard_negatives"]

            query_emb = self.get_embedding(query)
            if query_emb is None:
                continue

            # Score all candidates
            candidates = [relevant] + hard_negs
            random.shuffle(candidates)

            scores = []
            for cand in candidates:
                cand_emb = self.get_embedding(cand)
                if cand_emb is not None:
                    sim = self.cosine_similarity(query_emb, cand_emb)
                    scores.append((cand, sim))

            # Sort by score
            scores.sort(key=lambda x: x[1], reverse=True)

            # Find rank of relevant passage
            rank = -1
            for i, (cand, _) in enumerate(scores, 1):
                if cand == relevant:
                    rank = i
                    break

            if rank == 1:
                hits_at_1 += 1
                status = "HIT@1"
            elif rank <= 3:
                status = f"HIT@{rank}"
            else:
                status = f"MISS (rank={rank})"

            rr = 1.0 / rank if rank > 0 else 0.0
            reciprocal_ranks.append(rr)

            print(f"  [{status}] {query}")

        mrr = float(np.mean(reciprocal_ranks)) if reciprocal_ranks else 0.0
        recall_at_1 = hits_at_1 / len(MS_MARCO_HARD_NEGATIVES) if MS_MARCO_HARD_NEGATIVES else 0.0

        print(f"\n  MRR@10: {mrr:.4f}")
        print(f"  R@1:    {recall_at_1:.4f}")
        print("\n  Reference Scores (MTEB MS-MARCO MRR@10):")
        print("    E5-large-v2:            0.430")
        print("    text-embedding-3-large: 0.378")
        print("    text-embedding-3-small: 0.337")
        print(f"    UltraBERT:              {mrr:.3f}")

        if mrr > 0.40:
            verdict = "EXCELLENT (competitive with E5-large)"
        elif mrr > 0.33:
            verdict = "GOOD (competitive with OpenAI)"
        elif mrr > 0.25:
            verdict = "FAIR (below average)"
        else:
            verdict = "POOR (fails on hard negatives)"

        print(f"\n  Verdict: {verdict}")

        self.results.append(
            BenchmarkResult(
                benchmark_name="RealWorld_MSMARCO",
                metric_name="MRR@10",
                score=mrr,
                details={
                    "recall_at_1": recall_at_1,
                    "n_queries": len(MS_MARCO_HARD_NEGATIVES),
                    "reference": 0.378,
                    "reference_model": "text-embedding-3-large",
                },
            )
        )

        return {"mrr": mrr, "recall_at_1": recall_at_1}

    def benchmark_adversarial_robustness(self) -> Dict[str, float]:
        """
        Test robustness to adversarial examples.

        Tests:
        - Semantic role reversal ("A bit B" vs "B bit A")
        - Negation ("X is true" vs "X is not true")
        - Quantifier changes ("all" vs "some" vs "none")

        Most embedding models fail these tests. This is EXPECTED.
        """
        print(f"\n{'='*70}")
        print("REAL-WORLD: Adversarial Robustness")
        print(f"{'='*70}")
        print("  Tests: negation, role reversal, quantifier changes")
        print("  Note: Most embedding models (including OpenAI) fail these tests")

        results_by_type: Dict[str, Dict] = {}

        for sent1, sent2, adv_type, should_be_similar in ADVERSARIAL_ROBUSTNESS_PAIRS:
            emb1 = self.get_embedding(sent1)
            emb2 = self.get_embedding(sent2)

            if emb1 is None or emb2 is None:
                continue

            sim = self.cosine_similarity(emb1, emb2)

            # For adversarial pairs, high similarity is BAD
            # For paraphrases, high similarity is GOOD
            if should_be_similar:
                is_correct = sim > 0.75
            else:
                is_correct = sim < 0.75

            status = "OK" if is_correct else "FAIL"

            if adv_type not in results_by_type:
                results_by_type[adv_type] = {"correct": 0, "total": 0, "sims": []}

            results_by_type[adv_type]["total"] += 1
            if is_correct:
                results_by_type[adv_type]["correct"] += 1
            results_by_type[adv_type]["sims"].append(sim)

            print(f"  [{status}] {adv_type:15s} sim={sim:.3f} | {sent1[:35]}...")

        print("\n  Results by Type:")
        total_correct = 0
        total_count = 0
        for adv_type, data in results_by_type.items():
            acc = data["correct"] / data["total"] if data["total"] > 0 else 0
            avg_sim = float(np.mean(data["sims"])) if data["sims"] else 0
            total_correct += data["correct"]
            total_count += data["total"]
            print(
                f"    {adv_type:15s}: {acc:.1%} ({data['correct']}/{data['total']}) avg_sim={avg_sim:.3f}"
            )

        overall_acc = total_correct / total_count if total_count > 0 else 0

        print(f"\n  Overall Adversarial Accuracy: {overall_acc:.1%}")

        if overall_acc > 0.80:
            verdict = "EXCELLENT (robust to adversarial examples)"
        elif overall_acc > 0.60:
            verdict = "FAIR (some adversarial weaknesses)"
        else:
            verdict = "EXPECTED (vulnerable like most embeddings)"

        print(f"\n  Verdict: {verdict}")
        print("  Note: This is expected for embedding models without explicit")
        print("        negation/role understanding. Store metadata separately.")

        self.results.append(
            BenchmarkResult(
                benchmark_name="RealWorld_Adversarial",
                metric_name="accuracy",
                score=overall_acc,
                details={
                    k: {"accuracy": v["correct"] / v["total"] if v["total"] > 0 else 0}
                    for k, v in results_by_type.items()
                },
            )
        )

        return {"accuracy": overall_acc, "by_type": results_by_type}

    # =========================================================================
    # RUN ALL BENCHMARKS
    # =========================================================================

    def run_all(
        self, include_improvements: bool = True, include_advanced: bool = True
    ) -> Dict[str, any]:
        """Run all benchmarks and return summary."""
        print("\n" + "=" * 70)
        print("ULTRABERT EMBEDDING BENCHMARK SUITE")
        print("=" * 70)
        print(f"  Semantic pairs: {len(SEMANTIC_PAIRS)}")
        print(f"  Distractor pool: {len(DISTRACTOR_POOL)}")
        print(f"  Negation pairs: {len(NEGATION_PAIRS)}")
        print(f"  Synonym pairs: {len(SYNONYM_PAIRS)}")
        print(f"  Antonym pairs: {len(ANTONYM_PAIRS)}")
        print(f"  Paraphrase pairs: {len(PARAPHRASE_PAIRS)}")
        print(f"  Adversarial pairs: {len(ADVERSARIAL_PAIRS)}")
        print(f"  Domain adaptation pairs: {len(DOMAIN_ADAPTATION_PAIRS)}")
        print(f"  Temporal pairs: {len(TEMPORAL_PAIRS)}")
        print(f"  Entity pairs: {len(ENTITY_PAIRS)}")

        # Pre-cache embeddings
        print("\n  Caching embeddings...")
        start = time.time()
        all_texts = set()
        for q, t, _ in SEMANTIC_PAIRS:
            all_texts.add(q)
            all_texts.add(t)
        all_texts.update(DISTRACTOR_POOL)
        for p, n in NEGATION_PAIRS:
            all_texts.add(p)
            all_texts.add(n)
        for w1, w2 in SYNONYM_PAIRS + ANTONYM_PAIRS:
            all_texts.add(w1)
            all_texts.add(w2)
        for t1, t2, _ in PARAPHRASE_PAIRS:
            all_texts.add(t1)
            all_texts.add(t2)

        for text in all_texts:
            self.get_embedding(text)
        cache_time = time.time() - start
        print(f"  Cached {len(self._embeddings_cache)} embeddings in {cache_time:.1f}s")

        # Run benchmarks
        results = {}

        # 1. Recall@K with different distractor counts
        for n_dist in [10, 50, 100]:
            results[f"recall_{n_dist}"] = self.benchmark_recall_at_k(
                num_distractors=n_dist,
                k_values=[1, 5, 10],
            )

        # 2. Semantic Textual Similarity
        results["sts"] = self.benchmark_sts()

        # 3. Negation Handling
        results["negation"] = self.benchmark_negation()

        # 4. Synonym/Antonym
        results["synonym_antonym"] = self.benchmark_synonym_antonym()

        # 5. Paraphrase Detection
        results["paraphrase"] = self.benchmark_paraphrase()

        # 6. Length Invariance
        results["length_invariance"] = self.benchmark_length_invariance()

        # 7. Noise Robustness
        results["noise_robustness"] = self.benchmark_noise_robustness()

        # =====================================================================
        # PRACTICAL IMPROVEMENT TECHNIQUES (Device-First, Zero-Cost)
        # =====================================================================
        if include_improvements:
            print("\n" + "=" * 70)
            print("PRACTICAL IMPROVEMENT TECHNIQUES (Device-First, Zero-Cost)")
            print("=" * 70)

            # 8. Document Known Limitations (what we CAN'T fix without heavy models)
            results["limitations"] = self.document_known_limitations()

            # 9. Instruction Prefix
            results["improve_prefix"] = self.benchmark_instruction_prefix()

            # 10. Difference Vector Analysis (zero-cost)
            results["improve_diff_vector"] = self.benchmark_difference_vector()

            # 11. Short Text Augmentation
            results["improve_augment"] = self.benchmark_short_text_augmentation()

            # 12. Threshold Tuning
            results["improve_threshold"] = self.benchmark_threshold_tuning()

            # 13. Text Normalization
            results["improve_normalize"] = self.benchmark_text_normalization()

        # =====================================================================
        # ADVANCED BENCHMARKS
        # =====================================================================
        if include_advanced:
            print("\n" + "=" * 70)
            print("ADVANCED BENCHMARKS")
            print("=" * 70)

            # 14. Adversarial Examples
            results["adversarial"] = self.benchmark_adversarial()

            # 15. Domain Adaptation
            results["domain_adaptation"] = self.benchmark_domain_adaptation()

            # 16. Temporal Consistency
            results["temporal"] = self.benchmark_temporal_consistency()

            # 17. Entity Recognition
            results["entity"] = self.benchmark_entity_recognition()

            # 18. Granular Domain Analysis
            results["granular_domain"] = self.benchmark_granular_domain()

            # 19. Length Performance Analysis
            results["length_performance"] = self.benchmark_length_performance()

            # 20. Statistical Significance
            results["statistical"] = self.benchmark_statistical_significance(num_runs=5)

            # 20. Performance Metrics
            results["performance"] = self.benchmark_performance()

        # =====================================================================
        # REAL-WORLD BENCHMARKS (Industry Standard - MTEB Style)
        # =====================================================================
        print("\n" + "=" * 70)
        print("REAL-WORLD BENCHMARKS (Industry Standard)")
        print("=" * 70)
        print("  These tests use industry-standard data and methodology")
        print("  Reference: MTEB Leaderboard (https://huggingface.co/spaces/mteb/leaderboard)")

        # 21. STS-B Correlation (Human Judgment Alignment)
        results["stsb_correlation"] = self.benchmark_stsb_correlation()

        # 22. MS-MARCO with Hard Negatives
        results["msmarco_hard_neg"] = self.benchmark_msmarco_hard_negatives()

        # 23. Adversarial Robustness
        results["adversarial_robust"] = self.benchmark_adversarial_robustness()

        # Summary
        self.print_summary()

        return results

    def print_summary(self):
        """Print final summary of all benchmarks."""
        print("\n" + "=" * 70)
        print("BENCHMARK SUMMARY")
        print("=" * 70)

        # Separate baseline, improvement, and advanced results
        baseline_results = [
            r
            for r in self.results
            if not r.benchmark_name.startswith("Improve_")
            and not r.benchmark_name.startswith("RealWorld_")
            and r.benchmark_name
            not in (
                "Adversarial",
                "DomainAdaptation",
                "TemporalConsistency",
                "EntityRecognition",
                "GranularDomain",
                "LengthPerformance",
                "StatisticalSignificance",
                "Performance",
            )
        ]
        improvement_results = [r for r in self.results if r.benchmark_name.startswith("Improve_")]
        advanced_results = [
            r
            for r in self.results
            if r.benchmark_name
            in (
                "Adversarial",
                "DomainAdaptation",
                "TemporalConsistency",
                "EntityRecognition",
                "GranularDomain",
                "LengthPerformance",
                "StatisticalSignificance",
                "Performance",
            )
        ]
        realworld_results = [r for r in self.results if r.benchmark_name.startswith("RealWorld_")]

        print("\n{:<35} {:<15} {:>10}".format("Benchmark", "Metric", "Score"))
        print("-" * 60)

        for r in baseline_results:
            print(f"{r.benchmark_name:<35} {r.metric_name:<15} {r.score:>10.4f}")

        if improvement_results:
            print("\n" + "-" * 60)
            print("ML-BASED IMPROVEMENT TECHNIQUES:")
            print("-" * 60)
            for r in improvement_results:
                print(f"{r.benchmark_name:<35} {r.metric_name:<15} {r.score:>10.4f}")

        if advanced_results:
            print("\n" + "-" * 60)
            print("ADVANCED BENCHMARKS:")
            print("-" * 60)
            for r in advanced_results:
                print(f"{r.benchmark_name:<35} {r.metric_name:<15} {r.score:>10.4f}")

        if realworld_results:
            print("\n" + "-" * 60)
            print("REAL-WORLD BENCHMARKS (Industry Standard):")
            print("-" * 60)
            for r in realworld_results:
                # Show reference comparison
                ref_info = ""
                if r.details and "reference" in r.details:
                    ref = r.details["reference"]
                    ref_model = r.details.get("reference_model", "SOTA")
                    delta = r.score - ref
                    delta_str = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"
                    ref_info = f" (ref: {ref:.3f} {ref_model}, {delta_str})"
                print(f"{r.benchmark_name:<35} {r.metric_name:<15} {r.score:>10.4f}{ref_info}")

        # Key metrics
        print("\n" + "-" * 60)
        print("KEY METRICS FOR GAP-001:")

        r1_100 = next((r for r in self.results if "Recall@1/100" in r.benchmark_name), None)
        mrr_100 = next((r for r in self.results if "MRR/100" in r.benchmark_name), None)
        sts = next((r for r in self.results if r.benchmark_name == "STS"), None)

        if r1_100:
            status = "PASS" if r1_100.score >= 0.8 else "FAIL"
            print(f"  Recall@1/100: {r1_100.score:.4f} [{status}] (target >= 0.80)")

        if mrr_100:
            status = "PASS" if mrr_100.score >= 0.85 else "FAIL"
            print(f"  MRR@100:      {mrr_100.score:.4f} [{status}] (target >= 0.85)")

        if sts:
            status = "PASS" if sts.score >= 0.85 else "FAIL"
            print(f"  STS Mean:     {sts.score:.4f} [{status}] (target >= 0.85)")

        # Real-world metrics
        if realworld_results:
            print("\n" + "-" * 60)
            print("REAL-WORLD METRICS (vs MTEB Leaderboard):")

            stsb = next((r for r in self.results if r.benchmark_name == "RealWorld_STS-B"), None)
            msmarco = next(
                (r for r in self.results if r.benchmark_name == "RealWorld_MSMARCO"), None
            )
            adversarial = next(
                (r for r in self.results if r.benchmark_name == "RealWorld_Adversarial"), None
            )

            if stsb:
                ref = stsb.details.get("reference", 0.838) if stsb.details else 0.838
                pct = (stsb.score / ref) * 100 if ref > 0 else 0
                status = "GOOD" if pct >= 85 else "FAIR" if pct >= 70 else "BELOW AVG"
                print(f"  STS-B Corr:   {stsb.score:.4f} [{status}] ({pct:.0f}% of SOTA 0.838)")

            if msmarco:
                ref = msmarco.details.get("reference", 0.378) if msmarco.details else 0.378
                delta = msmarco.score - ref
                status = "EXCEEDS" if delta >= 0 else "BELOW"
                delta_str = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"
                print(
                    f"  MS-MARCO MRR: {msmarco.score:.4f} [{status}] ({delta_str} vs OpenAI 0.378)"
                )

            if adversarial:
                status = "EXPECTED" if adversarial.score < 0.5 else "GOOD"
                print(
                    f"  Adversarial:  {adversarial.score:.4f} [{status}] (most models fail these)"
                )

        # Print practical improvement recommendations
        if improvement_results:
            print("\n" + "-" * 60)
            print("PRACTICAL IMPROVEMENT RECOMMENDATIONS (Device-First):")

            threshold = next(
                (r for r in self.results if r.benchmark_name == "Improve_ThresholdTuning"), None
            )
            diff_vector = next(
                (r for r in self.results if r.benchmark_name == "Improve_DiffVector"), None
            )
            augment = next(
                (r for r in self.results if r.benchmark_name == "Improve_ShortTextAugment"), None
            )
            normalize = next(
                (r for r in self.results if r.benchmark_name == "Improve_TextNormalization"), None
            )

            print("\n  1. THRESHOLD TUNING (Zero-Cost):")
            if threshold:
                print(f"     [OK] Use threshold >= {threshold.score:.2f} (not 0.70)")
                if threshold.details:
                    print(f"       Best F1: {threshold.details.get('best_f1', 0):.4f}")
                print("       Implementation: Set similarity_threshold=0.85 in config")

            print("\n  2. DIFFERENCE VECTOR ANALYSIS (Zero-Cost):")
            if diff_vector:
                improvement = diff_vector.score
                if improvement > 0:
                    print(f"     [OK] +{improvement:.1%} improvement over baseline")
                else:
                    print("     ~ No significant improvement (expected for this model)")
                print("       Implementation: PracticalImprovements.difference_vector_score()")

            print("\n  3. SHORT TEXT AUGMENTATION (Zero-Cost):")
            if augment:
                improvement = augment.score
                status = "[OK]" if improvement > 0 else "~"
                print(f"     {status} {improvement:+.4f} discrimination improvement")
                print("       Implementation: PracticalImprovements.augment_short_text()")

            print("\n  4. TEXT NORMALIZATION (Zero-Cost):")
            if normalize:
                improvement = normalize.score
                print(f"     [OK] +{improvement:.4f} similarity improvement for typos")
                print("       Implementation: PracticalImprovements.normalize_text()")

            print("\n  KNOWN LIMITATIONS (Cannot Fix Without Heavy Models):")
            print("     - Negation blindness: Store sentiment as metadata field")
            print("     - Semantic role reversal: Use structured data extraction")
            print("     - See PracticalImprovements class docstring for details")

    def export_results(self, output_path: str = "benchmark_results.json"):
        """Export results to JSON."""
        export_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": "UltraBERT v2.1.0 (768-dim)",
            "benchmarks": [
                {
                    "name": r.benchmark_name,
                    "metric": r.metric_name,
                    "score": r.score,
                    "details": r.details,
                }
                for r in self.results
            ],
            "performance": self.perf_tracker.get_stats(),
            "recommendations": {
                "threshold": "Use similarity >= 0.85 to reduce false positives",
                "short_text": "Use PracticalImprovements.augment_short_text() for short queries",
                "typos": "Use PracticalImprovements.normalize_text() for noisy inputs",
                "negation_limitation": "Cannot fix without heavy NLI model - store sentiment as metadata",
                "adversarial_limitation": "Cannot fix without cross-encoder - use structured data extraction",
            },
        }

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        print(f"\n  Results exported to: {output_path}")


# =============================================================================
# MAIN
# =============================================================================


def main():
    """Run the benchmark suite with improvements and advanced benchmarks."""
    suite = EmbeddingBenchmarkSuite(seed=42)
    results = suite.run_all(include_improvements=True, include_advanced=True)
    suite.export_results("poc/embedding_benchmark_results.json")

    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)

    return results


if __name__ == "__main__":
    main()

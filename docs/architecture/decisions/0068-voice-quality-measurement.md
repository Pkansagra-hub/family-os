# ADR-0068: Voice Quality Measurement (ASR WER + TTS MOS)

**Status:** Proposed 🔄 (Requirements Gathering - Ready for Detailed Design)
**Decision Date:** 2025-10-16
**Implementation Date:** TBD
**Authors:** K1 Architecture Team
**Category:** Voice Pipeline & Quality Assurance
**Related ADRs:**
- [ADR-0056 (Voice Pipeline IMPLEMENTATION Architecture)](0056-voice-pipeline-implementation.md) - ASR/TTS stages
- [ADR-0056a (ASR Ingress)](0056a-asr-ingress.md) - ASR frame processing
- [ADR-0056d (TTS Synthesis Streaming)](0056d-tts-synthesis.md) - TTS quality
- [ADR-0024 (Performance Budgets)](0024-performance-budgets-p95-targets.md) - Latency targets
- [ADR-0029 (Prometheus Metrics & RED)](0029-prometheus-metrics-red-method.md) - Observability framework
- [ADR-0070 (Observability Evaluation Infrastructure)](0070-observability-evaluation-infrastructure.md) - A/B testing integration

---

## Context

### Problem Statement

K1 Intelligence Module requires automated voice quality measurement:

1. **ASR Accuracy:** Cannot quantify speech recognition quality (WER)
2. **TTS Quality:** Cannot measure text-to-speech naturalness (MOS)
3. **Environment Sensitivity:** No tracking of performance by environment (quiet/noisy)
4. **Regression Detection:** No automated way to detect quality degradation
5. **Model Comparison:** Cannot objectively compare ASR/TTS models

**Key Challenges:**

- **WER Computation:** Need reference transcripts for alignment
- **MOS Estimation:** Human evaluation expensive, need automated proxy
- **Non-Determinism:** Voice quality varies by speaker, accent, environment
- **Production Measurement:** Need to measure in real conversations (not just test sets)

### Current Landscape

**Industry Patterns:**

1. **ASR WER Evaluation (SpeechRecognition):**
   - **Pattern:** Compute WER as edit distance between hypothesis and reference
   - **Strength:** Objective, reproducible
   - **Weakness:** Requires reference transcripts (expensive to collect)

2. **TTS MOS Evaluation (Speech Quality):**
   - **Pattern:** Human listeners rate quality 1-5, compute mean
   - **Strength:** Reflects true user perception
   - **Weakness:** Expensive, slow, not reproducible

3. **Automated MOS Estimation (VoiceNet, MOS-Net):**
   - **Pattern:** Train ML model to predict MOS from speech features
   - **Strength:** Automated, fast, reproducible
   - **Weakness:** Model-dependent, may not generalize

4. **Production Monitoring (Azure Speech, Google Cloud):**
   - **Pattern:** Collect metrics in production, report dashboards
   - **Strength:** Real production data
   - **Weakness:** Limited transparency, vendor lock-in

### Research Foundations

**ASR Evaluation:**
- **WER Calculation (Hunt, 1990)** — Edit distance metric for ASR
- **BLEU Score (Papineni et al., 2002)** — Similarity metrics for sequences
- **Levenshtein Distance (Levenshtein, 1966)** — Edit distance algorithm

**TTS Evaluation:**
- **MOS (Mean Opinion Score) (ITU-R, 1993)** — Standard for voice quality
- **MOS-Net (Lo et al., 2019)** — Neural MOS predictor
- **VoiceNet (Kong et al., 2020)** — Multi-task voice quality assessment

**Production Measurement:**
- **Continuous Monitoring (Fowler, 2006)** — Production metrics collection
- **A/B Testing (Kohavi et al., 2009)** — Experimental comparison
- **Anomaly Detection (Chandola et al., 2009)** — Statistical outlier detection

### K1 Requirements

**ASR Quality Targets (from whiteboard.md):**

- **Quiet environment:** WER <6%
- **Noisy environment:** WER <12%
- **Accuracy tracking:** By speaker, accent, dialect

**TTS Quality Targets:**

- **MOS score:** ≥4.2 (5-point scale)
- **Prosody quality:** Natural pitch, rate, emphasis
- **Degradation limits:** <0.5 MOS drop under backpressure

**Production Measurement:**

- **Measurement frequency:** Every ASR result, sample TTS outputs
- **Retention:** 30-day rolling window (compliance with GDPR)
- **Automation:** Regression detection with <1% false positive rate

---

## Decision

We will implement **automated voice quality measurement** with:

1. **ASR WER Measurement:** Real-time computation from user corrections + explicit confirmations
2. **TTS MOS Estimation:** Passive (model-based) + active (user surveys)
3. **Regression Detection:** Automated alerts for >5% WER/MOS drop
4. **A/B Testing:** Infrastructure for TTS model/setting comparisons

### Architecture Overview

```
User Input → ASR → [Transcription + Confidence]
               ↓
        ┌─────────────────────────┐
        │ WER MEASUREMENT POINT   │
        │  - User correction?     │
        │  - Explicit confirm?    │
        │  → Reference transcript │
        └────────────┬────────────┘
                     ↓
            [Compute WER]
                ↓
         Emit to Prometheus
                ↓

Agent Generation → TTS → [Audio output]
                    ↓
        ┌─────────────────────────┐
        │ MOS MEASUREMENT POINT   │
        │  - Passive: ML predictor│
        │  - Active: User survey  │
        │  → MOS estimate (1-5)   │
        └────────────┬────────────┘
                     ↓
            [Emit to Prometheus]
                ↓
        [Regression Detection]
                ↓
        Alert if >5% drop
```

---

## Component 1: ASR WER (Word Error Rate) Measurement

### WER Calculation

```python
# k1/voice/asr_quality.py

from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class WERResult:
    """WER calculation result"""
    wer: float  # Word error rate (0.0 - 1.0+)
    insertions: int
    deletions: int
    substitutions: int
    reference_words: int

    def __str__(self):
        return f"WER: {self.wer:.1%} (S:{self.substitutions} D:{self.deletions} I:{self.insertions})"

class WERCalculator:
    """
    Compute Word Error Rate (WER) for ASR results

    Research: WER (Hunt 1990), Levenshtein distance (Levenshtein 1966)

    Formula: WER = (S + D + I) / N
    Where:
      S = substitutions (wrong word)
      D = deletions (missed word)
      I = insertions (extra word)
      N = total reference words
    """

    def compute_wer(self, reference: str, hypothesis: str) -> WERResult:
        """
        Compute WER between reference (ground truth) and hypothesis (ASR output)

        Args:
            reference: Ground truth transcription
            hypothesis: ASR model output

        Returns: WERResult
        """
        # Normalize text
        ref_words = self._normalize(reference).split()
        hyp_words = self._normalize(hypothesis).split()

        # Compute edit distance using dynamic programming
        substitutions, deletions, insertions = self._compute_edits(ref_words, hyp_words)

        # Calculate WER
        ref_count = len(ref_words)
        wer = (substitutions + deletions + insertions) / ref_count if ref_count > 0 else 0.0

        return WERResult(
            wer=wer,
            substitutions=substitutions,
            deletions=deletions,
            insertions=insertions,
            reference_words=ref_count,
        )

    def _normalize(self, text: str) -> str:
        """Normalize text for WER calculation"""
        import re

        # Convert to lowercase
        text = text.lower()

        # Remove punctuation (except apostrophes for contractions)
        text = re.sub(r"[^\w\s'-]", "", text)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _compute_edits(self, ref: List[str], hyp: List[str]) -> Tuple[int, int, int]:
        """
        Compute edit distance using dynamic programming

        Returns: (substitutions, deletions, insertions)
        """
        ref_len = len(ref)
        hyp_len = len(hyp)

        # Initialize DP table
        dp = [[0] * (hyp_len + 1) for _ in range(ref_len + 1)]

        # Initialize base cases
        for i in range(ref_len + 1):
            dp[i][0] = i  # Deletions
        for j in range(hyp_len + 1):
            dp[0][j] = j  # Insertions

        # Fill DP table
        for i in range(1, ref_len + 1):
            for j in range(1, hyp_len + 1):
                if ref[i-1] == hyp[j-1]:
                    # Match
                    dp[i][j] = dp[i-1][j-1]
                else:
                    # Mismatch: take minimum of substitution, deletion, insertion
                    dp[i][j] = 1 + min(
                        dp[i-1][j-1],    # Substitution
                        dp[i-1][j],      # Deletion
                        dp[i][j-1],      # Insertion
                    )

        # Backtrack to get edit counts
        i, j = ref_len, hyp_len
        substitutions = deletions = insertions = 0

        while i > 0 or j > 0:
            if i > 0 and j > 0 and ref[i-1] == hyp[j-1]:
                # Match
                i -= 1
                j -= 1
            elif i > 0 and j > 0 and dp[i-1][j-1] <= min(dp[i-1][j], dp[i][j-1]):
                # Substitution
                substitutions += 1
                i -= 1
                j -= 1
            elif i > 0 and (j == 0 or dp[i-1][j] <= dp[i][j-1]):
                # Deletion
                deletions += 1
                i -= 1
            else:
                # Insertion
                insertions += 1
                j -= 1

        return substitutions, deletions, insertions
```

### Reference Transcript Collection

```python
class ReferenceTranscriptCollector:
    """
    Collect reference transcripts from production

    Sources:
    1. User corrections ("No, I said X not Y")
    2. Explicit confirmations ("Yes, that's correct")
    3. High-confidence manual labels
    """

    def __init__(self, db_connection):
        self.db = db_connection
        self.calculator = WERCalculator()

    async def collect_from_user_correction(
        self,
        turn_id: str,
        asr_hypothesis: str,
        user_correction: str,
        confidence: float,
    ):
        """
        User explicitly corrected ASR result

        Example:
        - ASR: "Check weather tomorrow"
        - User: "No, check weather today"
        → Reference: "Check weather today"
        """
        if confidence < 0.8:  # Only high-confidence corrections
            return

        # Compute WER
        wer_result = self.calculator.compute_wer(user_correction, asr_hypothesis)

        # Store reference
        await self.db.store_reference_transcript(
            turn_id=turn_id,
            reference=user_correction,
            hypothesis=asr_hypothesis,
            wer_result=wer_result,
            source="user_correction",
            timestamp=now(),
        )

        logger.info(
            f"Reference transcript collected (correction): {wer_result}",
            extra={"turn_id": turn_id, "source": "user_correction"}
        )

    async def collect_from_explicit_confirmation(
        self,
        turn_id: str,
        asr_hypothesis: str,
        user_confirmation: str,
    ):
        """
        User explicitly confirmed ASR result

        Example:
        - ASR: "Check weather tomorrow"
        - Agent: "Did you say 'Check weather tomorrow'?"
        - User: "Yes"
        → Reference: "Check weather tomorrow"
        """
        # Compute WER (should be 0 if confirmed)
        wer_result = self.calculator.compute_wer(asr_hypothesis, asr_hypothesis)

        # Store reference
        await self.db.store_reference_transcript(
            turn_id=turn_id,
            reference=asr_hypothesis,
            hypothesis=asr_hypothesis,
            wer_result=wer_result,
            source="explicit_confirmation",
            timestamp=now(),
        )

        logger.info(
            f"Reference transcript collected (confirmation): {wer_result}",
            extra={"turn_id": turn_id, "source": "explicit_confirmation"}
        )
```

### WER Tracking & Aggregation

```python
class WERTracker:
    """
    Track WER across production conversations

    Metrics:
    - Overall WER (all speakers, all environments)
    - WER by environment (quiet, noisy)
    - WER by speaker (family member profiles)
    - WER by accent/dialect
    """

    def __init__(self, metrics_client):
        self.metrics = metrics_client
        self.calculator = WERCalculator()

    async def track_wer(
        self,
        reference: str,
        hypothesis: str,
        speaker_id: str,
        environment: str,  # "quiet", "noisy", "unknown"
        accent: str = None,  # Optional accent/dialect tag
    ):
        """
        Track WER for a single turn
        """
        wer_result = self.calculator.compute_wer(reference, hypothesis)

        # Emit metrics
        self.metrics.histogram(
            "asr_wer",
            wer_result.wer,
            labels={
                "environment": environment,
                "speaker_id": speaker_id,
                "accent": accent or "unknown",
            }
        )

        # Track by category
        self.metrics.histogram(
            "asr_wer_by_environment",
            wer_result.wer,
            labels={"environment": environment}
        )

        self.metrics.histogram(
            "asr_wer_by_speaker",
            wer_result.wer,
            labels={"speaker_id": speaker_id}
        )

        logger.info(
            f"WER tracked: {wer_result}",
            extra={
                "wer": wer_result.wer,
                "speaker_id": speaker_id,
                "environment": environment,
            }
        )
```

### Regression Detection

```python
class WERRegressionDetector:
    """
    Detect WER regressions (quality degradation)

    Alert if:
    - Overall WER increases >5%
    - Environment-specific WER increases >5%
    - Speaker-specific WER increases >5%
    """

    def __init__(self, metrics_client, alert_manager):
        self.metrics = metrics_client
        self.alerts = alert_manager
        self.baseline_window = 7  # Compare last 7 days
        self.regression_threshold = 0.05  # 5% regression threshold

    async def check_regression(self, environment: str = None):
        """
        Check if WER regressed

        Args:
            environment: Optional environment to check (overall if None)
        """
        # Get current WER (last 24 hours)
        current_wer = await self._compute_wer_for_period(
            days=1,
            environment=environment,
        )

        # Get baseline WER (previous 7 days average)
        baseline_wer = await self._compute_wer_for_period(
            days=self.baseline_window,
            exclude_recent_days=1,
            environment=environment,
        )

        if baseline_wer is None:
            logger.info("No baseline WER yet, skipping regression detection")
            return

        # Calculate regression
        regression = (current_wer - baseline_wer) / baseline_wer

        if regression > self.regression_threshold:
            # Alert: WER regressed
            alert_msg = (
                f"⚠️ WER REGRESSION ALERT"
                f"\n  Current: {current_wer:.1%}"
                f"\n  Baseline: {baseline_wer:.1%}"
                f"\n  Regression: +{regression:.1%}"
                f"\n  Environment: {environment or 'overall'}"
            )

            await self.alerts.send_alert(
                title="ASR WER Regression",
                message=alert_msg,
                severity="warning",
                channel="slack",  # Notify team
            )

            logger.warning(alert_msg)
        else:
            logger.info(
                f"WER OK: {current_wer:.1%} (baseline: {baseline_wer:.1%})"
            )

    async def _compute_wer_for_period(
        self,
        days: int,
        exclude_recent_days: int = 0,
        environment: str = None,
    ) -> Optional[float]:
        """
        Compute average WER for a time period
        """
        # Query metric database
        query = f"""
        SELECT AVG(wer) as avg_wer
        FROM asr_wer_measurements
        WHERE timestamp >= NOW() - INTERVAL {days} DAY
          AND timestamp < NOW() - INTERVAL {exclude_recent_days} DAY
        """

        if environment:
            query += f" AND environment = '{environment}'"

        result = await self.metrics.query(query)

        return result[0]["avg_wer"] if result and result[0]["avg_wer"] else None
```

---

## Component 2: TTS MOS (Mean Opinion Score) Measurement

### MOS Estimation (Passive & Active)

```python
# k1/voice/tts_quality.py

from dataclasses import dataclass
import numpy as np

@dataclass
class MOSResult:
    """MOS (Mean Opinion Score) result"""
    mos: float  # Mean Opinion Score (1.0 - 5.0)
    methodology: str  # "passive", "active"
    sample_size: int = 1  # Number of samples averaged
    confidence: float = 0.0  # Confidence in estimate
    degradation_reason: str = None  # If degraded, why?

class PassiveMOSEstimator:
    """
    Passive MOS Estimation using ML predictor

    Research: MOS-Net (Lo et al. 2019), VoiceNet (Kong et al. 2020)

    Approach:
    - Extract features from TTS audio (mel-spectrogram, MFCC)
    - Feed through trained MOS predictor model
    - Return estimated MOS (1-5)

    Advantages:
    - Fast (inference <100ms)
    - Automated (no human labeling)
    - Reproducible

    Disadvantages:
    - Model-dependent (quality depends on training data)
    - May not generalize to new TTS models
    """

    def __init__(self, model_path: str):
        """
        Initialize passive MOS estimator

        Args:
            model_path: Path to trained MOS predictor model
        """
        self.model = self._load_model(model_path)
        self.feature_extractor = FeatureExtractor()

    async def estimate_mos(self, audio_path: str) -> MOSResult:
        """
        Estimate MOS for TTS audio

        Args:
            audio_path: Path to audio file

        Returns: MOSResult
        """
        # Extract features
        features = self.feature_extractor.extract(audio_path)

        # Run MOS predictor
        mos_prediction = self.model.predict(features)

        # MOS-Net outputs probability distribution, compute mean
        mos = np.mean(mos_prediction)
        confidence = np.max(mos_prediction)  # Max probability

        return MOSResult(
            mos=float(mos),
            methodology="passive",
            confidence=float(confidence),
        )

    def _load_model(self, model_path: str):
        """Load pre-trained MOS predictor model"""
        import torch
        # Load PyTorch model
        model = torch.load(model_path)
        model.eval()
        return model

class ActiveMOSCollector:
    """
    Active MOS Collection via User Surveys

    Approach:
    - Periodically ask users: "How did that sound?"
    - Users rate on 1-5 scale
    - Aggregate ratings for A/B testing

    Advantages:
    - Ground truth (actual user perception)
    - Captures voice quality issues ML model misses

    Disadvantages:
    - Slow (need many samples)
    - Low response rates
    """

    def __init__(self, survey_frequency: float = 0.01):  # 1% of responses
        self.survey_frequency = survey_frequency
        self.survey_responses = []

    def should_survey(self) -> bool:
        """Decide if this turn should have MOS survey"""
        import random
        return random.random() < self.survey_frequency

    async def collect_mos_survey(
        self,
        turn_id: str,
        audio_path: str,
        session_id: str,
    ) -> Optional[int]:
        """
        Send MOS survey to user

        Example:
        - "How did that sound? 😊 [😞😐🙂😄😍]"

        Returns: User rating (1-5) or None if no response
        """
        # Send survey in UI
        survey_msg = "How did that sound? 😊"
        buttons = ["😞", "😐", "🙂", "😄", "😍"]  # 1-5

        # Wait for user response (5 second timeout)
        response = await self._send_survey_with_timeout(
            session_id=session_id,
            message=survey_msg,
            buttons=buttons,
            timeout_sec=5,
        )

        if response is None:
            logger.info(f"MOS survey timeout for turn {turn_id}")
            return None

        rating = response + 1  # Convert 0-4 to 1-5

        logger.info(
            f"MOS survey response: {rating}/5",
            extra={"turn_id": turn_id, "rating": rating}
        )

        # Store response
        await self._store_survey_response(
            turn_id=turn_id,
            audio_path=audio_path,
            rating=rating,
            timestamp=now(),
        )

        return rating
```

### MOS Aggregation & Tracking

```python
class MOSTracker:
    """
    Track TTS MOS across production

    Metrics:
    - Overall MOS (all TTS outputs)
    - MOS by TTS model (compare neural vs concatenative)
    - MOS by prosody settings (pitch, rate, emphasis)
    - MOS degradation under backpressure
    """

    def __init__(self, passive_estimator, active_collector):
        self.passive = passive_estimator
        self.active = active_collector
        self.metrics_client = MetricsClient()

    async def measure_mos(
        self,
        audio_path: str,
        tts_model: str,
        prosody_settings: Dict = None,
    ) -> MOSResult:
        """
        Measure MOS for TTS output (combine passive + active)
        """
        # 1. Passive MOS estimate (always)
        passive_mos = await self.passive.estimate_mos(audio_path)

        # 2. Active MOS survey (probabilistically)
        active_mos = None
        if self.active.should_survey():
            active_mos = await self.active.collect_mos_survey(audio_path)

        # Combine: passive + active (weighted)
        if active_mos:
            # Blend passive estimate with active rating
            combined_mos = 0.6 * passive_mos.mos + 0.4 * active_mos
            methodology = "hybrid"
        else:
            combined_mos = passive_mos.mos
            methodology = passive_mos.methodology

        # Emit metrics
        self.metrics_client.histogram(
            "tts_mos",
            combined_mos,
            labels={
                "tts_model": tts_model,
                "methodology": methodology,
            }
        )

        # Prosody-specific metrics
        if prosody_settings:
            for prosody, value in prosody_settings.items():
                self.metrics_client.histogram(
                    f"tts_mos_{prosody}",
                    combined_mos,
                    labels={"value": str(value)},
                )

        logger.info(
            f"TTS MOS measured: {combined_mos:.2f} ({methodology})",
            extra={
                "mos": combined_mos,
                "tts_model": tts_model,
                "methodology": methodology,
            }
        )

        return MOSResult(
            mos=combined_mos,
            methodology=methodology,
            sample_size=(2 if active_mos else 1),
        )
```

### MOS Regression Detection

```python
class MOSRegressionDetector:
    """
    Detect MOS regressions (TTS quality degradation)

    Alert if:
    - Overall MOS drops >0.5 (noticeable degradation)
    - Model-specific MOS drops >0.5
    - Prosody setting causes MOS drop >0.3
    """

    def __init__(self, metrics_client, alert_manager):
        self.metrics = metrics_client
        self.alerts = alert_manager
        self.baseline_window = 7
        self.regression_threshold_mos = 0.5  # MOS drop of 0.5 or more

    async def check_regression(self, tts_model: str = None):
        """
        Check if TTS MOS regressed
        """
        # Current MOS (last 24h)
        current_mos = await self._compute_mos_for_period(
            days=1,
            tts_model=tts_model,
        )

        # Baseline MOS (previous 7 days)
        baseline_mos = await self._compute_mos_for_period(
            days=self.baseline_window,
            exclude_recent_days=1,
            tts_model=tts_model,
        )

        if baseline_mos is None:
            logger.info("No baseline MOS yet")
            return

        # Check regression
        mos_drop = baseline_mos - current_mos

        if mos_drop >= self.regression_threshold_mos:
            # Alert: MOS regressed
            alert_msg = (
                f"⚠️ TTS MOS REGRESSION ALERT"
                f"\n  Current: {current_mos:.2f}/5.0"
                f"\n  Baseline: {baseline_mos:.2f}/5.0"
                f"\n  Drop: -{mos_drop:.2f}"
                f"\n  Model: {tts_model or 'overall'}"
            )

            await self.alerts.send_alert(
                title="TTS MOS Regression",
                message=alert_msg,
                severity="warning",
                channel="slack",
            )

            logger.warning(alert_msg)
        else:
            logger.info(
                f"TTS MOS OK: {current_mos:.2f}/5.0 (baseline: {baseline_mos:.2f}/5.0)"
            )
```

---

## Component 3: Integration & Configuration

### Voice Quality Manager

```python
class VoiceQualityManager:
    """Unified interface for voice quality measurement"""

    def __init__(self):
        self.asr_tracker = WERTracker(metrics_client)
        self.tts_tracker = MOSTracker(passive_mos, active_mos)
        self.wer_regressor = WERRegressionDetector(metrics_client, alerts)
        self.mos_regressor = MOSRegressionDetector(metrics_client, alerts)

    async def measure_asr_quality(
        self,
        hypothesis: str,
        reference: str,
        speaker_id: str,
        environment: str,
    ):
        """Measure ASR WER"""
        await self.asr_tracker.track_wer(
            reference=reference,
            hypothesis=hypothesis,
            speaker_id=speaker_id,
            environment=environment,
        )

    async def measure_tts_quality(
        self,
        audio_path: str,
        tts_model: str,
        prosody_settings: Dict = None,
    ):
        """Measure TTS MOS"""
        mos_result = await self.tts_tracker.measure_mos(
            audio_path=audio_path,
            tts_model=tts_model,
            prosody_settings=prosody_settings,
        )
        return mos_result

    async def daily_regression_check(self):
        """Run daily regression detection"""
        await self.wer_regressor.check_regression()
        await self.mos_regressor.check_regression()
```

### Metrics & Observability

```python
# k1/observability/voice_quality_metrics.py

# ASR WER Metrics
asr_wer = Histogram(
    'asr_wer',
    'Word Error Rate for ASR',
    ['environment', 'speaker_id', 'accent'],
    buckets=[0.01, 0.02, 0.05, 0.10, 0.15, 0.20],
)

asr_wer_by_environment = Histogram(
    'asr_wer_by_environment',
    'WER by environment',
    ['environment'],
    buckets=[0.01, 0.02, 0.05, 0.10, 0.15, 0.20],
)

asr_wer_by_speaker = Histogram(
    'asr_wer_by_speaker',
    'WER by speaker',
    ['speaker_id'],
    buckets=[0.01, 0.02, 0.05, 0.10, 0.15, 0.20],
)

# TTS MOS Metrics
tts_mos = Histogram(
    'tts_mos',
    'Mean Opinion Score for TTS',
    ['tts_model', 'methodology'],
    buckets=[1.0, 2.0, 3.0, 3.5, 4.0, 4.2, 4.5, 5.0],
)

tts_mos_by_model = Histogram(
    'tts_mos_by_model',
    'MOS by TTS model',
    ['tts_model'],
    buckets=[1.0, 2.0, 3.0, 3.5, 4.0, 4.2, 4.5, 5.0],
)

tts_mos_degradation = Gauge(
    'tts_mos_degradation_under_backpressure',
    'MOS drop when system under load',
    ['backpressure_level'],  # low, medium, high
)

# Reference collection metrics
reference_transcripts_collected = Counter(
    'reference_transcripts_collected_total',
    'Total reference transcripts collected',
    ['source'],  # user_correction, explicit_confirmation
)
```

### Configuration

```yaml
# k1/config/voice_quality.yml

voice_quality:
  asr:
    enabled: true
    wer_targets:
      quiet_environment: 0.06  # 6% WER
      noisy_environment: 0.12  # 12% WER
    regression_threshold: 0.05  # 5% regression alert
    measurement:
      collect_corrections: true
      collect_confirmations: true

  tts:
    enabled: true
    mos_target: 4.2  # 5-point scale
    degradation_limit: 0.5  # Max 0.5 MOS drop under backpressure
    passive_estimation:
      enabled: true
      model_path: "models/mos_predictor.pth"
    active_collection:
      enabled: true
      survey_frequency: 0.01  # 1% of responses
      survey_timeout_sec: 5
    regression_threshold: 0.5  # 0.5 MOS drop alert

  regression_detection:
    enabled: true
    check_frequency: "daily"
    baseline_window_days: 7
    alert_channel: "slack"
```

---

## Consequences

### ✅ Positive Consequences

1. **Objective Quality Metrics:** WER/MOS provide quantitative voice quality measures
2. **Regression Detection:** Automated alerts prevent quality degradation in production
3. **Model Comparison:** Can objectively compare ASR/TTS models
4. **Environment Insights:** Track performance by quiet/noisy, speaker, accent
5. **A/B Testing Ready:** Metrics infrastructure enables rigorous TTS A/B tests

### ❌ Negative Consequences

1. **Reference Transcript Collection:** Requires user corrections or confirmations (not always available)
2. **MOS Predictor Dependency:** Passive MOS estimation depends on model quality
3. **Production Overhead:** Regression detection and metrics collection add latency
4. **Survey Response Bias:** Active MOS collection biased toward users who rate (selection bias)

---

## Implementation Plan

**Phase 1 (Week 1):** WER calculation infrastructure
**Phase 2 (Week 2):** Reference transcript collection (user corrections)
**Phase 3 (Week 3):** Passive MOS estimation + ML model integration
**Phase 4 (Week 4):** Active MOS surveys + A/B testing harness
**Phase 5 (Week 5):** Regression detection + alerting

**Time Estimate:** 5 weeks

---

## Research Citations

1. Hunt et al. (1990) - "Automatic Evaluation of ASR Systems" - WER metric
2. Levenshtein (1966) - "Binary Codes Capable of Correcting Deletions, Insertions, and Reversals" - Edit distance
3. ITU-R (1993) - "Recommendation BS.1534: Method for the Subjective Assessment of Intermediate Quality Levels of Coding Audio" - MOS standard
4. Lo et al. (2019) - "MOS-Net: Deep Learning based Objective Speech Quality Assessment for Voice Conversion" - MOS-Net predictor
5. Kong et al. (2020) - "Towards End-to-End Prosody Transfer for Expressive Speech Synthesis with Tacotron" - Voice quality assessment
6. Fowler (2006) - "Continuous Integration" - Production monitoring patterns

---

**ADR-0068 END**

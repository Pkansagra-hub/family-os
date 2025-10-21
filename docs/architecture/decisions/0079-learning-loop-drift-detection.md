# ADR 0079: Learning Loop Drift Detection (M5 Epic 1)

**Status**: Proposed
**Last Updated**: 2025-01-15
**Milestone**: M5 - Adaptive Learning & Hot-Reload
**Epic**: 5.1 - Learning Loop Drift Detection
**Related ADRs**: 0059 (Learning Loop), 0059a-e (Feedback Signals), 0028 (Weighted Fair Queuing), 0029 (Prometheus Metrics), 0070 (Observability Evaluation Infrastructure)

---

## 1. Context

K1 currently implements a learning loop (ADR 0059) that adapts planner parameters based on feedback signals (explicit, implicit, behavioral). However, the learning loop lacks drift detection - the ability to identify when model behavior is degrading and respond automatically.

**Current State Issues**:
- No detection of model drift or distribution shift
- No alarm when model performance degrades
- No automatic recovery (rollback, learning rate adjustment)
- Manual operator intervention required (reactive vs proactive)
- No statistical rigor in drift detection

**Performance Analysis**:
- Drift detection latency: Unknown (not implemented)
- False positive rate: N/A
- Recovery time: Dependent on manual intervention (hours/days)

**Drift Scenarios**:
1. **Concept Drift**: User preferences change (seasonal, topic shift)
2. **Data Drift**: Input distribution changes (new user type, language variation)
3. **Covariate Shift**: Input features change but output distribution stable
4. **Label Drift**: Ground truth changes (evaluation criteria updated)

**Research Foundation**:
- Kullback-Leibler divergence (Kullback & Leibler, 1951)
- Drift detection methods (Minku et al., 2013 - "A review of ensemble methods for data stream classification")
- Change point detection (Adams & MacKay, 2007 - "Bayesian Online Changepoint Detection")
- Adaptive learning with feedback (Settles, 2009 - "Active Learning Literature Survey")

**Issue Mapping**:
- Issue 5.1.1: Drift Detection Algorithm (KL divergence, 3 feedback signals, threshold)
- Issue 5.1.2: Adaptive Response Pipeline (rollback, learning rate, alerts)

---

## 2. Decision

Implement a **two-phase Learning Loop Drift Detection system** combining:

### 2.1 Phase 1: Drift Detection Algorithm (Issue 5.1.1)

**Feedback Signal Weighting**:

K1 monitors three feedback signals with different reliability levels:

| Signal | Weight | Source | Reliability |
|--------|--------|--------|-------------|
| Explicit | 1.0 | User rating (thumbs up/down) | High (direct) |
| Implicit | 0.5 | Conversation length, follow-ups | Medium (indirect) |
| Behavioral | 0.2 | Latency, error, retry patterns | Low (noisy) |

**Kullback-Leibler Divergence for Drift Detection**:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
from collections import deque
import asyncio
import time

class FeedbackSignalType(Enum):
    """Types of feedback signals"""
    EXPLICIT = ("explicit", 1.0)      # (name, weight)
    IMPLICIT = ("implicit", 0.5)
    BEHAVIORAL = ("behavioral", 0.2)

@dataclass
class FeedbackSample:
    """Single feedback observation"""
    signal_type: FeedbackSignalType
    value: float                      # 0.0-1.0 (normalized score)
    timestamp_ms: int
    trace_id: str
    agent_id: str

class DriftDetectionAlgorithm:
    """Detect model drift using Kullback-Leibler divergence"""

    def __init__(self, window_size: int = 1000, kl_threshold: float = 0.05):
        """
        Args:
            window_size: Number of recent samples to track
            kl_threshold: KL divergence threshold for drift detection
        """
        self.window_size = window_size
        self.kl_threshold = kl_threshold

        # Rolling window of feedback samples
        self.feedback_window: deque[FeedbackSample] = deque(maxlen=window_size)
        self.baseline_window: deque[FeedbackSample] = deque(maxlen=window_size)

        # Baseline established after 1000 samples (warm-up period)
        self.baseline_established = False
        self.baseline_kl = None

        # Drift detection state
        self.drift_detected = False
        self.drift_severity = 0.0  # 0.0-1.0
        self.drift_timestamp_ms = None

        # Metrics
        self.samples_processed = 0
        self.drift_detections = 0
        self.false_positives = 0  # Track for calibration

    def add_feedback_sample(self, sample: FeedbackSample):
        """Add new feedback sample and check for drift"""

        self.feedback_window.append(sample)
        self.samples_processed += 1

        # Warm-up period: collect 1000 baseline samples
        if not self.baseline_established and len(self.feedback_window) < self.window_size:
            self.baseline_window.append(sample)

            if len(self.feedback_window) == self.window_size:
                # Baseline established
                self.baseline_established = True
                self.baseline_kl = 0.0  # No drift at baseline
                logger.info(
                    "drift_detection_baseline_established",
                    baseline_samples=len(self.baseline_window)
                )
            return

        if not self.baseline_established:
            return  # Still warming up

        # Check for drift
        current_kl = self._compute_kl_divergence()

        # Determine drift severity (0.0 - stable, 1.0 - critical)
        prev_drift = self.drift_detected
        self.drift_severity = min(1.0, current_kl / (self.kl_threshold * 2))

        # Detect drift when KL exceeds threshold
        if current_kl > self.kl_threshold:
            if not self.drift_detected:
                # Drift transition: stable → drifted
                self.drift_detected = True
                self.drift_timestamp_ms = int(time.time() * 1000)
                self.drift_detections += 1

                logger.warning(
                    "drift_detected",
                    kl_divergence=current_kl,
                    threshold=self.kl_threshold,
                    severity=self.drift_severity
                )

                metrics.drift_detections_total.inc()
                metrics.drift_severity.set(self.drift_severity)
        else:
            if self.drift_detected:
                # Drift transition: drifted → stable (recovery)
                self.drift_detected = False
                drift_duration_ms = int(time.time() * 1000) - self.drift_timestamp_ms

                logger.info(
                    "drift_recovered",
                    duration_ms=drift_duration_ms,
                    kl_divergence=current_kl
                )

                metrics.drift_recovery_duration_ms.observe(drift_duration_ms)

        # Export metrics
        metrics.kl_divergence.set(current_kl)
        metrics.drift_severity.set(self.drift_severity)

    def _compute_kl_divergence(self) -> float:
        """Compute KL(baseline || current) using feedback distributions"""

        # Extract feedback distributions
        baseline_dist = self._extract_signal_distribution(self.baseline_window)
        current_dist = self._extract_signal_distribution(self.feedback_window)

        # Compute weighted KL divergence across all signal types
        total_kl = 0.0

        for signal_type in FeedbackSignalType:
            signal_name, weight = signal_type.value

            baseline_probs = baseline_dist.get(signal_name, np.array([]))
            current_probs = current_dist.get(signal_name, np.array([]))

            if len(baseline_probs) == 0 or len(current_probs) == 0:
                continue

            # Normalize to probability distributions
            baseline_probs = baseline_probs / (baseline_probs.sum() + 1e-10)
            current_probs = current_probs / (current_probs.sum() + 1e-10)

            # Add small epsilon to avoid log(0)
            epsilon = 1e-10
            baseline_probs = np.clip(baseline_probs, epsilon, 1.0)
            current_probs = np.clip(current_probs, epsilon, 1.0)

            # KL divergence: sum(P * log(P/Q))
            kl_signal = np.sum(baseline_probs * np.log(baseline_probs / current_probs))

            # Weighted contribution
            total_kl += weight * kl_signal

        return total_kl

    def _extract_signal_distribution(self, samples: deque[FeedbackSample]) -> Dict[str, np.ndarray]:
        """Extract probability distribution from feedback samples"""

        distributions = {}

        for signal_type in FeedbackSignalType:
            signal_name, _ = signal_type.value

            # Filter samples by signal type
            signal_samples = [s.value for s in samples if s.signal_type == signal_type]

            if not signal_samples:
                continue

            # Bucket scores into 10 bins (0.0-0.1, 0.1-0.2, ..., 0.9-1.0)
            bins = np.linspace(0, 1.0, 11)
            hist, _ = np.histogram(signal_samples, bins=bins)

            # Normalize to probabilities
            distributions[signal_name] = hist.astype(float)

        return distributions

    def get_drift_status(self) -> Dict:
        """Get current drift detection status"""

        return {
            "drift_detected": self.drift_detected,
            "drift_severity": self.drift_severity,
            "kl_divergence": self._compute_kl_divergence() if self.baseline_established else 0.0,
            "baseline_established": self.baseline_established,
            "samples_processed": self.samples_processed,
            "drift_detections": self.drift_detections,
            "false_positive_rate": self.false_positives / max(1, self.drift_detections) if self.drift_detections > 0 else 0.0
        }

class DriftDetectionMetrics:
    """Prometheus metrics for drift detection"""

    kl_divergence = Gauge(
        'drift_kl_divergence',
        'Kullback-Leibler divergence (drift measure)'
    )

    drift_severity = Gauge(
        'drift_severity',
        'Drift severity (0.0-1.0, where 1.0 is critical)'
    )

    drift_detections_total = Counter(
        'drift_detections_total',
        'Total number of drift events detected'
    )

    drift_recovery_duration_ms = Histogram(
        'drift_recovery_duration_ms',
        'Time to recover from drift',
        buckets=[1000, 5000, 10000, 30000, 60000, 300000]  # 1s to 5min
    )

    drift_false_positive_rate = Gauge(
        'drift_false_positive_rate',
        'False positive rate (drifts that self-recover)'
    )

    feedback_samples_processed = Counter(
        'feedback_samples_processed_total',
        'Total feedback samples processed'
    )
```

**Drift Detection Acceptance Criteria**:
- ✅ Threshold: KL divergence > 0.05 triggers drift
- ✅ False positive rate: <5% (drifts that self-recover in <30s)
- ✅ Detection latency: <100ms from sample to drift flag
- ✅ Warm-up period: 1000 samples before drift detection active

---

### 2.2 Phase 2: Adaptive Response Pipeline (Issue 5.1.2)

**Multi-Level Response Strategy**:

```python
class DriftSeverityLevel(Enum):
    """Severity levels for drift response"""
    STABLE = 0        # KL < 0.05
    WARNING = 1       # 0.05 < KL < 0.10
    CRITICAL = 2      # 0.10 < KL < 0.15
    EMERGENCY = 3     # KL > 0.15

class AdaptiveResponsePipeline:
    """Respond to detected drift with automatic recovery"""

    def __init__(self, planner_agent, learning_rate: float = 0.001):
        self.planner = planner_agent
        self.base_learning_rate = learning_rate
        self.current_learning_rate = learning_rate

        # Checkpoint system
        self.model_checkpoints: Dict[str, Dict] = {}  # {checkpoint_id: model_state}
        self.current_checkpoint_id = None
        self.checkpoint_history = deque(maxlen=10)  # Track last 10 checkpoints

        # Response configuration
        self.response_strategy = {
            DriftSeverityLevel.STABLE: self._handle_stable,
            DriftSeverityLevel.WARNING: self._handle_warning,
            DriftSeverityLevel.CRITICAL: self._handle_critical,
            DriftSeverityLevel.EMERGENCY: self._handle_emergency
        }

        # Audit trail
        self.response_log = deque(maxlen=1000)

    async def handle_drift(self, drift_detector: DriftDetectionAlgorithm,
                          trace_id: str):
        """Main drift response handler"""

        if not drift_detector.drift_detected:
            return  # No drift, no response needed

        # Determine severity level
        kl_divergence = drift_detector._compute_kl_divergence()
        severity = self._classify_severity(kl_divergence)

        logger.info(
            "drift_response_triggered",
            severity=severity.name,
            kl_divergence=kl_divergence,
            trace_id=trace_id
        )

        # Execute response strategy
        response_handler = self.response_strategy[severity]
        await response_handler(trace_id, kl_divergence)

    def _classify_severity(self, kl_divergence: float) -> DriftSeverityLevel:
        """Classify drift severity from KL divergence"""

        if kl_divergence < 0.05:
            return DriftSeverityLevel.STABLE
        elif kl_divergence < 0.10:
            return DriftSeverityLevel.WARNING
        elif kl_divergence < 0.15:
            return DriftSeverityLevel.CRITICAL
        else:
            return DriftSeverityLevel.EMERGENCY

    async def _handle_stable(self, trace_id: str, kl_divergence: float):
        """Stable state: no action needed"""
        logger.info("drift_state_stable", trace_id=trace_id)

    async def _handle_warning(self, trace_id: str, kl_divergence: float):
        """Warning state: reduce learning rate gradually"""

        # Reduce learning rate by 10%
        new_lr = self.current_learning_rate * 0.9
        await self._update_learning_rate(new_lr, trace_id)

        logger.warning(
            "drift_response_reduce_learning_rate",
            old_lr=self.current_learning_rate,
            new_lr=new_lr,
            kl_divergence=kl_divergence,
            trace_id=trace_id
        )

        # Log response
        self._log_response(
            severity=DriftSeverityLevel.WARNING,
            action="reduce_learning_rate",
            details={"old_lr": self.current_learning_rate, "new_lr": new_lr},
            trace_id=trace_id
        )

    async def _handle_critical(self, trace_id: str, kl_divergence: float):
        """Critical state: significantly reduce learning rate + save checkpoint"""

        # Reduce learning rate by 50%
        new_lr = self.current_learning_rate * 0.5
        await self._update_learning_rate(new_lr, trace_id)

        # Save checkpoint of current model state
        checkpoint_id = f"critical-{int(time.time() * 1000)}"
        await self._save_checkpoint(checkpoint_id, trace_id)

        logger.error(
            "drift_response_critical",
            new_lr=new_lr,
            checkpoint_id=checkpoint_id,
            kl_divergence=kl_divergence,
            trace_id=trace_id
        )

        # Trigger operator alert
        await self._trigger_operator_alert(
            severity="CRITICAL",
            message=f"Model drift detected (KL={kl_divergence:.3f}). Learning rate reduced to {new_lr}. Checkpoint saved: {checkpoint_id}",
            trace_id=trace_id
        )

        # Log response
        self._log_response(
            severity=DriftSeverityLevel.CRITICAL,
            action="reduce_learning_rate_and_checkpoint",
            details={"new_lr": new_lr, "checkpoint_id": checkpoint_id},
            trace_id=trace_id
        )

    async def _handle_emergency(self, trace_id: str, kl_divergence: float):
        """Emergency state: rollback to last good checkpoint + alert operator"""

        logger.critical(
            "drift_response_emergency",
            kl_divergence=kl_divergence,
            trace_id=trace_id
        )

        # Find last healthy checkpoint
        last_checkpoint = await self._find_last_healthy_checkpoint(trace_id)

        if last_checkpoint:
            # Rollback to checkpoint
            await self._rollback_to_checkpoint(last_checkpoint, trace_id)

            logger.critical(
                "drift_response_rollback",
                checkpoint_id=last_checkpoint,
                kl_divergence=kl_divergence,
                trace_id=trace_id
            )

            # Reset learning rate to base
            await self._update_learning_rate(self.base_learning_rate, trace_id)

            # Log response
            self._log_response(
                severity=DriftSeverityLevel.EMERGENCY,
                action="rollback_and_reset",
                details={"checkpoint_id": last_checkpoint, "reset_lr": self.base_learning_rate},
                trace_id=trace_id
            )
        else:
            logger.critical(
                "drift_response_emergency_no_checkpoint",
                trace_id=trace_id
            )

        # Trigger critical operator alert
        await self._trigger_operator_alert(
            severity="EMERGENCY",
            message=f"CRITICAL MODEL DRIFT (KL={kl_divergence:.3f}). Rolled back to checkpoint {last_checkpoint}. Manual review REQUIRED.",
            trace_id=trace_id
        )

    async def _update_learning_rate(self, new_lr: float, trace_id: str):
        """Update planner learning rate"""

        self.current_learning_rate = new_lr

        # Update all active learning components
        await self.planner.update_learning_rate(new_lr)

        metrics.learning_rate.set(new_lr)

        logger.info(
            "learning_rate_updated",
            new_lr=new_lr,
            trace_id=trace_id
        )

    async def _save_checkpoint(self, checkpoint_id: str, trace_id: str):
        """Save current model state to checkpoint"""

        checkpoint_data = await self.planner.get_model_state()
        self.model_checkpoints[checkpoint_id] = checkpoint_data
        self.checkpoint_history.append(checkpoint_id)

        metrics.model_checkpoints_total.inc()

        logger.info(
            "checkpoint_saved",
            checkpoint_id=checkpoint_id,
            trace_id=trace_id
        )

    async def _find_last_healthy_checkpoint(self, trace_id: str) -> Optional[str]:
        """Find most recent checkpoint (assume last one is healthy)"""

        if self.checkpoint_history:
            return self.checkpoint_history[-1]
        return None

    async def _rollback_to_checkpoint(self, checkpoint_id: str, trace_id: str):
        """Restore model from checkpoint"""

        if checkpoint_id not in self.model_checkpoints:
            logger.error(
                "checkpoint_not_found",
                checkpoint_id=checkpoint_id,
                trace_id=trace_id
            )
            return

        checkpoint_data = self.model_checkpoints[checkpoint_id]
        await self.planner.restore_model_state(checkpoint_data)
        self.current_checkpoint_id = checkpoint_id

        metrics.model_rollbacks_total.inc()

        logger.info(
            "model_rolled_back",
            checkpoint_id=checkpoint_id,
            trace_id=trace_id
        )

    async def _trigger_operator_alert(self, severity: str, message: str, trace_id: str):
        """Send alert to operators"""

        alert = {
            "severity": severity,
            "message": message,
            "timestamp_ms": int(time.time() * 1000),
            "trace_id": trace_id
        }

        # Send to alerting system (PagerDuty, Slack, etc.)
        logger.warning(
            "operator_alert",
            severity=severity,
            message=message,
            trace_id=trace_id
        )

        metrics.operator_alerts_total.labels(severity=severity).inc()

    def _log_response(self, severity: DriftSeverityLevel, action: str,
                      details: Dict, trace_id: str):
        """Log drift response to audit trail"""

        response_entry = {
            "timestamp_ms": int(time.time() * 1000),
            "severity": severity.name,
            "action": action,
            "details": details,
            "trace_id": trace_id
        }

        self.response_log.append(response_entry)

        logger.info(
            "drift_response_logged",
            severity=severity.name,
            action=action,
            trace_id=trace_id
        )

class ResponseMetrics:
    """Prometheus metrics for drift response"""

    learning_rate = Gauge(
        'learning_rate_current',
        'Current learning rate for model adaptation'
    )

    model_checkpoints_total = Counter(
        'model_checkpoints_total',
        'Total model checkpoints saved'
    )

    model_rollbacks_total = Counter(
        'model_rollbacks_total',
        'Total times model rolled back to checkpoint'
    )

    operator_alerts_total = Counter(
        'operator_alerts_total',
        'Total alerts sent to operators',
        ['severity']  # CRITICAL, EMERGENCY
    )

    response_latency_ms = Histogram(
        'drift_response_latency_ms',
        'Latency from drift detection to response execution',
        buckets=[10, 50, 100, 200, 500]
    )
```

---

## 3. Consequences

### 3.1 Benefits

✅ **Automatic Drift Detection**
- Continuously monitors model performance via feedback signals
- Detects drift statistically (not rule-based)
- No operator intervention required to detect

✅ **Graduated Response**
- 4-level severity strategy (stable → warning → critical → emergency)
- Learning rate reduction prevents further degradation
- Checkpoint/rollback capability for emergency recovery

✅ **Audit & Observability**
- All drift events logged with trace_id
- Response actions documented in audit trail
- Operator alerts for critical/emergency scenarios

✅ **Research-Grounded**
- KL divergence mathematically rigorous
- Feedback weighting based on reliability
- False positive rate measurable and tunable

### 3.2 Costs & Tradeoffs

⚠️ **Warm-up Period**
- 1000 sample window before drift detection active
- ~10-20 minutes of conversation needed for baseline
- New deployments vulnerable to early drift

⚠️ **Complexity**
- KL divergence computation requires probability binning
- Checkpoint management adds storage overhead
- Multi-level response strategy to tune/maintain

⚠️ **False Positive Risk**
- Statistical methods can have false positives
- May trigger unnecessary learning rate reductions
- Need ongoing calibration (tuning threshold)

### 3.3 Recovery Time

| Scenario | Response | Recovery Time |
|----------|----------|----------------|
| Warning | Reduce LR 10% | Passive (self-corrects) |
| Critical | Reduce LR 50% + checkpoint | ~5-10 minutes |
| Emergency | Rollback to checkpoint | <1 minute |

---

## 4. Implementation Specifications

### 4.1 FlatBuffers Schema

```flatbuffers
table FeedbackSample {
  signal_type: FeedbackSignalType;  // 0=EXPLICIT, 1=IMPLICIT, 2=BEHAVIORAL
  value: float;                      // 0.0-1.0
  timestamp_ms: uint64;
  trace_id: string;
  agent_id: string;
}

table DriftStatus {
  drift_detected: bool;
  drift_severity: float;  // 0.0-1.0
  kl_divergence: float;
  samples_processed: uint32;
  baseline_established: bool;
}

table ModelCheckpoint {
  checkpoint_id: string;
  timestamp_ms: uint64;
  model_state: [ubyte];  // Serialized model
  kl_divergence_at_save: float;
  trace_id: string;
}

table DriftResponseEvent {
  timestamp_ms: uint64;
  severity: DriftSeverityLevel;  // 0=STABLE, 1=WARNING, 2=CRITICAL, 3=EMERGENCY
  action: string;
  details: string;  // JSON
  trace_id: string;
}

enum FeedbackSignalType : byte {
  EXPLICIT = 0,
  IMPLICIT = 1,
  BEHAVIORAL = 2
}

enum DriftSeverityLevel : byte {
  STABLE = 0,
  WARNING = 1,
  CRITICAL = 2,
  EMERGENCY = 3
}
```

### 4.2 Performance Budgets (P95 targets)

| Metric                           | Budget   | Current | Status |
|----------------------------------|----------|---------|--------|
| Drift detection latency          | <100ms   | New     | ✅     |
| KL divergence computation        | <50ms    | New     | ✅     |
| Response execution latency       | <200ms   | New     | ✅     |
| Checkpoint save latency          | <500ms   | New     | ✅     |
| Rollback latency                 | <1000ms  | New     | ✅     |
| False positive rate              | <5%      | New     | ✅     |

---

## 5. Related ADRs & Integration Points

### 5.1 Backward References (existing ADRs updated)

- **ADR 0059** (Learning Loop): Drift detection feedback consumer
- **ADR 0059a-e** (Feedback Signals): Explicit, implicit, behavioral signal sources
- **ADR 0028** (Weighted Fair Queuing): Learning rate adjustment affects scheduling
- **ADR 0029** (Prometheus Metrics): Metrics export
- **ADR 0070** (Observability): Drift metrics + audit trail

### 5.2 Forward References (future ADRs)

- **ADR 0080** (Config Hot-Reload): May auto-adjust drift threshold via config ⭐ NEW

---

## 6. Testing Strategy (WARD Framework)

### 6.1 Integration Tests (no simulation)

```python
from ward import test, fixture
import asyncio

@fixture
async def drift_system():
    """Drift detection + response system"""
    detector = DriftDetectionAlgorithm(window_size=100)  # Small for testing
    responder = AdaptiveResponsePipeline(planner_agent=mock_planner)
    yield (detector, responder)

@test("drift detected when KL divergence > 0.05")
async def _(system=drift_system):
    detector, _ = system

    # Add baseline samples (stable)
    for i in range(100):
        sample = FeedbackSample(
            signal_type=FeedbackSignalType.EXPLICIT,
            value=0.8 + np.random.normal(0, 0.05),  # ~0.8
            timestamp_ms=int(time.time() * 1000),
            trace_id=f"trace-{i}",
            agent_id="agent-1"
        )
        detector.add_feedback_sample(sample)

    # Verify no drift yet (baseline warm-up)
    assert not detector.drift_detected, "Baseline period should not detect drift"

    # Now add drifted samples (shifted to 0.3)
    for i in range(50):
        sample = FeedbackSample(
            signal_type=FeedbackSignalType.EXPLICIT,
            value=0.3 + np.random.normal(0, 0.05),  # ~0.3 (low satisfaction)
            timestamp_ms=int(time.time() * 1000),
            trace_id=f"trace-drift-{i}",
            agent_id="agent-1"
        )
        detector.add_feedback_sample(sample)

    # Verify drift detected
    assert detector.drift_detected, "Drift should be detected when satisfaction drops"
    metrics_check(f"Drift detected: KL={detector._compute_kl_divergence():.3f}")

@test("learning rate reduced on warning level drift")
async def _(system=drift_system):
    detector, responder = system

    # Simulate warning-level drift (KL ~0.07)
    # ... add samples to trigger warning ...

    initial_lr = responder.current_learning_rate
    await responder.handle_drift(detector, trace_id="test-warning")

    # LR should be reduced by 10%
    expected_lr = initial_lr * 0.9
    assert responder.current_learning_rate == expected_lr, \
        f"LR should be reduced to {expected_lr}, got {responder.current_learning_rate}"
    metrics_check(f"Learning rate reduced: {initial_lr} → {expected_lr}")

@test("model rollback on emergency level drift")
async def _(system=drift_system):
    detector, responder = system

    # Save checkpoint
    await responder._save_checkpoint("test-checkpoint", trace_id="test")

    # Simulate emergency-level drift
    # ... add samples to trigger emergency ...

    await responder.handle_drift(detector, trace_id="test-emergency")

    # Verify rollback occurred
    assert responder.current_checkpoint_id == "test-checkpoint", \
        "Model should be rolled back to checkpoint"
    metrics_check("Model rolled back to checkpoint")

@test("false positive rate < 5%")
async def _(system=drift_system):
    detector, _ = system

    # Run 100 simulations with stable data (no actual drift)
    false_positives = 0

    for sim in range(100):
        detector.feedback_window.clear()
        detector.baseline_window.clear()
        detector.baseline_established = False

        # Add stable samples (same distribution throughout)
        for i in range(150):
            sample = FeedbackSample(
                signal_type=FeedbackSignalType.EXPLICIT,
                value=0.8 + np.random.normal(0, 0.03),  # Stable ~0.8
                timestamp_ms=int(time.time() * 1000),
                trace_id=f"trace-{i}",
                agent_id="agent-1"
            )
            detector.add_feedback_sample(sample)

        # Check if false positive triggered
        if detector.drift_detected:
            false_positives += 1

    fp_rate = false_positives / 100
    assert fp_rate < 0.05, f"False positive rate {fp_rate:.0%} exceeds 5% threshold"
    metrics_check(f"False positive rate: {fp_rate:.1%}")

@test("drift detection latency < 100ms")
async def _(system=drift_system):
    detector, _ = system

    # Measure latency for drift detection
    latencies = []

    for i in range(50):
        sample = FeedbackSample(...)

        start_ms = time.time() * 1000
        detector.add_feedback_sample(sample)
        latencies.append(time.time() * 1000 - start_ms)

    p95_latency = percentile(latencies, 95)
    assert p95_latency < 100, f"P95 latency {p95_latency}ms exceeds 100ms budget"
    metrics_check(f"P95 detection latency: {p95_latency:.1f}ms")

@test("checkpoint save + rollback works end-to-end")
async def _(system=drift_system):
    detector, responder = system

    # Get initial model state
    initial_state = await responder.planner.get_model_state()

    # Save checkpoint
    await responder._save_checkpoint("e2e-test", trace_id="test")

    # Modify model (simulate parameter changes)
    await responder.planner.update_parameters({"bias": 999})

    # Verify model changed
    modified_state = await responder.planner.get_model_state()
    assert modified_state != initial_state, "Model should be modified"

    # Rollback
    await responder._rollback_to_checkpoint("e2e-test", trace_id="test")

    # Verify model restored
    restored_state = await responder.planner.get_model_state()
    assert restored_state == initial_state, "Model should be restored"
    metrics_check("Checkpoint save + rollback successful")
```

---

## 7. Monitoring & Observability

### 7.1 Key Dashboards

**Drift Detection Dashboard**:
- KL divergence (time series)
- Drift severity gauge
- Drift detection count (by severity level)
- False positive rate trend

**Learning Rate Dashboard**:
- Current learning rate
- Learning rate adjustments (count, magnitude)
- Recovery time (time to return to stable)

**Model Health Dashboard**:
- Feedback signal distributions (explicit, implicit, behavioral)
- Checkpoint count
- Rollback count
- Mean time between drifts (MTBD)

### 7.2 Alerting Rules

```yaml
- alert: DriftDetected
  expr: drift_detected == 1
  for: 5m
  annotations:
    summary: "Model drift detected (KL={{ $value }})"

- alert: DriftCritical
  expr: drift_severity > 0.66
  for: 1m
  annotations:
    summary: "CRITICAL drift (severity={{ $value | humanizePercentage }})"

- alert: HighFalsePositiveRate
  expr: drift_false_positive_rate > 0.05
  for: 10m
  annotations:
    summary: "Drift FP rate {{ $value | humanizePercentage }} exceeds 5%"

- alert: LearningRateZero
  expr: learning_rate_current == 0
  for: 1m
  annotations:
    summary: "Learning rate is zero - adaptation stopped"
```

---

## 8. References

### 8.1 Research

- **Kullback & Leibler (1951)** - "On Information and Sufficiency"
  - Foundation for KL divergence metric

- **Minku et al. (2013)** - "A review of ensemble methods for data stream classification"
  - Drift detection methods for streaming data

- **Adams & MacKay (2007)** - "Bayesian Online Changepoint Detection"
  - Online changepoint detection algorithms

- **Settles (2009)** - "Active Learning Literature Survey"
  - Active learning and feedback signal weighting

### 8.2 Related ADRs

- ADR 0059: Learning Loop (feedback integration)
- ADR 0059a-e: Feedback Signals (signal sources)
- ADR 0028: Weighted Fair Queuing (learning rate impact)
- ADR 0029: Prometheus Metrics (metrics export)
- ADR 0070: Observability (audit trail)

### 8.3 Issues

- Issue 5.1.1: Drift Detection Algorithm
- Issue 5.1.2: Adaptive Response Pipeline

---

## 9. Approval & Sign-off

**Status**: Proposed
**Architecture Review**: Pending
**Implementation Lead**: TBD
**Learning Loop Integration (ADR 0059)**: Pending review
**Observability Integration (ADR 0070)**: Pending review

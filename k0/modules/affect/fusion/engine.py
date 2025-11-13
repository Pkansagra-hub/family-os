"""Multi-modal fusion engine with EMA smoothing (ADR-0012d)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from pydantic import ValidationError

from ..models import AffectEMAState, CalibrationParams, ModalityScore

LOGGER = logging.getLogger(__name__)


class FusionEngine:
    """Confidence-weighted fusion with dual EMA + calibration."""

    FAST_ALPHA_DEFAULT = 0.5
    SLOW_ALPHA = 0.1
    CACHE_TTL_SECONDS = 300.0

    def __init__(
        self,
        *,
        storage: Optional[Any] = None,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        self.storage = storage
        self.cache_ttl_seconds = cache_ttl_seconds
        self._ema_cache: Dict[Tuple[str, str], Tuple[AffectEMAState, float]] = {}
        self._calibration_cache: Dict[str, CalibrationParams] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fuse_and_smooth(
        self,
        *,
        person_id: str,
        space_id: str,
        modality_scores: Sequence[Union[ModalityScore, Dict]],
        apply_calibration: bool = True,
        timestamp: Optional[float] = None,
    ) -> Tuple[float, float, float, Dict[str, float]]:
        """Fuse modality scores, apply calibration, and update EMA."""

        ts = timestamp or time.time()
        normalized_scores = self._normalize_scores(modality_scores)
        if not normalized_scores:
            state = self._get_ema_state(person_id, space_id, ts)
            attribution = {"no_modalities": 0.0}
            return state.v_fast, state.a_fast, 0.0, attribution

        valence_fused, arousal_fused, confidence_fused, attribution = self._fuse_modalities(
            normalized_scores
        )

        calibration = self._get_calibration(person_id)
        if apply_calibration:
            valence_fused, arousal_fused = self._apply_calibration(
                valence_fused, arousal_fused, calibration
            )

        state = self._get_ema_state(person_id, space_id, ts)
        updated_state = self._update_ema(
            state,
            valence_fused,
            arousal_fused,
            confidence_fused,
            calibration.alpha_fast,
            ts,
        )
        self._persist_ema_state(person_id, space_id, updated_state, ts)

        attribution.update(
            {
                "calibration_valence_bias": calibration.valence_bias,
                "calibration_arousal_bias": calibration.arousal_bias,
                "calibration_valence_temp": calibration.valence_temp,
                "calibration_arousal_temp": calibration.arousal_temp,
                "samples": updated_state.n_observations,
            }
        )

        return updated_state.v_fast, updated_state.a_fast, confidence_fused, attribution

    def update_calibration_params(self, params: CalibrationParams) -> None:
        """Store calibration params provided by P06."""

        params.last_updated = params.last_updated or time.time()
        self._calibration_cache[params.person_id] = params

    def get_trend(self, person_id: str, space_id: str) -> Tuple[str, float]:
        """Return trend label derived from fast/slow EMA divergence."""

        ts = time.time()
        state = self._get_ema_state(person_id, space_id, ts)
        v_div = state.v_fast - state.v_slow
        a_div = state.a_fast - state.a_slow

        v_trend = "improving" if v_div > 0.2 else "declining" if v_div < -0.2 else "stable"
        a_trend = "rising" if a_div > 0.2 else "falling" if a_div < -0.2 else "stable"

        return f"valence_{v_trend}_arousal_{a_trend}", abs(v_div) + abs(a_div)

    def clear_cache(self) -> None:
        """Clear EMA and calibration caches (testing utility)."""

        self._ema_cache.clear()
        self._calibration_cache.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_scores(
        self, modality_scores: Sequence[Union[ModalityScore, Dict]]
    ) -> List[ModalityScore]:
        normalized: List[ModalityScore] = []
        for score in modality_scores:
            if isinstance(score, ModalityScore):
                normalized.append(score)
                continue
            try:
                normalized.append(ModalityScore(**score))
            except (ValidationError, TypeError) as exc:
                LOGGER.warning("Dropped invalid modality score", extra={"error": str(exc)})
        return normalized

    def _fuse_modalities(
        self, scores: Sequence[ModalityScore]
    ) -> Tuple[float, float, float, Dict[str, float]]:
        if not scores:
            return 0.0, 0.0, 0.0, {}

        attribution: Dict[str, float] = {}

        valence_components = [(s.valence, s.confidence) for s in scores if s.valence != 0.0]
        if valence_components:
            total_weight_v = sum(conf for _, conf in valence_components) or 1.0
            valence_fused = sum(val * conf for val, conf in valence_components) / total_weight_v
        else:
            valence_fused = 0.0

        arousal_components = [(s.arousal, s.confidence) for s in scores]
        total_weight_a = sum(conf for _, conf in arousal_components) or 1.0
        arousal_fused = sum(arousal * conf for arousal, conf in arousal_components) / total_weight_a

        confidence_fused = sum(s.confidence for s in scores) / len(scores)

        for s in scores:
            source_name = s.source.value if hasattr(s.source, "value") else str(s.source)
            attribution[f"{source_name}_confidence"] = s.confidence
            attribution[f"{source_name}_arousal"] = s.arousal
            if s.valence != 0.0:
                attribution[f"{source_name}_valence"] = s.valence

        return valence_fused, arousal_fused, confidence_fused, attribution

    def _get_ema_state(self, person_id: str, space_id: str, timestamp: float) -> AffectEMAState:
        key = (person_id, space_id)
        cached = self._ema_cache.get(key)
        if cached:
            state, cached_ts = cached
            if timestamp - cached_ts <= self.cache_ttl_seconds:
                return state
            self._ema_cache.pop(key, None)

        if self.storage is not None:
            stored = self.storage.get_ema_state(person_id, space_id)
            if stored:
                self._ema_cache[key] = (stored, timestamp)
                return stored

        state = AffectEMAState(
            person_id=person_id,
            space_id=space_id,
            v_fast=0.0,
            a_fast=0.3,
            v_slow=0.0,
            a_slow=0.3,
            last_update=timestamp,
            n_observations=0,
        )
        self._ema_cache[key] = (state, timestamp)
        return state

    def _update_ema(
        self,
        state: AffectEMAState,
        valence: float,
        arousal: float,
        confidence: float,
        alpha_fast: float,
        timestamp: float,
    ) -> AffectEMAState:
        alpha_fast = max(0.3, min(0.7, alpha_fast or self.FAST_ALPHA_DEFAULT))

        state.v_fast = alpha_fast * valence + (1 - alpha_fast) * state.v_fast
        state.a_fast = alpha_fast * arousal + (1 - alpha_fast) * state.a_fast
        state.v_slow = self.SLOW_ALPHA * valence + (1 - self.SLOW_ALPHA) * state.v_slow
        state.a_slow = self.SLOW_ALPHA * arousal + (1 - self.SLOW_ALPHA) * state.a_slow
        state.n_observations += 1
        state.last_update = timestamp
        return state

    def _persist_ema_state(
        self, person_id: str, space_id: str, state: AffectEMAState, timestamp: float
    ) -> None:
        self._ema_cache[(person_id, space_id)] = (state, timestamp)
        if self.storage is not None:
            try:
                self.storage.update_ema_state(state)
            except NotImplementedError:
                LOGGER.debug("AffectStorage update_ema_state not implemented yet")

    def _get_calibration(self, person_id: str) -> CalibrationParams:
        params = self._calibration_cache.get(person_id)
        if params:
            return params

        params = CalibrationParams(
            person_id=person_id,
            valence_bias=0.0,
            arousal_bias=0.0,
            valence_temp=1.0,
            arousal_temp=1.0,
            alpha_fast=self.FAST_ALPHA_DEFAULT,
            n_feedback_samples=0,
            last_updated=time.time(),
        )
        self._calibration_cache[person_id] = params
        return params

    def _apply_calibration(
        self, valence: float, arousal: float, params: CalibrationParams
    ) -> Tuple[float, float]:
        v_cal = params.valence_temp * (valence + params.valence_bias)
        a_cal = params.arousal_temp * (arousal + params.arousal_bias)
        v_cal = max(-1.0, min(1.0, v_cal))
        a_cal = max(0.0, min(1.0, a_cal))
        return v_cal, a_cal

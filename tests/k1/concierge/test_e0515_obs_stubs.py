"""
Tests for E-0.5.15 -- Concierge Missing Observability Submodules.

Verifies all 6 stub submodules exist, are importable from obs package,
and have correct placeholder classes with functional methods.
"""

from __future__ import annotations

from k1.concierge.obs.metrics import MetricsCollector

# =====================================================================
# Import tests -- verify all 6 submodules are importable
# =====================================================================


class TestObsSubmoduleImports:
    """All 6 stub submodules must be importable from k1.concierge.obs."""

    def test_import_alerts(self):
        from k1.concierge.obs import AlertEngine, AlertEvent, AlertRule

        assert AlertRule is not None
        assert AlertEngine is not None
        assert AlertEvent is not None

    def test_import_fsm_metrics(self):
        from k1.concierge.obs import FSMMetricsSubscriber

        assert FSMMetricsSubscriber is not None

    def test_import_hitl_metrics(self):
        from k1.concierge.obs import HITLMetricsSubscriber

        assert HITLMetricsSubscriber is not None

    def test_import_arbiter_metrics(self):
        from k1.concierge.obs import ArbiterMetricsSubscriber

        assert ArbiterMetricsSubscriber is not None

    def test_import_weave_metrics(self):
        from k1.concierge.obs import WeaveMetricsSubscriber

        assert WeaveMetricsSubscriber is not None

    def test_import_phase1_metrics(self):
        from k1.concierge.obs import Phase1MetricsSubscriber

        assert Phase1MetricsSubscriber is not None

    def test_all_exports_in___all__(self):
        import k1.concierge.obs as obs

        expected_new = {
            "AlertRule",
            "AlertEngine",
            "AlertEvent",
            "FSMMetricsSubscriber",
            "HITLMetricsSubscriber",
            "ArbiterMetricsSubscriber",
            "WeaveMetricsSubscriber",
            "Phase1MetricsSubscriber",
        }
        assert expected_new.issubset(set(obs.__all__))


# =====================================================================
# AlertEngine functional tests
# =====================================================================


class TestAlertEngine:
    """AlertEngine registers rules and evaluates metrics."""

    def test_register_rule(self):
        from k1.concierge.obs.alerts import AlertEngine, AlertRule

        engine = AlertEngine()
        rule = AlertRule(rule_id="r1", metric_name="cpu", threshold=90.0)
        engine.register_rule(rule)
        assert len(engine.rules) == 1
        assert engine.rules[0].rule_id == "r1"

    def test_evaluate_triggers_on_gt(self):
        from k1.concierge.obs.alerts import AlertEngine, AlertRule

        engine = AlertEngine()
        engine.register_rule(
            AlertRule(rule_id="r1", metric_name="cpu", threshold=90.0, comparator="gt")
        )
        events = engine.evaluate("cpu", 95.0)
        assert len(events) == 1
        assert events[0].rule_id == "r1"
        assert events[0].observed_value == 95.0

    def test_evaluate_no_trigger_below_threshold(self):
        from k1.concierge.obs.alerts import AlertEngine, AlertRule

        engine = AlertEngine()
        engine.register_rule(
            AlertRule(rule_id="r1", metric_name="cpu", threshold=90.0, comparator="gt")
        )
        events = engine.evaluate("cpu", 80.0)
        assert len(events) == 0

    def test_evaluate_different_metric_ignored(self):
        from k1.concierge.obs.alerts import AlertEngine, AlertRule

        engine = AlertEngine()
        engine.register_rule(AlertRule(rule_id="r1", metric_name="cpu", threshold=90.0))
        events = engine.evaluate("memory", 95.0)
        assert len(events) == 0

    def test_fired_events_accumulated(self):
        from k1.concierge.obs.alerts import AlertEngine, AlertRule

        engine = AlertEngine()
        engine.register_rule(AlertRule(rule_id="r1", metric_name="cpu", threshold=90.0))
        engine.evaluate("cpu", 95.0)
        engine.evaluate("cpu", 99.0)
        assert len(engine.fired_events) == 2


# =====================================================================
# Subscriber stub tests -- verify construction + method calls
# =====================================================================


class TestFSMMetricsSubscriber:
    def test_construction_no_collector(self):
        from k1.concierge.obs.fsm_metrics import FSMMetricsSubscriber

        sub = FSMMetricsSubscriber()
        sub.on_transition("IDLE", "PLANNING")  # no-op, no crash

    def test_on_transition_emits_metric(self):
        from k1.concierge.obs.fsm_metrics import FSMMetricsSubscriber

        collector = MetricsCollector(session_id="s1")
        sub = FSMMetricsSubscriber(collector=collector)
        sub.on_transition("IDLE", "PLANNING", dwell_ms=100.0)
        assert len(collector.drain_pending()) > 0


class TestHITLMetricsSubscriber:
    def test_construction_no_collector(self):
        from k1.concierge.obs.hitl_metrics import HITLMetricsSubscriber

        sub = HITLMetricsSubscriber()
        sub.on_hitl_request("RELAY")  # no-op, no crash

    def test_on_request_emits_metric(self):
        from k1.concierge.obs.hitl_metrics import HITLMetricsSubscriber

        collector = MetricsCollector(session_id="s1")
        sub = HITLMetricsSubscriber(collector=collector)
        sub.on_hitl_request("RELAY")
        assert len(collector.drain_pending()) > 0

    def test_on_response_emits_latency(self):
        from k1.concierge.obs.hitl_metrics import HITLMetricsSubscriber

        collector = MetricsCollector(session_id="s1")
        sub = HITLMetricsSubscriber(collector=collector)
        sub.on_hitl_response("RELAY", latency_ms=500.0)
        drained = collector.drain_pending()
        assert len(drained) >= 2  # count + latency


class TestArbiterMetricsSubscriber:
    def test_construction_no_collector(self):
        from k1.concierge.obs.arbiter_metrics import ArbiterMetricsSubscriber

        sub = ArbiterMetricsSubscriber()
        sub.on_decision("approve")  # no-op, no crash

    def test_on_decision_emits_metric(self):
        from k1.concierge.obs.arbiter_metrics import ArbiterMetricsSubscriber

        collector = MetricsCollector(session_id="s1")
        sub = ArbiterMetricsSubscriber(collector=collector)
        sub.on_decision("approve", latency_ms=50.0)
        assert len(collector.drain_pending()) > 0


class TestWeaveMetricsSubscriber:
    def test_construction_no_collector(self):
        from k1.concierge.obs.weave_metrics import WeaveMetricsSubscriber

        sub = WeaveMetricsSubscriber()
        sub.on_weave_execution(policy_matched=True)  # no-op, no crash

    def test_on_execution_emits_metric(self):
        from k1.concierge.obs.weave_metrics import WeaveMetricsSubscriber

        collector = MetricsCollector(session_id="s1")
        sub = WeaveMetricsSubscriber(collector=collector)
        sub.on_weave_execution(policy_matched=True, quality_score=0.85)
        assert len(collector.drain_pending()) > 0


class TestPhase1MetricsSubscriber:
    def test_construction_no_collector(self):
        from k1.concierge.obs.phase1_metrics import Phase1MetricsSubscriber

        sub = Phase1MetricsSubscriber()
        sub.on_classification("greeting")  # no-op, no crash

    def test_on_classification_emits_metric(self):
        from k1.concierge.obs.phase1_metrics import Phase1MetricsSubscriber

        collector = MetricsCollector(session_id="s1")
        sub = Phase1MetricsSubscriber(collector=collector)
        sub.on_classification("greeting", confidence=0.95, latency_ms=12.0)
        assert len(collector.drain_pending()) > 0

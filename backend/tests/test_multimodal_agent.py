from __future__ import annotations

import asyncio

from app.agents.multimodal_predictive_agent import MultimodalPredictiveAgent
from app.models import OperatorFeedback, RandomSimulationConfig
from app.science.calculation_modules import ScientificPredictionEngine
from app.simulator.random_stream import RandomTelemetryGenerator


def test_random_stream_is_bounded_and_correlated():
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=1234, scenario="mixed", intensity=0.8, noise=0.15, step_minutes=5)
    )

    snapshots = [generator.latest()]
    for _ in range(32):
        snapshots.append(generator.advance())

    assert all(0 <= item.battery_percent <= 100 for item in snapshots)
    assert all(0 <= item.gpu_utilization_percent <= 100 for item in snapshots)
    assert all(35 <= item.gpu_temperature_celsius <= 110 for item in snapshots)
    assert all(item.ecc_corrected_errors >= 0 for item in snapshots)
    assert snapshots[-1].ecc_corrected_errors >= snapshots[0].ecc_corrected_errors

    high_power = [item for item in snapshots if item.gpu_power_watts > 3300]
    low_power = [item for item in snapshots if item.gpu_power_watts < 2200]
    if high_power and low_power:
        assert max(item.gpu_temperature_celsius for item in high_power) >= min(
            item.gpu_temperature_celsius for item in low_power
        )


def test_multimodal_agent_produces_predictive_result():
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=777, scenario="radiation_pass", intensity=0.9, noise=0.1, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(24):
        history.append(generator.advance())

    engine = ScientificPredictionEngine()
    assessment = engine.assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    result = agent.analyze_stream(history[-1], history, assessment)

    assert result.source == "local"
    assert result.module_results
    assert result.evidence
    assert result.reasoning_trace
    assert result.recommended_actions
    assert any(item.modality == "image" for item in result.multimodal_inputs)
    assert any(item.modality == "calculation" for item in result.multimodal_inputs)
    assert any(item.modality == "thermal" for item in result.multimodal_inputs)


def test_deep_agent_adds_default_multimodal_inputs_and_feedback():
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=90210, scenario="scheduler_mismatch", intensity=0.85, noise=0.1, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(16):
        history.append(generator.advance())

    engine = ScientificPredictionEngine()
    assessment = engine.assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    agent.record_feedback(
        OperatorFeedback(
            message="Prefer conservative operations during validation.",
            risk_tolerance="conservative",
            policy_notes=["preserve checkpoint evidence before destructive action"],
        )
    )

    result = agent.analyze_stream(history[-1], history, assessment)
    assert result.adaptation_notes
    assert agent.memory.feedback_count == 1
    assert agent.export_training_examples()


def test_chat_answers_thermal_question_with_thermal_context(monkeypatch):
    monkeypatch.setenv("MOCK_CRUSOE", "true")
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=411, scenario="thermal_ramp", intensity=0.9, noise=0.08, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(20):
        history.append(generator.advance())

    assessment = ScientificPredictionEngine().assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    result = asyncio.run(
        agent.answer_chat(
            "What is the thermal risk, and which measurements prove it?",
            history[-1],
            history,
            assessment,
        )
    )

    answer = (result.response_text or "").lower()
    assert "thermal_physical" in answer
    assert "temperature" in answer or "thermal" in answer
    assert "score" in answer


def test_chat_intents_produce_distinct_answers(monkeypatch):
    monkeypatch.setenv("MOCK_CRUSOE", "true")
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=944, scenario="radiation_pass", intensity=0.85, noise=0.12, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(18):
        history.append(generator.advance())

    assessment = ScientificPredictionEngine().assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    evidence = asyncio.run(agent.answer_chat("Give me the evidence behind the diagnosis", history[-1], history, assessment))
    refusal = asyncio.run(agent.answer_chat("If I reject the action, what happens next?", history[-1], history, assessment))

    assert evidence.response_text != refusal.response_text
    assert "primary evidence" in (evidence.response_text or "").lower()
    assert "if you reject" in (refusal.response_text or "").lower()


def test_chat_explains_multimodal_bundle(monkeypatch):
    monkeypatch.setenv("MOCK_CRUSOE", "true")
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=5331, scenario="mixed", intensity=0.78, noise=0.12, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(12):
        history.append(generator.advance())

    assessment = ScientificPredictionEngine().assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    result = asyncio.run(
        agent.answer_chat(
            "How does Nemotron use the topology image and multimodal bundle?",
            history[-1],
            history,
            assessment,
        )
    )

    answer = (result.response_text or "").lower()
    assert "telemetry json" in answer
    assert "topology image" in answer
    assert "calculation outputs" in answer


def test_nemotron_training_pack_is_complete_and_video_free():
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=6331, scenario="mixed", intensity=0.8, noise=0.12, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(14):
        history.append(generator.advance())

    assessment = ScientificPredictionEngine().assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    agent.analyze_stream(history[-1], history, assessment)
    pack = agent.build_nemotron_training_pack(history[-1], history, assessment)

    assert "Nemotron-3-Nano-Omni-Reasoning-30B-A3B" in pack["model"]
    assert pack["system_prompt"]
    assert pack["few_shot_examples"]
    assert pack["evaluation_questions"]
    assert pack["grading_rubric"]
    modality_names = {item["name"] for item in pack["modalities"]}
    assert {"telemetry", "calculation", "thermal", "image", "operator_message"} <= modality_names
    assert "video" not in modality_names
    bundle_modalities = {item["modality"] for item in pack["current_context"]["multimodal_bundle"]}
    assert "video" not in bundle_modalities


def test_overheat_recommends_operator_approved_action():
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=9331, scenario="thermal_ramp", intensity=1.0, noise=0.05, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(10):
        history.append(generator.advance())

    hot_snapshot = history[-1].model_copy(
        update={
            "gpu_temperature_celsius": 96.8,
            "hbm_temperature_c": 104.2,
            "board_temperature_celsius": 73.4,
            "radiator_temperature_celsius": 71.5,
            "gpu_power_watts": 4380.0,
            "compute_power_watts": 4380.0,
            "thermal_control_power_watts": 900.0,
            "thermal_throttle_flag": True,
        }
    )
    history.append(hot_snapshot)

    assessment = ScientificPredictionEngine().assess(hot_snapshot, generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    result = agent.analyze_stream(hot_snapshot, history, assessment)

    action = result.recommended_actions[0]
    assert result.primary_driver in {"thermal_physical", "workload_gpu", "orbit_power", "radiation_integrity", "checkpoint_downlink"}
    assert action["source_module"] == "thermal_physical"
    assert action["approval"] is True
    assert action["approval_status"] == "pending"
    assert action["gate"] == "operator_approval"

    agent.record_feedback(
        OperatorFeedback(
            message=f"Approve {action['action_id']}",
            accepted_action_ids=[action["action_id"]],
            policy_notes=["operator approved thermal power reduction"],
        )
    )
    approved = agent.analyze_stream(hot_snapshot, history, assessment)
    approved_action = approved.recommended_actions[0]
    assert approved_action["approval_status"] == "approved"


def test_chat_answers_nemotron_training_question(monkeypatch):
    monkeypatch.setenv("MOCK_CRUSOE", "true")
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=7331, scenario="thermal_ramp", intensity=0.78, noise=0.12, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(12):
        history.append(generator.advance())

    assessment = ScientificPredictionEngine().assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    result = asyncio.run(
        agent.answer_chat(
            "Explain how Nemotron 3 is trained and evaluated for this mission agent.",
            history[-1],
            history,
            assessment,
        )
    )

    answer = (result.response_text or "").lower()
    assert "training" in answer
    assert "evaluation" in answer
    assert "nemotron" in answer
    assert "telemetry" in answer


def test_chat_handles_broad_french_and_what_if_questions(monkeypatch):
    monkeypatch.setenv("MOCK_CRUSOE", "true")
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=8123, scenario="power_eclipse", intensity=0.86, noise=0.12, step_minutes=5)
    )
    history = [generator.latest()]
    for _ in range(18):
        history.append(generator.advance())

    assessment = ScientificPredictionEngine().assess(history[-1], generator.elapsed_minutes, history)
    agent = MultimodalPredictiveAgent()
    broad = asyncio.run(agent.answer_chat("Tu peux faire quoi exactement comme agent ?", history[-1], history, assessment))
    what_if = asyncio.run(agent.answer_chat("Que se passe-t-il si la batterie baisse encore ?", history[-1], history, assessment))
    calc = asyncio.run(agent.answer_chat("Explique comment le score est calcule", history[-1], history, assessment))

    assert "Je peux" in (broad.response_text or "")
    assert "Scenario hypothetique" in (what_if.response_text or "")
    assert "Calcul" in (calc.response_text or "")


def test_random_stream_remains_realistic_over_long_infinite_run():
    generator = RandomTelemetryGenerator(
        RandomSimulationConfig(seed=424242, scenario="mixed", intensity=0.82, noise=0.16, step_minutes=5)
    )

    snapshots = [generator.latest()]
    for _ in range(800):
        snapshots.append(generator.advance())

    assert len({item.orbit_phase for item in snapshots}) >= 3
    assert any(item.downlink_window_seconds > 0 for item in snapshots)
    assert any(item.downlink_window_seconds == 0 for item in snapshots)
    assert max(item.gpu_temperature_celsius for item in snapshots) - min(item.gpu_temperature_celsius for item in snapshots) > 8
    assert max(item.battery_percent for item in snapshots) <= 100
    assert min(item.battery_percent for item in snapshots) >= 0
    assert snapshots[-1].timestamp > snapshots[0].timestamp

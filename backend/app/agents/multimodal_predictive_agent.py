from __future__ import annotations

import asyncio
import base64
import json
import os
import unicodedata
from typing import Any

from ..crusoe_client import get_crusoe_openai_client, mock_mode, nemotron_omni_model
from ..models import (
    AgentMemoryState,
    AgentTrainingExample,
    MultimodalObservation,
    OperatorFeedback,
    PredictiveAgentResult,
    Severity,
    TelemetrySnapshot,
    utc_now,
)
from ..science.calculation_modules import severity_from_score
from ..science.types import ModulePredictionResult, ScientificAssessment


SYSTEM_PROMPT = """You are OrbitOps Multimodal Predictive Agent.
Use the provided telemetry, calculation module outputs, thermal readout, operator feedback, and topology image.
You must use evidence from the payload, not generic advice.
Do not reveal hidden chain-of-thought. Provide an auditable reasoning trace made of concise evidence steps.
Return JSON only with these keys:
predicted_event, confidence, evidence, reasoning_trace, recommended_actions, operator_questions, adaptation_notes, response_text.
Recommended actions must be reversible unless critical risk requires escalation.
"""


class MultimodalPredictiveAgent:
    def __init__(self) -> None:
        self.memory = AgentMemoryState()

    def record_feedback(self, feedback: OperatorFeedback) -> AgentMemoryState:
        self.memory.feedback_count += 1
        self.memory.risk_tolerance = feedback.risk_tolerance
        self.memory.policy_notes = _dedupe([*self.memory.policy_notes, *feedback.policy_notes])[-12:]
        self.memory.accepted_action_ids = _dedupe([*self.memory.accepted_action_ids, *feedback.accepted_action_ids])[-40:]
        self.memory.rejected_action_ids = _dedupe([*self.memory.rejected_action_ids, *feedback.rejected_action_ids])[-40:]
        return self.memory

    def analyze_stream(
        self,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
        observations: list[MultimodalObservation] | None = None,
    ) -> PredictiveAgentResult:
        enriched_observations = self._default_observations(snapshot, assessment, observations or [], None)
        result = self._local_result(snapshot, history, assessment, enriched_observations, source="local", mode="stream")
        self._remember_result(result, snapshot, assessment)
        return result

    async def analyze_deep(
        self,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
        observations: list[MultimodalObservation] | None = None,
        message: str | None = None,
        force_crusoe: bool = False,
    ) -> PredictiveAgentResult:
        observations = self._default_observations(snapshot, assessment, observations or [], message)
        local = self._local_result(snapshot, history, assessment, observations, source="local", mode="deep_analysis")
        if mock_mode() and not force_crusoe:
            self._remember_result(local, snapshot, assessment)
            return local
        try:
            result = await self._crusoe_result(snapshot, history, assessment, observations, local, mode="deep_analysis")
            self._remember_result(result, snapshot, assessment)
            return result
        except Exception as exc:
            fallback = local.model_copy(
                update={
                    "source": "fallback",
                    "adaptation_notes": [
                        *local.adaptation_notes,
                        f"Crusoe analysis unavailable: {str(exc)[:180]}",
                    ],
                }
            )
            self._remember_result(fallback, snapshot, assessment)
            return fallback

    async def answer_chat(
        self,
        message: str,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
        observations: list[MultimodalObservation] | None = None,
        force_crusoe: bool = False,
    ) -> PredictiveAgentResult:
        observations = self._default_observations(snapshot, assessment, observations or [], message)
        local = self._local_result(snapshot, history, assessment, observations, source="local", mode="chat")
        local.response_text = self._local_chat_answer(message, snapshot, history, assessment, local)
        if mock_mode() and not force_crusoe:
            self._remember_result(local, snapshot, assessment)
            return local
        try:
            result = await self._crusoe_result(snapshot, history, assessment, observations, local, mode="chat")
            self._remember_result(result, snapshot, assessment)
            return result
        except Exception as exc:
            fallback = local.model_copy(
                update={
                    "source": "fallback",
                    "adaptation_notes": [
                        *local.adaptation_notes,
                        f"Crusoe chat unavailable: {str(exc)[:180]}",
                    ],
                }
            )
            self._remember_result(fallback, snapshot, assessment)
            return fallback

    def export_training_examples(self) -> list[AgentTrainingExample]:
        return self.memory.training_examples[-100:]

    def build_nemotron_training_pack(
        self,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
    ) -> dict[str, Any]:
        observations = self._default_observations(
            snapshot,
            assessment,
            [],
            "Build a training and evaluation pack for the OrbitOps multimodal mission agent.",
        )
        baseline = self._local_result(snapshot, history, assessment, observations, source="local", mode="chat")
        return {
            "version": "orbitops-nemotron-training-pack-v1",
            "purpose": "Supervised evaluation and in-context training pack for the OrbitOps autonomous multimodal agent.",
            "model": nemotron_omni_model(),
            "crusoe_inference": {
                "base_url": "https://api.inference.crusoecloud.com/v1/",
                "api_key_env": "CRUSOE_API_KEY",
                "model": nemotron_omni_model(),
                "mode": "chat.completions multimodal reasoning",
            },
            "system_prompt": SYSTEM_PROMPT,
            "modalities": _nemotron_training_modalities(),
            "response_contract": {
                "format": "json_object",
                "required_keys": [
                    "predicted_event",
                    "confidence",
                    "evidence",
                    "reasoning_trace",
                    "recommended_actions",
                    "operator_questions",
                    "adaptation_notes",
                    "response_text",
                ],
                "constraints": [
                    "Ground every answer in telemetry, calculation, thermal, topology or operator-memory evidence.",
                    "Prefer reversible actions before destructive or human-gated commands.",
                    "Expose concise evidence steps, not hidden chain-of-thought.",
                    "State uncertainty and ask an operator question when the action gate is ambiguous.",
                ],
            },
            "current_context": {
                "snapshot": snapshot.model_dump(mode="json"),
                "scientific_assessment": assessment.model_dump(mode="json"),
                "multimodal_bundle": [obs.model_dump(mode="json") for obs in observations],
                "local_baseline": baseline.model_dump(mode="json", exclude={"module_results", "multimodal_inputs"}),
            },
            "few_shot_examples": _nemotron_few_shot_examples(snapshot, assessment, baseline),
            "evaluation_questions": _nemotron_eval_questions(snapshot, assessment),
            "grading_rubric": _nemotron_grading_rubric(),
            "live_training_examples": [item.model_dump(mode="json") for item in self.export_training_examples()],
            "operator_memory": self.memory.model_dump(mode="json", exclude={"recent_predictions", "training_examples"}),
            "recommended_usage": [
                "Use this pack as the payload context for Nemotron 3 during deep analysis and chatbot evaluation.",
                "Replay evaluation_questions against /api/agents/chat with force_crusoe=true and grade the JSON response using grading_rubric.",
                "Append accepted operator corrections to AgentTrainingExample records before future fine-tuning or provider-side supervised training.",
            ],
        }

    def _local_result(
        self,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
        observations: list[MultimodalObservation],
        source: str,
        mode: str,
    ) -> PredictiveAgentResult:
        primary = max(assessment.modules, key=lambda module: module.risk_score)
        eta = _estimate_eta(primary, assessment)
        severity = _adaptive_severity(assessment.overall_risk_score, self.memory.risk_tolerance)
        evidence = _evidence_from_assessment(assessment)
        trace = [
            f"Forecast mode {assessment.data_mode} uses {assessment.samples_used} samples over {assessment.trend_window_minutes:.1f} minutes.",
            f"Primary driver is {assessment.primary_driver} at {assessment.primary_risk_score:.1f}/100.",
            f"Compound risk is {assessment.compound_risk_score:.1f}/100, so correlated modules are considered.",
            f"Current state: phase={snapshot.orbit_phase.value}, battery={snapshot.battery_percent:.1f}%, GPU={snapshot.gpu_temperature_celsius:.1f}C, ECC={snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors}.",
        ]
        if self.memory.rejected_action_ids:
            trace.append("Operator rejection history is applied before repeating actions.")
        actions = _actions_for_assessment(
            primary,
            assessment,
            self.memory.rejected_action_ids,
            self.memory.accepted_action_ids,
        )
        questions = _operator_questions(primary, snapshot, self.memory.risk_tolerance)
        notes = _adaptation_notes(self.memory)
        response = (
            f"{primary.module_name}: {primary.predicted_event}. "
            f"Overall risk {assessment.overall_risk_score:.1f}/100 ({severity.value}); "
            f"recommended decision: {primary.recommended_decision}."
        )
        return PredictiveAgentResult(
            source=source,  # type: ignore[arg-type]
            model=nemotron_omni_model() if source == "crusoe" else "local-scientific-orchestrator",
            mission_id=snapshot.mission_id,
            mode=mode,  # type: ignore[arg-type]
            multimodal_inputs=observations,
            overall_risk_score=assessment.overall_risk_score,
            severity=severity,
            primary_driver=assessment.primary_driver,
            predicted_event=primary.predicted_event,
            eta_minutes=eta,
            confidence=round(min(0.97, max(0.38, primary.confidence * (0.92 + 0.04 * len(history) / 24))), 3),
            evidence=evidence,
            reasoning_trace=trace,
            recommended_actions=actions,
            operator_questions=questions,
            adaptation_notes=notes,
            module_results=[module.model_dump(mode="json") for module in assessment.modules],
            performance_metrics=_performance_metrics(assessment, history, eta),
            response_text=response,
        )

    async def _crusoe_result(
        self,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
        observations: list[MultimodalObservation],
        local: PredictiveAgentResult,
        mode: str,
    ) -> PredictiveAgentResult:
        payload = _llm_payload(snapshot, history, assessment, observations, self.memory, local)
        image_uri = next((obs.uri for obs in observations if obs.modality == "image" and obs.uri), None)
        client = get_crusoe_openai_client()
        model = nemotron_omni_model()
        response = await asyncio.to_thread(
            _invoke_crusoe,
            client,
            model,
            payload,
            image_uri,
        )
        parsed = _parse_json_response(response)
        result = local.model_copy(
            update={
                "source": "crusoe",
                "model": model,
                "mode": mode,
                "predicted_event": parsed.get("predicted_event") or local.predicted_event,
                "confidence": _clamped_float(parsed.get("confidence"), local.confidence, 0, 1),
                "evidence": _string_list(parsed.get("evidence")) or local.evidence,
                "reasoning_trace": _string_list(parsed.get("reasoning_trace")) or local.reasoning_trace,
                "recommended_actions": _dict_list(parsed.get("recommended_actions")) or local.recommended_actions,
                "operator_questions": _string_list(parsed.get("operator_questions")) or local.operator_questions,
                "adaptation_notes": _string_list(parsed.get("adaptation_notes")) or local.adaptation_notes,
                "response_text": parsed.get("response_text") or local.response_text,
            }
        )
        return result

    def _default_observations(
        self,
        snapshot: TelemetrySnapshot,
        assessment: ScientificAssessment,
        observations: list[MultimodalObservation],
        message: str | None,
    ) -> list[MultimodalObservation]:
        defaults = [
            MultimodalObservation(
                modality="telemetry",
                summary="Current telemetry snapshot",
                content=_snapshot_summary(snapshot),
            ),
            MultimodalObservation(
                modality="calculation",
                summary="Calculation module assessment",
                content={
                    "overall_risk_score": assessment.overall_risk_score,
                    "primary_driver": assessment.primary_driver,
                    "global_action": assessment.global_action,
                    "modules": [
                        {
                            "module_id": module.module_id,
                            "risk_score": module.risk_score,
                            "severity": module.severity.value,
                            "predicted_event": module.predicted_event,
                            "dashboard_summary": module.dashboard_summary,
                        }
                        for module in assessment.modules
                    ],
                },
            ),
            MultimodalObservation(
                modality="thermal",
                summary="Thermal sensor readout",
                content=_thermal_readout(snapshot, assessment),
            ),
            MultimodalObservation(
                modality="image",
                summary="Professional mission topology heatmap",
                mime_type="image/svg+xml",
                uri=_topology_svg_uri(snapshot, assessment),
            ),
        ]
        if message:
            defaults.append(MultimodalObservation(modality="operator_message", summary="Operator message", content=message))
        return [*defaults, *observations]

    def _local_chat_answer(
        self,
        message: str,
        snapshot: TelemetrySnapshot,
        history: list[TelemetrySnapshot],
        assessment: ScientificAssessment,
        result: PredictiveAgentResult,
    ) -> str:
        lower = _normalized_text(message)
        french = _prefers_french(lower)
        primary = _primary_module(assessment)
        explicit_target = _module_for_query(lower, assessment)
        targeted = explicit_target or primary

        if _mentions_any(lower, ("bonjour", "salut", "hello", "hi ", "hey", "tu peux", "what can you", "que peux tu", "capable", "help", "aide")):
            return _capabilities_answer(french)

        if _mentions_any(lower, ("training", "train", "trained", "fine tune", "finetune", "evaluation", "evaluated", "eval", "dataset", "formation", "entrain", "entrainement")):
            return _training_answer(assessment, result, french)

        if _mentions_any(lower, ("mission", "satellite", "orbite", "orbit", "akja", "where", "position", "location", "phase")):
            return _mission_answer(snapshot, assessment, result, french)

        if _mentions_any(lower, ("what if", "suppose", "scenario", "simulate", "si ", "si la", "si le", "si on", "que se passe", "hypothese", "hypothetical")):
            return _what_if_answer(lower, snapshot, assessment, result, french)

        if _mentions_any(lower, ("formule", "formula", "calcul", "calculation", "score", "computed", "comment est calcule", "how is", "derive", "equation")):
            return _calculation_answer(targeted, assessment, result, french)

        if _mentions_any(lower, ("trend", "timeline", "historique", "evolution", "tendance", "last tick", "derniere", "change", "monte", "baisse")):
            return _trend_answer(snapshot, history, assessment, result, french)

        if _mentions_any(lower, ("agent autonome", "autonomous", "commander", "decision loop", "boucle", "observe", "reasoning loop", "qui decide", "who decides")):
            return _autonomy_answer(assessment, result, french)

        if _mentions_any(lower, ("explain", "definition", "meaning", "c est quoi", "c'est quoi", "veut dire", "glossary", "eta", "ecc", "downlink", "checkpoint")):
            return _glossary_answer(lower, snapshot, assessment, result, french)

        if _mentions_any(lower, ("preuve", "evidence", "pourquoi", "raison", "justifie", "explique")):
            return _evidence_answer(primary, result, french)

        if _mentions_any(lower, ("si je refuse", "refuse", "reject", "rejected", "without action", "sans action", "no action", "ne rien faire", "ignore")):
            safest = _first_reversible_action(result.recommended_actions)
            return _rejection_answer(primary, assessment, safest, french)

        if _mentions_any(lower, ("action", "recommande", "decision", "faire", "corriger", "mitiger", "plan")):
            return _action_answer(targeted, assessment, result, french)

        if _mentions_any(lower, ("confiance", "incertitude", "fiable", "qualite", "precision")):
            return _confidence_answer(primary, assessment, result, french)

        if _mentions_any(lower, ("multimodal", "nemotron", "topology", "image", "visual", "schema", "diagram", "thermal readout", "lecture")):
            return _multimodal_answer(result, french)

        if explicit_target is not None:
            return _module_answer(targeted, assessment, result, french)

        if _mentions_any(lower, ("module", "compare", "classement", "priorite", "drivers", "tous")):
            return _module_ranking_answer(assessment, french)

        if _mentions_any(lower, ("etat", "status", "resume", "synthese", "situation", "risque")):
            return _status_answer(snapshot, history, assessment, result, french)

        return _fallback_answer(primary, assessment, result, french)

    def _remember_result(self, result: PredictiveAgentResult, snapshot: TelemetrySnapshot, assessment: ScientificAssessment) -> None:
        self.memory.recent_predictions = [result, *self.memory.recent_predictions[:23]]
        self.memory.training_examples = [
            AgentTrainingExample(
                input_summary={
                    "snapshot": _snapshot_summary(snapshot),
                    "assessment": {
                        "overall_risk_score": assessment.overall_risk_score,
                        "primary_driver": assessment.primary_driver,
                        "modules": [
                            {
                                "module_id": module.module_id,
                                "risk_score": module.risk_score,
                                "predicted_event": module.predicted_event,
                            }
                            for module in assessment.modules
                        ],
                    },
                },
                expected_output={
                    "predicted_event": result.predicted_event,
                    "severity": result.severity.value,
                    "evidence": result.evidence,
                    "recommended_actions": result.recommended_actions,
                },
            ),
            *self.memory.training_examples[:99],
        ]


def _invoke_crusoe(client: Any, model: str, payload: dict[str, Any], image_uri: str | None) -> str:
    text = json.dumps(payload, indent=2)
    content: Any = [{"type": "text", "text": text}]
    if image_uri:
        content.append({"type": "image_url", "image_url": {"url": image_uri}})
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=1800,
        )
    choice = response.choices[0]
    return getattr(choice.message, "content", "") or ""


def _llm_payload(
    snapshot: TelemetrySnapshot,
    history: list[TelemetrySnapshot],
    assessment: ScientificAssessment,
    observations: list[MultimodalObservation],
    memory: AgentMemoryState,
    local: PredictiveAgentResult,
) -> dict[str, Any]:
    recent = history[-12:]
    return {
        "task": "real-time multimodal prediction and operator interaction",
        "model_required": nemotron_omni_model(),
        "current_snapshot": snapshot.model_dump(mode="json"),
        "recent_history": [item.model_dump(mode="json") for item in recent],
        "scientific_assessment": assessment.model_dump(mode="json"),
        "multimodal_observations": [obs.model_dump(mode="json") for obs in observations],
        "operator_memory": memory.model_dump(mode="json", exclude={"recent_predictions", "training_examples"}),
        "local_baseline": local.model_dump(mode="json", exclude={"module_results", "multimodal_inputs"}),
        "conversation_training_hints": _conversation_training_hints(local),
        "response_requirements": {
            "no_hidden_chain_of_thought": True,
            "auditable_reasoning_trace": True,
            "prefer_reversible_actions": True,
            "ask_operator_questions_when_uncertainty_blocks_action": True,
        },
    }


def _nemotron_training_modalities() -> list[dict[str, str]]:
    return [
        {
            "name": "telemetry",
            "purpose": "Current and historical orbital datacenter measurements: power, orbit phase, GPU, ECC and downlink.",
        },
        {
            "name": "calculation",
            "purpose": "Scientific module outputs, risk scores, formulas, severity and recommended decisions.",
        },
        {
            "name": "thermal",
            "purpose": "Derived thermal readout with margin, hotspot probability and cooling pressure.",
        },
        {
            "name": "image",
            "purpose": "Topology heatmap as a visual modality for cross-checking risk concentration.",
        },
        {
            "name": "operator_message",
            "purpose": "Natural-language operator intent, feedback and policy constraints.",
        },
    ]


def _conversation_training_hints(local: PredictiveAgentResult) -> list[dict[str, Any]]:
    return [
        {
            "operator_question": "What should I do first?",
            "expected_behavior": "Rank by immediate mission risk, recommend the least destructive reversible action, and cite evidence.",
            "baseline_action": _action_title(local.recommended_actions),
        },
        {
            "operator_question": "Why is this diagnosis credible?",
            "expected_behavior": "Use telemetry, calculation, thermal and topology evidence; avoid generic spacecraft advice.",
            "baseline_evidence": local.evidence[:3],
        },
        {
            "operator_question": "What changes if I reject the action?",
            "expected_behavior": "Explain operational consequence, keep the risk score grounded, and propose a lower-impact fallback.",
            "baseline_eta_minutes": local.eta_minutes,
        },
    ]


def _nemotron_few_shot_examples(
    snapshot: TelemetrySnapshot,
    assessment: ScientificAssessment,
    baseline: PredictiveAgentResult,
) -> list[dict[str, Any]]:
    primary = _primary_module(assessment)
    return [
        {
            "input": {
                "question": "Give me the mission state in operator language.",
                "telemetry_focus": ["orbit_phase", "battery_percent", "gpu_temperature_celsius", "downlink_capacity_gb"],
            },
            "expected_output": {
                "response_text": (
                    f"Mission {snapshot.mission_id} is in {snapshot.orbit_phase.value}; risk is "
                    f"{assessment.overall_risk_score:.1f}/100 with {assessment.primary_driver} as the main driver."
                ),
                "must_include": ["risk score", "primary driver", "next reversible action"],
            },
        },
        {
            "input": {
                "question": "What if the operator rejects the proposed action?",
                "risk_context": baseline.predicted_event,
            },
            "expected_output": {
                "response_text": (
                    "State that the predicted event remains active, keep the global risk grounded, "
                    "and offer a less intrusive monitoring or evidence-preservation fallback."
                ),
                "must_include": ["consequence", "fallback", "uncertainty"],
            },
        },
        {
            "input": {
                "question": "Explain the calculation behind the main driver.",
                "module": primary.module_id,
            },
            "expected_output": {
                "response_text": (
                    f"Explain {primary.module_id} with score {primary.risk_score:.1f}/100, severity "
                    f"{primary.severity.value}, dominant metrics and formula summary."
                ),
                "must_include": ["module score", "dominant metrics", "formula sketch"],
            },
        },
    ]


def _nemotron_eval_questions(snapshot: TelemetrySnapshot, assessment: ScientificAssessment) -> list[dict[str, Any]]:
    return [
        {
            "id": "broad_capabilities",
            "question": "What can you do as an autonomous multimodal OrbitOps agent?",
            "expected_focus": ["capabilities", "modalities", "operator interaction"],
        },
        {
            "id": "evidence_grounding",
            "question": "Why is the current diagnosis credible? Cite the telemetry and calculation evidence.",
            "expected_focus": ["evidence", assessment.primary_driver, "risk score"],
        },
        {
            "id": "what_if_power",
            "question": "What if battery drops by 10 percent during eclipse while downlink remains closed?",
            "expected_focus": ["power reserve", "downlink", "reversible action"],
        },
        {
            "id": "thermal_visual",
            "question": "Use the thermal readout and topology image to explain whether we have a hotspot problem.",
            "expected_focus": ["thermal margin", "visual topology", "uncertainty"],
        },
        {
            "id": "calculation_modules",
            "question": "Rank the current calculation modules and explain the top two drivers.",
            "expected_focus": ["module ranking", "calculation", "primary driver"],
        },
        {
            "id": "operator_rejection",
            "question": "If I reject your proposed action, what is the safest fallback?",
            "expected_focus": ["rejection consequence", "fallback", "mission risk"],
        },
        {
            "id": "french_broad",
            "question": "Explique la situation et la meilleure action reversible en francais.",
            "expected_focus": ["French answer", "risk", "action"],
        },
        {
            "id": "current_snapshot",
            "question": (
                f"At phase {snapshot.orbit_phase.value}, with battery {snapshot.battery_percent:.1f}% and "
                f"GPU {snapshot.gpu_temperature_celsius:.1f}C, what should the operator watch next?"
            ),
            "expected_focus": ["current snapshot", "watch item", "operator question"],
        },
    ]


def _nemotron_grading_rubric() -> list[dict[str, Any]]:
    return [
        {
            "criterion": "grounding",
            "weight": 0.28,
            "pass_condition": "Uses current telemetry, calculation modules, thermal readout or topology input; no generic answer.",
        },
        {
            "criterion": "action_quality",
            "weight": 0.22,
            "pass_condition": "Recommends reversible action first unless the risk is critical and human approval is required.",
        },
        {
            "criterion": "operator_interaction",
            "weight": 0.18,
            "pass_condition": "Answers the written question directly and asks a useful follow-up only when needed.",
        },
        {
            "criterion": "uncertainty",
            "weight": 0.14,
            "pass_condition": "States limits, confidence or ambiguity without exposing hidden chain-of-thought.",
        },
        {
            "criterion": "json_contract",
            "weight": 0.18,
            "pass_condition": "Returns the required JSON keys with valid evidence, reasoning_trace and response_text fields.",
        },
    ]


def _parse_json_response(content: str) -> dict[str, Any]:
    content = content.strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return {"response_text": content[:1200]}
        return {"response_text": content[:1200]}


def _estimate_eta(primary: ModulePredictionResult, assessment: ScientificAssessment) -> float | None:
    if primary.severity in {Severity.HIGH, Severity.CRITICAL}:
        return 0.0
    if assessment.overall_risk_score >= 60:
        return float(max(5, primary.prediction_horizon_minutes // 3))
    if assessment.overall_risk_score >= 42:
        return float(max(10, primary.prediction_horizon_minutes // 2))
    return None


def _adaptive_severity(score: float, tolerance: str) -> Severity:
    adjusted = score
    if tolerance == "conservative":
        adjusted += 5
    elif tolerance == "aggressive":
        adjusted -= 5
    return severity_from_score(adjusted)


def _evidence_from_assessment(assessment: ScientificAssessment) -> list[str]:
    ranked = sorted(assessment.modules, key=lambda module: module.risk_score, reverse=True)
    evidence = [
        f"Global risk {assessment.overall_risk_score:.1f}/100; primary {assessment.primary_driver}; compound {assessment.compound_risk_score:.1f}/100.",
    ]
    for module in ranked[:4]:
        evidence.append(
            f"{module.module_id}: {module.risk_score:.1f}/100 {module.severity.value}; {module.predicted_event}; {module.dashboard_summary}"
        )
    return evidence


def _normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def _mentions_any(value: str, fragments: tuple[str, ...]) -> bool:
    return any(_normalized_text(fragment) in value for fragment in fragments)


def _prefers_french(query: str) -> bool:
    french_markers = (
        "quoi",
        "pourquoi",
        "comment",
        "peux",
        "peut",
        "fais",
        "faire",
        "risque",
        "preuve",
        "donne",
        "explique",
        "si je",
        "que se passe",
        "c est",
        "c'est",
        "batterie",
        "thermique",
        "puissance",
        "orbite",
        "etat",
        "resume",
    )
    return _mentions_any(query, french_markers)


def _primary_module(assessment: ScientificAssessment) -> ModulePredictionResult:
    return next((module for module in assessment.modules if module.module_id == assessment.primary_driver), assessment.modules[0])


def _module_for_query(query: str, assessment: ScientificAssessment) -> ModulePredictionResult | None:
    keyword_map = {
        "thermal_physical": (
            "thermal",
            "thermique",
            "temperature",
            "radiateur",
            "radiator",
            "cool",
            "chauffe",
            "hotspot",
        ),
        "orbit_power": (
            "battery",
            "batterie",
            "energie",
            "power",
            "puissance",
            "eclipse",
            "solar",
            "solaire",
            "reserve",
        ),
        "radiation_integrity": (
            "radiation",
            "ecc",
            "bit",
            "flip",
            "integrite",
            "canary",
            "hash",
            "rollback",
            "corruption",
        ),
        "checkpoint_downlink": (
            "downlink",
            "contact",
            "transmettre",
            "payload",
            "recovery",
            "ground",
            "ack",
            "stockage",
            "storage",
            "checkpoint",
        ),
        "workload_gpu": (
            "scheduler",
            "cuda",
            "workload",
            "job",
            "process",
            "memoire",
            "memory",
            "utilisation",
            "stall",
            "nccl",
            "gpu",
        ),
    }
    modules = {module.module_id: module for module in assessment.modules}
    best: tuple[int, ModulePredictionResult] | None = None
    for module_id, keywords in keyword_map.items():
        module = modules.get(module_id)
        if not module:
            continue
        score = sum(1 for keyword in keywords if keyword in query)
        if score and (best is None or score > best[0] or (score == best[0] and module.risk_score > best[1].risk_score)):
            best = (score, module)
    return best[1] if best else None


def _capabilities_answer(french: bool) -> str:
    if french:
        return (
            "Je peux repondre a des questions larges sur la mission, les risques, les preuves, les calculs, "
            "les modules agents, les actions recommandees, les scenarios hypothetique, la lecture thermique, "
            "l'image topology et le bundle multimodal envoye a Nemotron. Tu peux ecrire normalement, par exemple: "
            "'pourquoi ce risque ?', 'que se passe-t-il si la batterie baisse ?', ou 'compare thermique et downlink'."
        )
    return (
        "I can answer broad written questions about mission state, risk, evidence, calculations, domain agents, "
        "recommended actions, what-if scenarios, thermal/topology readings, and the multimodal bundle sent to Nemotron. "
        "You can write naturally, for example: 'why this risk?', 'what if battery drops?', or 'compare thermal and downlink'."
    )


def _mission_answer(
    snapshot: TelemetrySnapshot,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    if french:
        return (
            f"Mission {snapshot.mission_id}: phase {snapshot.orbit_phase.value}, risque {assessment.overall_risk_score:.1f}/100, "
            f"driver {assessment.primary_driver}. Etat courant: GPU {snapshot.gpu_temperature_celsius:.1f}C, "
            f"batterie {snapshot.battery_percent:.1f}%, downlink {snapshot.downlink_capacity_gb:.2f}GB, "
            f"ECC {snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors}. Prochaine decision: {_action_title(result.recommended_actions)}."
        )
    return (
        f"Mission {snapshot.mission_id}: phase {snapshot.orbit_phase.value}, risk {assessment.overall_risk_score:.1f}/100, "
        f"driver {assessment.primary_driver}. Current state: GPU {snapshot.gpu_temperature_celsius:.1f}C, "
        f"battery {snapshot.battery_percent:.1f}%, downlink {snapshot.downlink_capacity_gb:.2f}GB, "
        f"ECC {snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors}. Next decision: {_action_title(result.recommended_actions)}."
    )


def _what_if_answer(
    query: str,
    snapshot: TelemetrySnapshot,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    focused = _scenario_focus(query)
    base = assessment.overall_risk_score
    if focused == "battery":
        delta = 10 if snapshot.battery_percent < 25 else 6
        consequence = "power reserve becomes the governing constraint before compute scheduling"
        action = "reduce compute power budget and preserve downlink/cooling reserve"
        fr_consequence = "la reserve d'energie devient la contrainte principale avant le scheduling compute"
        fr_action = "reduire le budget compute et reserver l'energie pour downlink/refroidissement"
    elif focused == "thermal":
        delta = 8 if snapshot.gpu_temperature_celsius >= 80 else 5
        consequence = "thermal margin shrinks and throttling risk rises"
        action = "increase checkpoint frequency, then lower GPU power if the margin keeps shrinking"
        fr_consequence = "la marge thermique diminue et le risque de throttling augmente"
        fr_action = "augmenter les checkpoints, puis baisser la puissance GPU si la marge continue de baisser"
    elif focused == "downlink":
        delta = 7 if snapshot.downlink_capacity_gb < 1 else 4
        consequence = "the system must prioritize compact evidence over full checkpoint transfer"
        action = "send manifest, hashes and critical logs before large checkpoint payloads"
        fr_consequence = "le systeme doit prioriser les preuves compactes plutot que le checkpoint complet"
        fr_action = "envoyer manifest, hashes et logs critiques avant les gros checkpoints"
    elif focused == "radiation":
        delta = 9
        consequence = "checkpoint trust and ECC integrity become the main blockers"
        action = "run canary validation and keep rollback options protected"
        fr_consequence = "la confiance checkpoint et l'integrite ECC deviennent les blocages principaux"
        fr_action = "lancer une validation canary et proteger les options de rollback"
    else:
        delta = 5
        consequence = "the agent would re-rank modules and choose the least destructive reversible action first"
        action = "request deep Nemotron analysis if the operator needs a new plan"
        fr_consequence = "l'agent reclasserait les modules et choisirait d'abord l'action reversible la moins destructive"
        fr_action = "demander une analyse Nemotron si l'operateur veut un nouveau plan"
    projected = min(100.0, base + delta)
    if french:
        return (
            f"Scenario hypothetique ({focused}): le risque passerait approximativement de {base:.1f}/100 a {projected:.1f}/100. "
            f"Effet probable: {fr_consequence}. Action prudente: {fr_action}. "
            "Ce n'est pas une nouvelle simulation physique complete; c'est une projection locale basee sur les modules actuels."
        )
    return (
        f"What-if scenario ({focused}): risk would move roughly from {base:.1f}/100 to {projected:.1f}/100. "
        f"Likely effect: {consequence}. Conservative action: {action}. "
        "This is not a full physical re-simulation; it is a local projection based on the current modules."
    )


def _scenario_focus(query: str) -> str:
    if _mentions_any(query, ("battery", "batterie", "power", "energie", "eclipse")):
        return "battery"
    if _mentions_any(query, ("thermal", "thermique", "temperature", "heat", "chauffe")):
        return "thermal"
    if _mentions_any(query, ("downlink", "contact", "checkpoint", "storage", "stockage")):
        return "downlink"
    if _mentions_any(query, ("radiation", "ecc", "bit", "integrity", "integrite")):
        return "radiation"
    return "general"


def _calculation_answer(
    module: ModulePredictionResult,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    formulas = "; ".join(module.formula_summary[:3]) if module.formula_summary else "formula summary unavailable"
    metrics = _metric_summary(module)
    if french:
        return (
            f"Calcul pour {module.module_id}: score {module.risk_score:.1f}/100, severite {module.severity.value}. "
            f"Mesures dominantes: {metrics}. Formules utilisees: {formulas}. "
            f"Le score global {assessment.overall_risk_score:.1f}/100 combine le module primaire, le risque compose et la confiance agent {result.confidence:.0%}."
        )
    return (
        f"Calculation for {module.module_id}: score {module.risk_score:.1f}/100, severity {module.severity.value}. "
        f"Dominant measurements: {metrics}. Formula sketch: {formulas}. "
        f"The global score {assessment.overall_risk_score:.1f}/100 combines primary module pressure, compound risk and agent confidence {result.confidence:.0%}."
    )


def _trend_answer(
    snapshot: TelemetrySnapshot,
    history: list[TelemetrySnapshot],
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    previous = history[-2] if len(history) >= 2 else None
    if previous:
        temp_delta = snapshot.gpu_temperature_celsius - previous.gpu_temperature_celsius
        battery_delta = snapshot.battery_percent - previous.battery_percent
        downlink_delta = snapshot.downlink_capacity_gb - previous.downlink_capacity_gb
    else:
        temp_delta = battery_delta = downlink_delta = 0.0
    metrics = result.performance_metrics
    if french:
        return (
            f"Tendance recente: temperature {temp_delta:+.1f}C/tick, batterie {battery_delta:+.1f}%/tick, "
            f"downlink {downlink_delta:+.2f}GB/tick. Fenetre {assessment.trend_window_minutes:.1f} min avec {assessment.samples_used} echantillons. "
            f"Lead time estime: {_eta_text(result.eta_minutes)}. Ratio compose/primaire: {metrics.get('compound_to_primary_ratio', '--')}."
        )
    return (
        f"Recent trend: temperature {temp_delta:+.1f}C/tick, battery {battery_delta:+.1f}%/tick, "
        f"downlink {downlink_delta:+.2f}GB/tick. Window {assessment.trend_window_minutes:.1f} min with {assessment.samples_used} samples. "
        f"Estimated lead time: {_eta_text(result.eta_minutes)}. Compound/primary ratio: {metrics.get('compound_to_primary_ratio', '--')}."
    )


def _autonomy_answer(assessment: ScientificAssessment, result: PredictiveAgentResult, french: bool) -> str:
    question = result.operator_questions[0] if result.operator_questions else "No blocking operator question."
    notes = " ".join(result.adaptation_notes[:2])
    if french:
        return (
            f"Mode agent autonome: observer les flux, calculer les modules, raisonner sur le driver {assessment.primary_driver}, "
            f"puis proposer une action reversible. Action actuelle: {_action_title(result.recommended_actions)}. "
            f"Question operateur: {question} Notes memoire: {notes or 'aucune'}."
        )
    return (
        f"Autonomous agent mode: observe streams, calculate modules, reason over driver {assessment.primary_driver}, "
        f"then propose a reversible action. Current action: {_action_title(result.recommended_actions)}. "
        f"Operator question: {question} Memory notes: {notes or 'none'}."
    )


def _glossary_answer(
    query: str,
    snapshot: TelemetrySnapshot,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    terms = []
    if _mentions_any(query, ("eta", "lead time", "delai")):
        terms.append(f"ETA = estimated time before the predicted event or required action ({_eta_text(result.eta_minutes)} now)")
    if _mentions_any(query, ("ecc", "bit", "memory")):
        terms.append(f"ECC = memory error correction counters; current corrected/uncorrected is {snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors}")
    if _mentions_any(query, ("downlink", "contact")):
        terms.append(f"Downlink = available communication window to send recovery evidence; current capacity is {snapshot.downlink_capacity_gb:.2f}GB")
    if _mentions_any(query, ("checkpoint", "rollback")):
        terms.append(f"Checkpoint = recoverable training state; latest status is {snapshot.checkpoint_latest_status.value}")
    if not terms:
        terms.append(f"Primary driver = the module currently explaining most risk pressure, here {assessment.primary_driver}")
    if french:
        return "Glossaire operationnel: " + " | ".join(terms)
    return "Operational glossary: " + " | ".join(terms)


def _evidence_answer(primary: ModulePredictionResult, result: PredictiveAgentResult, french: bool) -> str:
    if french:
        return (
            "Preuves principales: "
            f"{'; '.join(result.evidence[:4])}. "
            f"Conclusion: {primary.module_id} reste prioritaire car son risque module vaut "
            f"{primary.risk_score:.1f}/100 avec {primary.confidence:.0%} de confiance module."
        )
    return (
        "Primary evidence: "
        f"{'; '.join(result.evidence[:4])}. "
        f"Conclusion: {primary.module_id} stays first because its module risk is "
        f"{primary.risk_score:.1f}/100 with {primary.confidence:.0%} module confidence."
    )


def _rejection_answer(primary: ModulePredictionResult, assessment: ScientificAssessment, safest: str, french: bool) -> str:
    if french:
        return (
            f"Si tu refuses l'action proposee, le scenario le plus probable reste: {primary.predicted_event}. "
            f"Le risque global reste a {assessment.overall_risk_score:.1f}/100 et l'action globale calculee est: "
            f"{assessment.global_action}. Repli moins intrusif: {safest}."
        )
    return (
        f"If you reject the proposed action, the most likely scenario remains: {primary.predicted_event}. "
        f"Global risk stays at {assessment.overall_risk_score:.1f}/100 and the computed global action is: "
        f"{assessment.global_action}. Less intrusive fallback: {safest}."
    )


def _confidence_answer(
    primary: ModulePredictionResult,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    if french:
        return (
            f"Confiance agent: {result.confidence:.0%}. Elle combine la confiance du module dominant "
            f"({primary.module_id}: {primary.confidence:.0%}), {assessment.samples_used} echantillons, "
            f"le mode de donnees {assessment.data_mode} et une fenetre de {assessment.trend_window_minutes:.1f} minutes. "
            "Les limites principales sont les capteurs contradictoires, les checkpoints suspects et les ruptures de tendance."
        )
    return (
        f"Agent confidence: {result.confidence:.0%}. It combines dominant-module confidence "
        f"({primary.module_id}: {primary.confidence:.0%}), {assessment.samples_used} samples, "
        f"data mode {assessment.data_mode}, and a {assessment.trend_window_minutes:.1f} minute trend window. "
        f"The main limits are contradictory sensors, suspect checkpoints, and abrupt trend breaks."
    )


def _training_answer(assessment: ScientificAssessment, result: PredictiveAgentResult, french: bool) -> str:
    if french:
        return (
            "Le mode training Nemotron 3 utilise un pack supervise/evaluation genere depuis l'etat mission courant: "
            "telemetry, calculs, lecture thermique, image topology, intention operateur, exemples few-shot et rubric de scoring. "
            f"Le cas courant entraine l'agent sur {assessment.primary_driver}, risque {assessment.overall_risk_score:.1f}/100, "
            f"avec action cible {_action_title(result.recommended_actions)}. L'endpoint /api/agents/nemotron-training-pack expose ce dataset "
            "pour rejouer les questions, noter les reponses et alimenter de futurs exemples corriges. "
            "Les approbations/refus operateur deviennent de la memoire agent et servent d'exemples decisionnels."
        )
    return (
        "Nemotron 3 training mode uses a supervised/evaluation pack generated from the current mission state: "
        "telemetry, calculation outputs, thermal readout, topology image, operator intent, few-shot examples and a grading rubric. "
        f"The current case trains the agent around {assessment.primary_driver}, risk {assessment.overall_risk_score:.1f}/100, "
        f"with target action {_action_title(result.recommended_actions)}. The /api/agents/nemotron-training-pack endpoint exposes this pack "
        "so responses can be replayed, graded and converted into future corrected examples. "
        "Operator approvals and rejections become agent memory and decision-training material."
    )


def _multimodal_answer(result: PredictiveAgentResult, french: bool) -> str:
    modalities = ", ".join(obs.modality for obs in result.multimodal_inputs)
    image_input = next((obs for obs in result.multimodal_inputs if obs.modality == "image"), None)
    if french:
        return (
            f"Le bundle agent contient {len(result.multimodal_inputs)} modalites: {modalities}. "
                "Nemotron recoit telemetry JSON, calculs, lecture thermique, image topology et question operateur dans une seule requete. "
            f"L'image visuelle est '{image_input.summary if image_input else 'topology heatmap'}'. Elle sert a recouper temperature GPU, downlink et ECC."
        )
    return (
        f"The agent bundle currently contains {len(result.multimodal_inputs)} modalities: {modalities}. "
        f"Nemotron receives the telemetry JSON, calculation outputs, thermal readout, topology image, and the operator query in one request. "
        f"The visual input is '{image_input.summary if image_input else 'topology heatmap'}', which helps cross-check the risk center against GPU temperature, "
        f"downlink capacity and ECC state. The final answer is still constrained by the auditable module evidence and action contract."
    )


def _module_ranking_answer(assessment: ScientificAssessment, french: bool) -> str:
    ranked = sorted(assessment.modules, key=lambda module: module.risk_score, reverse=True)
    details = [
        f"{index}. {module.module_id} {module.risk_score:.1f}/100: {module.predicted_event}"
        for index, module in enumerate(ranked[:5], start=1)
    ]
    if french:
        return (
            f"Classement actuel: {' | '.join(details)}. "
            f"Je traite d'abord {ranked[0].module_id}, puis je garde les autres modules comme signaux de correlation."
        )
    return (
        f"Current ranking: {' | '.join(details)}. "
        f"I handle {ranked[0].module_id} first, then keep the other modules as correlation signals."
    )


def _fallback_answer(
    primary: ModulePredictionResult,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool,
) -> str:
    if french:
        return (
            f"Reponse ciblee: {primary.module_name} signale '{primary.predicted_event}'. "
            f"Risque global {assessment.overall_risk_score:.1f}/100, severite {result.severity.value}, "
            f"ETA {_eta_text(result.eta_minutes)}. Action prioritaire: {_action_title(result.recommended_actions)}. "
            "Tu peux poser une question sur les preuves, le calcul, la thermique, la batterie, le downlink, la radiation, le classement des modules ou un scenario hypothetique."
        )
    return (
        f"Targeted answer: {primary.module_name} reports '{primary.predicted_event}'. "
        f"Global risk {assessment.overall_risk_score:.1f}/100, severity {result.severity.value}, "
        f"ETA {_eta_text(result.eta_minutes)}. Priority action: {_action_title(result.recommended_actions)}. "
        "You can ask about evidence, calculation, thermal risk, battery, downlink, radiation, module ranking, or a what-if scenario."
    )


def _module_answer(module: ModulePredictionResult, assessment: ScientificAssessment, result: PredictiveAgentResult, french: bool = False) -> str:
    metrics = _metric_summary(module)
    action = _first_module_action(module, result)
    if french:
        return (
            f"{module.module_id}: {module.predicted_event}. "
            f"Score {module.risk_score:.1f}/100, severite {module.severity.value}, confiance module {module.confidence:.0%}. "
            f"Mesures utiles: {metrics}. Decision: {module.recommended_decision}. Action: {action}. "
            f"Impact mission: risque global {assessment.overall_risk_score:.1f}/100."
        )
    return (
        f"{module.module_id}: {module.predicted_event}. "
        f"Score {module.risk_score:.1f}/100, severity {module.severity.value}, module confidence {module.confidence:.0%}. "
        f"Useful measurements: {metrics}. Decision: {module.recommended_decision}. Action: {action}. "
        f"Mission impact: global risk {assessment.overall_risk_score:.1f}/100."
    )


def _action_answer(
    module: ModulePredictionResult,
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool = False,
) -> str:
    action = _first_module_action(module, result)
    reversible = _first_reversible_action(result.recommended_actions)
    if french:
        return (
            f"Action prioritaire pour {module.module_id}: {action}. "
            f"Raison: {module.recommended_decision}. "
            f"Risque module {module.risk_score:.1f}/100, risque global {assessment.overall_risk_score:.1f}/100. "
            f"Pour limiter le risque operationnel, commence par l'option reversible: {reversible}."
        )
    return (
        f"Priority action for {module.module_id}: {action}. "
        f"Reason: {module.recommended_decision}. "
        f"Module risk {module.risk_score:.1f}/100, global risk {assessment.overall_risk_score:.1f}/100. "
        f"To limit operational risk, start with the reversible option: {reversible}."
    )


def _status_answer(
    snapshot: TelemetrySnapshot,
    history: list[TelemetrySnapshot],
    assessment: ScientificAssessment,
    result: PredictiveAgentResult,
    french: bool = False,
) -> str:
    primary = _primary_module(assessment)
    previous = history[-2] if len(history) >= 2 else None
    thermal_delta = snapshot.gpu_temperature_celsius - previous.gpu_temperature_celsius if previous else 0.0
    battery_delta = snapshot.battery_percent - previous.battery_percent if previous else 0.0
    if french:
        return (
            f"Synthese mission: risque {assessment.overall_risk_score:.1f}/100 ({result.severity.value}), "
            f"driver {primary.module_id}, evenement prevu: {primary.predicted_event}. "
            f"Etat courant: phase {snapshot.orbit_phase.value}, GPU {snapshot.gpu_temperature_celsius:.1f}C "
            f"({thermal_delta:+.1f}C/tick), batterie {snapshot.battery_percent:.1f}% ({battery_delta:+.1f}%/tick), "
            f"ECC {snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors}, downlink {snapshot.downlink_capacity_gb:.2f}GB. "
            f"Prochaine decision: {_action_title(result.recommended_actions)}."
        )
    return (
        f"Mission synthesis: risk {assessment.overall_risk_score:.1f}/100 ({result.severity.value}), "
        f"driver {primary.module_id}, forecast event: {primary.predicted_event}. "
        f"Current state: phase {snapshot.orbit_phase.value}, GPU {snapshot.gpu_temperature_celsius:.1f}C "
        f"({thermal_delta:+.1f}C/tick), battery {snapshot.battery_percent:.1f}% ({battery_delta:+.1f}%/tick), "
        f"ECC {snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors}, downlink {snapshot.downlink_capacity_gb:.2f}GB. "
        f"Next decision: {_action_title(result.recommended_actions)}."
    )


def _metric_summary(module: ModulePredictionResult) -> str:
    interesting_by_module = {
        "thermal_physical": ("temperature", "thermal", "radiator", "heat", "deficit", "margin", "slope"),
        "orbit_power": ("battery", "solar", "draw", "power", "eclipse", "net"),
        "radiation_integrity": ("ecc", "dose", "trust", "checkpoint", "canary", "hash"),
        "checkpoint_downlink": ("capacity", "payload", "checkpoint", "contact", "ack", "storage", "fit"),
        "workload_gpu": ("utilization", "memory", "scheduler", "process", "nccl", "interconnect", "residency"),
    }
    keys = interesting_by_module.get(module.module_id, ())
    hits = []
    for metric in module.metrics:
        name = _normalized_text(metric.name)
        if any(key in name for key in keys):
            unit = f" {metric.unit}" if metric.unit else ""
            hits.append(f"{metric.name} {metric.value}{unit}")
        if len(hits) >= 4:
            break
    return "; ".join(hits) if hits else module.result


def _first_module_action(module: ModulePredictionResult, result: PredictiveAgentResult) -> str:
    module_actions = [
        action
        for action in result.recommended_actions
        if action.get("source_module") == module.module_id or action.get("action_id") in {item.get("type") for item in module.recommended_actions}
    ]
    action = module_actions[0] if module_actions else (module.recommended_actions[0] if module.recommended_actions else None)
    if not action:
        return module.recommended_decision
    return _format_action(action)


def _first_reversible_action(actions: list[dict[str, Any]]) -> str:
    for action in actions:
        if not action.get("approval"):
            return _format_action(action)
    return _format_action(actions[0]) if actions else "increase monitoring and preserve evidence before any destructive action"


def _action_title(actions: list[dict[str, Any]]) -> str:
    return _format_action(actions[0]) if actions else "reinforced monitoring"


def _format_action(action: dict[str, Any]) -> str:
    title = str(action.get("type") or action.get("action_id") or "ACTION")
    reason = str(action.get("reason") or action.get("description") or "").strip()
    value = action.get("value")
    value_text = f" ({value})" if value not in {None, ""} else ""
    approval = " with human approval" if action.get("approval") else ""
    return f"{title}{value_text}{approval}" + (f" - {reason}" if reason else "")


def _eta_text(value: float | None) -> str:
    return "--" if value is None else f"{value:.0f} minutes"


def _actions_for_assessment(
    primary: ModulePredictionResult,
    assessment: ScientificAssessment,
    rejected: list[str],
    accepted: list[str],
) -> list[dict[str, Any]]:
    actions = _actions_from_primary(primary, rejected, accepted)
    thermal = next((module for module in assessment.modules if module.module_id == "thermal_physical"), None)
    if thermal and thermal.risk_score >= 68:
        thermal_actions = _actions_from_primary(thermal, rejected, accepted)
        approval_action = next((action for action in thermal_actions if action.get("approval")), None)
        if approval_action:
            approval_action = {
                **approval_action,
                "gate": "operator_approval",
                "approval_required_reason": (
                    "Thermal risk is high; operator approval is required before reducing GPU power or pausing workloads."
                ),
            }
            actions = [approval_action, *[action for action in actions if action.get("action_id") != approval_action.get("action_id")]]
    if not actions:
        actions = _actions_from_primary(primary, rejected, accepted)
    return actions


def _actions_from_primary(
    primary: ModulePredictionResult,
    rejected: list[str],
    accepted: list[str] | None = None,
) -> list[dict[str, Any]]:
    accepted = accepted or []
    actions = []
    for index, action in enumerate(primary.recommended_actions[:5], start=1):
        action_id = str(action.get("type", f"{primary.module_id}-action-{index}"))
        if action_id in rejected:
            continue
        payload = dict(action)
        payload.setdefault("action_id", action_id)
        payload.setdefault("source_module", primary.module_id)
        if payload.get("approval"):
            if action_id in accepted:
                payload["approval_status"] = "approved"
            else:
                payload["approval_status"] = "pending"
        actions.append(payload)
    if not actions:
        actions.append(
            {
                "action_id": f"{primary.module_id}-monitor",
                "type": "INCREASE_MONITORING",
                "reason": primary.recommended_decision,
                "approval": primary.requires_human_approval,
                "source_module": primary.module_id,
            }
        )
    return actions


def _operator_questions(primary: ModulePredictionResult, snapshot: TelemetrySnapshot, tolerance: str) -> list[str]:
    questions = []
    if primary.requires_human_approval:
        questions.append("Approve human-gated action, or keep the system in evidence-preservation mode?")
    if snapshot.checkpoint_latest_status.value != "TRUSTED":
        questions.append("Should the latest checkpoint be excluded from rollback targets?")
    if tolerance != "conservative" and primary.risk_score >= 68:
        questions.append("Switch to conservative policy until this incident window clears?")
    if not questions:
        questions.append("Keep autonomous monitoring, or request a deep Crusoe/Nemotron analysis now?")
    return questions[:3]


def _adaptation_notes(memory: AgentMemoryState) -> list[str]:
    notes = [f"Risk tolerance: {memory.risk_tolerance}."]
    if memory.feedback_count:
        notes.append(f"Applied {memory.feedback_count} operator feedback events.")
    if memory.policy_notes:
        notes.append(f"Active policy note: {memory.policy_notes[-1]}")
    if memory.rejected_action_ids:
        notes.append("Recently rejected actions are deprioritized.")
    return notes


def _performance_metrics(assessment: ScientificAssessment, history: list[TelemetrySnapshot], eta: float | None) -> dict[str, Any]:
    latest = history[-1] if history else None
    previous = history[-2] if len(history) >= 2 else None
    thermal_slope = None
    battery_slope = None
    if latest and previous:
        thermal_slope = round(latest.gpu_temperature_celsius - previous.gpu_temperature_celsius, 3)
        battery_slope = round(latest.battery_percent - previous.battery_percent, 3)
    return {
        "samples_used": assessment.samples_used,
        "trend_window_minutes": assessment.trend_window_minutes,
        "lead_time_minutes": eta,
        "thermal_delta_last_tick_c": thermal_slope,
        "battery_delta_last_tick_pct": battery_slope,
        "compound_to_primary_ratio": round(assessment.compound_risk_score / max(assessment.primary_risk_score, 1), 3),
        "stream_generated_at": utc_now(),
    }


def _snapshot_summary(snapshot: TelemetrySnapshot) -> dict[str, Any]:
    return {
        "timestamp": snapshot.timestamp,
        "mission_id": snapshot.mission_id,
        "phase": snapshot.orbit_phase.value,
        "scheduler": snapshot.scheduler_state.value,
        "gpu_utilization_percent": snapshot.gpu_utilization_percent,
        "gpu_temperature_celsius": snapshot.gpu_temperature_celsius,
        "battery_percent": snapshot.battery_percent,
        "downlink_capacity_gb": snapshot.downlink_capacity_gb,
        "ecc_corrected": snapshot.ecc_corrected_errors,
        "ecc_uncorrected": snapshot.ecc_uncorrected_errors,
        "checkpoint": snapshot.checkpoint_latest_status.value,
    }


def _thermal_readout(snapshot: TelemetrySnapshot, assessment: ScientificAssessment) -> dict[str, Any]:
    thermal_module = next((module for module in assessment.modules if module.module_id == "thermal_physical"), None)
    margin = round(95 - snapshot.gpu_temperature_celsius, 2)
    band = "critical" if snapshot.gpu_temperature_celsius >= 95 else "hot" if snapshot.gpu_temperature_celsius >= 84 else "watch" if snapshot.gpu_temperature_celsius >= 72 else "stable"
    hotspot_probability = min(0.98, max(0.02, (snapshot.gpu_temperature_celsius - 58) / 48))
    return {
        "gpu_temperature_c": round(snapshot.gpu_temperature_celsius, 2),
        "board_temperature_c": round(snapshot.board_temperature_celsius, 2),
        "radiator_temperature_c": round(snapshot.radiator_temperature_celsius, 2),
        "thermal_margin_c": margin,
        "thermal_band": band,
        "hotspot_probability": round(hotspot_probability, 3),
        "thermal_module_risk": round(thermal_module.risk_score, 1) if thermal_module else None,
        "thermal_module_event": thermal_module.predicted_event if thermal_module else "thermal module unavailable",
    }


def _topology_svg_uri(snapshot: TelemetrySnapshot, assessment: ScientificAssessment) -> str:
    risk = assessment.overall_risk_score
    hot = "#ff4f3d" if risk >= 86 else "#ff8a24" if risk >= 68 else "#36a6ff" if risk >= 42 else "#46c887"
    battery_width = round(max(0, min(100, snapshot.battery_percent)) * 2.18, 1)
    temp_width = round(max(0, min(100, (snapshot.gpu_temperature_celsius - 35) / 75 * 100)) * 2.18, 1)
    downlink_width = round(max(0, min(100, snapshot.downlink_capacity_gb / 8 * 100)) * 2.18, 1)
    ecc_pressure = min(1.0, (snapshot.ecc_corrected_errors + snapshot.ecc_uncorrected_errors * 40) / 600)
    ecc_width = round(ecc_pressure * 218, 1)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
<defs>
  <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
    <stop offset="0%" stop-color="#0f151f"/>
    <stop offset="50%" stop-color="#080b10"/>
    <stop offset="100%" stop-color="#17100e"/>
  </linearGradient>
  <linearGradient id="hot" x1="0" x2="1">
    <stop offset="0%" stop-color="#ffed73"/>
    <stop offset="48%" stop-color="#ff8a24"/>
    <stop offset="100%" stop-color="#ff4f3d"/>
  </linearGradient>
  <linearGradient id="cool" x1="0" x2="1">
    <stop offset="0%" stop-color="#36a6ff"/>
    <stop offset="100%" stop-color="#46c887"/>
  </linearGradient>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="8" result="blur"/>
    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <style>
    .label {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif; fill: #f7f4ef; font-weight: 760; }}
    .muted {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif; fill: #aaa7a0; }}
    .panel {{ fill: rgba(255,255,255,0.055); stroke: rgba(255,255,255,0.16); stroke-width: 1.2; }}
    .flow {{ stroke-dasharray: 9 14; animation: dash 2.8s linear infinite; }}
    .pulse {{ animation: pulse 2.1s ease-in-out infinite; transform-origin: center; }}
    @keyframes dash {{ to {{ stroke-dashoffset: -92; }} }}
    @keyframes pulse {{ 0%,100% {{ opacity: .35; transform: scale(1); }} 50% {{ opacity: .92; transform: scale(1.08); }} }}
  </style>
</defs>
<rect width="960" height="540" fill="url(#bg)"/>
<path d="M52 388 C210 280 346 238 498 236 C636 236 784 280 908 374" fill="none" stroke="rgba(255,138,36,0.13)" stroke-width="64"/>
<path d="M74 384 C252 246 436 202 604 218 C724 230 820 282 900 354" fill="none" stroke="rgba(255,255,255,0.10)" stroke-width="1.5"/>

<text x="42" y="52" class="label" font-size="27">Mission topology analysis</text>
<text x="42" y="82" class="muted" font-size="14">risk {risk:.1f}/100 - primary driver {assessment.primary_driver}</text>
<rect x="760" y="34" width="150" height="42" rx="21" fill="{hot}" opacity="0.18" stroke="{hot}"/>
<circle cx="786" cy="55" r="7" fill="{hot}" class="pulse"/>
<text x="804" y="61" class="label" font-size="13">{assessment.overall_severity.value}</text>

<g transform="translate(378 142)">
  <circle cx="102" cy="102" r="100" fill="rgba(255,138,36,0.055)" stroke="rgba(255,138,36,0.22)"/>
  <circle cx="102" cy="102" r="72" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.12)"/>
  <rect x="52" y="68" width="100" height="68" rx="10" fill="#131820" stroke="{hot}" stroke-width="2.6" filter="url(#glow)"/>
  <rect x="92" y="34" width="20" height="34" rx="4" fill="#283548" stroke="rgba(255,255,255,0.28)"/>
  <rect x="18" y="78" width="34" height="48" rx="5" fill="#1d2d45" stroke="rgba(54,166,255,0.45)"/>
  <rect x="152" y="78" width="34" height="48" rx="5" fill="#1d2d45" stroke="rgba(54,166,255,0.45)"/>
  <line x1="52" y1="102" x2="18" y2="102" stroke="rgba(255,255,255,0.28)" stroke-width="3"/>
  <line x1="152" y1="102" x2="186" y2="102" stroke="rgba(255,255,255,0.28)" stroke-width="3"/>
  <text x="70" y="96" class="label" font-size="17">GPU</text>
  <text x="62" y="118" class="muted" font-size="12">{snapshot.gpu_temperature_celsius:.1f}C / {snapshot.gpu_utilization_percent:.1f}%</text>
</g>

<path d="M300 244 C350 220 382 216 426 225" fill="none" stroke="{hot}" stroke-width="3.5" class="flow"/>
<path d="M536 225 C590 206 650 196 724 192" fill="none" stroke="#36a6ff" stroke-width="3.5" class="flow"/>
<path d="M532 290 C610 328 686 360 762 408" fill="none" stroke="#46c887" stroke-width="3.5" class="flow"/>
<path d="M420 296 C342 338 280 368 198 404" fill="none" stroke="#b487ff" stroke-width="3.5" class="flow"/>

<rect x="48" y="146" width="250" height="134" rx="14" class="panel"/>
<text x="70" y="180" class="label" font-size="18">Thermal readout</text>
<text x="70" y="207" class="muted" font-size="13">GPU {snapshot.gpu_temperature_celsius:.1f}C / radiator {snapshot.radiator_temperature_celsius:.1f}C</text>
<rect x="70" y="232" width="218" height="12" rx="6" fill="rgba(255,255,255,0.10)"/>
<rect x="70" y="232" width="{temp_width}" height="12" rx="6" fill="url(#hot)"/>
<text x="70" y="260" class="muted" font-size="12">thermal margin {95 - snapshot.gpu_temperature_celsius:.1f}C</text>

<rect x="668" y="126" width="246" height="148" rx="14" class="panel"/>
<text x="692" y="162" class="label" font-size="18">Downlink link</text>
<text x="692" y="190" class="muted" font-size="13">{snapshot.downlink_capacity_gb:.2f} GB contact window</text>
<rect x="692" y="214" width="218" height="12" rx="6" fill="rgba(255,255,255,0.10)"/>
<rect x="692" y="214" width="{downlink_width}" height="12" rx="6" fill="url(#cool)"/>
<text x="692" y="246" class="muted" font-size="12">contact geometry and bandwidth quality</text>

<rect x="48" y="338" width="250" height="128" rx="14" class="panel"/>
<text x="70" y="372" class="label" font-size="18">Power reserve</text>
<text x="70" y="398" class="muted" font-size="13">phase {snapshot.orbit_phase.value} / battery {snapshot.battery_percent:.1f}%</text>
<rect x="70" y="422" width="218" height="12" rx="6" fill="rgba(255,255,255,0.10)"/>
<rect x="70" y="422" width="{battery_width}" height="12" rx="6" fill="#46c887"/>

<rect x="668" y="336" width="246" height="130" rx="14" class="panel"/>
<text x="692" y="370" class="label" font-size="18">Integrity watch</text>
<text x="692" y="396" class="muted" font-size="13">ECC {snapshot.ecc_corrected_errors}/{snapshot.ecc_uncorrected_errors} / checkpoint {snapshot.checkpoint_latest_status.value}</text>
<rect x="692" y="420" width="218" height="12" rx="6" fill="rgba(255,255,255,0.10)"/>
<rect x="692" y="420" width="{ecc_width}" height="12" rx="6" fill="#b487ff"/>

<rect x="374" y="430" width="212" height="58" rx="14" fill="rgba(255,84,27,0.13)" stroke="rgba(255,138,36,0.34)"/>
<text x="404" y="456" class="label" font-size="15">Fusion confidence</text>
<text x="404" y="476" class="muted" font-size="12">calculation + thermal + topology</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _clamped_float(value: Any, default: float, lower: float, upper: float) -> float:
    try:
        return round(max(lower, min(upper, float(value))), 3)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:8]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:8]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result

"""Deterministic safety checks for mission patches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.constants import CommandType


SAFE_AUTONOMOUS_ACTIONS = {
    CommandType.collect_logs.value,
    CommandType.snapshot_evidence.value,
    CommandType.increase_monitoring.value,
    CommandType.run_health_check.value,
    CommandType.mark_node_suspect.value,
    CommandType.increase_checkpoint_frequency.value,
}


APPROVAL_REQUIRED_ACTIONS = {
    CommandType.mark_checkpoint_suspect.value,
    CommandType.rollback_training.value,
    CommandType.cordon_node.value,
    CommandType.pause_job.value,
    CommandType.kill_process.value,
    CommandType.set_gpu_power_limit.value,
    CommandType.switch_cooling_loop.value,
    CommandType.transfer_priority.value,
}


@dataclass(frozen=True)
class SafetyResult:
    allowed: bool
    reason: str
    approval_required: bool = True
    safe_alternative: str | None = None


def validate_mission_patch(actions: list[dict[str, Any]], world_state: dict[str, Any]) -> SafetyResult:
    """Validate command payloads before a patch can wait for human approval."""
    if not actions:
        return SafetyResult(False, "Mission patch must include at least one executable action.")

    approval_required = False
    seen_action_keys: set[tuple[str, str]] = set()
    for action in actions:
        action_type = action.get("type")
        try:
            CommandType(action_type)
        except ValueError:
            return SafetyResult(False, f"Unsupported command type: {action_type}.")

        target_key = str(action.get("node_id") or action.get("checkpoint_id") or action.get("job_id") or "global")
        action_key = (action_type, target_key)
        if action_key in seen_action_keys:
            return SafetyResult(False, f"Duplicate command action for {action_type}:{target_key}.")
        seen_action_keys.add(action_key)

        if action_type in APPROVAL_REQUIRED_ACTIONS:
            approval_required = True
        elif action_type not in SAFE_AUTONOMOUS_ACTIONS:
            return SafetyResult(False, f"Command type has no safety classification: {action_type}.")

        action_result = _validate_action(action, world_state)
        if not action_result.allowed:
            return action_result

    return SafetyResult(True, "Mission patch passed deterministic safety checks.", approval_required)


def _validate_action(action: dict[str, Any], world_state: dict[str, Any]) -> SafetyResult:
    action_type = action["type"]
    training = world_state.get("training", {})
    latest_checkpoint = training.get("latest_checkpoint")
    latest_status = training.get("latest_checkpoint_status")
    last_trusted_checkpoint = training.get("last_trusted_checkpoint")

    if action_type == CommandType.rollback_training.value:
        checkpoint_id = action.get("checkpoint_id")
        if action.get("job_id") != training.get("job_id"):
            return SafetyResult(False, "rollback_training job_id must match the active training job.")
        if checkpoint_id != last_trusted_checkpoint:
            return SafetyResult(
                False,
                f"Cannot rollback to {checkpoint_id}; only {last_trusted_checkpoint} is trusted.",
                safe_alternative=f"rollback_to_{last_trusted_checkpoint}",
            )
        if checkpoint_id == latest_checkpoint and latest_status == "suspect":
            return SafetyResult(
                False,
                f"Cannot rollback to {checkpoint_id} because checkpoint status is suspect.",
                safe_alternative=f"rollback_to_{last_trusted_checkpoint}",
            )

    if action_type == CommandType.mark_checkpoint_suspect.value and action.get("checkpoint_id") == last_trusted_checkpoint:
        return SafetyResult(False, "Cannot mark the last trusted checkpoint as suspect.")
    if action_type == CommandType.mark_checkpoint_suspect.value and not action.get("checkpoint_id"):
        return SafetyResult(False, "mark_checkpoint_suspect requires checkpoint_id.")

    if action_type == CommandType.collect_logs.value:
        if not action.get("asset_id") or not _non_empty_list(action.get("log_types")):
            return SafetyResult(False, "collect_logs requires asset_id and log_types.")

    if action_type == CommandType.snapshot_evidence.value:
        if not _non_empty_list(action.get("asset_ids")) or not _non_empty_list(action.get("include")):
            return SafetyResult(False, "snapshot_evidence requires non-empty asset_ids and include lists.")

    if action_type == CommandType.increase_monitoring.value:
        if not action.get("agent_name") or not _non_empty_list(action.get("asset_ids")):
            return SafetyResult(False, "increase_monitoring requires agent_name and asset_ids.")
        if not isinstance(action.get("duration_minutes"), int) or action["duration_minutes"] <= 0:
            return SafetyResult(False, "increase_monitoring requires positive duration_minutes.")

    if action_type == CommandType.run_health_check.value:
        if not action.get("asset_id") or not action.get("check_suite"):
            return SafetyResult(False, "run_health_check requires asset_id and check_suite.")

    if action_type == CommandType.mark_node_suspect.value:
        if not action.get("node_id") or not action.get("reason"):
            return SafetyResult(False, "mark_node_suspect requires node_id and reason.")

    if action_type == CommandType.set_gpu_power_limit.value:
        if not action.get("node_id"):
            return SafetyResult(False, "set_gpu_power_limit requires node_id.")
        power_percent = action.get("power_percent")
        if not isinstance(power_percent, int) or power_percent < 50 or power_percent > 100:
            return SafetyResult(False, "GPU power limit must be an integer from 50 to 100 percent.")

    if action_type == CommandType.cordon_node.value:
        node_id = action.get("node_id")
        known_nodes = {node.get("id") for node in world_state.get("nodes", [])}
        if node_id not in known_nodes:
            return SafetyResult(False, f"Cannot cordon unknown node {node_id}.")
        if not action.get("scope"):
            return SafetyResult(False, "cordon_node requires scope.")

    if action_type == CommandType.pause_job.value:
        if action.get("job_id") != training.get("job_id") or not action.get("reason"):
            return SafetyResult(False, "pause_job requires active job_id and reason.")

    if action_type == CommandType.kill_process.value:
        if not action.get("node_id") or not action.get("process_id") or not action.get("evidence_id"):
            return SafetyResult(False, "kill_process requires node_id, process_id, and evidence_id.")

    if action_type == CommandType.increase_checkpoint_frequency.value:
        if action.get("job_id") != training.get("job_id"):
            return SafetyResult(False, "increase_checkpoint_frequency job_id must match the active training job.")
        if not isinstance(action.get("interval_minutes"), int) or action["interval_minutes"] <= 0:
            return SafetyResult(False, "increase_checkpoint_frequency requires positive interval_minutes.")

    if action_type == CommandType.transfer_priority.value:
        send_first = action.get("send_first")
        defer = action.get("defer")
        if not isinstance(send_first, list) or not send_first:
            return SafetyResult(False, "transfer_priority requires a non-empty send_first list.")
        if not isinstance(defer, list):
            return SafetyResult(False, "transfer_priority requires a defer list.")

    if action_type == CommandType.switch_cooling_loop.value:
        if not action.get("from_loop_id") or not action.get("to_loop_id"):
            return SafetyResult(False, "switch_cooling_loop requires from_loop_id and to_loop_id.")

    return SafetyResult(True, "Action passed safety checks.")


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0

from __future__ import annotations

from app.constants import CommandType, StreamName
from app.config import settings
from app.db.models import AgentStatus, AgentStatusEvent


def test_crusoe_model_is_exactly_expected_case() -> None:
    assert settings.crusoe_model == "moonshotai/Kimi-K2.6"


def test_command_enum_contains_allowed_actions() -> None:
    expected = {
        "collect_logs",
        "snapshot_evidence",
        "increase_monitoring",
        "run_health_check",
        "mark_node_suspect",
        "mark_checkpoint_suspect",
        "rollback_training",
        "cordon_node",
        "pause_job",
        "kill_process",
        "set_gpu_power_limit",
        "increase_checkpoint_frequency",
        "switch_cooling_loop",
        "transfer_priority",
    }
    assert expected == {member.value for member in CommandType}


def test_agent_status_projection_and_event_tables_are_distinct() -> None:
    assert AgentStatus.__tablename__ == "agent_statuses"
    assert AgentStatusEvent.__tablename__ == "agent_status_events"


def test_stream_names_include_phase2_telemetry_stream() -> None:
    assert StreamName.telemetry_events.value == "telemetry:events"
    assert StreamName.ui_events.value == "ui:events"

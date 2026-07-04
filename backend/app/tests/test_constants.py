from __future__ import annotations

from app.constants import CommandType
from app.config import settings


def test_crusoe_model_is_exactly_expected_case() -> None:
    assert settings.crusoe_model == "deepseek-ai/DeepSeek-V4-Flash"


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

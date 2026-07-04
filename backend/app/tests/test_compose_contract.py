from __future__ import annotations

from pathlib import Path


def test_compose_declares_phase3_workers() -> None:
    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    text = compose.read_text(encoding="utf-8")

    assert "orbitops-simulator:" in text
    assert "orbitops-agents:" in text
    assert "orbitops-executor:" in text
    assert "python\", \"-m\", \"app.agents.runner" in text

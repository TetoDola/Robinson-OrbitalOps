"""Optional LLM explanation polish for Commander output."""

from __future__ import annotations

from app.config import settings


async def polish_mission_patch_summary(summary: str, _context: dict) -> str:
    """Return deterministic text unless Crusoe is explicitly enabled.

    The hackathon backend must boot without external credentials. The Commander
    still owns deterministic actions and safety; this hook is only for future
    wording polish when `CRUSOE_ENABLED=true` and credentials are present.
    """
    if not settings.crusoe_enabled or not settings.crusoe_api_key:
        return summary
    return summary

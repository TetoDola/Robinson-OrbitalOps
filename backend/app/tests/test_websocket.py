from __future__ import annotations

import inspect

from app.routers.websocket import ws_live


def test_websocket_does_not_hold_injected_db_session() -> None:
    signature = inspect.signature(ws_live)
    assert list(signature.parameters) == ["websocket"]

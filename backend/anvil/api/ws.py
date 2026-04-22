from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from anvil.config import get_settings
from anvil.pubsub import get_broadcaster

router = APIRouter(tags=["ws"])


@router.websocket("/ws/runs/{run_id}")
async def run_feed(websocket: WebSocket, run_id: str, token: str = Query("")) -> None:
    settings = get_settings()
    if token != settings.bearer_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    broadcaster = get_broadcaster()
    topic = f"runs:{run_id}"
    queue = await broadcaster.subscribe(topic)
    try:
        await websocket.send_text(json.dumps({"event": "connected", "payload": {"run_id": run_id}}))
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                await websocket.send_text(json.dumps({"event": "ping", "payload": {}}))
                continue
            await websocket.send_text(json.dumps(message))
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await broadcaster.unsubscribe(topic, queue)

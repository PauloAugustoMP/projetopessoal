"""Near-real-time quote channel (`/ws/quotes`, docs/architecture.md §4.1).

The price_poll job runs on a scheduler thread, so broadcasts cross into the
event loop through run_coroutine_threadsafe — the loop is captured at startup.
"""

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.api.security import decode_token
from backend.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


class QuoteBroadcaster:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, payload: dict) -> None:
        for connection in list(self._connections):
            try:
                await connection.send_json(payload)
            except Exception:
                self.disconnect(connection)

    def broadcast_from_thread(self, payload: dict) -> None:
        if self._loop is None or not self._connections:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)


broadcaster = QuoteBroadcaster()


def _rejection_reason(token: str, secret: str) -> str:
    """Diagnostic only — never sent to the client, which gets a generic rejection."""
    import jwt

    try:
        jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return "token expired"
    except jwt.InvalidSignatureError:
        return "signature does not match JWT_SECRET"
    except jwt.PyJWTError as error:
        return f"invalid token ({type(error).__name__})"
    return "wrong token type (a refresh token cannot open the channel)"


@router.websocket("/ws/quotes")
async def quotes_websocket(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    settings = get_settings()
    if token is None or decode_token(token, settings.jwt_secret, "access") is None:
        # Closing before accepting makes Starlette reject the handshake with HTTP
        # 403, so the client never sees this code — hence the explicit log line:
        # an expired token is by far the most common cause and looks identical to
        # a forged one in the access log.
        logger.info(
            "Rejected /ws/quotes handshake: %s. The client should refresh the "
            "access token before reconnecting.",
            "no token provided" if token is None else _rejection_reason(token, settings.jwt_secret),
        )
        await websocket.close(code=4401, reason="Missing or invalid access token.")
        return

    await broadcaster.connect(websocket)
    try:
        while True:
            # Clients don't need to send anything; this just keeps the socket open
            # and lets us notice disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)

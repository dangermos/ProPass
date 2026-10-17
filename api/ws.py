"""Live snapshot stream: every published state goes to every connected dashboard."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def router(runtime):
    api = APIRouter()

    @api.websocket("/api/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        runtime.clients.add(socket)
        try:
            async with runtime.lock:
                await socket.send_json(runtime.snapshot())
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            runtime.clients.discard(socket)

    return api

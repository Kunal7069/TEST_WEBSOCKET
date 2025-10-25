from fastapi import FastAPI, WebSocket, HTTPException
from typing import Dict
import json
import asyncio

app = FastAPI()

active_connections: Dict[str, WebSocket] = {}
pending_responses: Dict[str, asyncio.Queue] = {}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    pending_responses[client_id] = asyncio.Queue()
    print(f"Client {client_id} connected")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"📩 Message from {client_id}: {data}")
            await pending_responses[client_id].put(data)
    except Exception as e:
        print(f"Client {client_id} disconnected: {e}")
        active_connections.pop(client_id, None)
        pending_responses.pop(client_id, None)


@app.post("/ws_call/{client_id}")
async def ws_call(client_id: str, payload: dict):
    """
    Send a WebSocket API call command to the user client.
    Example payload:
    {
      "method": "GET",
      "endpoint": "/test_api",
      "body": {}
    }
    """
    ws = active_connections.get(client_id)
    if not ws:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not connected")

    await ws.send_text(json.dumps(payload))
    print(f"Sent to {client_id}: {payload}")

    try:
        response = await asyncio.wait_for(pending_responses[client_id].get(), timeout=20)
        return {"client_id": client_id, "result": json.loads(response)}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout waiting for response")

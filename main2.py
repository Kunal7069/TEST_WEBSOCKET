from fastapi import FastAPI, WebSocket, HTTPException
from typing import Dict
import json
import asyncio

app = FastAPI()

active_connections: Dict[str, WebSocket] = {}
pending_futures: Dict[str, asyncio.Future] = {}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Handle incoming WebSocket connection from a client"""
    await websocket.accept()
    active_connections[client_id] = websocket
    print(f"✅ Client {client_id} connected")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Message from {client_id}: {data}")

            # Try to parse JSON message
            try:
                msg = json.loads(data)
            except:
                msg = {"raw": data}

            # Match any pending API call waiting for this client's response
            fut = pending_futures.pop(client_id, None)
            if fut and not fut.done():
                fut.set_result(data)

    except Exception as e:
        print(f"⚠️ Client {client_id} disconnected: {e}")
    finally:
        # Cleanup
        active_connections.pop(client_id, None)
        pending_futures.pop(client_id, None)
        print(f"🧹 Cleaned up client {client_id}")


@app.post("/ws_call/{client_id}")
async def ws_call(client_id: str, payload: dict):
    """Send a WebSocket API call command to the client and wait for immediate response."""
    ws = active_connections.get(client_id)
    if not ws:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not connected")

    # Create a future and register it
    fut = asyncio.get_event_loop().create_future()
    pending_futures[client_id] = fut

    # Send payload to client
    await ws.send_text(json.dumps(payload))
    print(f"➡️ Sent to {client_id}: {payload}")

    try:
        response = await asyncio.wait_for(fut, timeout=30)
        return {"client_id": client_id, "result": json.loads(response)}
    except asyncio.TimeoutError:
        pending_futures.pop(client_id, None)
        raise HTTPException(status_code=504, detail="Timeout waiting for response")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error receiving response: {str(e)}")

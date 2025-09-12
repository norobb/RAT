import os
import subprocess
import sys
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def main():
    """
    Starts the RAT server and a client in local development mode.
    """
    print("Starting server and client in local development mode...")

    # Command to run uvicorn server
    server_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload"
    ]

    # Start the server in a background process
    server_process = subprocess.Popen(server_command)

    # Give the server a moment to start
    time.sleep(5)

    # Set environment for the client
    client_env = os.environ.copy()
    client_env["SERVER_URI"] = "ws://127.0.0.1:8000/rat"

    # Command to run the client
    client_command = [sys.executable, "client.py"]

    # Start the client in a background process
    client_process = subprocess.Popen(client_command, env=client_env)

    try:
        # Wait for the server to exit
        server_process.wait()
    except KeyboardInterrupt:
        print("\nStopping server and client...")
        server_process.terminate()
        client_process.terminate()
        server_process.wait()
        client_process.wait()
        print("Server and client stopped.")

if __name__ == "__main__":
    main()
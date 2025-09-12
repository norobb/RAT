import pytest
import subprocess
import sys
import time
import os

@pytest.fixture(scope="session")
def server_process():
    """
    Starts the server as a subprocess for integration testing.
    """
    env = os.environ.copy()
    env["ADMIN_USERNAME"] = "testuser"
    env["ADMIN_PASSWORD"] = "testpass"
    env["JWT_SECRET"] = "testsecret"

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8001",
    ]

    # Capture stdout and stderr
    proc = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for the server to start
    time.sleep(3) # Increased sleep time

    yield proc

    # Teardown: stop the server
    proc.terminate()
    try:
        outs, errs = proc.communicate(timeout=5)
        print("--- Server Output ---")
        print(outs)
        print("--- Server Errors ---")
        print(errs)
    except subprocess.TimeoutExpired:
        proc.kill()
        outs, errs = proc.communicate()
        print("--- Server Output (killed) ---")
        print(outs)
        print("--- Server Errors (killed) ---")
        print(errs)
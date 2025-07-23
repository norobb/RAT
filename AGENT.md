# RAT (Remote Administration Tool) - Agent Guidelines

## Build/Test Commands
- **Start Server:** `python server.py`
- **Install Dependencies:** `pip install -r requirements.txt`
- **Build Client Executable:** `pyinstaller --noconsole --onefile --icon=icon.ico client.py`
- **Test Server:** Visit `http://localhost:8000` (or the configured port) for the web UI.

## Architecture
- **FastAPI Backend (`server.py`):** Manages WebSocket connections from both the web UI and RAT clients. Uses JWT for secure UI authentication and features a robust, asynchronous architecture. Handles command forwarding and client state management.
- **Python Client (`client.py`):** Connects to the server via WebSocket, registers itself by sending a structured JSON `info` message, and then awaits commands. Includes modules for screen streaming (base64), file operations, and system information gathering. Features persistence on Windows and a keylogger.
- **Web UI (`index.html`):** A responsive, single-page application built with Tailwind CSS and vanilla JavaScript. Provides a full control panel for interacting with connected clients, viewing live media streams, and monitoring server status. It is optimized for both desktop and mobile use.
- **Authentication:** JWT for the web UI, ensuring that only authenticated users can connect to the WebSocket and access the control panel. Includes brute-force protection.

## Code Style
- **Language:** Python 3.10+ with `asyncio` for concurrency. Type hints are used for clarity.
- **Frontend:** Modern vanilla JavaScript (ES6+) with Tailwind CSS for styling. The UI is self-contained in `index.html`.
- **Communication Protocol:** All communication between server, client, and UI is done via JSON-formatted WebSocket messages.
- **Error Handling:** Robust error handling and connection-retry logic with exponential backoff in the client.
- **Logging:** Standard Python `logging` module is used on both client and server for diagnostics.

## Key Patterns
- **Client Handshake:** Clients initiate connection and send an `info` message with their system details. The server uses this to register the client and assign a unique ID.
- **Command Forwarding:** The web UI sends commands for specific `target_ids` to the server, which then relays the command to the appropriate client(s).
- **Asynchronous Tasks:** Server and client make extensive use of `asyncio.create_task` to handle concurrent operations like heartbeats, command processing, and media streaming without blocking.
- **State Management:** Server maintains the state of connected clients (`CLIENT_INFOS`) and web UIs (`WEB_UI_SOCKETS`) in memory. Inactive clients are periodically cleaned up.

# RAT (Remote Administration Tool) - Agent Guidelines

## Build/Test Commands
- **Start Server:** `python server.py` or `uvicorn server:app --host 0.0.0.0 --port 8000`
- **Start Server (Unix):** `bash start.sh`
- **Install Dependencies:** `pip install -r requirements.txt`
- **Build Client Executable:** `pyinstaller --noconsole --onefile --icon=icon.ico client.py`
- **Quick Client Build:** Run `compile.bat` (Windows)
- **Test Server:** Visit `http://localhost:8000` for web UI (admin/supersecretpassword123)
- **Syntax Check:** `python -m py_compile server.py client.py hash.py`

## Architecture
- **FastAPI Backend:** `server.py` - WebSocket server with REST API, command logging, IP banning
- **Python Client:** `client.py` - RAT client with persistence, keylogging, screen streaming, process management
- **Web UI:** `index.html` - Enhanced SPA with server stats, improved command interface
- **Components:** `components/CommandInput.tsx` - React components for command input
- **Executables:** Auto-built via GitHub Actions workflow, stored in `executables/`
- **Authentication:** JWT + Basic Auth with brute-force protection, IP banning, fallback mechanisms
- **APIs:** REST endpoints for stats (/api/stats), clients (/api/clients), IP management with JWT auth

## New Features Added
- **Process Management:** List processes (/process_list), kill processes (/kill_process)
- **Network Tools:** Network info (/network_info), network scanning (/network_scan)
- **Server Monitoring:** Real-time server stats with CPU, RAM, disk usage
- **Security:** IP banning system, failed login tracking, command audit logging
- **Enhanced UI:** Server stats modal, new quick action buttons, improved command parsing

## Code Style
- **Language:** Python 3.10+ with async/await patterns, type hints for key functions
- **Frontend:** TypeScript/React components (CommandInput.tsx), vanilla JS for main UI
- **Imports:** Standard library first, then third-party (asyncio, websockets, fastapi, psutil)
- **Error Handling:** Try-catch blocks with logging, graceful WebSocket disconnections
- **Naming:** snake_case for functions/variables, all UI text in English
- **Logging:** Use Python logging module with INFO level, structured messages
- **WebSockets:** JSON message protocol, handle both text and binary data
- **Security:** Never log secrets, use bcrypt for passwords, JWT for authentication
- **UI:** Responsive design with Tailwind CSS, categorized command suggestions, notifications

## Key Patterns
- WebSocket handlers use typed global dictionaries (RAT_CLIENTS, CLIENT_INFOS, COMMAND_LOGS)
- Command processing in async loops with proper exception handling and logging
- File uploads/downloads via base64 encoding with chunked upload support
- Persistent client state via local files, enhanced with process/network monitoring

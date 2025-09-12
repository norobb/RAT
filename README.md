# RAT (Remote Administration Tool)

This project is a cross-platform Remote Administration Tool (RAT) written in Python, featuring a web-based control panel and a modular client.

## Features

- **Web-based Control Panel:** A modern, responsive web interface for managing clients.
- **Cross-Platform Client:** The client is designed to run on Windows, macOS, and Linux.
- **Modular Architecture:** The client's functionality is broken down into modules, making it easy to extend.
- **Real-time Communication:** Uses WebSockets for low-latency communication between the server and clients.
- **Core Features:**
  - Interactive Shell
  - Screen Streaming
  - Webcam Streaming
  - File Manager (list, upload, download, remove, mkdir)
  - Process Manager (list, kill)
  - System Information
  - Keylogger
  - Persistence

## Project Structure

```
.
├── modules/         # Client-side modules
├── tests/           # Unit and integration tests
├── .dockerignore      # Files to ignore in Docker builds
├── .env             # Environment variables (local)
├── client.py        # Main client application
├── Dockerfile       # Dockerfile for the server
├── Dockerfile.client # Dockerfile for the client
├── Dockerfile.test  # Dockerfile for running tests
├── docker-compose.yml # Docker Compose for local development
├── README.md        # This file
├── requirements.txt # Python dependencies
├── run_local.py     # Script to run the server locally
└── server.py        # Main server application
```

## Getting Started

### Prerequisites

- Python 3.10+
- Docker and Docker Compose (for containerized setup)

### Local Development

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the server:**
    ```bash
    python run_local.py
    ```
    The server will be running at `http://127.0.0.1:8000`.

4.  **Run the client:**
    In a separate terminal, run the client with the `--local` flag:
    ```bash
    python client.py --local
    ```

### Docker Development

1.  **Create a `.env` file:**
    Copy the contents of the provided `.env` file and replace the placeholder values with your own secrets.

2.  **Build and run with Docker Compose:**
    ```bash
    docker compose up --build
    ```
    This will build and start the server and a client container. The server will be accessible at `http://127.0.0.1:8000`.

## Running Tests

### Locally

To run the tests directly on your machine, make sure you have installed the dependencies from `requirements.txt` and then run:

```bash
python -m pytest
```

### With Docker

To run the tests in a containerized environment, use the `test` service defined in `docker-compose.yml`:

```bash
docker compose run --rm test
```

## Deployment to Koyeb

This application is designed to be easily deployed to platforms like Koyeb.

1.  **Push your code to a GitHub repository.**

2.  **Create a new App on Koyeb:**
    - Choose GitHub as the deployment method and select your repository.
    - Koyeb should automatically detect the `Dockerfile` and configure the build.

3.  **Configure Environment Variables:**
    In the Koyeb service configuration, set the following environment variables:
    - `ADMIN_USERNAME`: Your desired admin username.
    - `ADMIN_PASSWORD`: A strong and secret password.
    - `JWT_SECRET`: A long, random, and secret key for signing JWTs.

4.  **Deploy:**
    Koyeb will build and deploy your application. The server will be available at the public URL provided by Koyeb.

5.  **Client Configuration:**
    To connect a client to your deployed server, you need to set the `SERVER_URI` environment variable on the client machine to your Koyeb WebSocket URL (e.g., `wss://<your-app-name>-<your-org>.koyeb.app/rat`).
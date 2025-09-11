# Dockerfile

# --- Stage 1: Build / Dependencies ---
FROM python:3.10-slim as base

WORKDIR /app

# Abhängigkeiten kopieren
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Code kopieren
COPY . .

# Ports etc.
EXPOSE 8000

# Kommando zum Starten
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

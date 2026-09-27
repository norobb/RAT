# --- Stage 1: Build / Dependencies ---
FROM python:3.10 AS builder

# Create a non-root user for building
RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser

# Copy only requirements to leverage Docker cache
COPY requirements.txt .

# Install dependencies to the user's local directory
# This ensures we can build C extensions like evdev
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Final Image ---
FROM python:3.10-slim AS final

# Install runtime dependencies for OpenCV and other modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create and switch to a non-root user
RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser

# Copy installed packages from the builder stage
COPY --from=builder /home/appuser/.local /home/appuser/.local

# Copy the application code
COPY . .

# Set the PATH to include the installed packages
ENV PATH=/home/appuser/.local/bin:$PATH

# Expose the port
EXPOSE 8000

# Command to start the server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

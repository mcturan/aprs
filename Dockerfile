FROM python:3.11-slim

# Set timezone env
ENV TZ=Europe/Istanbul

# Install git and minimal system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY aprs_beacon.py aprs_manager.py web_manager.py ./
COPY templates/ ./templates/

# Install python dependencies (Flask)
RUN pip install --no-cache-dir flask

# Expose web manager portal port
EXPOSE 8080

# Environment variables
ENV DOCKER_MODE=true
ENV PORT=8080

# Run the web manager
CMD ["python3", "web_manager.py"]

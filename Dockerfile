FROM python:3.12-slim

# Install Node.js (for gws CLI)
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install gws CLI
RUN npm install -g @googleworkspace/cli

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py
WORKDIR /app

# gws credentials will be mounted or set via env
ENV GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/app/credentials.json

EXPOSE 8000

CMD ["python", "server.py", "--port", "8000", "--transport", "streamable-http"]

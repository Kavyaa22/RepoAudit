FROM python:3.12-slim

# git: repo clone/import; curl/tar: Gitleaks + OSV-Scanner binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV REPOAUDIT_SECURITY_TOOLS_DIR=/usr/local/bin

COPY scripts/install_security_tools.sh /tmp/install_security_tools.sh
RUN chmod +x /tmp/install_security_tools.sh && /tmp/install_security_tools.sh

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]

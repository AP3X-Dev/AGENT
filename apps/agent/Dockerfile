# ─────────────────────────────────────────────────────────────────
# AG3NT Agent Worker — Python FastAPI container
# Build context: project root (set by docker-compose.yml)
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r ag3nt && useradd -r -g ag3nt -m ag3nt
RUN mkdir -p /home/ag3nt/.ag3nt/workspace /home/ag3nt/.ag3nt/memory && \
    chown -R ag3nt:ag3nt /home/ag3nt

# Install Python dependencies
COPY apps/agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install vendored deepagents
COPY vendor/deepagents /vendor/deepagents
RUN pip install --no-cache-dir -e /vendor/deepagents/libs/deepagents

# Copy application
COPY apps/agent/ag3nt_agent/ ag3nt_agent/

# Environment
ENV PYTHONUNBUFFERED=1
ENV AG3NT_AGENT_HOST=0.0.0.0
ENV AG3NT_AGENT_PORT=18790

EXPOSE 18790

USER ag3nt

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:18790/health')" || exit 1

CMD ["python", "-m", "ag3nt_agent.worker"]

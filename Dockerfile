# ── Stage 1: Build the React frontend ─────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist/


# ── Stage 2: Python backend + serve built frontend ─────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps (kuzu needs libstdc++)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py wrapper.py gemini_utils.py ./
COPY agent/ ./agent/
COPY graph_rag/ ./graph_rag/

# Copy the pre-built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Mount the frontend build as static files via FastAPI.
# Add this to main.py's startup if not already present:
#   app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
# OR use the ENV flag below to auto-enable it at runtime.
ENV SERVE_FRONTEND=true

# Render injects $PORT at runtime; default to 8000 for local Docker use
ENV PORT=8000

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}

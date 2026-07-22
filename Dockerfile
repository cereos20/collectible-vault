FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose ports: 8000 for FastAPI Web UI, 8001 for FastMCP server if isolated
EXPOSE 8000 8001

ENV PORT=8000
ENV DATABASE_URL=sqlite:///./vault.db
ENV OLLAMA_HOST=http://host.docker.internal:11434

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

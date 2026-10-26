FROM python:3.12-slim

WORKDIR /app

# Ensure output is sent straight to terminal without buffering
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy source code
COPY backend ./backend
COPY scripts ./scripts

# Create data directory for cache persistence
RUN mkdir -p /app/data/cache

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

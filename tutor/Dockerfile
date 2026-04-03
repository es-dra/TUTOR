# TUTOR Docker image - Fixed for actual project structure
# The 'tutor/' directory is a Python package, so we copy it as a whole

FROM python:3.11-slim

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install uvicorn explicitly (may not be in requirements.txt)
RUN pip install --no-cache-dir "uvicorn[standard]"

# Copy the entire tutor package as a directory (preserves Python package structure)
COPY tutor /app/tutor

# Create data directory
RUN mkdir -p /app/data

# Environment - parent of 'tutor' is the working dir, so 'tutor' package is importable
ENV PYTHONPATH="/app"
ENV TUTOR_HOME="/app/data"
ENV DATA_PATH="/app/data/tutor_runs.db"

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Default command - run from /app (parent of tutor/) so 'tutor' is importable
# uvicorn looks for 'api' module which is at /app/tutor/api
CMD ["uvicorn", "tutor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
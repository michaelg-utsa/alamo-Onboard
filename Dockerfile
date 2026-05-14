# Stage 1: install dependencies
FROM python:3.11-slim AS deps

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Stage 2: runtime image (non-root)
FROM python:3.11-slim AS runtime

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source
COPY --chown=appuser:appuser . .

# Create output directories and ensure appuser owns /app itself so coverage,
# pytest cache, and other runtime-generated files can be written from the
# project root without permission errors.
RUN mkdir -p output/index output/logs reports \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 7860

# Gradio binds to 0.0.0.0 inside the container so Docker port mapping works
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

CMD ["python", "main.py"]

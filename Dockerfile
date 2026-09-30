# Multi-stage build
# Stage 1: Build & install dependencies
FROM python:3.13-slim AS builder

WORKDIR /app

# DEFECT: source is copied BEFORE dependencies are installed
COPY . .
RUN pip install --no-cache-dir -r api/requirements.txt

# Stage 2: Runtime image
FROM python:3.13-slim AS runner

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

EXPOSE 8000
CMD ["flask", "--app", "api/app.py", "run", "--host", "0.0.0.0", "--port", "8000"]

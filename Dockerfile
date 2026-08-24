# Multi-stage build.
# JAVA: the equivalent of building a fat jar in one stage and copying it into
#       a slim JRE image in the next.

FROM python:3.12-slim AS builder

WORKDIR /build

# Copy ONLY the dependency file first. Docker caches this layer, so changing
# your source code does not reinstall every package. Same trick as copying
# pom.xml before src/ in a Java build.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

# Never run as root. If the app is compromised, the attacker inherits this user.
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# /app must be owned by appuser, not just its contents. With SQLite the app
# CREATES app.db at runtime, and creating a file needs write permission on the
# DIRECTORY. Without this line the container starts as root-owned /app, the
# non-root user cannot create the database, and boot fails with a confusing
# "unable to open database file".
RUN chown appuser:appuser /app && \
    mkdir -p /app/storage && chown appuser:appuser /app/storage

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser data/ ./data/

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"

# --workers: start with (2 x CPU cores) + 1, then measure. Each worker is a
# separate PROCESS - Python's GIL means threads will not use your other cores.
# Behind nginx/ALB, so no TLS here; terminate TLS at the proxy.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]

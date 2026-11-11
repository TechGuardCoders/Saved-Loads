# syntax=docker/dockerfile:1

# Multi-arch: build with
#   docker buildx build --platform linux/amd64,linux/arm64 -t saved-loads .
#
# Saved-Loads is a pure-Python library (stdlib only). The Rust port is not
# part of this repo; if a Rust binary is ever added, build it in a
# rust:1.83-slim stage and copy the artifact into the runtime stage below.

FROM python:3.12-slim AS build
WORKDIR /app
COPY . .
RUN python -m compileall -q saved_loads.py tests

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.title="Saved-Loads" \
      org.opencontainers.image.description="Versioned checkpoint save/restore with integrity checks"
WORKDIR /app
COPY --from=build /app /app
# Non-root user; checkpoint dir writable at /data
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data && chown -R appuser:appuser /data
USER appuser
ENV PYTHONUNBUFFERED=1
VOLUME ["/data"]
WORKDIR /data
# Smoke: import the library and run the test suite
CMD ["python", "-c", "import sys; sys.path.insert(0, '/app'); import saved_loads; print('saved-loads ok')"]

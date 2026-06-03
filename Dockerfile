# Single-stage Django image. The frontend is its own App Platform
# component (see chat-frontend/) so this container is just the API + admin.
# WhiteNoise still serves Django admin's own collected static at /static/.

# Base image pinned by immutable multi-arch index digest (not just the
# floating :3.12-slim tag) so a rebuild can't silently pull a different
# underlying image. Update the digest only via a reviewed change.
# Resolve a fresh digest with:
#   docker buildx imagetools inspect python:3.12-slim --format '{{.Manifest.Digest}}'
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend

# Run as an unprivileged user (least privilege — SOC2 CC6.1). The app account
# is created up front; everything copied below is chowned to it so gunicorn,
# the trace-purge worker, and collectstatic all run as non-root. USER is set
# just before CMD so build-time RUN steps (pip install, collectstatic) keep
# the access they need.
RUN useradd --create-home --uid 10001 app

COPY backend/requirements.txt ./
# --require-hashes: requirements.txt is a fully-pinned, hashed lock compiled
# from requirements.in (pip-compile --generate-hashes). A hash mismatch or any
# unpinned/extra package fails the build instead of silently installing an
# untested version. Regenerate the lock with pip-compile, never hand-edit it.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY --chown=app:app backend/ ./

# Collect Django admin's own static into staticfiles/ at build time.
#
# NOTE (SOC2 CC6.1): SECRET_KEY / DATABASE_URL / DEBUG below are NON-SECRET
# build-only placeholders — they only let settings import so collectstatic can
# run (it touches no DB or network). They are set inline on this RUN (not as
# ARG/ENV) so they do not persist as container env vars, though they DO appear
# verbatim in `docker history`. Never pass a REAL secret this way: real secrets
# are injected by App Platform runtime env, and any genuine build-time secret
# must use BuildKit `RUN --mount=type=secret` so it never lands in a layer.
RUN SECRET_KEY=build-only \
    DATABASE_URL=postgres://u:p@localhost:5432/db \
    DEBUG=False \
    python manage.py collectstatic --noinput

# Drop to the unprivileged account for the runtime process (gunicorn API and
# the trace-purge worker, which both reuse this image).
USER app

# app.yaml pins http_port: 8080, so bind it directly. JSON exec form (no
# shell) so gunicorn is PID 1 and gets SIGTERM for graceful drains on
# redeploy.
EXPOSE 8080
CMD ["gunicorn", "core.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

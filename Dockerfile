# Two-stage build: compile the React SPA, then bake it into the Django image
# so Django/WhiteNoise serves it same-origin (settings.WHITENOISE_ROOT).
#
# Repo layout is preserved inside the image (/app/backend, /app/frontend/dist)
# because settings.FRONTEND_DIST is BASE_DIR.parent / "frontend" / "dist".

# ---- Stage 1: frontend ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend ----
FROM python:3.12-slim AS backend
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Collect Django admin's own static into staticfiles/ at build time. The
# real secrets are injected by App Platform at runtime; these throwaway
# values just let settings import (collectstatic touches no DB or network).
RUN SECRET_KEY=build-only \
    DATABASE_URL=postgres://u:p@localhost:5432/db \
    DEBUG=False \
    python manage.py collectstatic --noinput

# app.yaml pins http_port: 8080, so bind it directly. JSON exec form (no
# shell) so gunicorn is PID 1 and gets SIGTERM for graceful drains on
# redeploy. WhiteNoise (in MIDDLEWARE) serves the SPA + admin static.
EXPOSE 8080
CMD ["gunicorn", "core.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

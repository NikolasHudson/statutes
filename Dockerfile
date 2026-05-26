# Single-stage Django image. The frontend is its own App Platform
# component (see chat-frontend/) so this container is just the API + admin.
# WhiteNoise still serves Django admin's own collected static at /static/.

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Collect Django admin's own static into staticfiles/ at build time. The
# real secrets are injected by App Platform at runtime; these throwaway
# values just let settings import (collectstatic touches no DB or network).
RUN SECRET_KEY=build-only \
    DATABASE_URL=postgres://u:p@localhost:5432/db \
    DEBUG=False \
    python manage.py collectstatic --noinput

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

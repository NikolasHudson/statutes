# Iowa Legal Corpus — Backend

Django 5 + Postgres 16 + pgvector. Hosts the corpus models, custom email-login User, API key model, and a Django Ninja API skeleton.

## First-time setup

```bash
cd backend
cp .env.example .env

# Start Postgres + pgvector
docker compose up -d db

# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Apply migrations (installs pg_trgm + vector extensions)
python manage.py migrate

# Create an admin user (logs in by email, not username)
python manage.py createsuperuser
```

## Run

```bash
python manage.py runserver 0.0.0.0:8000
```

- Admin: http://localhost:8000/admin/
- API health: http://localhost:8000/api/health
- API docs (OpenAPI): http://localhost:8000/api/docs

## Layout

```
backend/
├── core/           # Django project (settings, urls, asgi, wsgi)
├── apps/
│   ├── accounts/   # Custom User (email login), APIKey, Tier
│   ├── corpus/     # Jurisdiction, Source, NodeType, Node, NodeVersion, ...
│   └── api/        # Django Ninja API
├── docker-compose.yml
├── manage.py
├── requirements.txt
└── requirements-dev.txt
```

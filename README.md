# GYM CULTURE

GYM CULTURE uses Django Templates, native static files, HTML, CSS and vanilla JavaScript. The Home V1 has no catalogue, cart, checkout or customizer yet.

- `backend/`: Django, REST API, products, users, JWT and media.
- `backend/templates/`: base page, Home and reusable visual sections.
- `backend/static/`: CSS and JavaScript served through Django staticfiles.

Configure the root `.env` with the PostgreSQL values, then run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py runserver
```

Open `http://127.0.0.1:8000/` for the Home. The API health response is `GET /api/`; products and categories are available at `/api/products/` and `/api/categories/`. JWT endpoints are `/api/auth/login/` and `/api/auth/refresh/`.

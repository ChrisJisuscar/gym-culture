# GYM CULTURE

GYM CULTURE uses Django Templates, native static files, HTML, CSS and vanilla JavaScript. The Django backend serves the rendered frontend, REST API and product media.

- `backend/`: Django, REST API, products, users, JWT and media.
- `frontend/templates/`: base page, Home, authentication pages and reusable visual sections.
- `frontend/static/`: CSS, JavaScript and visual assets served through Django staticfiles.
- `backend/media/`: uploaded product media, kept on the backend side.

Configure the root `.env` with the PostgreSQL values, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py runserver
```

Open `http://127.0.0.1:8000/` for the Home. The API health response is `GET /api/`; products and categories are available at `/api/products/` and `/api/categories/`. JWT endpoints are `/api/auth/login/` and `/api/auth/refresh/`.

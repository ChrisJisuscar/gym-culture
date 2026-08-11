# GYM CULTURE backend

## Setup

1. Create and activate a Python virtual environment.
2. Install the backend dependencies:

   ```powershell
   pip install Django djangorestframework djangorestframework-simplejwt python-dotenv "psycopg[binary]"
   ```

3. Copy `.env.example` to `.env` and replace `DJANGO_SECRET_KEY` with a newly generated secret. Never reuse the previously committed key.
4. Start PostgreSQL and create the database configured by `DB_NAME` (the development example is `gym_culture`). Ensure the `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` values in `.env` match your local PostgreSQL instance.
5. From `backend`, run:

   ```powershell
   python manage.py migrate
   python manage.py runserver
   ```

## Authentication API

- `POST /api/auth/register/` accepts `username`, `email`, and `password`. All public registrations become `CUSTOMER` users.
- `POST /api/auth/login/` accepts `username` and `password`, returning `access` and `refresh` JWTs.
- `POST /api/auth/refresh/` accepts `refresh`, returning a new access JWT.
- `GET /api/users/me/` requires `Authorization: Bearer <access-token>` and returns `id`, `username`, `email`, and `role`.

Example login request:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/login/ -ContentType 'application/json' -Body '{"username":"member","password":"your-password"}'
```

Use the returned `refresh` value in the same way with `/api/auth/refresh/`:

```json
{"refresh":"<refresh-token>"}
```

## Validation

Run these commands from `backend`:

```powershell
python manage.py check
python manage.py test
python manage.py makemigrations --check
```

The authentication register and login routes are rate-limited in development. Adjust `login` and `register` rates in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` when needed.

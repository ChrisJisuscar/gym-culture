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

## Custom Lab persistence

The 3D editor keeps changes locally until the customer saves or adds the garment to the cart. It then sends one authenticated multipart request to `POST /api/customizations/`: Django stores uploaded artwork and front/back previews below `MEDIA_ROOT/customizations/`, persists only a versioned reconstruction configuration with asset references, and can create the linked `CartItem` in the same database transaction. Existing designs are loaded with `GET /api/customizations/<uuid>/` and saved with `PATCH` to that URL. Access is restricted to the owner; a customization linked to a cart item must be removed from the cart before it can be deleted.

## Checkout and operations

`POST /api/orders/` converts the authenticated user's cart into an order in one transaction. Product prices are recalculated server-side, product and customization snapshots are stored on each `OrderItem`, variants are locked with `select_for_update()`, and stock is deducted immediately after every item has passed validation. A checkout UUID makes retries idempotent. Purchased customizations are frozen and their previews/assets are retained. Cancelling a pending or confirmed order restores stock exactly once.

Customers use `/checkout/` and `/mis-pedidos/`. Operational users with the `ADMIN` role (or Django staff status) use `/backoffice/` for dashboard metrics, paginated order management, controlled status transitions, the custom-production queue, and authenticated asset downloads. Payment remains `PENDING` until a real payment provider is integrated.

The operational backoffice also owns `/backoffice/products/`, `/backoffice/stock/`, and `/backoffice/customers/`; these no longer depend on Django Admin. Product and variant deactivation preserves historical references. Inventory adjustments lock the variant row and record a `StockMovement`; checkout and cancellation use the same ledger with `ORDER` and `CANCELLATION` entries. Customer totals exclude cancelled orders and administrative serializers never expose authentication fields. Django Admin remains available separately at `/admin/` for technical maintenance.

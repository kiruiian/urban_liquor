# Urban Liquor POS API

Initial liquor-store POS with a React/Vite checkout, staff login, product catalog, stock
adjustments, checkout, and sale history. Prices are treated as final KES amounts;
checkout records cash and M-Pesa tenders, including split payments. M-Pesa is recorded
only—this version does not contact Safaricom or confirm payments with a provider.

## Run locally

1. Create a PostgreSQL database named `urban_liquor`.
2. Copy `.env.example` to `.env` and update `DATABASE_URL` to match your local
   PostgreSQL username/password. Keep `.env` private; it is ignored by Git.
3. Create and activate a virtual environment, then install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Apply the database migration and run the API:

   ```powershell
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

5. Create the first owner account (prompts securely for a password):

   ```powershell
   python -m app.modules.auth.bootstrap --email owner@yourstore.co.ke --name "Store Owner"
   ```

6. In a separate terminal, install and run the POS web client:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

The web client is available at `http://localhost:5173` and proxies API requests to
`http://localhost:8000`. Interactive API documentation is at `http://localhost:8000/docs`.
For deployment, set `VITE_API_URL` to the public API path and configure `DATABASE_URL`,
`SECRET_KEY`, `APP_ENV=production`, `DEBUG=false`, and `CORS_ORIGINS` for the deployment.

## Initial endpoints

- `POST /api/v1/inventory/products` — add a product, optionally with initial stock.
- `GET /api/v1/inventory/products` — list/search products; supports low-stock filtering.
- `GET` / `PATCH /api/v1/inventory/products/{product_id}` — view or edit a product.
- `POST /api/v1/inventory/products/{product_id}/stock-adjustments` — record a signed
  quantity change with a reason.
- `POST /api/v1/sales` — complete checkout using server-side prices, reduce stock, and
  record one or both tenders (`cash`, `mpesa`).
- `GET /api/v1/sales` and `GET /api/v1/sales/{sale_id}` — browse sale history.
- `POST /api/v1/auth/login` — authenticate staff and receive an access token.
- `GET /api/v1/auth/me` — get the authenticated staff member.
- `POST /api/v1/auth/staff` — owner-only creation of an owner or cashier account.

Sales and their stock movements are written in one database transaction. A sale request
contains product IDs and quantities, plus payment allocations that must add up exactly
to the server-calculated total. For cash, `cash_received` can be greater than the
allocation; the response records the change due. An M-Pesa reference may be recorded.

Staff API access is required for products, sales, and inventory. Owners can manage
products and staff; cashiers can view products and complete sales. The first owner is
created once using the CLI bootstrap command.

This is an early development foundation, not a production-ready POS: age-verification
workflows, tax rules, receipt printing, refunds, provider-backed M-Pesa confirmation,
and production deployment hardening/monitoring are not included yet.

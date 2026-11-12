# Urban Liquor POS API

Initial liquor-store POS with a React/Vite checkout, staff login, admin staff and product
management, stock adjustments, checkout, and sale history. Prices are treated as final KES amounts;
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

5. Create the first admin account (prompts securely for a password):

   ```powershell
   python -m app.modules.auth.bootstrap --username storeadmin --name "Store Admin"
   ```

To reset the only admin account when you do not know its current username, and set it
to `admin`:

```powershell
python -m app.modules.auth.reset_credentials --admin --new-username admin
```

The command prompts for and confirms the new password; it does not print or store it in
shell history. If multiple admins exist, target one by its current username instead:

```powershell
python -m app.modules.auth.reset_credentials --username CURRENT_USERNAME --new-username admin
```

6. In a separate terminal, install and run the POS web client:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

The web client is available at `http://localhost:5173` and proxies API requests to
`http://localhost:8000`. Interactive API documentation is at `http://localhost:8000/docs`.
For deployment, build the client with `npm run build` from `frontend/` and publish the
generated `frontend/dist/` directory to a static web host. Set `VITE_API_URL` at build
time to the deployed API base path (for example, `https://api.example.com/api/v1`).
Deploy the FastAPI service separately and configure `DATABASE_URL`, `SECRET_KEY`,
`APP_ENV=production`, `DEBUG=false`, and `CORS_ORIGINS` to include the client origin.

## Run locally as a single-computer app

The POS can run on one Windows computer without a web-hosting subscription. PostgreSQL,
the API, and the built browser client stay on that computer; open the POS at
`http://127.0.0.1:8000`. This setup is only accessible from that computer.

1. Make sure the local PostgreSQL service is running and the `urban_liquor` database
   exists.
2. Copy `.env.example` to `.env`. Set `APP_ENV=production`, `DEBUG=false`, a unique
   `SECRET_KEY` of at least 32 characters, and the local `DATABASE_URL`. Generate a
   key with:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Set `CORS_ORIGINS=http://127.0.0.1:8000`. Use a unique PostgreSQL password rather
   than keeping the sample credentials.

3. Install Python dependencies if needed:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Build the client once (and again after client updates). The local API path is set
   explicitly so the browser uses the same server:

   ```powershell
   Set-Location frontend
   npm ci
   $env:VITE_API_URL = "/api/v1"
   npm run build
   Remove-Item Env:VITE_API_URL
   Set-Location ..
   ```

5. Start the POS:

   ```powershell
   .\run-local.ps1
   ```

   The script applies pending migrations and starts the app bound to this computer only.
   Keep its PowerShell window open while using the POS; press `Ctrl+C` to stop it.

   To start it by double-clicking instead, use `start-pos.bat` in the project folder.
   To run it automatically after signing in to Windows, press `Win+R`, enter
   `shell:startup`, and place a shortcut to `start-pos.bat` in the Startup folder.
   The launcher window must remain open while the POS is in use. PostgreSQL must also
   be configured to start automatically with Windows.

Back up the PostgreSQL database regularly to a separate drive. A local-only installation
does not provide off-site backup or remote access.

## Run tests

The backend tests use Python's standard library and isolated fake database sessions; they
do not connect to or modify the configured store database:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Initial endpoints

- `POST /api/v1/inventory/products` — add a product, optionally with initial stock; the
  API generates an internal SKU when one is not supplied.
- `GET /api/v1/inventory/products` — list/search products; supports low-stock filtering.
- `GET` / `PATCH /api/v1/inventory/products/{product_id}` — view or edit a product.
- `POST /api/v1/inventory/products/{product_id}/stock-adjustments` — record a signed
  quantity change with a reason.
- `GET` / `POST /api/v1/suppliers` — admin-only supplier directory.
- `PATCH /api/v1/suppliers/{supplier_id}` — admin-only supplier contact and activation updates.
- `GET /api/v1/suppliers/receipts` and `POST /api/v1/suppliers/receipts` — admin-only
  supplier delivery history and stock receiving; duplicate supplier references are rejected.
- `GET /api/v1/wholesale/customers` — list shops that buy stock from the depot.
- `POST` / `PATCH /api/v1/wholesale/customers` — admin-only shop customer management.
- `GET` / `POST /api/v1/wholesale/sales` — list or record shop deliveries at negotiated
  per-delivery product prices; deliveries reduce depot stock and may be paid now or on credit.
- `POST /api/v1/wholesale/sales/{sale_id}/payments` — record cash or M-Pesa payments
  against an outstanding wholesale balance.
- `POST /api/v1/sales` — complete checkout using server-side prices, reduce stock, and
  record one or both tenders (`cash`, `mpesa`).
- `GET /api/v1/sales` and `GET /api/v1/sales/{sale_id}` — browse sale history.
- `GET /api/v1/sales/summary/daily?date=YYYY-MM-DD` — daily sales count and cash/M-Pesa
  payment allocations, using the Africa/Nairobi calendar day.
- `GET /api/v1/sales/summary?period=daily|weekly|monthly&date=YYYY-MM-DD` — cumulative
  sales totals for the selected local day, Monday-to-Sunday week, or calendar month.
- `POST /api/v1/auth/login` — authenticate staff and receive an access token.
- `GET /api/v1/auth/me` — get the authenticated staff member.
- `POST /api/v1/auth/staff` — admin-only creation of an admin or cashier account.
- `GET /api/v1/auth/staff` — admin-only staff directory.
- `PATCH /api/v1/auth/staff/{staff_id}` — admin-only staff profile, role, and activation updates.

Sales and their stock movements are written in one database transaction. A sale request
contains product IDs and quantities, plus payment allocations that must add up exactly
to the server-calculated total. For cash, `cash_received` can be greater than the
allocation; the response records the change due. An M-Pesa reference may be recorded.

Staff API access is required for products, sales, and inventory. Admins can manage
products and staff; cashiers can view products, complete sales, and review sales
summaries and transaction details. The first admin is
created once using the CLI bootstrap command. New staff sign in with a username.
Existing accounts keep their former email value as their initial username after
migration; enter that value in the username field.

Admins and cashiers see an in-app low-stock alert for active products whose quantity
is at or below the product's configured low-stock threshold.

Admins can manage supplier contacts and record deliveries using an invoice or delivery
reference. Each receipt updates stock and creates stock-movement records. Cashiers and
admins can print a customer sales receipt from the checkout confirmation using the
browser's print dialog.

Admins manage wholesale shop accounts; admins and cashiers can record shop deliveries,
set the agreed unit price for each line, take cash/M-Pesa payments, and apply later
payments to the outstanding balance. Wholesale deliveries create stock movements and
printable invoices; they are tracked separately from counter sales.

This is an early development foundation, not a production-ready POS: age-verification
workflows, tax rules, refunds, provider-backed M-Pesa confirmation, and production
deployment hardening/monitoring are not included yet.

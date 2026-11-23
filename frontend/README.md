# Soundwave — Music Store Frontend

A React 19 + TypeScript + Vite + Tailwind CSS 4 frontend for the team's **E-commerce Product Recommendation** repository. The storefront is inspired by the category-first, instrument-focused merchandising approach of independent specialist music retailers (including Tân Nhạc Cụ), but uses its own UI, copy, and code. It is **not a clone** of the reference site.

## Routes

| Route | Description | API |
|---|---|---|
| `/` | Editorial music-store homepage, categories, featured products, optional personalized recommendations | `GET /api/v1/products`, `GET /api/v1/recommendations/{user_id}`, `POST /api/v1/products/batch` |
| `/shop` | Search, category filter, sorting, pagination | `GET /api/v1/products` |
| `/products/:productId` | Product information, high-resolution gallery, Add to Cart and Buy Now | `GET /api/v1/products/{id}`, `POST /api/v1/cart/items` |
| `/cart` | Authenticated cart, quantity changes, remove and checkout navigation | `GET /api/v1/cart`, `PUT /api/v1/cart/items/{id}` |
| `/checkout` | Checkout form and order submission (authenticated) | `POST /api/v1/orders/checkout` |
| `/signin`, `/signup` | Authentication | Auth service |
| `/profile`, `/profile/edit` | Account dashboard and profile editor | Auth service |
| `/profile/purchases` | Purchase history, filter and order detail modal | Order service |
| `/profile/notifications` | Notification inbox and detail modal | Demo storage only |

The home page and product pages are public; account and cart pages are protected. My Purchases and Notifications open detailed modal views, including click-outside and Escape dismissal. Deep links still work as standalone pages.

## Local install (VS Code / Windows PowerShell)

In the *cloned repository* from GitHub, copy the contents of this package's `frontend/` into the repository's `frontend/`. Preserve any teammate changes you want to keep.

```powershell
cd D:\repogit\E-commerce-Product-Recommendation\frontend
npm install
```

Create `frontend/.env.local` with:

```dotenv
VITE_DEMO_MODE=true
```

Then run:

```powershell
npm run dev
```

Open **http://localhost:5173/**. The local demo login is `alexmusic` / `Demo123!`. You can also create a demo account. The app uses sample images and VND prices **only in demo mode**. No images need to be downloaded from Hugging Face yet.

> Demo products and cart/order data are local examples, not actual inventory or payment records. The demo auth implementation stores accounts locally and is not suitable for production use. Do not enter real credentials or private information in demo mode.

## Backend integration

When ready, change `.env.local` to:

```dotenv
VITE_DEMO_MODE=false
# Leave empty when running via AKS same-origin ingress
VITE_API_BASE_URL=
# OR configure separate endpoints if needed:
# VITE_AUTH_API_URL=http://localhost:8001
# VITE_ORDER_API_URL=http://localhost:8002
# VITE_RECOMMENDER_API_URL=http://localhost:8003
```

The Vite development server proxies `/api/v1/auth` to port 8001, `/api/v1/products`, `/api/v1/cart`, `/api/v1/orders` to port 8002, and `/api/v1/recommendations` to port 8003. Production Nginx serves the SPA and the existing AKS ingress is expected to route `/api/v1/*` to the correct services.

**Important price contract:** The UI displays monetary values as `vi-VN`/VND, including order and cart totals, **without exchange-rate conversion**. Confirm that your team's source database and backend API have converted all amounts into VND before using live data. If the backend still stores USD, you must migrate/convert values in backend/database, not simply relabel the numbers as VND. High-value VND product prices may also require increasing the database's current `NUMERIC(10,2)` precision.

**Backend limitations:** Live profile updates (`PATCH /api/v1/auth/me`), notifications, courier milestones and payment details are not implemented in the referenced backend snapshot. The relevant actions are disabled or absent; the frontend does not fabricate API data. Shopping bag supports add/update/remove, and the checkout page can create an order in the development backend. **The checkout API does not yet store shipping details or charge a payment method.** No real payment processing is implemented.

**Authentication:** The prototype currently uses `sessionStorage` bearer tokens. Before accepting real users, review safer session management with the backend team. Public registration role assignment and password validation must also be enforced server-side.

## Images

- Demo and editorial imagery currently references freely usable Unsplash photos by URL; these require internet access and may be replaced with team-owned product images later.
- If an image fails, the app falls back to `public/assets/instrument-placeholder.svg`.
- **Production:** render product `large_urls` / `hi_res_url` where practical, and fall back to `image_url` / `thumb_url` from `GET /api/v1/products`; these should resolve to the team’s Azure Blob Storage assets. The React app should not embed Hugging Face access tokens or database secrets.
- All demo product names, prices and reviews are examples only.

## Report fixes and presentation preferences (revision 7)

- **E02 name-focused search:** Both homepage search and catalog search now match **product names only**, ignoring description-only matches. The backend's `/api/v1/products?search=` still matches descriptions; for searched lists, the frontend loads candidate pages (up to 100 products per request), filters every name, ranks exact / prefix / substring / all-word results, then paginates consistently. This makes searches more accurate but can issue extra read-only requests for broad queries. Ordinary catalog browsing remains server-paginated.
- **E04 purchase-search overlap:** A dedicated `.purchase-search-input` class reserves enough left space for the search icon on mobile and desktop.
- **Settings:** Hamburger menu on desktop/mobile; click-away and Escape dismissal; saved **light/dark theme** and **English/Vietnamese** preferences. When English is active the button says “Language: Vietnamese”; when Vietnamese is active it says “Ngôn ngữ: Tiếng Anh”. Demo UI text is translated. Backend product metadata stays in the language supplied by the API.
- **Image quality:** Product cards prefer `large_urls[0]`, detail pages prefer `hi_res_url`, and both preserve aspect ratio (`object-contain`). Broken image requests fall back through alternate URLs. This cannot increase the actual source resolution; verify Azure Blob originals before migrating to Hugging Face assets.
- **Current branch features preserved:** Buy Now, Checkout, interaction logging, the cart, and all account routes. The checkout test-only amber panel is hidden by default. For explicit **isolated development-database** rollback testing only, set `VITE_ENABLE_FAILURE_TEST=true` in `.env.local`, restart Vite, and unset it afterward.
- **Known backend gaps (unchanged):** Profile edits and delivery address persistence require backend changes. The checkout UI clearly discloses that shipping/payment values are not yet stored or charged.

### Quick quality checks

```powershell
cd D:\repogit\E-commerce-Product-Recommendation\frontend
npm install
npm run build
npm run lint
npm run dev
```

Test in both languages, both themes, and at mobile widths. Confirm search `mixer` excludes items where only the description mentions mixer, verify a multi-page search, check My Purchases search text/icon separation, inspect product cards and high-resolution image previews, and verify Buy Now / Checkout against **disposable** backend test data.

## Build and deployment

```powershell
npm install         # generates package-lock.json
npm run build       # tsc -b && vite build
npm run lint
```

Commit `frontend/package-lock.json` because GitHub Actions uses `npm ci`. Do **not** commit `node_modules`, `dist` or `.env.local`.

The included `Dockerfile` and `nginx.conf` remain aligned with the main branch AKS/Nginx frontend deployment setup. CI configuration is in `.github/workflows/deploy-frontend.yml` at the repository root.

## Design reference

- https://tannhaccu.vn/
- https://tannhaccu.vn/collections/dan-piano

The reference sites guided category discovery, editorial imagery, and clear product cards—not exact designs, assets, claims, or copy.

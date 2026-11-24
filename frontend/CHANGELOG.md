## v8 — Review API integration and payment UI correction
- Public product reviews and JWT-protected star rating/comments connected to FastAPI Order Service.
- Review events recorded with the supported FaaS `rating` action; UI supports theme, translation and demo storage.
- Online payment selector changed from cards/e-wallets to VietQR, with explicit backend-not-ready protection. COD-style test order behavior unchanged; no fake payment confirmation.
- Existing v7 improvements and checkout/Buy Now preserved.

# Frontend homepage release — v5

- New independent music-store homepage at `/`: editorial hero, instrument collection cards, featured catalog tabs, optional authenticated recommendations, and discovery sections.
- New browsable catalog at `/shop` with URL-backed category/search/sort/page state.
- New product detail route at `/products/:productId`, quantity selector, and add-to-cart.
- New authenticated `/cart` page with line-item quantity and removal; checkout intentionally excluded.
- Shared responsive storefront navigation (logo goes home, search works, category paths work, account and bag shortcuts) and footer.
- Preserved Sign In, Sign Up, Profile, Edit Profile, My Purchases and Notifications; order and notification dialogs remain same-tab modals.
- Removed yellow demo/developer note banners on account pages and removed the redundant support/account-center header badges.
- Demo catalog and demo orders now show Vietnamese Dong. Live pricing must be converted by the backend/database before activating live mode.
- Product images use backend image URL fields when live; sample/editorial photos use Unsplash links with an offline SVG fallback.
- Added `/api/v1/products`, `/api/v1/cart`, `/api/v1/recommendations` to the Vite development proxy and `src/vite-env.d.ts` for Vite environment variable typing.

## Known backend constraints

Profile updating, notifications, shipping details, payment method, and checkout/payment completion require further backend work. No false data is sent to Azure. See README for integration instructions and security considerations.


## v7 — Frontend report corrections
- Search: name-only matching, exact/prefix ranking, and full filtered pagination across backend pages.
- My Purchases: fixed search icon/placeholder overlap.
- Integrated saved English/Vietnamese and dark/light preferences from v6 into the branch with Checkout and Buy Now.
- Higher-resolution Azure product imagery with aspect-ratio preservation and image URL fallbacks.
- Removed checkout's yellow developer test panel from ordinary UI (opt-in via environment variable).
- Documented backend gaps and preserved checkout, existing account routes, and Azure deployment files.

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

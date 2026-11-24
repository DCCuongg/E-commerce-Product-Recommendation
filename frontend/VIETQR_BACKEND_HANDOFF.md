# VietQR integration — backend/frontend handoff (pending contract)

## Confirmed in `E-commerce-Product-Recommendation-main(1)(1).zip`

- The Order API implements `POST /api/v1/orders/checkout` with optional `items` and `simulate_failure`. It creates a `CONFIRMED` order and returns `OrderResponse` (order ID, user, total, status, items).
- Neither this checkout request nor the returned order carries a payment method, payment reference, VietQR code, transaction expiry, or payment status.
- `services/order_service/payment_handler.py` and `/api/v1/payments` routes described in the root README are **not present** in the included source code.
- Root SQL describes payment-related tables, but a schema alone does not create a functioning payment service.
- The frontend displays amounts in USD. An actual Vietnamese bank transfer needs a correctly determined VND payable amount from the trusted backend.

## Backend team decisions needed before enabling online payment

1. Define a dedicated **authenticated** checkout/payment-initiation endpoint for `payment_method=ONLINE` that creates an order in `PENDING_PAYMENT` and atomically reserves inventory. Do not reuse the existing checkout endpoint unchanged for online payment.
2. Return trustworthy data for the payment screen: `order_id`, **VND** amount, bank/VietQR QR payload or image URL, a unique `payment_code`, payment expiry, and current `payment_status`. The backend—not the browser—must determine the exchange rate and final amount.
3. Define an authenticated payment-status read endpoint and state values (at least `PENDING_PAYMENT`, `PAID/CONFIRMED`, `EXPIRED`, `CANCELLED`). Define an idempotent and authenticated/verified webhook receiver for payment confirmation. **Never** mark an order paid based only on a frontend button, QR display, or unverified webhook.
4. Specify how the pending order releases inventory on expiry/cancellation and how retry/double payment is handled.
5. Extend existing COD checkout to record `payment_method=COD`, and persist shipping/contact details in a dedicated checkout request with appropriate access controls, or clearly separate that as a follow-up.
6. Agree on request/response JSON and routing (Vite proxy and AKS Ingress) before writing the frontend client. **No example endpoint names in this handoff should be interpreted as already implemented.**

## Frontend readiness in this revision

- The checkout UI now offers only **Cash on Delivery** and **VietQR bank transfer**.
- Selecting VietQR displays an explicit integration-pending explanation and disables submission. No fake QR, static bank details, or payment confirmation is generated.
- COD-style checkout still uses the existing order creation API **for isolated test usage**; the current backend does not store that payment selection.
- After the backend payment API arrives: show the server-generated QR in a pending-payment state, handle expiry/retry and poll payment status; only navigate to an authenticated order confirmation when the server reports payment succeeded.

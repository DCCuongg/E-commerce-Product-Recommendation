import { DEMO_MODE } from './auth';

export type ProductReview = {
  id: number;
  user_id: string;
  product_id: string;
  rating: number;
  title: string | null;
  comment: string | null;
  created_at: string | null;
};

export type NewReview = {
  rating: number;
  title?: string;
  comment?: string;
};

const API_URL = (import.meta.env.VITE_ORDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const DEMO_REVIEWS_KEY = 'soundwave-demo-product-reviews-v1';

function demoReviews(): ProductReview[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(DEMO_REVIEWS_KEY) || '[]');
    return Array.isArray(value) ? value as ProductReview[] : [];
  } catch {
    return [];
  }
}

async function responseError(response: Response): Promise<Error> {
  const body: unknown = await response.json().catch(() => null);
  const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
  const message = typeof detail === 'string'
    ? detail
    : detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string'
      ? detail.message
      : `Review request failed (${response.status}).`;
  return new Error(message);
}

/** GET is public, including when the visitor is not logged in. */
export async function getProductReviews(productId: string, limit = 20): Promise<ProductReview[]> {
  const safeLimit = Math.min(100, Math.max(1, Math.floor(limit)));
  if (DEMO_MODE) {
    return demoReviews()
      .filter((review) => review.product_id === productId)
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      .slice(0, safeLimit);
  }
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/products/${encodeURIComponent(productId)}/reviews?limit=${safeLimit}`);
  } catch {
    throw new Error('Cannot reach the review service. Check that the Order API is running.');
  }
  if (!response.ok) throw await responseError(response);
  const reviews: unknown = await response.json();
  if (!Array.isArray(reviews)) throw new Error('Unexpected review response from the server.');
  return reviews as ProductReview[];
}

/** The POST requires an Auth Service JWT and records the review in PostgreSQL. */
export async function submitProductReview(
  productId: string,
  token: string | null,
  userId: string,
  input: NewReview,
): Promise<ProductReview> {
  if (!Number.isInteger(input.rating) || input.rating < 1 || input.rating > 5) {
    throw new Error('Please choose a rating from 1 to 5 stars.');
  }
  const payload = {
    rating: input.rating,
    title: (input.title || '').trim().slice(0, 255),
    comment: (input.comment || '').trim(),
  };
  if (DEMO_MODE) {
    const created: ProductReview = {
      id: Date.now(),
      user_id: userId,
      product_id: productId,
      rating: payload.rating,
      title: payload.title,
      comment: payload.comment,
      created_at: new Date().toISOString(),
    };
    localStorage.setItem(DEMO_REVIEWS_KEY, JSON.stringify([created, ...demoReviews()]));
    return created;
  }
  if (!token) throw new Error('Please sign in to write a review.');
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/products/${encodeURIComponent(productId)}/reviews`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error('Cannot reach the review service. Check that the Order API is running.');
  }
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<ProductReview>;
}

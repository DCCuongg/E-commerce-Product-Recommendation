import { TOKEN_KEY } from '../context/AuthContext';
import { DEMO_MODE } from './auth';
import { demoProducts, type Product } from './catalog';

export type CartLine = {
  product_id: string;
  product_name: string;
  image_url?: string | null;
  thumb_url?: string | null;
  unit_price: number;
  quantity: number;
  subtotal: number;
  stock_quantity: number;
};

export type Cart = {
  total_amount: number;
  total_quantity: number;
  items: CartLine[];
};

const API = (import.meta.env.VITE_ORDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const key = (userId: string) => `soundwave-demo-cart-${userId}`;

function demoRead(userId: string): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(key(userId)) || '{}') as Record<string, number>;
  } catch {
    return {};
  }
}

function demoSave(userId: string, items: Record<string, number>) {
  localStorage.setItem(key(userId), JSON.stringify(items));
}

function demoCart(userId: string): Cart {
  const lines = Object.entries(demoRead(userId)).flatMap(([id, quantity]) => {
    const product: Product | undefined = demoProducts.find((p) => p.id === id);
    return product && quantity > 0
      ? [
          {
            product_id: id,
            product_name: product.name,
            image_url: product.image_url,
            unit_price: product.price,
            quantity,
            subtotal: product.price * quantity,
            stock_quantity: product.stock_quantity,
          },
        ]
      : [];
  });
  return {
    items: lines,
    total_quantity: lines.reduce((s, p) => s + p.quantity, 0),
    total_amount: lines.reduce((s, p) => s + p.subtotal, 0),
  };
}

async function cartRequest(path: string, init: RequestInit = {}) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) throw new Error('Please sign in to manage your cart.');
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Cart request failed (${response.status}).`);
  }
  const data = (await response.json()) as Cart;
  if (init.method && init.method !== 'GET') {
    window.dispatchEvent(new Event('soundwave-cart-update'));
  }
  return data;
}

export async function getCart(userId: string): Promise<Cart> {
  return DEMO_MODE ? demoCart(userId) : cartRequest('/api/v1/cart');
}

export async function addToCart(userId: string, id: string, quantity = 1): Promise<Cart> {
  if (!DEMO_MODE) {
    return cartRequest('/api/v1/cart/items', {
      method: 'POST',
      body: JSON.stringify({ product_id: id, quantity }),
    });
  }
  const data = demoRead(userId);
  const product = demoProducts.find((p) => p.id === id);
  if (!product) throw new Error('Product not found.');
  if ((data[id] || 0) + quantity > product.stock_quantity) throw new Error('Not enough stock available.');
  data[id] = (data[id] || 0) + quantity;
  demoSave(userId, data);
  window.dispatchEvent(new Event('soundwave-cart-update'));
  return demoCart(userId);
}

export async function setCartQuantity(userId: string, id: string, quantity: number): Promise<Cart> {
  if (!DEMO_MODE) {
    if (quantity <= 0) {
      return cartRequest(`/api/v1/cart/items/${encodeURIComponent(id)}`, { method: 'DELETE' });
    }
    return cartRequest(`/api/v1/cart/items/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify({ quantity }),
    });
  }
  const data = demoRead(userId);
  const p = demoProducts.find((x) => x.id === id);
  if (p && quantity > p.stock_quantity) throw new Error('Not enough stock available.');
  if (quantity <= 0) delete data[id];
  else data[id] = quantity;
  demoSave(userId, data);
  window.dispatchEvent(new Event('soundwave-cart-update'));
  return demoCart(userId);
}

export async function clearCart(userId: string): Promise<Cart> {
  if (!DEMO_MODE) return cartRequest('/api/v1/cart', { method: 'DELETE' });
  demoSave(userId, {});
  window.dispatchEvent(new Event('soundwave-cart-update'));
  return { items: [], total_quantity: 0, total_amount: 0 };
}
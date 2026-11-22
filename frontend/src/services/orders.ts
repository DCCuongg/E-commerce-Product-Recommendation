import { DEMO_MODE } from './auth';
import { clearCart, getCart } from './cart';
import { demoProducts, editorialImages, formatVND } from './catalog';

export type OrderItem = {
  id: number;
  product_id: string;
  product_name: string | null;
  image_url: string | null;
  thumb_url?: string | null;
  quantity: number;
  unit_price: number;
  subtotal: number;
};

export type Order = {
  id: number;
  user_id: string;
  total_amount: number;
  status: string;
  created_at: string | null;
  items: OrderItem[];
};

export type CheckoutPayload = {
  items?: Array<{ product_id: string; quantity: number }>;
  simulate_failure?: boolean;
};

const API_URL = (import.meta.env.VITE_ORDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const demoOrdersKey = (userId: string) => `soundwave-demo-orders-${userId}`;

const demoItems: OrderItem[] = [
  { id: 1, product_id: 'DEMO-G02', product_name: 'Ivory Electric Guitar', image_url: editorialImages.electric, thumb_url: null, quantity: 1, unit_price: 9750000, subtotal: 9750000 },
  { id: 2, product_id: 'DEMO-S01', product_name: 'Home Studio Accessories', image_url: editorialImages.studio, thumb_url: null, quantity: 1, unit_price: 350000, subtotal: 350000 },
  { id: 3, product_id: 'DEMO-K01', product_name: 'Essential 61 Keyboard', image_url: editorialImages.keys, thumb_url: null, quantity: 1, unit_price: 6400000, subtotal: 6400000 },
  { id: 4, product_id: 'DEMO-HDP', product_name: 'Studio Monitor Headphones', image_url: editorialImages.studio, thumb_url: null, quantity: 1, unit_price: 2850000, subtotal: 2850000 },
];

function readSavedDemoOrders(userId: string): Order[] {
  try {
    return JSON.parse(localStorage.getItem(demoOrdersKey(userId)) || '[]') as Order[];
  } catch {
    return [];
  }
}

export async function getOrders(token: string, userId: string): Promise<Order[]> {
  if (DEMO_MODE) {
    const base: Order[] = [
      { id: 10428, user_id: userId, total_amount: 10100000, status: 'CONFIRMED', created_at: '2026-11-18T10:30:00Z', items: demoItems.slice(0, 2) },
      { id: 10396, user_id: userId, total_amount: 6400000, status: 'DELIVERED', created_at: '2026-11-02T12:20:00Z', items: [demoItems[2]] },
      { id: 10281, user_id: userId, total_amount: 2850000, status: 'DELIVERED', created_at: '2026-10-11T08:40:00Z', items: [demoItems[3]] },
    ];
    return [...readSavedDemoOrders(userId), ...base];
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/orders`, { headers: { Authorization: `Bearer ${token}` } });
  } catch {
    throw new Error('Cannot reach the order service. Check VITE_ORDER_API_URL and that the backend is running.');
  }
  if (!response.ok) throw new Error(`Unable to fetch orders (${response.status}).`);
  return (await response.json()) as Order[];
}

export async function checkoutOrder(
  token: string | null,
  userId: string,
  payload: CheckoutPayload = {},
): Promise<Order> {
  if (DEMO_MODE) {
    await new Promise((r) => setTimeout(r, 350));
    if (payload.simulate_failure) {
      throw new Error('Payment gateway declined (simulated). PostgreSQL ROLLBACK restored inventory.');
    }

    let orderItems: OrderItem[] = [];
    if (payload.items && payload.items.length > 0) {
      orderItems = payload.items.map((req, idx) => {
        const p = demoProducts.find((x) => x.id === req.product_id);
        if (!p) throw new Error(`Product ${req.product_id} not found.`);
        if (req.quantity > p.stock_quantity) throw new Error('INSUFFICIENT_STOCK: Not enough inventory.');
        return {
          id: Date.now() + idx,
          product_id: p.id,
          product_name: p.name,
          image_url: p.image_url,
          thumb_url: p.thumb_url ?? null,
          quantity: req.quantity,
          unit_price: p.price,
          subtotal: p.price * req.quantity,
        };
      });
    } else {
      const cart = await getCart(userId);
      if (!cart.items.length) throw new Error('Your shopping bag is empty.');
      orderItems = cart.items.map((c, idx) => ({
        id: Date.now() + idx,
        product_id: c.product_id,
        product_name: c.product_name,
        image_url: c.image_url ?? null,
        thumb_url: c.thumb_url ?? null,
        quantity: c.quantity,
        unit_price: c.unit_price,
        subtotal: c.subtotal,
      }));
      await clearCart(userId);
    }

    const created: Order = {
      id: Math.floor(10500 + Math.random() * 89000),
      user_id: userId,
      total_amount: orderItems.reduce((sum, i) => sum + i.subtotal, 0),
      status: 'CONFIRMED',
      created_at: new Date().toISOString(),
      items: orderItems,
    };
    const existing = readSavedDemoOrders(userId);
    localStorage.setItem(demoOrdersKey(userId), JSON.stringify([created, ...existing]));
    return created;
  }

  if (!token) throw new Error('Please sign in to complete your order.');

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/orders/checkout`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error('Cannot reach the order service to process checkout.');
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 409) {
      throw new Error(
        typeof body.detail === 'string'
          ? body.detail
          : 'Insufficient stock (409 Conflict). Someone else may have purchased the remaining items.',
      );
    }
    throw new Error(
      typeof body.detail === 'string' ? body.detail : `Checkout failed (${response.status}). Inventory rolled back.`,
    );
  }

  if (!payload.items?.length) {
    window.dispatchEvent(new Event('soundwave-cart-update'));
  }
  return body as Order;
}

export const formatMoney = formatVND;
export const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'Date unavailable';
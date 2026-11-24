import { DEMO_MODE } from './auth';
import { clearCart, getCart } from './cart';
import { demoProducts, editorialImages, formatVND } from './catalog';

export type PaymentMethod = 'COD' | 'ONLINE';

export type PaymentStatus =
  | 'PENDING'
  | 'PAID'
  | 'EXPIRED'
  | 'FAILED'
  | 'REFUNDED';

export type VietQRPaymentInfo = {
  qr_url?: string;
  qr_image_url?: string;
  vietqr_url?: string;
  bank_id?: string;
  bank_bin?: string;
  bank_name?: string;
  account_no?: string;
  account_number?: string;
  account_name?: string;
  amount_vnd?: number;
  amount?: number;
  transfer_content?: string;
  content?: string;
  add_info?: string;
  payment_code?: string;
  expires_at?: string | null;
  [key: string]: unknown;
};

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
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  payment_code?: string | null;
  payment_expires_at?: string | null;
  paid_at?: string | null;
  payment_info?: VietQRPaymentInfo | null;
  created_at: string | null;
  items: OrderItem[];
};

export type OrderPaymentStatusResponse = {
  order_id: number;
  status: string;
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  payment_code?: string | null;
  paid_at?: string | null;
  payment_expires_at?: string | null;
  remaining_seconds: number;
};

export type CheckoutPayload = {
  items?: Array<{ product_id: string; quantity: number }>;
  payment_method?: PaymentMethod;
  simulate_failure?: boolean;
};

const API_URL = (
  import.meta.env.VITE_ORDER_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  ''
).replace(/\/$/, '');

const demoOrdersKey = (userId: string) => `soundwave-demo-orders-${userId}`;

const demoItems: OrderItem[] = [
  {
    id: 1,
    product_id: 'DEMO-G02',
    product_name: 'Ivory Electric Guitar',
    image_url: editorialImages.electric,
    thumb_url: null,
    quantity: 1,
    unit_price: 9750000,
    subtotal: 9750000,
  },
  {
    id: 2,
    product_id: 'DEMO-S01',
    product_name: 'Home Studio Accessories',
    image_url: editorialImages.studio,
    thumb_url: null,
    quantity: 1,
    unit_price: 350000,
    subtotal: 350000,
  },
  {
    id: 3,
    product_id: 'DEMO-K01',
    product_name: 'Essential 61 Keyboard',
    image_url: editorialImages.keys,
    thumb_url: null,
    quantity: 1,
    unit_price: 6400000,
    subtotal: 6400000,
  },
  {
    id: 4,
    product_id: 'DEMO-HDP',
    product_name: 'Studio Monitor Headphones',
    image_url: editorialImages.studio,
    thumb_url: null,
    quantity: 1,
    unit_price: 2850000,
    subtotal: 2850000,
  },
];

function readSavedDemoOrders(userId: string): Order[] {
  try {
    return JSON.parse(localStorage.getItem(demoOrdersKey(userId)) || '[]') as Order[];
  } catch {
    return [];
  }
}

function writeSavedDemoOrders(userId: string, orders: Order[]): void {
  localStorage.setItem(demoOrdersKey(userId), JSON.stringify(orders));
}

function getBaseDemoOrders(userId: string): Order[] {
  return [
    {
      id: 10428,
      user_id: userId,
      total_amount: 10100000,
      status: 'CONFIRMED',
      payment_method: 'ONLINE',
      payment_status: 'PAID',
      payment_code: 'PAY10428DEMO',
      paid_at: '2026-11-18T10:32:00Z',
      created_at: '2026-11-18T10:30:00Z',
      items: demoItems.slice(0, 2),
    },
    {
      id: 10396,
      user_id: userId,
      total_amount: 6400000,
      status: 'DELIVERED',
      payment_method: 'COD',
      payment_status: 'PAID',
      paid_at: '2026-11-05T14:00:00Z',
      created_at: '2026-11-02T12:20:00Z',
      items: [demoItems[2]],
    },
    {
      id: 10281,
      user_id: userId,
      total_amount: 2850000,
      status: 'DELIVERED',
      payment_method: 'COD',
      payment_status: 'PAID',
      paid_at: '2026-10-14T09:15:00Z',
      created_at: '2026-10-11T08:40:00Z',
      items: [demoItems[3]],
    },
  ];
}

function buildDemoVietQRInfo(
  orderId: number,
  totalAmount: number,
  expiresAt: string,
): VietQRPaymentInfo {
  const paymentCode = `PAY${orderId}`;
  const amountVnd = Math.round(totalAmount);
  return {
    qr_url: `https://img.vietqr.io/image/MB-0000123456789-compact2.png?amount=${amountVnd}&addInfo=${paymentCode}&accountName=SOUNDWAVE%20STORE`,
    bank_id: 'MB',
    bank_name: 'MB Bank',
    account_no: '0000123456789',
    account_name: 'SOUNDWAVE STORE',
    amount_vnd: amountVnd,
    transfer_content: paymentCode,
    payment_code: paymentCode,
    expires_at: expiresAt,
  };
}

export function simulateDemoOrderPaid(userId: string, orderId: number): Order | null {
  if (!DEMO_MODE) return null;
  const saved = readSavedDemoOrders(userId);
  let updatedOrder: Order | null = null;
  const next = saved.map((o) => {
    if (o.id !== orderId) return o;
    updatedOrder = {
      ...o,
      status: 'CONFIRMED',
      payment_status: 'PAID',
      paid_at: new Date().toISOString(),
      payment_info: null,
    };
    return updatedOrder;
  });
  writeSavedDemoOrders(userId, next);
  return updatedOrder;
}

export async function getOrders(token: string, userId: string): Promise<Order[]> {
  if (DEMO_MODE) {
    return [...readSavedDemoOrders(userId), ...getBaseDemoOrders(userId)];
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/orders`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error(
      'Cannot reach the order service. Check VITE_ORDER_API_URL and that the backend is running.',
    );
  }
  if (!response.ok) throw new Error(`Unable to fetch orders (${response.status}).`);
  return (await response.json()) as Order[];
}

export async function getOrderById(
  token: string,
  orderId: number,
  userId?: string,
): Promise<Order> {
  if (DEMO_MODE) {
    const all = [
      ...(userId ? readSavedDemoOrders(userId) : []),
      ...getBaseDemoOrders(userId || 'demo-user'),
    ];
    const found = all.find((o) => o.id === orderId);
    if (!found) throw new Error(`Order #${orderId} not found.`);
    return found;
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/orders/${orderId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error('Cannot reach the order service to load order details.');
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : `Unable to fetch order #${orderId} (${response.status}).`,
    );
  }
  return body as Order;
}

export async function getOrderPaymentStatus(
  token: string,
  orderId: number,
  userId?: string,
): Promise<OrderPaymentStatusResponse> {
  if (DEMO_MODE) {
    const order = await getOrderById(token, orderId, userId);
    const expiresMs = order.payment_expires_at
      ? new Date(order.payment_expires_at).getTime()
      : 0;
    const remaining =
      order.payment_status === 'PENDING' && expiresMs > Date.now()
        ? Math.floor((expiresMs - Date.now()) / 1000)
        : 0;

    return {
      order_id: order.id,
      status: order.status,
      payment_method: order.payment_method,
      payment_status: order.payment_status,
      payment_code: order.payment_code,
      paid_at: order.paid_at,
      payment_expires_at: order.payment_expires_at,
      remaining_seconds: remaining,
    };
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/orders/${orderId}/payment-status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error('Cannot check payment status right now.');
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : `Unable to check payment status (${response.status}).`,
    );
  }
  return body as OrderPaymentStatusResponse;
}

export async function cancelOrder(
  token: string,
  orderId: number,
  userId?: string,
): Promise<Order> {
  if (DEMO_MODE) {
    if (!userId) throw new Error('User session not found.');
    const saved = readSavedDemoOrders(userId);
    const updated = saved.map((o) =>
      o.id === orderId
        ? {
          ...o,
          status: 'CANCELLED',
          payment_status:
            o.payment_status === 'PAID'
              ? ('REFUNDED' as PaymentStatus)
              : ('EXPIRED' as PaymentStatus),
          payment_info: null,
        }
        : o,
    );
    writeSavedDemoOrders(userId, updated);
    return getOrderById(token, orderId, userId);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/orders/${orderId}/cancel`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error('Cannot reach the order service to cancel order.');
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : `Unable to cancel order #${orderId} (${response.status}).`,
    );
  }
  return body as Order;
}

export async function checkoutOrder(
  token: string | null,
  userId: string,
  payload: CheckoutPayload = {},
): Promise<Order> {
  const paymentMethod: PaymentMethod = payload.payment_method || 'COD';

  if (DEMO_MODE) {
    await new Promise((r) => setTimeout(r, 350));
    if (payload.simulate_failure) {
      throw new Error(
        'Payment gateway declined (simulated). PostgreSQL ROLLBACK restored inventory.',
      );
    }

    let orderItems: OrderItem[] = [];
    if (payload.items && payload.items.length > 0) {
      orderItems = payload.items.map((req, idx) => {
        const p = demoProducts.find((x) => x.id === req.product_id);
        if (!p) throw new Error(`Product ${req.product_id} not found.`);
        if (req.quantity > p.stock_quantity) {
          throw new Error('INSUFFICIENT_STOCK: Not enough inventory.');
        }
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

    const orderId = Math.floor(10500 + Math.random() * 89000);
    const totalAmount = orderItems.reduce((sum, i) => sum + i.subtotal, 0);
    const isOnline = paymentMethod === 'ONLINE';
    const expiresAt = isOnline
      ? new Date(Date.now() + 15 * 60 * 1000).toISOString()
      : null;

    const created: Order = {
      id: orderId,
      user_id: userId,
      total_amount: totalAmount,
      status: isOnline ? 'PENDING_PAYMENT' : 'CONFIRMED',
      payment_method: paymentMethod,
      payment_status: 'PENDING',
      payment_code: isOnline ? `PAY${orderId}` : null,
      payment_expires_at: expiresAt,
      paid_at: null,
      payment_info:
        isOnline && expiresAt
          ? buildDemoVietQRInfo(orderId, totalAmount, expiresAt)
          : null,
      created_at: new Date().toISOString(),
      items: orderItems,
    };

    const existing = readSavedDemoOrders(userId);
    writeSavedDemoOrders(userId, [created, ...existing]);
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
      body: JSON.stringify({
        ...payload,
        payment_method: paymentMethod,
      }),
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
      typeof body.detail === 'string'
        ? body.detail
        : `Checkout failed (${response.status}). Inventory rolled back.`,
    );
  }

  if (!payload.items?.length) {
    window.dispatchEvent(new Event('soundwave-cart-update'));
  }
  return body as Order;
}

export function formatTransferVND(amountVnd: number): string {
  return `${new Intl.NumberFormat('vi-VN').format(Math.round(amountVnd))} VND`;
}

export const formatMoney = formatVND;
export const formatDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
    : 'Date unavailable';
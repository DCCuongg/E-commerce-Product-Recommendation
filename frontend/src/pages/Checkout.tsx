import { Tr, usePreferences } from '../context/PreferencesContext';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Banknote,
  CheckCircle2,
  Lock,
  QrCode,
  ShieldCheck,
} from 'lucide-react';
import StoreHeader, { StoreFooter } from '../components/StoreHeader';
import VietQRPaymentPanel from '../components/VietQRPaymentPanel';
import { TOKEN_KEY, useAuth } from '../context/AuthContext';
import { getCart, type CartLine } from '../services/cart';
import { formatVND } from '../services/catalog';
import { checkoutOrder, type Order } from '../services/orders';
import { logInteraction } from '../services/faas';

type BuyNowItem = {
  product_id: string;
  product_name: string;
  image_url?: string | null;
  unit_price: number;
  quantity: number;
  stock_quantity: number;
};

type CheckoutLocationState = {
  buyNowItem?: BuyNowItem;
} | null;

export default function Checkout() {
  const { t } = usePreferences();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const buyNowItem = (location.state as CheckoutLocationState)?.buyNowItem;

  const [items, setItems] = useState<CartLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const [fullName, setFullName] = useState(user?.username || '');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<'cod' | 'vietqr'>('cod');
  const [simulateFailure, setSimulateFailure] = useState(false);
  const [pendingOnlineOrder, setPendingOnlineOrder] = useState<Order | null>(null);

  useEffect(() => {
    if (!user) return;
    if (buyNowItem) {
      setItems([
        {
          product_id: buyNowItem.product_id,
          product_name: buyNowItem.product_name,
          image_url: buyNowItem.image_url,
          unit_price: buyNowItem.unit_price,
          quantity: buyNowItem.quantity,
          subtotal: buyNowItem.unit_price * buyNowItem.quantity,
          stock_quantity: buyNowItem.stock_quantity,
        },
      ]);
      setLoading(false);
      return;
    }

    let ignore = false;
    getCart(user.id)
      .then((cart) => {
        if (!ignore) setItems(cart.items);
      })
      .catch((e) => {
        if (!ignore) setError(e instanceof Error ? e.message : 'Unable to load order items.');
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [user, buyNowItem]);

  const totalAmount = items.reduce((sum, item) => sum + item.subtotal, 0);
  const totalQuantity = items.reduce((sum, item) => sum + item.quantity, 0);
  const token = sessionStorage.getItem(TOKEN_KEY);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!user || !items.length) return;

    setSubmitting(true);
    setError('');

    for (const item of items) {
      void logInteraction({ userId: user.id, productId: item.product_id, action: 'checkout' });
    }

    const apiPaymentMethod = paymentMethod === 'vietqr' ? 'ONLINE' : 'COD';

    try {
      const order = await checkoutOrder(token, user.id, {
        ...(buyNowItem
          ? { items: [{ product_id: buyNowItem.product_id, quantity: buyNowItem.quantity }] }
          : {}),
        payment_method: apiPaymentMethod,
        simulate_failure: simulateFailure,
      });

      if (apiPaymentMethod === 'ONLINE') {
        setPendingOnlineOrder(order);
        return;
      }

      for (const item of items) {
        void logInteraction({
          userId: user.id,
          productId: item.product_id,
          action: 'purchase',
          value: 5.0,
        });
      }

      navigate(`/profile/purchases/${order.id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Checkout failed.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#faf9f6] dark:bg-[#0b1322] dark:text-slate-100">
      <StoreHeader />
      <main className="mx-auto max-w-[1180px] px-5 py-12 sm:px-8">
        <Link
          to="/cart"
          className="inline-flex items-center gap-2 text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-indigo-600"
        >
          <ArrowLeft size={14} />
          <Tr text={'Back to shopping bag'} />
        </Link>

        <p className="mt-6 text-[11px] font-extrabold uppercase tracking-[.22em] text-indigo-600">
          <Tr text={'Secure checkout'} />
        </p>
        <h1 className="mt-2 font-['Georgia',serif] text-[40px] tracking-[-.05em] sm:text-[52px]">
          <Tr text={'Complete your order.'} />
        </h1>

        {error && (
          <div
            className="mt-6 flex items-start gap-3 rounded-2xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-4 text-sm text-red-700 dark:text-red-300"
            role="alert"
          >
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <span>{t(error)}</span>
          </div>
        )}

        {pendingOnlineOrder ? (
          <div className="mt-9 grid items-start gap-8 lg:grid-cols-[1fr_360px]">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-indigo-100 dark:border-indigo-500/20 bg-indigo-50/70 dark:bg-indigo-500/10 px-5 py-4 text-sm">
                <p className="font-semibold text-indigo-950 dark:text-indigo-200">
                  {t('Order')} #{pendingOnlineOrder.id} ·{' '}
                  <Tr text={'Inventory reserved while awaiting VietQR transfer.'} />
                </p>
                <Link
                  to={`/profile/purchases/${pendingOnlineOrder.id}`}
                  className="inline-flex items-center gap-1.5 font-bold text-indigo-600 dark:text-indigo-300 hover:underline"
                >
                  <Tr text={'View order'} /> <ArrowRight size={15} />
                </Link>
              </div>

              <VietQRPaymentPanel
                order={pendingOnlineOrder}
                token={token}
                userId={user?.id}
                onOrderUpdated={(updated) => {
                  setPendingOnlineOrder(updated);
                }}
              />
            </div>

            <aside className="rounded-2xl border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 p-7">
              <h2 className="text-lg font-bold">
                <Tr text={'Order summary'} />
              </h2>
              <ul className="mt-5 divide-y divide-slate-100 dark:divide-slate-800">
                {pendingOnlineOrder.items.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-3 py-3 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-800 dark:text-slate-200">
                        {item.product_name || item.product_id}
                      </p>
                      <p className="text-xs text-slate-400">
                        {t('Qty')}: {item.quantity}
                      </p>
                    </div>
                    <span className="shrink-0 font-bold text-slate-900 dark:text-slate-100">
                      {formatVND(item.subtotal)}
                    </span>
                  </li>
                ))}
              </ul>

              <div className="mt-4 space-y-2 border-t border-slate-100 dark:border-slate-800 pt-4 text-sm">
                <div className="flex justify-between text-slate-500 dark:text-slate-400">
                  <span>{t('Payment method')}</span>
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                    VietQR
                  </span>
                </div>
                <div className="flex items-center justify-between pt-2">
                  <span className="font-bold">
                    <Tr text={'Total'} />
                  </span>
                  <span className="text-xl font-extrabold text-slate-900 dark:text-slate-100">
                    {formatVND(pendingOnlineOrder.total_amount)}
                  </span>
                </div>
              </div>
            </aside>
          </div>
        ) : loading ? (
          <div className="my-10 h-64 animate-pulse rounded-2xl bg-white dark:bg-slate-900" />
        ) : items.length === 0 ? (
          <div className="my-10 rounded-3xl bg-white dark:bg-slate-900 p-12 text-center">
            <h2 className="text-xl font-bold">
              <Tr text={'Nothing to check out'} />
            </h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              <Tr text={'Add an instrument to your bag first.'} />
            </p>
            <Link
              to="/shop"
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#263247] px-7 py-3 text-sm font-bold text-white"
            >
              <Tr text={'Browse instruments'} />
            </Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="mt-9 grid items-start gap-8 lg:grid-cols-[1fr_360px]">
            <section className="space-y-6 rounded-2xl border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sm:p-8">
              <div>
                <h2 className="text-lg font-bold text-[#242b37] dark:text-slate-100">
                  <Tr text={'Shipping details'} />
                </h2>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                      <Tr text={'Full name'} />
                    </label>
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-600"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                      <Tr text={'Phone number'} />
                    </label>
                    <input
                      type="tel"
                      required
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="09xx xxx xxx"
                      className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-600"
                    />
                  </div>
                </div>
                <div className="mt-4">
                  <label className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300">
                    <Tr text={'Delivery address'} />
                  </label>
                  <input
                    type="text"
                    required
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder={t('Street, ward, district, city')}
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-600"
                  />
                </div>
              </div>

              <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                <Tr text="Shipping information is collected by the interface but not yet saved by the current Order API. Do not use real personal details for testing." />
              </p>

              <div className="border-t border-slate-100 pt-6 dark:border-slate-800">
                <h2 className="text-lg font-bold text-[#242b37] dark:text-slate-100">
                  <Tr text={'Payment method'} />
                </h2>
                <p className="mt-1.5 text-xs leading-5 text-slate-500 dark:text-slate-400">
                  <Tr text="Choose how you would like to pay for your order." />
                </p>

                <div
                  className="mt-4 grid gap-3 sm:grid-cols-2"
                  role="radiogroup"
                  aria-label={t('Payment method')}
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={paymentMethod === 'cod'}
                    onClick={() => {
                      setPaymentMethod('cod');
                      setError('');
                    }}
                    className={`flex items-start gap-3 rounded-2xl border p-4 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 ${paymentMethod === 'cod'
                      ? 'border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600/20 dark:bg-indigo-500/10'
                      : 'border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800'
                      }`}
                  >
                    <Banknote
                      size={22}
                      className="mt-0.5 shrink-0 text-indigo-600 dark:text-indigo-300"
                    />
                    <span>
                      <span className="block text-sm font-bold text-slate-900 dark:text-slate-100">
                        <Tr text="Cash on Delivery" />
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-slate-500 dark:text-slate-400">
                        <Tr text="Place an order without paying online." />
                      </span>
                    </span>
                  </button>

                  <button
                    type="button"
                    role="radio"
                    aria-checked={paymentMethod === 'vietqr'}
                    onClick={() => {
                      setPaymentMethod('vietqr');
                      setError('');
                    }}
                    className={`flex items-start gap-3 rounded-2xl border p-4 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 ${paymentMethod === 'vietqr'
                      ? 'border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600/20 dark:bg-indigo-500/10'
                      : 'border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800'
                      }`}
                  >
                    <QrCode
                      size={22}
                      className="mt-0.5 shrink-0 text-indigo-600 dark:text-indigo-300"
                    />
                    <span>
                      <span className="block text-sm font-bold text-slate-900 dark:text-slate-100">
                        <Tr text="VietQR bank transfer" />
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-slate-500 dark:text-slate-400">
                        <Tr text="Scan a payment QR in your banking app." />
                      </span>
                    </span>
                  </button>
                </div>

                {paymentMethod === 'vietqr' ? (
                  <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50/70 px-4 py-3 text-xs leading-6 text-indigo-900 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-200">
                    <Tr text="A dynamic VietQR code with an exact transfer reference and VND amount will be generated immediately. Inventory is reserved while awaiting bank webhook confirmation." />
                  </div>
                ) : (
                  <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    <Tr text="Your order will be confirmed immediately and paid in cash upon delivery." />
                  </p>
                )}
              </div>

              {import.meta.env.DEV && import.meta.env.VITE_ENABLE_FAILURE_TEST === 'true' && (
                <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/70 dark:bg-amber-950/30 p-4">
                  <label className="flex cursor-pointer items-start gap-2.5 text-xs text-amber-950 dark:text-amber-200">
                    <input
                      type="checkbox"
                      checked={simulateFailure}
                      onChange={(e) => setSimulateFailure(e.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      <strong>
                        <Tr text="Demo mode: Simulate payment failure" />
                      </strong>{' '}
                      (sends <code>simulate_failure: true</code> to verify PostgreSQL pessimistic
                      lock & automatic inventory ROLLBACK)
                    </span>
                  </label>
                </div>
              )}
            </section>

            <aside className="rounded-2xl border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 p-7">
              <h2 className="text-lg font-bold">
                <Tr text={'Order summary'} />
              </h2>
              <ul className="mt-5 divide-y divide-slate-100 dark:divide-slate-800">
                {items.map((item) => (
                  <li
                    key={item.product_id}
                    className="flex items-center justify-between gap-3 py-3 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-800 dark:text-slate-200">
                        {item.product_name}
                      </p>
                      <p className="text-xs text-slate-400">
                        {t('Qty')}: {item.quantity}
                      </p>
                    </div>
                    <span className="shrink-0 font-bold text-slate-900 dark:text-slate-100">
                      {formatVND(item.subtotal)}
                    </span>
                  </li>
                ))}
              </ul>

              <div className="mt-4 space-y-2 border-t border-slate-100 dark:border-slate-800 pt-4 text-sm">
                <div className="flex justify-between text-slate-500 dark:text-slate-400">
                  <span>
                    {t('Items')} ({totalQuantity})
                  </span>
                  <span>{formatVND(totalAmount)}</span>
                </div>
                <div className="flex justify-between text-slate-500 dark:text-slate-400">
                  <span>{t('Shipping')}</span>
                  <span className="font-semibold text-emerald-600">
                    <Tr text={'Free'} />
                  </span>
                </div>
                <div className="flex items-center justify-between pt-2">
                  <span className="font-bold">
                    <Tr text={'Total'} />
                  </span>
                  <span className="text-xl font-extrabold text-slate-900 dark:text-slate-100">
                    {formatVND(totalAmount)}
                  </span>
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#263247] px-5 py-3.5 text-sm font-bold text-white transition hover:bg-indigo-600 disabled:bg-slate-300"
              >
                {submitting ? (
                  t('Processing transaction...')
                ) : paymentMethod === 'vietqr' ? (
                  <>
                    <QrCode size={16} /> <Tr text={'Pay with VietQR'} /> ·{' '}
                    {formatVND(totalAmount)}
                  </>
                ) : (
                  <>
                    <Lock size={15} /> {t('Place order')} {formatVND(totalAmount)}
                  </>
                )}
              </button>

              <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
                <ShieldCheck size={14} className="text-emerald-600" />
                <Tr text={'Stock is checked when the order is placed.'} />
              </p>
              {simulateFailure && (
                <p className="mt-2 flex items-center justify-center gap-1 text-[11px] font-semibold text-amber-700">
                  <CheckCircle2 size={13} />
                  <Tr text={'Will trigger rollback test on submit'} />
                </p>
              )}
            </aside>
          </form>
        )}
      </main>
      <StoreFooter />
    </div>
  );
}
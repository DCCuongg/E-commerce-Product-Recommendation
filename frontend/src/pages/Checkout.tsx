import { Tr, usePreferences } from '../context/PreferencesContext';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, CheckCircle2, CreditCard, Lock, ShieldCheck } from 'lucide-react';
import StoreHeader, { StoreFooter } from '../components/StoreHeader';
import { TOKEN_KEY, useAuth } from '../context/AuthContext';
import { getCart, type CartLine } from '../services/cart';
import { formatVND } from '../services/catalog';
import { checkoutOrder } from '../services/orders';
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
  const [paymentMethod, setPaymentMethod] = useState<'card' | 'e_wallet' | 'cod'>('card');
  const [simulateFailure, setSimulateFailure] = useState(false);

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

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!user || !items.length) return;

    setSubmitting(true);
    setError('');

    for (const item of items) {
      void logInteraction({ userId: user.id, productId: item.product_id, action: 'checkout' });
    }

    try {
      const token = sessionStorage.getItem(TOKEN_KEY);
      const order = await checkoutOrder(token, user.id, {
        ...(buyNowItem
          ? { items: [{ product_id: buyNowItem.product_id, quantity: buyNowItem.quantity }] }
          : {}),
        simulate_failure: simulateFailure,
      });

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
        <Link to="/cart" className="inline-flex items-center gap-2 text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-indigo-600">
          <ArrowLeft size={14} /><Tr text={'Back to shopping bag'}/></Link>

        <p className="mt-6 text-[11px] font-extrabold uppercase tracking-[.22em] text-indigo-600"><Tr text={'Secure checkout'}/></p>
        <h1 className="mt-2 font-['Georgia',serif] text-[40px] tracking-[-.05em] sm:text-[52px]"><Tr text={'Complete your order.'}/></h1>

        {error && (
          <div className="mt-6 flex items-start gap-3 rounded-2xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-4 text-sm text-red-700 dark:text-red-300" role="alert">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <span>{t(error)}</span>
          </div>
        )}

        {loading ? (
          <div className="my-10 h-64 animate-pulse rounded-2xl bg-white dark:bg-slate-900" />
        ) : items.length === 0 ? (
          <div className="my-10 rounded-3xl bg-white dark:bg-slate-900 p-12 text-center">
            <h2 className="text-xl font-bold"><Tr text={'Nothing to check out'}/></h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400"><Tr text={'Add an instrument to your bag first.'}/></p>
            <Link
              to="/shop"
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#263247] px-7 py-3 text-sm font-bold text-white"
            ><Tr text={'Browse instruments'}/></Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="mt-9 grid items-start gap-8 lg:grid-cols-[1fr_360px]">
            <section className="space-y-6 rounded-2xl border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sm:p-8">
              <div>
                <h2 className="text-lg font-bold text-[#242b37] dark:text-slate-100"><Tr text={'Shipping details'}/></h2>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300"><Tr text={'Full name'}/></label>
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-600"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300"><Tr text={'Phone number'}/></label>
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
                  <label className="mb-1.5 block text-xs font-semibold text-slate-600 dark:text-slate-300"><Tr text={'Delivery address'}/></label>
                  <input
                    type="text"
                    required
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder={t("Street, ward, district, city")}
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-600"
                  />
                </div>
              </div>

              <p className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-4 py-3 text-xs leading-5 text-slate-600 dark:text-slate-300"><Tr text="Delivery and payment fields are for the checkout interface; the current order API does not save these details or charge a payment method."/></p>

              <div className="border-t border-slate-100 dark:border-slate-800 pt-6">
                <h2 className="text-lg font-bold text-[#242b37] dark:text-slate-100"><Tr text={'Payment method'}/></h2>
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  {[
                    { id: 'card', label: 'Credit / Debit Card' },
                    { id: 'e_wallet', label: 'E-Wallet' },
                    { id: 'cod', label: 'Cash on Delivery' },
                  ].map((opt) => (
                    <button
                      type="button"
                      key={opt.id}
                      onClick={() => setPaymentMethod(opt.id as typeof paymentMethod)}
                      className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-3 text-xs font-bold transition ${
                        paymentMethod === opt.id
                          ? 'border-[#263247] bg-[#263247] text-white'
                          : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800'
                      }`}
                    >
                      <CreditCard size={14} />
                      {t(opt.label)}
                    </button>
                  ))}
                </div>
              </div>

              {import.meta.env.DEV && import.meta.env.VITE_ENABLE_FAILURE_TEST === 'true' && <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/70 dark:bg-amber-950/30 p-4">
                <label className="flex cursor-pointer items-start gap-2.5 text-xs text-amber-950 dark:text-amber-200">
                  <input
                    type="checkbox"
                    checked={simulateFailure}
                    onChange={(e) => setSimulateFailure(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    <strong><Tr text="Demo mode: Simulate payment failure"/></strong> (sends <code>simulate_failure: true</code> to
                    verify PostgreSQL pessimistic lock &amp; automatic inventory ROLLBACK)
                  </span>
                </label>
              </div>}
            </section>

            <aside className="rounded-2xl border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 p-7">
              <h2 className="text-lg font-bold"><Tr text={'Order summary'}/></h2>
              <ul className="mt-5 divide-y divide-slate-100">
                {items.map((item) => (
                  <li key={item.product_id} className="flex items-center justify-between gap-3 py-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-800 dark:text-slate-200">{item.product_name}</p>
                      <p className="text-xs text-slate-400">{t("Qty")}: {item.quantity}</p>
                    </div>
                    <span className="shrink-0 font-bold text-slate-900 dark:text-slate-100">{formatVND(item.subtotal)}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-4 space-y-2 border-t border-slate-100 dark:border-slate-800 pt-4 text-sm">
                <div className="flex justify-between text-slate-500 dark:text-slate-400">
                  <span>{t("Items")} ({totalQuantity})</span>
                  <span>{formatVND(totalAmount)}</span>
                </div>
                <div className="flex justify-between text-slate-500 dark:text-slate-400">
                  <span>{t("Shipping")}</span>
                  <span className="font-semibold text-emerald-600"><Tr text={'Free'}/></span>
                </div>
                <div className="flex items-center justify-between pt-2">
                  <span className="font-bold"><Tr text={'Total'}/></span>
                  <span className="text-xl font-extrabold text-slate-900 dark:text-slate-100">{formatVND(totalAmount)}</span>
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#263247] px-5 py-3.5 text-sm font-bold text-white transition hover:bg-indigo-600 disabled:bg-slate-300"
              >
                {submitting ? (
                  t('Processing transaction...')
                ) : (
                  <>
                    <Lock size={15} /> {t("Place order")} {formatVND(totalAmount)}
                  </>
                )}
              </button>

              <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
                <ShieldCheck size={14} className="text-emerald-600" /><Tr text={'Stock is checked when the order is placed.'}/></p>
              {simulateFailure && (
                <p className="mt-2 flex items-center justify-center gap-1 text-[11px] font-semibold text-amber-700">
                  <CheckCircle2 size={13} /><Tr text={'Will trigger rollback test on submit'}/></p>
              )}
            </aside>
          </form>
        )}
      </main>
      <StoreFooter />
    </div>
  );
}
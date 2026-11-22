import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Minus, Plus, ShoppingBag, Trash2 } from 'lucide-react';
import StoreHeader, { StoreFooter } from '../components/StoreHeader';
import { clearCart, getCart, setCartQuantity, type Cart as CartType } from '../services/cart';
import { formatVND } from '../services/catalog';
import { useAuth } from '../context/AuthContext';

export default function Cart() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [cart, setCart] = useState<CartType | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!user) return;
    let ignore = false;
    getCart(user.id)
      .then((data) => {
        if (!ignore) setCart(data);
      })
      .catch((e) => {
        if (!ignore) setError(e instanceof Error ? e.message : 'Cart unavailable.');
      });
    return () => {
      ignore = true;
    };
  }, [user]);

  async function change(id: string, qty: number) {
    if (!user) return;
    setBusy(true);
    setError('');
    try {
      setCart(await setCartQuantity(user.id, id, qty));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to update cart.');
    } finally {
      setBusy(false);
    }
  }

  async function onClear() {
    if (!user) return;
    setBusy(true);
    setError('');
    try {
      setCart(await clearCart(user.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to clear cart.');
    } finally {
      setBusy(false);
    }
  }

  const hasStockIssue = Boolean(
    cart?.items.some((item) => item.stock_quantity <= 0 || item.quantity > item.stock_quantity),
  );

  return (
    <div className="min-h-screen bg-[#faf9f6]">
      <StoreHeader />
      <main className="mx-auto max-w-[1180px] px-5 py-12 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[11px] font-extrabold uppercase tracking-[.22em] text-indigo-600">Your selection</p>
            <h1 className="mt-3 font-['Georgia',serif] text-[43px] tracking-[-.05em] sm:text-[60px]">
              Shopping bag.
            </h1>
            <p className="mt-2 text-sm text-slate-500">Review the instruments you've selected.</p>
          </div>

          {cart && cart.items.length > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={onClear}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-600 transition hover:border-red-200 hover:text-red-600 disabled:opacity-50"
            >
              <Trash2 size={14} /> Clear bag
            </button>
          )}
        </div>

        {error && (
          <p className="mt-7 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        {!cart ? (
          <div className="my-12 h-40 animate-pulse rounded-2xl bg-white" />
        ) : cart.items.length === 0 ? (
          <div className="my-12 rounded-3xl bg-white p-12 text-center">
            <ShoppingBag className="mx-auto text-indigo-500" size={38} />
            <h2 className="mt-4 text-xl font-bold">Your bag is empty.</h2>
            <p className="mt-2 text-sm text-slate-500">Your next favorite instrument is waiting.</p>
            <Link
              to="/shop"
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-[#263247] px-7 py-3 text-sm font-bold text-white"
            >
              Explore instruments <ArrowRight size={17} />
            </Link>
          </div>
        ) : (
          <div className="mt-9 grid items-start gap-8 lg:grid-cols-[1fr_340px]">
            <section className="space-y-4">
              {cart.items.map((item) => {
                const overStock = item.stock_quantity <= 0 || item.quantity > item.stock_quantity;
                return (
                  <div
                    key={item.product_id}
                    className="flex flex-wrap items-center gap-5 rounded-2xl border border-[#eeebe5] bg-white p-5 sm:flex-nowrap"
                  >
                    <Link
                      to={`/products/${encodeURIComponent(item.product_id)}`}
                      className="h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-[#f4f1ea]"
                    >
                      <img
                        src={item.thumb_url || item.image_url || '/assets/instrument-placeholder.svg'}
                        className="h-full w-full object-cover"
                        alt={item.product_name}
                        onError={(e) => {
                          e.currentTarget.onerror = null;
                          e.currentTarget.src = '/assets/instrument-placeholder.svg';
                        }}
                      />
                    </Link>

                    <div className="min-w-[160px] flex-1">
                      <Link
                        className="text-sm font-bold hover:text-indigo-600"
                        to={`/products/${encodeURIComponent(item.product_id)}`}
                      >
                        {item.product_name}
                      </Link>
                      <p className="mt-2 text-sm font-extrabold text-slate-900">{formatVND(item.unit_price)}</p>
                      {overStock && (
                        <p className="mt-1 text-xs font-semibold text-red-600">
                          {item.stock_quantity <= 0
                            ? 'Out of stock'
                            : `Only ${item.stock_quantity} left in stock`}
                        </p>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => change(item.product_id, 0)}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-red-500"
                      >
                        <Trash2 size={13} /> Remove
                      </button>
                    </div>

                    <div className="flex items-center gap-2 rounded-full border border-slate-200 px-2 py-1">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => change(item.product_id, item.quantity - 1)}
                        aria-label="Decrease quantity"
                        className="p-1"
                      >
                        <Minus size={15} />
                      </button>
                      <span className="min-w-5 text-center text-xs font-bold">{item.quantity}</span>
                      <button
                        type="button"
                        disabled={busy || item.quantity >= item.stock_quantity}
                        onClick={() => change(item.product_id, item.quantity + 1)}
                        aria-label="Increase quantity"
                        className="p-1 disabled:opacity-40"
                      >
                        <Plus size={15} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </section>

            <aside className="rounded-2xl border border-[#eeebe5] bg-white p-7">
              <h2 className="text-lg font-bold">Order summary</h2>
              <div className="mt-6 flex justify-between text-sm">
                <span className="text-slate-500">Items ({cart.total_quantity})</span>
                <span className="font-semibold">{formatVND(cart.total_amount)}</span>
              </div>
              <div className="mt-5 border-t border-slate-100 pt-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold">Subtotal</span>
                  <span className="text-xl font-extrabold">{formatVND(cart.total_amount)}</span>
                </div>
              </div>
              <p className="mt-4 text-xs leading-6 text-slate-500">
                Inventory is reserved securely when you confirm payment.
              </p>

              <button
                type="button"
                disabled={busy || hasStockIssue}
                onClick={() => navigate('/checkout')}
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#263247] px-5 py-3.5 text-sm font-bold text-white transition hover:bg-indigo-600 disabled:bg-slate-300"
              >
                Proceed to checkout <ArrowRight size={16} />
              </button>

              <Link
                className="mt-3 inline-flex w-full items-center justify-center rounded-full border border-slate-200 px-5 py-3 text-xs font-bold text-slate-600 transition hover:bg-slate-50"
                to="/shop"
              >
                Continue shopping
              </Link>
            </aside>
          </div>
        )}
      </main>
      <StoreFooter />
    </div>
  );
}
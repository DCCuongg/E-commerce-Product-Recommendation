import { Tr, usePreferences } from '../context/PreferencesContext';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  CreditCard,
  MapPin,
  Package,
  QrCode,
  ReceiptText,
  RefreshCcw,
  Truck,
  Wallet,
  XCircle,
} from 'lucide-react';
import { BackLink } from '../components/UI';
import VietQRPaymentPanel from '../components/VietQRPaymentPanel';
import { useAuth, TOKEN_KEY } from '../context/AuthContext';
import {
  cancelOrder,
  formatMoney,
  getOrderById,
  type Order,
} from '../services/orders';

const stages = ['CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'];

function stageIndex(status: string) {
  const index = stages.indexOf(status.toUpperCase());
  return index >= 0 ? index : -1;
}

export default function OrderDetail() {
  const { t, date } = usePreferences();
  const { orderId } = useParams();
  const { user } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');

  const token = sessionStorage.getItem(TOKEN_KEY);

  useEffect(() => {
    const currentToken = sessionStorage.getItem(TOKEN_KEY);
    if (!user || !currentToken || !orderId) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError('');
    getOrderById(currentToken, Number(orderId), user.id)
      .then((found) => {
        if (active) setOrder(found);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : 'Unable to load order');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [user?.id, orderId, retry]);

  async function handleCancel() {
    if (!token || !order) return;
    setCancelling(true);
    setCancelError('');
    try {
      const updated = await cancelOrder(token, order.id, user?.id);
      setOrder(updated);
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : 'Unable to cancel order.');
    } finally {
      setCancelling(false);
    }
  }

  if (loading) {
    return (
      <div className="panel p-10 text-center text-slate-500 dark:text-slate-400">
        <Tr text={'Loading order…'} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel p-9">
        <BackLink to="/profile/purchases" label="Back to purchases" />
        <div className="mt-5 flex items-center gap-3 text-red-700 dark:text-red-300">
          <AlertCircle />
          {t(error)}
        </div>
        <button onClick={() => setRetry((x) => x + 1)} className="secondary-button mt-6">
          <RefreshCcw size={16} /> <Tr text={'Retry'} />
        </button>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="panel p-9">
        <BackLink to="/profile/purchases" label="Back to purchases" />
        <h1 className="mt-6 text-2xl font-bold">
          <Tr text={'Order not found'} />
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          <Tr text={"This order is not present in your account's order history."} />
        </p>
      </div>
    );
  }

  const status = order.status.toUpperCase();
  const progress = stageIndex(status);
  const canceled = ['CANCELLED', 'CANCELED'].includes(status);
  const pendingPayment = status === 'PENDING_PAYMENT';
  const itemSum = order.items.reduce((acc, item) => acc + item.subtotal, 0);
  const isOnline = order.payment_method === 'ONLINE';
  const payStatus = (order.payment_status || 'PENDING').toUpperCase();
  const canCancel = ['PENDING', 'PENDING_PAYMENT', 'CONFIRMED'].includes(status);

  return (
    <div className="space-y-6">
      <BackLink to="/profile/purchases" label="Back to my purchases" />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">
            <Tr text={'ORDER DETAILS'} />
          </p>
          <h1 className="page-title">
            {t('Order')} #{order.id}
          </h1>
          <p className="page-subtitle">
            {t('Placed')} {date(order.created_at)} · {order.items.length} {t('products')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-bold ${payStatus === 'PAID'
              ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
              : payStatus === 'EXPIRED' || payStatus === 'FAILED'
                ? 'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
              }`}
          >
            {isOnline ? <QrCode size={14} /> : <Wallet size={14} />}
            {isOnline ? 'VietQR' : 'COD'} · {t(payStatus)}
          </span>

          <span
            className={`rounded-full px-4 py-2 text-xs font-extrabold tracking-wider ${canceled
              ? 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300'
              : pendingPayment
                ? 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300'
                : progress === 3
                  ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                  : 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300'
              }`}
          >
            {t(status)}
          </span>
        </div>
      </div>

      {isOnline && (
        <VietQRPaymentPanel
          order={order}
          token={token}
          userId={user?.id}
          onOrderUpdated={setOrder}
        />
      )}

      <section className="panel overflow-hidden">
        <div className="flex items-center gap-3 border-b border-slate-100 dark:border-slate-800 p-6">
          <Truck size={21} className="text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-lg font-bold">
            <Tr text={'Order progress'} />
          </h2>
        </div>
        <div className="p-6 sm:p-8">
          {progress >= 0 ? (
            <div className="grid gap-4 sm:grid-cols-4">
              {stages.map((step, index) => (
                <div key={step} className="flex items-start gap-3 sm:flex-col">
                  <span
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${index <= progress
                      ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-400'
                      }`}
                  >
                    {index <= progress ? (
                      <CheckCircle2 size={21} />
                    ) : (
                      <span className="font-bold">{index + 1}</span>
                    )}
                  </span>
                  <div>
                    <p
                      className={`text-sm font-bold ${index <= progress
                        ? 'text-slate-800 dark:text-slate-200'
                        : 'text-slate-400 dark:text-slate-400'
                        }`}
                    >
                      {t(step)}
                    </p>
                    <p className="mt-1 text-xs text-slate-400 dark:text-slate-400">
                      {t(
                        index === progress
                          ? 'Current recorded status'
                          : index < progress
                            ? 'Completed stage'
                            : 'Awaiting update',
                      )}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl bg-slate-50 dark:bg-slate-800 p-4 text-sm text-slate-600 dark:text-slate-300">
              <Tr text={'Current backend status:'} /> <strong>{t(order.status)}</strong>.{' '}
              <Tr text="No shipment milestones are available for this status." />
            </div>
          )}
          <p className="mt-6 border-t border-slate-100 dark:border-slate-800 pt-4 text-xs leading-6 text-slate-500 dark:text-slate-400">
            <Tr
              text={
                'This represents your current order status; shipment scans and timestamps are not available.'
              }
            />
          </p>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel p-6">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <MapPin size={19} className="text-indigo-600 dark:text-indigo-400" />{' '}
            <Tr text={'Delivery address'} />
          </h2>
          <div className="mt-5 rounded-xl bg-slate-50 dark:bg-slate-800 p-5">
            <p className="font-semibold">
              <Tr text={'Not available'} />
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
              <Tr text={'Delivery address details are not available for this order.'} />
            </p>
          </div>
        </section>

        <section className="panel p-6">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <Truck size={19} className="text-indigo-600 dark:text-indigo-400" />{' '}
            <Tr text={'Shipping details'} />
          </h2>
          <div className="mt-5 rounded-xl bg-slate-50 dark:bg-slate-800 p-5">
            <p className="font-semibold">
              <Tr text={'Carrier / tracking number unavailable'} />
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
              <Tr text={'No carrier tracking details are available for this order.'} />
            </p>
          </div>
        </section>
      </div>

      <section className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 p-6">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <Package size={20} className="text-indigo-600 dark:text-indigo-400" />{' '}
            <Tr text={'Purchased products'} />
          </h2>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            {order.items.length} {t('products')}
          </span>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {order.items.map((item) => (
            <div key={item.id} className="flex items-center gap-4 p-5 sm:p-6">
              <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-100 dark:border-slate-800 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-300">
                {item.thumb_url || item.image_url ? (
                  <img
                    alt={t(item.product_name || 'Product')}
                    src={item.thumb_url || item.image_url || ''}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <Package size={28} />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-bold text-slate-900 dark:text-slate-100">
                  {t(item.product_name || item.product_id)}
                </p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {t('Unit price:')} {formatMoney(item.unit_price)} · {t('Quantity:')}{' '}
                  {item.quantity}
                </p>
              </div>
              <p className="shrink-0 font-bold">{formatMoney(item.subtotal)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-6 sm:p-8">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <ReceiptText size={21} className="text-indigo-600 dark:text-indigo-400" />{' '}
          <Tr text={'Payment summary'} />
        </h2>
        <div className="ml-auto mt-6 max-w-lg space-y-4 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-slate-500 dark:text-slate-400">
              <Tr text={'Products subtotal'} />
            </span>
            <span className="font-semibold">{formatMoney(itemSum)}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-slate-500 dark:text-slate-400">
              <Tr text={'Payment method'} />
            </span>
            <span className="font-semibold">
              {isOnline ? t('VietQR bank transfer') : t('Cash on Delivery')}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-slate-500 dark:text-slate-400">
              <Tr text={'Payment status'} />
            </span>
            <span className="font-semibold">{t(payStatus)}</span>
          </div>
          {order.payment_code && (
            <div className="flex justify-between gap-4">
              <span className="text-slate-500 dark:text-slate-400">
                <Tr text={'Reference'} />
              </span>
              <span className="font-mono font-semibold">{order.payment_code}</span>
            </div>
          )}
          <div className="flex justify-between gap-4 border-t border-slate-100 dark:border-slate-800 pt-4">
            <span className="text-base font-bold">
              <Tr text={'Order total'} />
            </span>
            <span className="text-2xl font-extrabold text-indigo-700 dark:text-indigo-300">
              {formatMoney(order.total_amount)}
            </span>
          </div>
          <div className="flex items-start gap-2 rounded-xl bg-slate-50 dark:bg-slate-800 p-4 text-xs leading-5 text-slate-500 dark:text-slate-400">
            <CreditCard className="mt-0.5 shrink-0" size={17} />
            <span>
              {order.paid_at
                ? `${t('Paid at')}: ${date(order.paid_at)}`
                : isOnline
                  ? t('Verified automatically upon VietQR bank transfer confirmation.')
                  : t('Pay in cash when your order is delivered.')}
            </span>
          </div>
        </div>
      </section>

      {cancelError && (
        <p className="text-right text-xs font-medium text-rose-600 dark:text-rose-400">
          {t(cancelError)}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3">
        {canCancel && !pendingPayment && (
          <button
            type="button"
            disabled={cancelling}
            onClick={handleCancel}
            className="secondary-button text-rose-600 dark:text-rose-300"
          >
            <XCircle size={16} /> <Tr text={'Cancel order'} />
          </button>
        )}
        <Link to="/profile/purchases" className="secondary-button">
          <Tr text={'Return to purchases'} /> <ArrowRight size={16} />
        </Link>
      </div>
    </div>
  );
}
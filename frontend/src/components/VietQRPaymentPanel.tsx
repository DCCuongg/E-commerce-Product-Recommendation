import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CircleCheck,
  Clock3,
  Copy,
  QrCode,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { Tr, usePreferences } from '../context/PreferencesContext';
import { DEMO_MODE } from '../services/auth';
import { logInteraction } from '../services/faas';
import {
  cancelOrder,
  formatMoney,
  formatTransferVND,
  getOrderPaymentStatus,
  simulateDemoOrderPaid,
  type Order,
} from '../services/orders';

type VietQRPaymentPanelProps = {
  order: Order;
  token: string | null;
  userId?: string;
  onOrderUpdated?: (updated: Order) => void;
};

function formatCountdown(seconds: number): string {
  const safe = Math.max(0, seconds);
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export default function VietQRPaymentPanel({
  order,
  token,
  userId,
  onOrderUpdated,
}: VietQRPaymentPanelProps) {
  const { t } = usePreferences();
  const [currentOrder, setCurrentOrder] = useState<Order>(order);
  const [remainingSeconds, setRemainingSeconds] = useState<number>(() => {
    if (!order.payment_expires_at) return 0;
    const diff = Math.floor(
      (new Date(order.payment_expires_at).getTime() - Date.now()) / 1000,
    );
    return Math.max(0, diff);
  });
  const [copiedField, setCopiedField] = useState<'account' | 'content' | null>(null);
  const [checking, setChecking] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [actionError, setActionError] = useState('');
  const purchaseLoggedRef = useRef(order.payment_status === 'PAID');

  useEffect(() => {
    setCurrentOrder(order);
    if (order.payment_expires_at) {
      const diff = Math.floor(
        (new Date(order.payment_expires_at).getTime() - Date.now()) / 1000,
      );
      setRemainingSeconds(Math.max(0, diff));
    }
  }, [order]);

  const isPendingOnline =
    currentOrder.payment_method === 'ONLINE' &&
    currentOrder.payment_status === 'PENDING' &&
    currentOrder.status === 'PENDING_PAYMENT';

  // Đếm ngược mỗi giây
  useEffect(() => {
    if (!isPendingOnline || remainingSeconds <= 0) return;
    const timer = window.setInterval(() => {
      setRemainingSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isPendingOnline, remainingSeconds]);

  // Polling trạng thái thanh toán mỗi 4 giây
  useEffect(() => {
    if (!isPendingOnline || !token) return;

    let active = true;
    const poll = async () => {
      try {
        const res = await getOrderPaymentStatus(token, currentOrder.id, userId);
        if (!active) return;
        setRemainingSeconds(res.remaining_seconds);

        if (
          res.payment_status !== currentOrder.payment_status ||
          res.status !== currentOrder.status
        ) {
          const nextOrder: Order = {
            ...currentOrder,
            status: res.status,
            payment_status: res.payment_status,
            paid_at: res.paid_at ?? currentOrder.paid_at,
            payment_info:
              res.payment_status === 'PENDING' ? currentOrder.payment_info : null,
          };

          if (res.payment_status === 'PAID' && !purchaseLoggedRef.current && userId) {
            purchaseLoggedRef.current = true;
            for (const item of nextOrder.items) {
              void logInteraction({
                userId,
                productId: item.product_id,
                action: 'purchase',
                value: 5.0,
              });
            }
          }

          setCurrentOrder(nextOrder);
          onOrderUpdated?.(nextOrder);
        }
      } catch {
        // Bỏ qua lỗi mạng tạm thời khi polling nền
      }
    };

    const interval = window.setInterval(poll, 4000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [isPendingOnline, token, currentOrder, userId, onOrderUpdated]);

  const qrDetails = useMemo(() => {
    const info = currentOrder.payment_info || {};
    const bankId = (info.bank_id || info.bank_bin || '') as string;
    const accountNo = (info.account_no || info.account_number || '') as string;
    const accountName = (info.account_name || '') as string;
    const transferContent = (info.transfer_content ||
      info.content ||
      info.add_info ||
      currentOrder.payment_code ||
      '') as string;
    const amountVnd =
      typeof info.amount_vnd === 'number'
        ? info.amount_vnd
        : typeof info.amount === 'number'
          ? info.amount
          : null;

    let qrUrl = (info.qr_url || info.qr_image_url || info.vietqr_url || '') as string;
    if (!qrUrl && bankId && accountNo) {
      const params = new URLSearchParams();
      if (amountVnd && amountVnd > 0) params.set('amount', String(Math.round(amountVnd)));
      if (transferContent) params.set('addInfo', transferContent);
      if (accountName) params.set('accountName', accountName);
      qrUrl = `https://img.vietqr.io/image/${encodeURIComponent(bankId)}-${encodeURIComponent(accountNo)}-compact2.png?${params.toString()}`;
    }

    return {
      qrUrl,
      bankName: (info.bank_name || bankId || 'VietQR') as string,
      accountNo,
      accountName,
      transferContent,
      amountVnd,
    };
  }, [currentOrder]);

  const handleCopy = async (text: string, field: 'account' | 'content') => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      window.setTimeout(() => setCopiedField(null), 1800);
    } catch {
      // Bỏ qua nếu trình duyệt chặn clipboard
    }
  };

  const handleManualCheck = async () => {
    if (!token) return;
    setChecking(true);
    setActionError('');
    try {
      const res = await getOrderPaymentStatus(token, currentOrder.id, userId);
      setRemainingSeconds(res.remaining_seconds);
      if (
        res.payment_status !== currentOrder.payment_status ||
        res.status !== currentOrder.status
      ) {
        const nextOrder: Order = {
          ...currentOrder,
          status: res.status,
          payment_status: res.payment_status,
          paid_at: res.paid_at ?? currentOrder.paid_at,
          payment_info:
            res.payment_status === 'PENDING' ? currentOrder.payment_info : null,
        };
        setCurrentOrder(nextOrder);
        onOrderUpdated?.(nextOrder);
      }
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'Unable to check payment status.',
      );
    } finally {
      setChecking(false);
    }
  };

  const handleCancelOrder = async () => {
    if (!token) return;
    setCancelling(true);
    setActionError('');
    try {
      const updated = await cancelOrder(token, currentOrder.id, userId);
      setCurrentOrder(updated);
      onOrderUpdated?.(updated);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to cancel order.');
    } finally {
      setCancelling(false);
    }
  };

  const handleDemoPaid = () => {
    if (!DEMO_MODE || !userId) return;
    const updated = simulateDemoOrderPaid(userId, currentOrder.id);
    if (updated) {
      setCurrentOrder(updated);
      onOrderUpdated?.(updated);
    }
  };

  if (currentOrder.payment_method !== 'ONLINE') {
    return null;
  }

  // 1. Đã thanh toán thành công
  if (currentOrder.payment_status === 'PAID') {
    return (
      <div className="panel border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/60 dark:bg-emerald-500/10 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-emerald-100 dark:bg-emerald-500/20 p-2.5 text-emerald-600 dark:text-emerald-300">
            <CircleCheck size={22} />
          </div>
          <div>
            <h3 className="font-bold text-emerald-900 dark:text-emerald-200">
              <Tr text={'Online payment confirmed'} />
            </h3>
            <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-300">
              <Tr text={'Your VietQR transfer has been verified and your order is confirmed.'} />
            </p>
            {currentOrder.payment_code && (
              <p className="mt-2 font-mono text-xs text-emerald-700/90 dark:text-emerald-300/90">
                {t('Reference')}: {currentOrder.payment_code}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 2. Đã hết hạn hoặc đã hủy
  if (
    currentOrder.payment_status === 'EXPIRED' ||
    currentOrder.status === 'CANCELLED'
  ) {
    return (
      <div className="panel border border-rose-200 dark:border-rose-500/30 bg-rose-50/60 dark:bg-rose-500/10 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-rose-100 dark:bg-rose-500/20 p-2.5 text-rose-600 dark:text-rose-300">
            <AlertTriangle size={22} />
          </div>
          <div>
            <h3 className="font-bold text-rose-900 dark:text-rose-200">
              <Tr text={'Payment expired or order cancelled'} />
            </h3>
            <p className="mt-1 text-sm text-rose-700 dark:text-rose-300">
              <Tr text={'Reserved inventory has been automatically released back to stock.'} />
            </p>
          </div>
        </div>
      </div>
    );
  }

  // 3. Đang chờ quét mã QR thanh toán
  return (
    <div className="panel border border-indigo-200 dark:border-indigo-500/30 p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-4">
        <div className="flex items-center gap-2.5">
          <span className="rounded-xl bg-indigo-50 dark:bg-indigo-500/10 p-2 text-indigo-600 dark:text-indigo-400">
            <QrCode size={20} />
          </span>
          <div>
            <h3 className="font-bold text-slate-900 dark:text-slate-100">
              <Tr text={'Scan VietQR to complete payment'} />
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              <Tr text={'Keep the transfer content exact for automatic confirmation.'} />
            </p>
          </div>
        </div>

        {remainingSeconds > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 dark:bg-amber-500/10 px-3 py-1 text-xs font-bold text-amber-700 dark:text-amber-300">
            <Clock3 size={14} />
            {formatCountdown(remainingSeconds)}
          </span>
        )}
      </div>

      <div className="mt-5 grid gap-6 md:grid-cols-[220px_1fr] md:items-center">
        <div className="mx-auto flex w-full max-w-[220px] flex-col items-center rounded-2xl border border-slate-200 dark:border-slate-700 bg-white p-3 shadow-sm">
          {qrDetails.qrUrl ? (
            <img
              src={qrDetails.qrUrl}
              alt="VietQR Payment Code"
              className="aspect-square w-full rounded-xl object-contain"
            />
          ) : (
            <div className="flex aspect-square w-full items-center justify-center rounded-xl bg-slate-100 text-slate-400">
              <QrCode size={48} />
            </div>
          )}
          <span className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {qrDetails.bankName}
          </span>
        </div>

        <div className="space-y-3 text-sm">
          <div className="space-y-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/70 p-3.5">
            {qrDetails.accountName && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-slate-500 dark:text-slate-400">
                  <Tr text={'Account holder'} />
                </span>
                <span className="font-bold text-slate-900 dark:text-slate-100">
                  {qrDetails.accountName}
                </span>
              </div>
            )}

            {qrDetails.accountNo && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-slate-500 dark:text-slate-400">
                  <Tr text={'Account number'} />
                </span>
                <button
                  type="button"
                  onClick={() => handleCopy(qrDetails.accountNo, 'account')}
                  className="inline-flex items-center gap-1.5 font-mono font-bold text-slate-900 dark:text-slate-100 hover:text-indigo-600"
                >
                  <span>{qrDetails.accountNo}</span>
                  {copiedField === 'account' ? (
                    <Check size={14} className="text-emerald-600" />
                  ) : (
                    <Copy size={14} className="text-slate-400" />
                  )}
                </button>
              </div>
            )}

            <div className="flex items-center justify-between gap-2">
              <span className="text-slate-500 dark:text-slate-400">
                <Tr text={'Amount'} />
              </span>
              <div className="text-right">
                <span className="text-base font-extrabold text-indigo-600 dark:text-indigo-400">
                  {qrDetails.amountVnd !== null
                    ? formatTransferVND(qrDetails.amountVnd)
                    : formatMoney(currentOrder.total_amount)}
                </span>
                {qrDetails.amountVnd !== null && (
                  <span className="block text-[11px] text-slate-400">
                    ({formatMoney(currentOrder.total_amount)})
                  </span>
                )}
              </div>
            </div>

            {qrDetails.transferContent && (
              <div className="flex items-center justify-between gap-2 border-t border-slate-200/70 dark:border-slate-700 pt-2.5">
                <span className="text-slate-500 dark:text-slate-400">
                  <Tr text={'Transfer content'} />
                </span>
                <button
                  type="button"
                  onClick={() => handleCopy(qrDetails.transferContent, 'content')}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-500/15 px-2.5 py-1 font-mono font-bold text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100"
                >
                  <span>{qrDetails.transferContent}</span>
                  {copiedField === 'content' ? (
                    <Check size={14} className="text-emerald-600" />
                  ) : (
                    <Copy size={14} className="text-slate-400" />
                  )}
                </button>
              </div>
            )}
          </div>

          {actionError && (
            <p className="text-xs font-medium text-rose-600 dark:text-rose-400">
              {t(actionError)}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <button
              type="button"
              onClick={handleManualCheck}
              disabled={checking}
              className="primary-button text-sm"
            >
              <RefreshCw size={15} className={checking ? 'animate-spin' : ''} />
              <Tr text={'I have paid · Check now'} />
            </button>

            <button
              type="button"
              onClick={handleCancelOrder}
              disabled={cancelling}
              className="secondary-button text-sm text-rose-600 dark:text-rose-300"
            >
              <XCircle size={15} />
              <Tr text={'Cancel order'} />
            </button>

            {DEMO_MODE && (
              <button
                type="button"
                onClick={handleDemoPaid}
                className="secondary-button text-xs"
              >
                Demo: Simulate Webhook Paid
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
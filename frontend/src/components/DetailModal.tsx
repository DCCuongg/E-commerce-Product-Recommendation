import { useEffect, useRef, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';
import { usePreferences } from '../context/PreferencesContext';

/** Route-aware overlay. The URL remains shareable, and direct URLs still render a full page. */
export default function DetailModal({ title, children, wide = false }: {title: string; children: ReactNode; wide?: boolean}) {
  const navigate = useNavigate();
  const {t}=usePreferences();
  const closeButton = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const close = () => navigate(-1);

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButton.current?.focus();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab' || !dialog.current) return;
      const controls = [...dialog.current.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
      if (!controls.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = oldOverflow;
      previousFocus.current?.focus();
    };
    // The route is the modal identity; effect should only run at mount/unmount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-[3px] sm:p-6" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}>
    <div ref={dialog} role="dialog" aria-modal="true" aria-label={t(title)} className={`flex max-h-[88dvh] w-full flex-col overflow-hidden rounded-2xl bg-[#f8f9fc] dark:bg-[#0b1322] shadow-2xl ${wide ? 'max-w-[920px]' : 'max-w-[680px]'}`}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-5 py-3 sm:px-6">
        <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">{t(title)}</h2>
        <button ref={closeButton} type="button" onClick={close} aria-label={t("Close details")} className="rounded-lg p-2 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100"><X size={20}/></button>
      </div>
      <div className="detail-modal-content min-h-0 overflow-y-auto p-4 sm:p-6">{children}</div>
    </div>
  </div>;
}

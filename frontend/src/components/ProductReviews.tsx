import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AlertCircle, CheckCircle2, LoaderCircle, MessageSquareText, Send, Star } from 'lucide-react';
import { useAuth, TOKEN_KEY } from '../context/AuthContext';
import { Tr, usePreferences } from '../context/PreferencesContext';
import { logInteraction } from '../services/faas';
import { getProductReviews, submitProductReview, type ProductReview } from '../services/reviews';

type Props = { productId: string; onPublished?: () => void };

function RatingStars({ rating }: { rating: number }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`${rating} / 5`}>
      {[1, 2, 3, 4, 5].map((value) => (
        <Star
          key={value}
          size={15}
          fill={value <= Math.round(rating) ? 'currentColor' : 'none'}
          className={value <= Math.round(rating) ? 'text-amber-500' : 'text-slate-300 dark:text-slate-600'}
        />
      ))}
    </span>
  );
}

export default function ProductReviews({ productId, onPublished }: Props) {
  const { t, date } = usePreferences();
  const { user } = useAuth();
  const location = useLocation();
  const [reviews, setReviews] = useState<ProductReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [success, setSuccess] = useState(false);
  const [sending, setSending] = useState(false);
  const [limit, setLimit] = useState(20);
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState('');
  const [comment, setComment] = useState('');

  const refresh = useCallback(async (reviewLimit: number) => {
    const response = await getProductReviews(productId, reviewLimit);
    setReviews(response);
    setError('');
  }, [productId]);

  useEffect(() => {
    let cancelled = false;
    getProductReviews(productId, 20)
      .then((next) => { if (!cancelled) setReviews(next); })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Unable to load customer reviews.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [productId]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      await refresh(100);
      setLimit(100);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load customer reviews.');
    } finally {
      setLoadingMore(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) return;
    if (rating < 1 || rating > 5) {
      setReviewError('Please choose a rating from 1 to 5 stars.');
      return;
    }
    setSending(true);
    setReviewError('');
    setSuccess(false);
    try {
      const created = await submitProductReview(productId, sessionStorage.getItem(TOKEN_KEY), user.id, {
        rating, title, comment,
      });
      // Keep the submitted review visible even when the read API is temporarily unavailable.
      setReviews((previous) => [created, ...previous.filter((item) => item.id !== created.id)].slice(0, limit));
      setRating(0);
      setTitle('');
      setComment('');
      setSuccess(true);
      onPublished?.();
      void logInteraction({ userId: user.id, productId, action: 'rating', value: created.rating });
      try { await refresh(limit); } catch { /* POST succeeded; do not misreport it as a failed submission. */ }
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : 'Unable to submit your review.');
    } finally {
      setSending(false);
    }
  }

  return (
    <section id="customer-reviews" className="mt-20 border-t border-[#eeebe5] pt-14 dark:border-slate-700" aria-labelledby="customer-reviews-title">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow"><Tr text="COMMUNITY FEEDBACK"/></p>
          <h2 id="customer-reviews-title" className="mt-2 font-['Georgia',serif] text-3xl tracking-[-.03em] text-[#242b37] dark:text-slate-100">
            <Tr text="Customer reviews"/>
          </h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400"><Tr text="Ratings and comments shared by Soundwave customers."/></p>
        </div>
        {!loading && <span className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
          {reviews.length} {t(reviews.length === 1 ? 'review shown' : 'reviews shown')}
        </span>}
      </div>

      <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-3xl border border-[#eeebe5] bg-white p-6 dark:border-slate-700 dark:bg-slate-900 sm:p-8">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400" role="status"><LoaderCircle size={17} className="animate-spin"/><Tr text="Loading reviews..."/></div>
          ) : error ? (
            <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-rose-600 dark:text-rose-300">
              <AlertCircle size={18}/><span>{t(error)}</span>
              <button type="button" className="font-bold underline" onClick={() => { setLoading(true); refresh(limit).catch((e: unknown) => setError(e instanceof Error ? e.message : 'Unable to load customer reviews.')).finally(() => setLoading(false)); }}><Tr text="Try again"/></button>
            </div>
          ) : reviews.length === 0 ? (
            <div className="py-6 text-center">
              <MessageSquareText size={33} className="mx-auto text-slate-400"/>
              <p className="mt-4 font-bold"><Tr text="No customer reviews yet"/></p>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400"><Tr text="Be the first to share your experience with this product."/></p>
            </div>
          ) : (
            <>
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {reviews.map((review) => (
                  <article key={review.id} className="py-6 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <RatingStars rating={review.rating}/>
                        <span className="text-xs font-bold text-amber-600 dark:text-amber-400">{review.rating.toFixed(1)}</span>
                      </div>
                      <time dateTime={review.created_at || undefined} className="text-xs text-slate-400 dark:text-slate-500">
                        {date(review.created_at)}
                      </time>
                    </div>
                    {review.title && <h3 className="mt-3 font-bold text-[#242b37] dark:text-slate-100">{review.title}</h3>}
                    {review.comment && <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-600 dark:text-slate-300">{review.comment}</p>}
                    <p className="mt-3 text-xs font-semibold text-slate-400 dark:text-slate-500">
                      {review.user_id === user?.id ? t('You') : t('Soundwave customer')}
                    </p>
                  </article>
                ))}
              </div>
              {reviews.length >= 20 && limit === 20 && (
                <button type="button" disabled={loadingMore} onClick={loadMore} className="mt-7 w-full rounded-full border border-slate-200 py-3 text-sm font-bold text-indigo-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-indigo-300 dark:hover:bg-slate-800">
                  {t(loadingMore ? 'Loading reviews...' : 'Load more reviews (up to 100)')}
                </button>
              )}
              {limit === 100 && reviews.length === 100 && <p className="mt-4 text-xs text-slate-400"><Tr text="Showing the 100 most recent reviews."/></p>}
            </>
          )}
        </div>

        <div className="rounded-3xl border border-[#eeebe5] bg-white p-6 dark:border-slate-700 dark:bg-slate-900 sm:p-8">
          <h3 className="text-lg font-bold text-[#242b37] dark:text-slate-100"><Tr text="Write a review"/></h3>
          {!user ? (
            <div className="mt-4">
              <p className="text-sm leading-6 text-slate-500 dark:text-slate-400"><Tr text="Sign in to rate this instrument and share your feedback."/></p>
              <Link to={`/signin?next=${encodeURIComponent(location.pathname + '#customer-reviews')}`} className="mt-5 inline-flex rounded-full bg-[#263247] px-6 py-3 text-sm font-bold text-white transition hover:bg-indigo-600"><Tr text="Sign in to review"/></Link>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mt-5 space-y-5">
              <div>
                <span className="mb-2 block text-xs font-semibold text-slate-600 dark:text-slate-300"><Tr text="Your rating"/> *</span>
                <div className="flex gap-1" role="group" aria-label={t('Your rating')}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <button key={value} type="button" aria-label={`${value} ${t(value === 1 ? 'star' : 'stars')}`} aria-pressed={rating === value} onClick={() => { setRating(value); setReviewError(''); }} className="rounded-lg p-1.5 transition hover:bg-amber-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:hover:bg-slate-800">
                      <Star size={26} fill={rating >= value ? 'currentColor' : 'none'} className={rating >= value ? 'text-amber-500' : 'text-slate-300 dark:text-slate-500'}/>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="review-title" className="mb-2 block text-xs font-semibold text-slate-600 dark:text-slate-300"><Tr text="Review title (optional)"/></label>
                <input id="review-title" maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('Summarize your experience')} className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm outline-none focus:border-indigo-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"/>
              </div>
              <div>
                <label htmlFor="review-comment" className="mb-2 block text-xs font-semibold text-slate-600 dark:text-slate-300"><Tr text="Your comment (optional)"/></label>
                <textarea id="review-comment" rows={4} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t('What did you like about this product?')} className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm outline-none focus:border-indigo-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"/>
              </div>
              {reviewError && <p role="alert" className="flex gap-2 text-xs text-rose-600 dark:text-rose-300"><AlertCircle size={16} className="shrink-0"/>{t(reviewError)}</p>}
              {success && <p role="status" className="flex gap-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400"><CheckCircle2 size={16} className="shrink-0"/><Tr text="Your review was published."/></p>}
              <button type="submit" disabled={sending || rating === 0} className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#263247] px-6 py-3.5 text-sm font-bold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50">
                {sending ? <LoaderCircle size={17} className="animate-spin"/> : <Send size={16}/>}
                {t(sending ? 'Publishing review...' : 'Publish review')}
              </button>
              <p className="text-xs leading-5 text-slate-400 dark:text-slate-500"><Tr text="Reviews are public. Do not share private contact information."/></p>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}

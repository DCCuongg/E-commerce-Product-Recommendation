import { Tr, usePreferences } from '../context/PreferencesContext';
import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, ChevronRight, Minus, Plus, ShoppingBag, Sparkles, Star, Zap } from 'lucide-react';
import StoreHeader, { StoreFooter } from '../components/StoreHeader';
import ProductCard from '../components/ProductCard';
import {
  formatVND,
  getFrequentlyBoughtTogether,
  getProduct,
  productImage,
  productImageCandidates,
  type Product,
  type RecommendationMeta,
} from '../services/catalog';
import { useAuth } from '../context/AuthContext';
import { addToCart } from '../services/cart';
import { logInteraction } from '../services/faas';

export default function ProductDetails() {
  const { t } = usePreferences();
  const { productId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState(false);
  const [image, setImage] = useState('');

  const [related, setRelated] = useState<Product[]>([]);
  const [recsMeta, setRecsMeta] = useState<RecommendationMeta | null>(null);
  const [recsLoading, setRecsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!productId) return;

    setLoading(true);
    setError('');
    setAdded(false);
    setQty(1);

    getProduct(productId)
      .then((p) => {
        if (cancelled) return;
        setProduct(p);
        setImage(productImage(p, "detail"));
        void logInteraction({ userId: user?.id, productId: p.id, action: 'view' });
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Unable to load product.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    setRecsLoading(true);
    getFrequentlyBoughtTogether(productId, 4)
      .then((res) => {
        if (cancelled) return;
        setRelated(res.items);
        setRecsMeta(res.meta);
      })
      .catch(() => {
        if (!cancelled) {
          setRelated([]);
          setRecsMeta(null);
        }
      })
      .finally(() => {
        if (!cancelled) setRecsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [productId, user?.id]);

  async function onAdd() {
    if (!user) {
      navigate(`/signin?next=${encodeURIComponent(location.pathname)}`);
      return;
    }
    if (!product) return;
    setBusy(true);
    setError('');
    try {
      await addToCart(user.id, product.id, qty);
      setAdded(true);
      void logInteraction({ userId: user.id, productId: product.id, action: 'add_to_cart' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to add to bag.');
    } finally {
      setBusy(false);
    }
  }

  function onBuyNow() {
    if (!product) return;
    if (!user) {
      navigate(`/signin?next=${encodeURIComponent(location.pathname)}`);
      return;
    }
    void logInteraction({ userId: user.id, productId: product.id, action: 'click' });
    navigate('/checkout', {
      state: {
        buyNowItem: {
          product_id: product.id,
          product_name: product.name,
          image_url: productImage(product, "detail"),
          unit_price: product.price,
          quantity: qty,
          stock_quantity: product.stock_quantity,
        },
      },
    });
  }

  return (
    <div className="min-h-screen bg-[#faf9f6] dark:bg-[#0b1322] dark:text-slate-100">
      <StoreHeader />
      <main className="mx-auto max-w-[1280px] px-5 pb-16 pt-8 sm:px-8">
        <div className="mb-8 flex flex-wrap items-center gap-2 text-xs font-medium text-slate-400">
          <Link to="/" className="hover:text-indigo-600"><Tr text={'Home'}/></Link>
          <ChevronRight size={13} />
          <Link to="/shop" className="hover:text-indigo-600"><Tr text={'Instruments'}/></Link>
          <ChevronRight size={13} />
          <span className="text-slate-700 dark:text-slate-200"><Tr text={'Product details'}/></span>
        </div>

        {loading ? (
          <div className="grid gap-10 lg:grid-cols-2">
            <div className="aspect-square animate-pulse rounded-3xl bg-slate-200 dark:bg-slate-700" />
            <div className="h-80 animate-pulse rounded-3xl bg-slate-100 dark:bg-slate-800" />
          </div>
        ) : error && !product ? (
          <div className="rounded-3xl bg-white dark:bg-slate-900 p-12 text-center">
            <h1 className="text-2xl font-bold"><Tr text={'Product unavailable'}/></h1>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{error || 'We could not find this instrument.'}</p>
            <Link to="/shop" className="mt-6 inline-flex items-center gap-2 font-bold text-indigo-600">
              <ArrowLeft size={17} /><Tr text={'Back to collection'}/></Link>
          </div>
        ) : product ? (
          <>
            <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-16">
              <div>
                <div className="aspect-[1.1] overflow-hidden rounded-[26px] bg-[#ebe8e1] dark:bg-slate-800">
                  <img
                    src={image}
                    alt={product.name}
                    className="h-full w-full object-contain p-5 sm:p-8"
                    decoding="async"
                    onError={() => {
                      if (!product) return;
                      const sources = productImageCandidates(product, 'detail');
                      const currentIndex = sources.indexOf(image);
                      const next = sources[currentIndex + 1];
                      if (next) setImage(next);
                    }}
                  />
                </div>
                {product.large_urls && product.large_urls.length > 1 && (
                  <div className="mt-4 flex gap-3">
                    {product.large_urls.slice(0, 4).map((url) => (
                      <button
                        type="button"
                        key={url}
                        onClick={() => setImage(url)}
                        className={`h-20 w-20 overflow-hidden rounded-xl border bg-white dark:bg-slate-900 ${
                          image === url ? 'border-indigo-600 ring-2 ring-indigo-600/20' : 'border-slate-200 dark:border-slate-700'
                        }`}
                      >
                        <img src={url} alt={t("Product alternate view")} className="h-full w-full object-contain p-1" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="py-3">
                <p className="text-[11px] font-extrabold uppercase tracking-[.2em] text-indigo-600">
                  {t(product.category || 'Instrument')}
                </p>
                <h1 className="mt-4 font-['Georgia',serif] text-[38px] leading-[1.1] tracking-[-.04em] text-[#242b37] dark:text-slate-100 sm:text-[54px]">
                  {product.name}
                </h1>
                <div className="mt-5 flex items-center gap-2 text-sm text-[#ad8b3e]">
                  {product.rating != null && (
                    <>
                      <Star size={16} fill="currentColor" />
                      <span className="font-bold">{product.rating.toFixed(1)}</span>
                      <span className="text-slate-400">({product.rating_count || 0} {t("reviews")})</span>
                    </>
                  )}
                </div>

                <p className="mt-7 text-[31px] font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
                  {formatVND(product.price)}
                </p>
                <p className="mt-5 max-w-lg text-[15px] leading-8 text-slate-500 dark:text-slate-400">
                  {t(product.description || 'Explore the details of this instrument, and discover the sound that works for you.')}
                </p>

                <div className="mt-8 flex items-center gap-2 text-sm">
                  <span className={`h-2 w-2 rounded-full ${product.stock_quantity > 0 ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    {product.stock_quantity > 0 ? `${product.stock_quantity} {t("available")}` : 'Out of stock'}
                  </span>
                </div>

                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <div className="inline-flex items-center gap-4 rounded-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2">
                    <button
                      type="button"
                      aria-label={t("Decrease quantity")}
                      disabled={qty <= 1}
                      onClick={() => setQty((q) => Math.max(1, q - 1))}
                      className="grid h-8 w-8 place-items-center disabled:opacity-40"
                    >
                      <Minus size={17} />
                    </button>
                    <span className="w-5 text-center text-sm font-bold">{qty}</span>
                    <button
                      type="button"
                      aria-label={t("Increase quantity")}
                      disabled={qty >= product.stock_quantity}
                      onClick={() => setQty((q) => Math.min(product.stock_quantity, q + 1))}
                      className="grid h-8 w-8 place-items-center disabled:opacity-40"
                    >
                      <Plus size={17} />
                    </button>
                  </div>

                  <button
                    type="button"
                    disabled={busy || product.stock_quantity <= 0}
                    onClick={onAdd}
                    className="inline-flex items-center gap-3 rounded-full bg-[#263247] px-7 py-4 text-sm font-bold text-white transition hover:bg-indigo-600 disabled:bg-slate-300"
                  >
                    {added ? (
                      <>
                        <Check size={18} /><Tr text={'Added to bag'}/></>
                    ) : (
                      <>
                        <ShoppingBag size={18} /> {t(busy ? 'Adding...' : 'Add to bag')}
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    disabled={busy || product.stock_quantity <= 0}
                    onClick={onBuyNow}
                    className="inline-flex items-center gap-2 rounded-full border border-[#263247] bg-white dark:bg-slate-900 px-6 py-4 text-sm font-bold text-[#263247] dark:text-slate-100 transition hover:bg-slate-100 disabled:border-slate-200 disabled:text-slate-300"
                  >
                    <Zap size={16} /><Tr text={'Buy now'}/></button>
                </div>

                {added && (
                  <Link to="/cart" className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-indigo-600"><Tr text={'View your bag'}/><ArrowRight size={16} />
                  </Link>
                )}

                {error && (
                  <p role="alert" className="mt-5 text-sm text-red-600">
                    {t(error)}
                  </p>
                )}

                <div className="mt-11 border-t border-slate-200 dark:border-slate-700 pt-7">
                  <h2 className="text-lg font-bold"><Tr text={'Product information'}/></h2>
                  <dl className="mt-4 grid gap-3 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-500 dark:text-slate-400"><Tr text={'Category'}/></dt>
                      <dd className="font-semibold">{product.category || 'Not specified'}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500 dark:text-slate-400"><Tr text={'Product ID'}/></dt>
                      <dd className="font-mono text-xs">{product.id}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>

            <section className="mt-20 border-t border-[#eeebe5] dark:border-slate-700 pt-14">
              <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="inline-flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[.2em] text-indigo-600">
                    <Sparkles size={13} /><Tr text={'Cloud Recommender'}/></p>
                  <h2 className="mt-2 font-['Georgia',serif] text-3xl tracking-[-.03em] text-[#242b37] dark:text-slate-100"><Tr text={'Frequently bought together'}/></h2>
                </div>
                {recsMeta && (
                  <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {recsMeta.data_source && (
                      <span className="rounded-full border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1">
                        {t("Source")}: <strong>{recsMeta.data_source}</strong>
                      </span>
                    )}
                    {recsMeta.deployment_slot && (
                      <span className="rounded-full border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1">
                        Slot: <strong className="uppercase">{recsMeta.deployment_slot}</strong>
                      </span>
                    )}
                    {recsMeta.latency_ms != null && (
                      <span className="rounded-full border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1">
                        {t("Latency")}: <strong>{recsMeta.latency_ms.toFixed(1)} ms</strong>
                      </span>
                    )}
                  </div>
                )}
              </div>

              {recsLoading ? (
                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                  {[0, 1, 2, 3].map((n) => (
                    <div key={n} className="h-80 animate-pulse rounded-2xl bg-white dark:bg-slate-900" />
                  ))}
                </div>
              ) : related.length > 0 ? (
                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                  {related.map((item) => (
                    <ProductCard key={item.id} product={item} />
                  ))}
                </div>
              ) : (
                <p className="rounded-2xl border border-[#eeebe5] dark:border-slate-700 bg-white dark:bg-slate-900 p-6 text-sm text-slate-500 dark:text-slate-400"><Tr text={'No complementary recommendations found for this instrument yet.'}/></p>
              )}
            </section>
          </>
        ) : null}
      </main>
      <StoreFooter />
    </div>
  );
}
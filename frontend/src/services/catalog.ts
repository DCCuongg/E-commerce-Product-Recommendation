import { DEMO_MODE } from './auth';

export type Product = {
  id: string;
  product_id?: string;
  name: string;
  category: string | null;
  price: number;
  image_url: string | null;
  thumb_url?: string | null;
  thumbnail_url?: string | null;
  hi_res_url?: string | null;
  large_urls?: string[];
  description?: string | null;
  stock_quantity: number;
  rating?: number;
  rating_count?: number;
  is_active?: boolean;
};
export type ProductPage = { items: Product[]; total: number; page: number; page_size: number };
export type CatalogParams = { page?: number; page_size?: number; category?: string; search?: string; sort_by?: 'default' | 'price_asc' | 'price_desc' | 'name_asc' };

const API_BASE = (import.meta.env.VITE_ORDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const RECS_BASE = (import.meta.env.VITE_RECOMMENDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

// Photographic previews are independent of the team's dataset. In live mode, product URLs come from FastAPI.
const photo = (id: string, width = 900) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=80`;
export const editorialImages = {
  hero: photo('photo-1520523839897-bd0b52f945a0', 1800),
  piano: photo('photo-1520523839897-bd0b52f945a0'),
  guitar: photo('photo-1510915361894-db8b60106cb1'),
  drums: photo('photo-1519892300165-cb5542fb47c7'),
  studio: photo('photo-1511379938547-c1f69419868d'),
  keys: photo('photo-1552422535-c45813c61732'),
  electric: photo('photo-1706356104839-5d3a4e8eb35f'),
};

export const demoProducts: Product[] = [
  { id: 'DEMO-P01', name: 'Studio 88 Digital Piano', category: 'Piano', price: 18900000, image_url: editorialImages.piano, description: 'A full-size digital piano for everyday practice and creative expression.', stock_quantity: 18, rating: 4.8, rating_count: 41 },
  { id: 'DEMO-G01', name: 'Warmwood Acoustic Guitar', category: 'Guitar', price: 4250000, image_url: editorialImages.guitar, description: 'A comfortable acoustic guitar with a warm, balanced character.', stock_quantity: 12, rating: 4.7, rating_count: 56 },
  { id: 'DEMO-G02', name: 'Ivory Electric Guitar', category: 'Guitar', price: 9750000, image_url: editorialImages.electric, description: 'A versatile electric guitar for bedroom sessions and the stage.', stock_quantity: 7, rating: 4.9, rating_count: 23 },
  { id: 'DEMO-D01', name: 'Session Acoustic Drum Kit', category: 'Drums', price: 16900000, image_url: editorialImages.drums, description: 'A dynamic drum kit made for rehearsal and live performance.', stock_quantity: 5, rating: 4.8, rating_count: 18 },
  { id: 'DEMO-K01', name: 'Essential 61 Keyboard', category: 'Keyboard', price: 6400000, image_url: editorialImages.keys, description: 'Explore melodies and arrangements with a portable keyboard.', stock_quantity: 15, rating: 4.5, rating_count: 37 },
  { id: 'DEMO-S01', name: 'Home Studio Essentials', category: 'Audio', price: 3850000, image_url: editorialImages.studio, description: 'A thoughtful start for building a personal music workspace.', stock_quantity: 9, rating: 4.7, rating_count: 31 },
  { id: 'DEMO-G03', name: 'Classic Acoustic Guitar', category: 'Guitar', price: 2950000, image_url: editorialImages.guitar, description: 'A classic shape designed for learners and casual players.', stock_quantity: 20, rating: 4.6, rating_count: 66 },
  { id: 'DEMO-P02', name: 'Concert Digital Piano', category: 'Piano', price: 27400000, image_url: editorialImages.piano, description: 'Expressive keys and an elegant profile for home playing.', stock_quantity: 4, rating: 4.9, rating_count: 12 },
];

/** Search only product names, not descriptions or categories.
 * The existing FastAPI endpoint searches all four fields and paginates before
 * returning results. To provide accurate counts and later pages, we request
 * every server-matching batch then filter/paginate locally. Search-only path;
 * normal browsing uses the backend's native pagination and remains unchanged.
 */
function normalizeName(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim().replace(/\s+/g, ' ');
}
function nameRelevance(product: Product, search: string): number {
  const name = normalizeName(product.name);
  const query = normalizeName(search);
  if (!query || !name) return -1;
  if (name === query) return 4;
  if (name.startsWith(query)) return 3;
  if (name.includes(query)) return 2;
  return query.split(' ').every((word) => name.includes(word)) ? 1 : -1;
}
const searchCache = new Map<string, { promise: Promise<Product[]>; created: number }>();
const CACHE_MS = 45_000;

async function nameOnlyLiveResults(params: CatalogParams): Promise<Product[]> {
  const search = params.search!.trim();
  // Use one search token to collect candidates; the client then checks ALL
  // name tokens, even when the user enters words in a different order.
  const backendSearch = search.split(/\s+/)[0];
  const sort = params.sort_by || 'default';
  const key = JSON.stringify([search.toLocaleLowerCase(), params.category || '', sort]);
  const cached = searchCache.get(key);
  if (cached && Date.now() - cached.created < CACHE_MS) return cached.promise;

  const load = async (): Promise<Product[]> => {
    const makeUrl = (page: number) => {
      const query = new URLSearchParams({
        page: String(page), page_size: '100', search: backendSearch, sort_by: sort,
      });
      if (params.category) query.set('category', params.category);
      return `${API_BASE}/api/v1/products?${query}`;
    };
    const getPage = async (page: number): Promise<ProductPage> => {
      const response = await fetch(makeUrl(page));
      if (!response.ok) throw new Error(`Unable to load products (${response.status}).`);
      return response.json() as Promise<ProductPage>;
    };
    const first = await getPage(1);
    const pageCount = Math.ceil(first.total / 100);
    // The current project's catalog has ~1,000 products. Avoid accidentally
    // issuing thousands of requests if a future backend changes unexpectedly.
    if (pageCount > 50) throw new Error('Search results are too large for name-only filtering. Please narrow the query.');
    const results: Product[] = [...first.items];
    for (let batch = 2; batch <= pageCount; batch += 4) {
      const batchPages = Array.from({ length: Math.min(4, pageCount - batch + 1) }, (_, i) => batch + i);
      const pages = await Promise.all(batchPages.map(getPage));
      pages.forEach((page) => results.push(...page.items));
    }
    const matching = results
      .map((product, position) => ({ product, position, score: nameRelevance(product, search) }))
      .filter((entry) => entry.score >= 0);
    if (sort === 'default') {
      matching.sort((a, b) => b.score - a.score || a.position - b.position);
    } // Other sorts preserve the API's order.
    return matching.map((entry) => entry.product);
  };
  const promise = load();
  // Bound the browser-side cache during long search sessions.
  if (searchCache.size >= 30) searchCache.delete(searchCache.keys().next().value!);
  searchCache.set(key, { promise, created: Date.now() });
  try { return await promise; }
  catch (error) { searchCache.delete(key); throw error; }
}

export async function getProducts(params: CatalogParams = {}): Promise<ProductPage> {
  const page = params.page ?? 1;
  const pageSize = params.page_size ?? 12;
  const search = params.search?.trim();

  if (DEMO_MODE) {
    await new Promise(resolve => setTimeout(resolve, 120));
    let items = [...demoProducts];
    if (params.category && params.category.toLowerCase() !== 'all') {
      items = items.filter((p) => (p.category || '').toLowerCase().includes(params.category!.toLowerCase()));
    }
    if (search) {
      items = items.filter((product) => nameRelevance(product, search) >= 0);
      if (!params.sort_by || params.sort_by === 'default') {
        items.sort((a, b) => nameRelevance(b, search) - nameRelevance(a, search));
      }
    }
    if (params.sort_by === 'price_asc') items.sort((a, b) => a.price - b.price);
    if (params.sort_by === 'price_desc') items.sort((a, b) => b.price - a.price);
    if (params.sort_by === 'name_asc') items.sort((a, b) => a.name.localeCompare(b.name));
    return { items: items.slice((page - 1) * pageSize, page * pageSize), page, page_size: pageSize, total: items.length };
  }

  if (search) {
    const items = await nameOnlyLiveResults(params);
    return { items: items.slice((page - 1) * pageSize, page * pageSize), page, page_size: pageSize, total: items.length };
  }

  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort_by: params.sort_by || 'default' });
  if (params.category) query.set('category', params.category);
  const response = await fetch(`${API_BASE}/api/v1/products?${query}`);
  if (!response.ok) throw new Error(`Unable to load products (${response.status}).`);
  return response.json() as Promise<ProductPage>;
}

export async function getProduct(id: string): Promise<Product> {
  if (DEMO_MODE) {
    const product = demoProducts.find(p => p.id === id);
    if (!product) throw new Error('Product not found.');
    return product;
  }
  const response = await fetch(`${API_BASE}/api/v1/products/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(`Unable to load product (${response.status}).`);
  return response.json() as Promise<Product>;
}

export async function getRecommendations(userId: string, count = 4): Promise<Product[]> {
  if (DEMO_MODE) return demoProducts.slice(2, 2 + count);
  const response = await fetch(`${RECS_BASE}/api/v1/recommendations/${encodeURIComponent(userId)}?top_k=${count}`);
  if (!response.ok) throw new Error('Recommendations are unavailable.');
  const payload = await response.json() as { recommendations?: { product_id?: string; id?: string }[] };
  const ids = (payload.recommendations || []).map(r => r.product_id || r.id).filter((value): value is string => Boolean(value));
  if (!ids.length) return [];
  const batch = await fetch(`${API_BASE}/api/v1/products/batch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product_ids: ids }) });
  if (!batch.ok) throw new Error('Recommended products could not be loaded.');
  return batch.json() as Promise<Product[]>;
}

export function formatVND(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

/** High-quality image candidates; never stretch a thumbnail as the first choice. */
export function productImageCandidates(product: Product, size: 'card' | 'detail' = 'card'): string[] {
  const sources = size === 'detail'
    ? [product.hi_res_url, ...(product.large_urls || []), product.image_url, product.thumb_url, product.thumbnail_url]
    : [product.large_urls?.[0], product.hi_res_url, product.image_url, ...(product.large_urls || []), product.thumb_url, product.thumbnail_url];
  const urls = sources.filter((url): url is string => typeof url === 'string' && url.trim().length > 0);
  return [...new Set([...urls, '/assets/instrument-placeholder.svg'])];
}

export function productImage(product: Product, size: 'card' | 'detail' = 'card'): string {
  return productImageCandidates(product, size)[0];
}

export type RecommendationMeta = {
  strategy?: string;
  data_source?: string;
  model_version?: string;
  deployment_slot?: string;
  latency_ms?: number;
};

export type FrequentlyBoughtResult = {
  items: Product[];
  meta: RecommendationMeta | null;
};

export async function getFrequentlyBoughtTogether(
  productId: string,
  count = 4,
): Promise<FrequentlyBoughtResult> {
  if (DEMO_MODE) {
    return {
      items: demoProducts.filter((p) => p.id !== productId).slice(0, count),
      meta: {
        strategy: 'item_similarity_demo',
        data_source: 'cosmos_db',
        model_version: 'v1.0-svd',
        deployment_slot: 'blue',
        latency_ms: 2.1,
      },
    };
  }

  const response = await fetch(
    `${RECS_BASE}/api/v1/products/${encodeURIComponent(productId)}/frequently-bought-together?top_k=${count}`,
  );
  if (!response.ok) throw new Error('Related recommendations are unavailable.');

  type RawRecItem = Partial<Product> & { product_id?: string; id?: string };
  const payload = (await response.json()) as RecommendationMeta & {
    frequently_bought_together?: RawRecItem[];
    recommendations?: RawRecItem[];
  };

  // Tương thích ngược: ưu tiên key chuẩn frequently_bought_together, fallback sang recommendations
  const recs = payload.frequently_bought_together ?? payload.recommendations ?? [];
  const meta: RecommendationMeta = {
    strategy: payload.strategy ?? 'item_similarity',
    data_source: payload.data_source,
    model_version: payload.model_version,
    deployment_slot: payload.deployment_slot,
    latency_ms: payload.latency_ms,
  };

  if (!recs.length) return { items: [], meta };

  const hasFullInfo = recs.every((r) => Boolean(r.name) && typeof r.price === 'number');
  if (hasFullInfo) {
    const items: Product[] = recs.map((r) => ({
      id: r.product_id || r.id || '',
      product_id: r.product_id || r.id,
      name: r.name || 'Instrument',
      category: r.category ?? null,
      price: r.price ?? 0,
      image_url: r.image_url || r.hi_res_url || r.thumbnail_url || null,
      thumbnail_url: r.thumbnail_url ?? null,
      thumb_url: r.thumb_url ?? null,
      hi_res_url: r.hi_res_url ?? null,
      large_urls: Array.isArray(r.large_urls) ? r.large_urls : [],
      stock_quantity: r.stock_quantity ?? 100,
      rating: r.rating,
      rating_count: r.rating_count,
    }));
    return { items: items.filter((item) => Boolean(item.id)), meta };
  }

  const ids = recs.map((r) => r.product_id || r.id).filter((v): v is string => Boolean(v));
  if (!ids.length) return { items: [], meta };

  const batch = await fetch(`${API_BASE}/api/v1/products/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_ids: ids }),
  });
  if (!batch.ok) throw new Error('Related products could not be loaded.');

  return { items: (await batch.json()) as Product[], meta };
}
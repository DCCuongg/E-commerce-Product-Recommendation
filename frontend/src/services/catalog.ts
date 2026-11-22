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
export type CatalogParams = { page?: number; page_size?: number; category?: string; search?: string; sort_by?: 'default'|'price_asc'|'price_desc'|'name_asc' };

const API_BASE = (import.meta.env.VITE_ORDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const RECS_BASE = (import.meta.env.VITE_RECOMMENDER_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

// Photographic previews are independent of the team's dataset. In live mode, product URLs come from FastAPI.
const photo = (id: string, width=900) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=80`;
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
  {id:'DEMO-P01',name:'Studio 88 Digital Piano',category:'Piano',price:18900000,image_url:editorialImages.piano,description:'A full-size digital piano for everyday practice and creative expression.',stock_quantity:18,rating:4.8,rating_count:41},
  {id:'DEMO-G01',name:'Warmwood Acoustic Guitar',category:'Guitar',price:4250000,image_url:editorialImages.guitar,description:'A comfortable acoustic guitar with a warm, balanced character.',stock_quantity:12,rating:4.7,rating_count:56},
  {id:'DEMO-G02',name:'Ivory Electric Guitar',category:'Guitar',price:9750000,image_url:editorialImages.electric,description:'A versatile electric guitar for bedroom sessions and the stage.',stock_quantity:7,rating:4.9,rating_count:23},
  {id:'DEMO-D01',name:'Session Acoustic Drum Kit',category:'Drums',price:16900000,image_url:editorialImages.drums,description:'A dynamic drum kit made for rehearsal and live performance.',stock_quantity:5,rating:4.8,rating_count:18},
  {id:'DEMO-K01',name:'Essential 61 Keyboard',category:'Keyboard',price:6400000,image_url:editorialImages.keys,description:'Explore melodies and arrangements with a portable keyboard.',stock_quantity:15,rating:4.5,rating_count:37},
  {id:'DEMO-S01',name:'Home Studio Essentials',category:'Audio',price:3850000,image_url:editorialImages.studio,description:'A thoughtful start for building a personal music workspace.',stock_quantity:9,rating:4.7,rating_count:31},
  {id:'DEMO-G03',name:'Classic Acoustic Guitar',category:'Guitar',price:2950000,image_url:editorialImages.guitar,description:'A classic shape designed for learners and casual players.',stock_quantity:20,rating:4.6,rating_count:66},
  {id:'DEMO-P02',name:'Concert Digital Piano',category:'Piano',price:27400000,image_url:editorialImages.piano,description:'Expressive keys and an elegant profile for home playing.',stock_quantity:4,rating:4.9,rating_count:12},
];

export async function getProducts(params: CatalogParams = {}): Promise<ProductPage> {
  const page = params.page ?? 1; const pageSize = params.page_size ?? 12;
  if (DEMO_MODE) {
    await new Promise(resolve => setTimeout(resolve, 120));
    let items = [...demoProducts];
    if (params.category && params.category.toLowerCase() !== 'all') items = items.filter(p => (p.category || '').toLowerCase().includes(params.category!.toLowerCase()));
    if (params.search) { const q = params.search.toLowerCase(); items = items.filter(p => `${p.name} ${p.category} ${p.description}`.toLowerCase().includes(q)); }
    if (params.sort_by === 'price_asc') items.sort((a,b) => a.price - b.price);
    if (params.sort_by === 'price_desc') items.sort((a,b) => b.price - a.price);
    if (params.sort_by === 'name_asc') items.sort((a,b) => a.name.localeCompare(b.name));
    return {items: items.slice((page-1)*pageSize,page*pageSize),page,page_size:pageSize,total:items.length};
  }
  const query = new URLSearchParams({page:String(page),page_size:String(pageSize),sort_by:params.sort_by || 'default'});
  if (params.category) query.set('category',params.category);
  if (params.search) query.set('search',params.search);
  const response = await fetch(`${API_BASE}/api/v1/products?${query}`);
  if (!response.ok) throw new Error(`Unable to load products (${response.status}).`);
  return response.json() as Promise<ProductPage>;
}

export async function getProduct(id: string): Promise<Product> {
  if (DEMO_MODE) {
    const product = demoProducts.find(p=>p.id === id);
    if (!product) throw new Error('Product not found.');
    return product;
  }
  const response = await fetch(`${API_BASE}/api/v1/products/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(`Unable to load product (${response.status}).`);
  return response.json() as Promise<Product>;
}

export async function getRecommendations(userId: string, count=4): Promise<Product[]> {
  if (DEMO_MODE) return demoProducts.slice(2,2+count);
  const response = await fetch(`${RECS_BASE}/api/v1/recommendations/${encodeURIComponent(userId)}?top_k=${count}`);
  if (!response.ok) throw new Error('Recommendations are unavailable.');
  const payload = await response.json() as { recommendations?: {product_id?:string;id?:string}[] };
  const ids = (payload.recommendations || []).map(r=>r.product_id || r.id).filter((value):value is string=>Boolean(value));
  if (!ids.length) return [];
  const batch = await fetch(`${API_BASE}/api/v1/products/batch`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_ids:ids})});
  if (!batch.ok) throw new Error('Recommended products could not be loaded.');
  return batch.json() as Promise<Product[]>;
}

export function formatVND(value: number): string {
  return new Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND',maximumFractionDigits:0}).format(value);
}

export function productImage(product: Product): string {
  return product.thumb_url || product.thumbnail_url || product.image_url || product.hi_res_url || '/assets/instrument-placeholder.svg';
}

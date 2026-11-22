import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight, Plus, Star } from 'lucide-react';
import type { Product } from '../services/catalog';
import { formatVND, productImage } from '../services/catalog';
import { useAuth } from '../context/AuthContext';
import { addToCart } from '../services/cart';
import { useState } from 'react';

export default function ProductCard({product}:{product:Product}){
 const {user}=useAuth(); const navigate=useNavigate(); const location=useLocation(); const [added,setAdded]=useState(false); const [error,setError]=useState('');
 async function add(){if(!user){navigate(`/signin?next=${encodeURIComponent(location.pathname+location.search)}`);return;}try{await addToCart(user.id,product.id);setAdded(true);setTimeout(()=>setAdded(false),1800);}catch(e){setError(e instanceof Error?e.message:'Could not add item.');}}
 return <article className="group flex min-w-0 flex-col overflow-hidden rounded-2xl border border-[#eeeae5] bg-white transition hover:-translate-y-1 hover:shadow-[0_18px_42px_rgba(30,35,46,.08)]">
  <Link to={`/products/${encodeURIComponent(product.id)}`} className="relative block aspect-[1.13] overflow-hidden bg-[#f5f3ee]" aria-label={`View ${product.name}`}><img src={productImage(product)} onError={e=>{e.currentTarget.onerror=null;e.currentTarget.src='/assets/instrument-placeholder.svg'}} loading="lazy" alt={product.name} className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.05]"/>{product.stock_quantity<=0?<span className="absolute left-3 top-3 rounded-full bg-slate-900 px-3 py-1 text-[10px] font-bold text-white">Sold out</span>:null}<span className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-full bg-white/95 text-slate-700 opacity-0 shadow-sm transition group-hover:opacity-100"><ArrowUpRight size={17}/></span></Link>
  <div className="flex flex-1 flex-col p-4 sm:p-5"><p className="mb-2 text-[10px] font-bold uppercase tracking-[.17em] text-indigo-600">{product.category||'Instruments'}</p><Link to={`/products/${encodeURIComponent(product.id)}`} className="line-clamp-2 min-h-[44px] text-[15px] font-bold leading-6 text-[#272a31] transition hover:text-indigo-600">{product.name}</Link><div className="mt-2 flex items-center gap-1.5 text-xs text-[#a07b30]">{product.rating!=null&&<><Star size={12} fill="currentColor"/>{product.rating.toFixed(1)}<span className="text-slate-400">({product.rating_count||0})</span></>}</div><div className="mt-auto flex items-end justify-between gap-2 pt-4"><div><p className="text-[10px] text-slate-400">Price</p><p className="text-[15px] font-extrabold text-[#232732] sm:text-base">{formatVND(product.price)}</p></div><button type="button" onClick={add} disabled={product.stock_quantity<=0} aria-label={`Add ${product.name} to cart`} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#222c3d] text-white transition hover:bg-indigo-600 disabled:bg-slate-300">{added?<span className="text-sm font-extrabold">✓</span>:<Plus size={19}/>}</button></div>{error&&<p role="alert" className="mt-2 text-xs text-red-600">{error}</p>}</div>
 </article>
}

import { useEffect, useState, type FormEvent } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { ArrowRight, Bell, Headphones, Menu, Search, ShoppingBag, UserRound, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getCart } from '../services/cart';

const categories = [
  {name:'Pianos & Keys',category:'Piano'},
  {name:'Guitars',category:'Guitar'},
  {name:'Drums',category:'Drums'},
  {name:'Studio & Audio',category:'Audio'},
];
export function StoreBrand(){return <Link to="/" className="inline-flex shrink-0 items-center gap-2.5" aria-label="Soundwave home"><span className="flex h-10 w-10 items-center justify-center rounded-[13px] bg-[#1b2030] text-white"><Headphones size={22} strokeWidth={2.4}/></span><span className="text-[23px] font-black tracking-[-.055em] text-[#1d2331]">sound<span className="text-indigo-600">wave.</span></span></Link>}

export default function StoreHeader({announcement=true}:{announcement?:boolean}) {
  const {user}=useAuth(); const navigate=useNavigate();
  const [query,setQuery]=useState('');const [mobileOpen,setMobileOpen]=useState(false);const [cartCount,setCartCount]=useState(0);
  useEffect(()=>{let cancelled=false;async function refresh(){if(!user){setCartCount(0);return;}try{const cart=await getCart(user.id);if(!cancelled)setCartCount(cart.total_quantity);}catch{if(!cancelled)setCartCount(0);}}void refresh();window.addEventListener('soundwave-cart-update',refresh);return()=>{cancelled=true;window.removeEventListener('soundwave-cart-update',refresh)};},[user]);
  const search=(event:FormEvent)=>{event.preventDefault();navigate(query.trim()?`/shop?q=${encodeURIComponent(query.trim())}`:'/shop');setMobileOpen(false)};
  return <div className="relative z-40 bg-white">
    {announcement&&<div className="bg-[#1c2432] px-4 py-2.5 text-center text-[11px] font-semibold tracking-[.14em] text-white/85 sm:text-xs">MADE FOR THE WAY YOU MAKE MUSIC <span className="mx-3 text-white/35">•</span> EXPLORE YOUR NEXT SOUND</div>}
    <header className="border-b border-[#ecece9]"><div className="mx-auto flex max-w-[1280px] items-center gap-4 px-5 py-4 sm:px-8 lg:gap-9 lg:py-5">
      <StoreBrand/>
      <form onSubmit={search} role="search" className="hidden min-w-0 max-w-[500px] flex-1 items-center gap-3 rounded-full border border-[#e8e7e3] bg-[#f8f8f6] px-4 py-2.5 transition focus-within:border-indigo-300 focus-within:bg-white md:flex"><Search size={18} className="shrink-0 text-slate-400"/><input value={query} onChange={e=>setQuery(e.target.value)} type="search" aria-label="Search instruments" placeholder="Search instruments, gear, and more..." className="min-w-0 flex-1 bg-transparent text-[13px] text-slate-800 outline-none placeholder:text-slate-400"/><button className="flex shrink-0 items-center gap-1 text-xs font-bold text-indigo-600" type="submit">Search<ArrowRight size={14}/></button></form>
      <nav className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-3" aria-label="Account shortcuts">
        {user?<Link to="/profile/notifications" aria-label="Notifications" className="header-icon"><Bell size={20}/></Link>:null}
        <Link to={user?'/profile':'/signin'} aria-label={user?'My account':'Sign in'} className="header-icon"><UserRound size={20}/></Link>
        <Link to={user?'/cart':'/signin?next=%2Fcart'} aria-label={`Shopping bag${cartCount?` with ${cartCount} items`:''}`} className="header-icon relative"><ShoppingBag size={20}/>{cartCount>0&&<span className="absolute -right-1 -top-1 rounded-full bg-indigo-600 px-1.5 py-0.5 text-[9px] font-extrabold leading-none text-white">{cartCount>99?'99+':cartCount}</span>}</Link>
        <button type="button" className="header-icon lg:hidden" aria-label={mobileOpen?'Close menu':'Open menu'} aria-expanded={mobileOpen} onClick={()=>setMobileOpen(x=>!x)}>{mobileOpen?<X size={21}/>:<Menu size={21}/>}</button>
      </nav>
    </div></header>
    <div className="hidden border-b border-[#eee] lg:block"><nav className="mx-auto flex max-w-[1280px] items-center gap-9 px-8 py-3 text-[13px] font-semibold text-[#575b65]" aria-label="Product categories">
      <NavLink end to="/" className={({isActive})=>isActive?'text-indigo-700':'hover:text-indigo-600'}>Home</NavLink>
      <NavLink to="/shop" className={({isActive})=>isActive?'text-indigo-700':'hover:text-indigo-600'}>All instruments</NavLink>
      {categories.map(c=><Link className="hover:text-indigo-600" to={`/shop?category=${encodeURIComponent(c.category)}`} key={c.category}>{c.name}</Link>)}
      <Link to={user?'/profile/purchases':'/signin'} className="ml-auto hover:text-indigo-600">My orders</Link>
    </nav></div>
    {mobileOpen&&<div className="absolute inset-x-0 top-full border-b border-slate-200 bg-white px-5 pb-6 shadow-xl lg:hidden"><form onSubmit={search} className="mt-4 flex items-center rounded-xl border border-slate-200 px-3"><Search size={17} className="text-slate-400"/><input value={query} onChange={e=>setQuery(e.target.value)} className="min-w-0 flex-1 p-3 text-sm outline-none" placeholder="Search instruments"/><button type="submit" aria-label="Submit search" className="text-indigo-600"><ArrowRight size={18}/></button></form><nav className="mt-3 flex flex-col text-sm font-semibold" aria-label="Mobile product categories"><Link onClick={()=>setMobileOpen(false)} to="/" className="py-3">Home</Link><Link onClick={()=>setMobileOpen(false)} to="/shop" className="py-3">All instruments</Link>{categories.map(c=><Link onClick={()=>setMobileOpen(false)} to={`/shop?category=${encodeURIComponent(c.category)}`} className="py-3" key={c.category}>{c.name}</Link>)}<Link to={user?'/profile':'/signin'} onClick={()=>setMobileOpen(false)} className="border-t border-slate-100 py-3">{user?'My profile':'Sign in / Register'}</Link></nav></div>}
  </div>;
}

export function StoreFooter(){return <footer className="mt-16 bg-[#1d2533] text-white"><div className="mx-auto grid max-w-[1280px] gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.5fr_1fr_1fr]"><div><div className="flex items-center gap-2.5 text-2xl font-black tracking-tight"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><Headphones size={22}/></span>sound<span className="-ml-2 text-[#acb5ff]">wave.</span></div><p className="mt-5 max-w-sm text-sm leading-7 text-white/55">Find your sound, from your first notes to your next big performance. A more personal way to discover instruments and gear.</p></div><div><h3 className="text-sm font-bold">Explore</h3><div className="mt-5 grid gap-3 text-sm text-white/60"><Link className="hover:text-white" to="/shop">All instruments</Link><Link className="hover:text-white" to="/shop?category=Piano">Pianos</Link><Link className="hover:text-white" to="/shop?category=Guitar">Guitars</Link><Link className="hover:text-white" to="/shop?category=Drums">Drums</Link></div></div><div><h3 className="text-sm font-bold">Your account</h3><div className="mt-5 grid gap-3 text-sm text-white/60"><Link className="hover:text-white" to="/signin">Sign in</Link><Link className="hover:text-white" to="/signup">Create account</Link><Link className="hover:text-white" to="/profile/purchases">My purchases</Link><Link className="hover:text-white" to="/profile/notifications">Notifications</Link></div></div></div><div className="border-t border-white/10 px-5 py-5 text-center text-xs text-white/40">© {new Date().getFullYear()} Soundwave. All rights reserved.</div></footer>}

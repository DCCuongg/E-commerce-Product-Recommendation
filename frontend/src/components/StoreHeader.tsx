import { useEffect, useState, type FormEvent } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { ArrowRight, Bell, Headphones, Search, ShoppingBag, UserRound } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getCart } from '../services/cart';
import { usePreferences } from '../context/PreferencesContext';
import PreferencesMenu from './PreferencesMenu';
const categories = [
  {name:'Pianos & Keys',category:'Piano'},
  {name:'Guitars',category:'Guitar'},
  {name:'Drums',category:'Drums'},
  {name:'Studio & Audio',category:'Audio'},
];
export function StoreBrand(){const {t}=usePreferences();return <Link to="/" className="inline-flex shrink-0 items-center gap-2.5" aria-label={t('Soundwave home')}><span className="flex h-10 w-10 items-center justify-center rounded-[13px] bg-[#1b2030] text-white dark:bg-indigo-600"><Headphones size={22} strokeWidth={2.4}/></span><span className="text-[23px] font-black tracking-[-.055em] text-[#1d2331] dark:text-slate-100">sound<span className="text-indigo-600 dark:text-indigo-400">wave.</span></span></Link>}
export default function StoreHeader({announcement=true}:{announcement?:boolean}) {
  const {user}=useAuth(); const navigate=useNavigate(); const {t}=usePreferences();
  const [query,setQuery]=useState('');const [cartCount,setCartCount]=useState(0);
  useEffect(()=>{let cancelled=false;async function refresh(){if(!user){setCartCount(0);return;}try{const cart=await getCart(user.id);if(!cancelled)setCartCount(cart.total_quantity);}catch{if(!cancelled)setCartCount(0);}}void refresh();window.addEventListener('soundwave-cart-update',refresh);return()=>{cancelled=true;window.removeEventListener('soundwave-cart-update',refresh)};},[user]);
  const search=(event:FormEvent)=>{event.preventDefault();navigate(query.trim()?`/shop?q=${encodeURIComponent(query.trim())}`:'/shop');};
  const shortcuts=[{to:'/',label:'Home'},{to:'/shop',label:'All instruments'},...categories.map(category=>({to:`/shop?category=${encodeURIComponent(category.category)}`,label:category.name})),{to:user?'/profile':'/signin',label:user?'My profile':'Sign in'},{to:user?'/profile/purchases':'/signin',label:'My orders'}];
  return <div className="relative z-40 bg-white dark:bg-slate-950">
    {announcement&&<div className="bg-[#1c2432] px-4 py-2.5 text-center text-[11px] font-semibold tracking-[.14em] text-white/85 sm:text-xs dark:bg-[#101728]">{t('MADE FOR THE WAY YOU MAKE MUSIC')} <span className="mx-3 text-white/35">•</span> {t('EXPLORE YOUR NEXT SOUND')}</div>}
    <header className="border-b border-[#ecece9] dark:border-slate-800"><div className="mx-auto flex max-w-[1280px] items-center gap-3 px-5 py-4 sm:px-8 lg:gap-9 lg:py-5">
      <StoreBrand/>
      <form onSubmit={search} role="search" className="hidden min-w-0 max-w-[500px] flex-1 items-center gap-3 rounded-full border border-[#e8e7e3] bg-[#f8f8f6] px-4 py-2.5 transition focus-within:border-indigo-300 focus-within:bg-white md:flex dark:border-slate-700 dark:bg-slate-900 dark:focus-within:bg-slate-800"><Search size={18} className="shrink-0 text-slate-400"/><input value={query} onChange={e=>setQuery(e.target.value)} type="search" aria-label={t('Search instruments')} placeholder={t('Search instruments, gear, and more...')} className="min-w-0 flex-1 bg-transparent text-[13px] text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100"/><button className="flex shrink-0 items-center gap-1 text-xs font-bold text-indigo-600 dark:text-indigo-400" type="submit">{t('Search')}<ArrowRight size={14}/></button></form>
      <nav className="ml-auto flex shrink-0 items-center gap-1 sm:gap-3" aria-label={t('Account shortcuts')}>
        {user?<Link to="/profile/notifications" aria-label={t('Notifications')} className="header-icon"><Bell size={20}/></Link>:null}
        <Link to={user?'/profile':'/signin'} aria-label={t(user?'My profile':'Sign in')} className="header-icon"><UserRound size={20}/></Link>
        <Link to={user?'/cart':'/signin?next=%2Fcart'} aria-label={`${t('Shopping bag')}${cartCount?` (${cartCount})`:''}`} className="header-icon relative"><ShoppingBag size={20}/>{cartCount>0&&<span className="absolute -right-1 -top-1 rounded-full bg-indigo-600 px-1.5 py-0.5 text-[9px] font-extrabold leading-none text-white">{cartCount>99?'99+':cartCount}</span>}</Link>
        <PreferencesMenu links={shortcuts}/>
      </nav>
    </div></header>
    <div className="hidden border-b border-[#eee] lg:block dark:border-slate-800"><nav className="mx-auto flex max-w-[1280px] items-center gap-9 px-8 py-3 text-[13px] font-semibold text-[#575b65] dark:text-slate-300" aria-label={t('Product categories')}>
      <NavLink end to="/" className={({isActive})=>isActive?'text-indigo-700 dark:text-indigo-400':'hover:text-indigo-600 dark:hover:text-indigo-400'}>{t('Home')}</NavLink>
      <NavLink to="/shop" className={({isActive})=>isActive?'text-indigo-700 dark:text-indigo-400':'hover:text-indigo-600 dark:hover:text-indigo-400'}>{t('All instruments')}</NavLink>
      {categories.map(c=><Link className="hover:text-indigo-600 dark:hover:text-indigo-400" to={`/shop?category=${encodeURIComponent(c.category)}`} key={c.category}>{t(c.name)}</Link>)}
      <Link to={user?'/profile/purchases':'/signin'} className="ml-auto hover:text-indigo-600 dark:hover:text-indigo-400">{t('My orders')}</Link>
    </nav></div>
    <div className="border-b border-[#eee] p-3 md:hidden dark:border-slate-800"><form onSubmit={search} className="mx-auto flex max-w-[600px] items-center rounded-xl border border-slate-200 px-3 dark:border-slate-700 dark:bg-slate-900"><Search size={17} className="text-slate-400"/><input value={query} onChange={e=>setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent p-3 text-sm text-slate-800 outline-none dark:text-slate-100" aria-label={t('Search instruments')} placeholder={t('Search instruments')}/><button type="submit" aria-label={t('Submit search')} className="text-indigo-600 dark:text-indigo-400"><ArrowRight size={18}/></button></form></div>
  </div>;
}
export function StoreFooter(){const {t}=usePreferences();return <footer className="mt-16 bg-[#1d2533] text-white dark:bg-[#0a1020]"><div className="mx-auto grid max-w-[1280px] gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.5fr_1fr_1fr]"><div><div className="flex items-center gap-2.5 text-2xl font-black tracking-tight"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><Headphones size={22}/></span>sound<span className="-ml-2 text-[#acb5ff]">wave.</span></div><p className="mt-5 max-w-sm text-sm leading-7 text-white/55">{t('Find your sound, from your first notes to your next big performance. A more personal way to discover instruments and gear.')}</p></div><div><h3 className="text-sm font-bold">{t('Explore')}</h3><div className="mt-5 grid gap-3 text-sm text-white/60"><Link className="hover:text-white" to="/shop">{t('All instruments')}</Link><Link className="hover:text-white" to="/shop?category=Piano">{t('Pianos')}</Link><Link className="hover:text-white" to="/shop?category=Guitar">{t('Guitars')}</Link><Link className="hover:text-white" to="/shop?category=Drums">{t('Drums')}</Link></div></div><div><h3 className="text-sm font-bold">{t('Your account')}</h3><div className="mt-5 grid gap-3 text-sm text-white/60"><Link className="hover:text-white" to="/signin">{t('Sign in')}</Link><Link className="hover:text-white" to="/signup">{t('Create account')}</Link><Link className="hover:text-white" to="/profile/purchases">{t('My purchases')}</Link><Link className="hover:text-white" to="/profile/notifications">{t('Notifications')}</Link></div></div></div><div className="border-t border-white/10 px-5 py-5 text-center text-xs text-white/40">© {new Date().getFullYear()} Soundwave. {t('All rights reserved.')}</div></footer>}

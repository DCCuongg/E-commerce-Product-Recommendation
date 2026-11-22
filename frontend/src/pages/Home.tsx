import { Tr, usePreferences } from '../context/PreferencesContext';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, AudioLines, CircleHelp, Guitar, Music2, Piano, SlidersHorizontal, Sparkles } from 'lucide-react';
import StoreHeader, { StoreFooter } from '../components/StoreHeader';
import ProductCard from '../components/ProductCard';
import { editorialImages, getProducts, getRecommendations, type Product } from '../services/catalog';
import { useAuth } from '../context/AuthContext';
import { DEMO_MODE } from '../services/auth';

const groups = [
  { title:'Pianos & keys', caption:'Find your rhythm in every key', category:'Piano', image:editorialImages.piano, icon:Piano },
  { title:'Guitars', caption:'Acoustic, electric & everything between', category:'Guitar', image:editorialImages.guitar, icon:Guitar },
  { title:'Drums & percussion', caption:'Make every beat count', category:'Drums', image:editorialImages.drums, icon:Music2 },
  { title:'Studio & audio', caption:'Shape the sound you imagine', category:'Audio', image:editorialImages.studio, icon:AudioLines },
];
const sections = [
 {label:'All instruments',value:''},
 {label:'Pianos',value:'Piano'},
 {label:'Guitars',value:'Guitar'},
 {label:'Drums',value:'Drums'},
];

export default function Home(){
 const {t}=usePreferences();
 const {user}=useAuth();
 const [category,setCategory]=useState('');
 const [items,setItems]=useState<Product[]>([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [retry,setRetry]=useState(0);
 const [recommended,setRecommended]=useState<Product[]>([]);
 useEffect(()=>{let cancel=false;setLoading(true);setError('');getProducts({page:1,page_size:8,category:category||undefined}).then(result=>{if(!cancel)setItems(result.items)}).catch(e=>{if(!cancel)setError(e instanceof Error?e.message:'Unable to load products.')}).finally(()=>{if(!cancel)setLoading(false)});return()=>{cancel=true}},[category,retry]);
 useEffect(()=>{if(!user){setRecommended([]);return;}let cancel=false;getRecommendations(user.id,4).then(data=>{if(!cancel)setRecommended(data)}).catch(()=>{if(!cancel)setRecommended([])});return()=>{cancel=true}},[user]);
 return <div className="min-h-screen bg-[#faf9f6] dark:bg-[#0b1322] text-[#24272e] dark:text-slate-100">
  <StoreHeader/>
  <main>
   <section className="mx-auto max-w-[1440px] px-4 pt-5 sm:px-6 sm:pt-8 lg:px-8">
    <div className="relative grid min-h-[530px] overflow-hidden rounded-[24px] bg-[#eae7e0] dark:bg-[#1a2637] lg:min-h-[580px] lg:grid-cols-[48%_52%] lg:rounded-[30px]">
      <div className="relative z-10 flex flex-col justify-center px-7 py-14 sm:px-12 lg:px-14 xl:px-20">
       <p className="mb-8 inline-flex w-fit items-center gap-2 border-b border-[#9da2a9] dark:border-slate-500 pb-2 text-[11px] font-extrabold uppercase tracking-[.24em] text-[#5a6371] dark:text-slate-300"><span className="h-1.5 w-1.5 rounded-full bg-indigo-600"/>{' '}<Tr text={"Curated for music makers"}/></p>
       <h1 className="max-w-xl font-['Georgia',serif] text-[49px] font-medium leading-[1.05] tracking-[-.055em] text-[#182130] dark:text-slate-50 sm:text-[68px] lg:text-[67px] xl:text-[82px]"><Tr text={"Make room"}/><br/><Tr text={"for"}/>{' '}<em className="font-normal text-indigo-600 dark:text-indigo-400"><Tr text={"music."}/></em></h1>
       <p className="mt-7 max-w-[390px] text-[15px] leading-8 text-[#5e6670] dark:text-slate-300"><Tr text={"From your very first notes to the sound you’ve always imagined. Discover instruments that move with you."}/></p>
       <div className="mt-9 flex flex-wrap items-center gap-4"><Link to="/shop" className="inline-flex items-center gap-3 rounded-full bg-[#222b3b] px-7 py-4 text-sm font-bold text-white transition hover:bg-indigo-600"><Tr text={"Explore instruments"}/>{' '}<ArrowUpRight size={18}/></Link><Link to="/shop?category=Piano" className="inline-flex items-center gap-2 rounded-full px-3 py-3 text-sm font-semibold text-[#303846] dark:text-slate-200 hover:text-indigo-700 dark:hover:text-indigo-300"><Tr text={"Shop pianos"}/>{' '}<ArrowRight size={17}/></Link></div>
       <div className="mt-12 flex items-center gap-4 border-t border-[#d1d0cc] dark:border-slate-700 pt-5 text-[12px] font-medium text-[#70767f] dark:text-slate-300"><AudioLines size={21} className="text-indigo-600 dark:text-indigo-400"/><span><Tr text={"Find your instrument. Find your voice."}/></span></div>
      </div>
      <div className="relative min-h-[310px] overflow-hidden bg-[#c8c5bb] dark:bg-slate-800 lg:min-h-full">
       <img src={editorialImages.hero} onError={e=>{e.currentTarget.onerror=null;e.currentTarget.src=editorialImages.studio}} alt={t("Piano and keyboard in a creative music setting")} className="absolute inset-0 h-full w-full object-cover object-center"/>
       <div className="absolute inset-0 bg-gradient-to-t from-[#121827]/65 via-[#121827]/10 to-transparent"/>
       <div className="absolute bottom-7 left-7 right-7 flex items-end justify-between gap-4 text-white sm:bottom-10 sm:left-10"><div><p className="text-[10px] font-bold uppercase tracking-[.22em] text-white/65"><Tr text={"The piano edit"}/></p><p className="mt-2 font-['Georgia',serif] text-2xl sm:text-[30px]"><Tr text={"Find your first note."}/></p></div><Link to="/shop?category=Piano" aria-label={t("Shop pianos")} className="grid h-12 w-12 shrink-0 place-items-center rounded-full border border-white/50 text-white transition hover:bg-white dark:hover:bg-slate-900 hover:text-slate-900 dark:hover:text-slate-100"><ArrowUpRight size={20}/></Link></div>
      </div>
    </div>
   </section>

   <section className="mx-auto grid max-w-[1280px] gap-5 px-5 py-8 sm:grid-cols-3 sm:px-8 sm:py-10">
     <div className="flex items-start gap-3"><div className="mt-0.5 rounded-xl bg-[#edebf5] dark:bg-indigo-500/10 p-2.5 text-indigo-600 dark:text-indigo-400"><SlidersHorizontal size={19}/></div><div><h2 className="text-sm font-bold"><Tr text={"Explore with confidence"}/></h2><p className="mt-1 text-xs leading-6 text-slate-500 dark:text-slate-400"><Tr text={"Browse by instrument and find the right fit."}/></p></div></div>
     <div className="flex items-start gap-3"><div className="mt-0.5 rounded-xl bg-[#edebf5] dark:bg-indigo-500/10 p-2.5 text-indigo-600 dark:text-indigo-400"><Music2 size={19}/></div><div><h2 className="text-sm font-bold"><Tr text={"For every stage"}/></h2><p className="mt-1 text-xs leading-6 text-slate-500 dark:text-slate-400"><Tr text={"From practice rooms to performance spaces."}/></p></div></div>
     <div className="flex items-start gap-3"><div className="mt-0.5 rounded-xl bg-[#edebf5] dark:bg-indigo-500/10 p-2.5 text-indigo-600 dark:text-indigo-400"><Sparkles size={19}/></div><div><h2 className="text-sm font-bold"><Tr text={"Made personal"}/></h2><p className="mt-1 text-xs leading-6 text-slate-500 dark:text-slate-400"><Tr text={"Discover recommendations as you explore."}/></p></div></div>
   </section>

   <section className="mx-auto max-w-[1280px] px-5 pb-16 pt-9 sm:px-8 sm:pb-20" aria-labelledby="categories-heading">
    <div className="mb-8 flex flex-wrap items-end justify-between gap-5"><div><p className="text-[11px] font-extrabold uppercase tracking-[.22em] text-indigo-600 dark:text-indigo-400"><Tr text={"The collection"}/></p><h2 id="categories-heading" className="mt-2 font-['Georgia',serif] text-[36px] tracking-[-.04em] text-[#1e2632] dark:text-slate-100 sm:text-[46px]"><Tr text={"Explore your sound."}/></h2></div><Link to="/shop" className="inline-flex items-center gap-2 border-b border-[#9ba0aa] dark:border-slate-500 pb-1 text-sm font-bold text-[#3a4351] dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400"><Tr text={"View all instruments"}/>{' '}<ArrowUpRight size={17}/></Link></div>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{groups.map(g=><Link key={g.title} to={`/shop?category=${g.category}`} className="group relative block aspect-[.95] overflow-hidden rounded-[20px] bg-[#ebe7df] dark:bg-slate-800 sm:aspect-[.92]"><img src={g.image} onError={e=>{e.currentTarget.onerror=null;e.currentTarget.src='/assets/instrument-placeholder.svg'}} loading="lazy" alt={t(g.title)} className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.07]"/><div className="absolute inset-0 bg-gradient-to-t from-[#11151f]/85 via-[#11151f]/10 to-transparent"/><div className="absolute inset-x-5 bottom-5 text-white"><span className="mb-4 inline-flex rounded-full border border-white/50 p-2"><g.icon size={20}/></span><h3 className="text-[21px] font-bold tracking-tight">{t(g.title)}</h3><div className="mt-1 flex items-center justify-between gap-2"><p className="text-xs text-white/75">{t(g.caption)}</p><ArrowUpRight size={19} className="shrink-0"/></div></div></Link>)}</div>
   </section>

   <section className="border-y border-[#eceae6] dark:border-slate-700 bg-white dark:bg-slate-900 py-16 sm:py-20" aria-labelledby="featured-heading"><div className="mx-auto max-w-[1280px] px-5 sm:px-8">
    <div className="mb-7 flex flex-wrap items-end justify-between gap-5"><div><p className="text-[11px] font-extrabold uppercase tracking-[.22em] text-indigo-600 dark:text-indigo-400"><Tr text={"Discover the collection"}/></p><h2 id="featured-heading" className="mt-2 font-['Georgia',serif] text-[34px] tracking-[-.04em] sm:text-[44px]"><Tr text={"Instruments to explore."}/></h2><p className="mt-2 text-sm text-slate-500 dark:text-slate-400"><Tr text={"Thoughtful choices for every kind of player."}/></p></div><Link className="inline-flex items-center gap-2 text-sm font-bold text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300" to={category?`/shop?category=${category}`:'/shop'}><Tr text={"Browse all"}/>{' '}<ArrowRight size={17}/></Link></div>
    <div className="mb-7 flex flex-wrap gap-2" role="group" aria-label={t("Filter featured products")}>{sections.map(s=><button type="button" key={s.label} onClick={()=>setCategory(s.value)} aria-pressed={category===s.value} className={`rounded-full px-5 py-2.5 text-xs font-bold transition ${category===s.value?'bg-[#202a3a] text-white':'border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:border-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300'}`}>{t(s.label)}</button>)}</div>
    {loading?<div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{Array.from({length:4},(_,i)=><div key={i} className="h-[380px] animate-pulse rounded-2xl bg-[#f1f0ed] dark:bg-slate-800"/>)}</div>:error?<div role="alert" className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-[#faf9f6] dark:bg-[#0b1322] p-9 text-center"><p className="font-semibold"><Tr text={"We couldn't load the instruments."}/></p><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{t(error)}</p><button type="button" onClick={()=>setRetry(x=>x+1)} className="mt-4 rounded-full bg-slate-900 px-5 py-2 text-sm font-bold text-white"><Tr text={"Try again"}/></button></div>:items.length?<div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{items.map(p=><ProductCard key={p.id} product={p}/>)}</div>:<p className="rounded-2xl bg-[#faf9f6] dark:bg-[#0b1322] p-10 text-center text-slate-500 dark:text-slate-400"><Tr text={"No products found in this category."}/>{' '}<Link className="font-bold text-indigo-600 dark:text-indigo-400" to="/shop"><Tr text={"Browse all instruments"}/></Link>.</p>}
   </div></section>

   <section className="mx-auto max-w-[1280px] px-5 py-16 sm:px-8 sm:py-20" aria-labelledby="story-heading"><div className="grid overflow-hidden rounded-[25px] bg-[#263348] lg:grid-cols-2"><div className="relative min-h-[330px] bg-[#3e4b60]"><img src={editorialImages.studio} alt={t("Music recording workspace")} loading="lazy" className="h-full w-full object-cover" onError={e=>{e.currentTarget.onerror=null;e.currentTarget.src='/assets/instrument-placeholder.svg'}}/></div><div className="flex flex-col justify-center px-8 py-14 text-white sm:px-14 lg:py-16"><p className="text-[11px] font-extrabold uppercase tracking-[.23em] text-[#b5bcff]"><Tr text={"A sound of your own"}/></p><h2 id="story-heading" className="mt-5 max-w-lg font-['Georgia',serif] text-[35px] leading-tight tracking-[-.04em] sm:text-[47px]"><Tr text={"Every great sound starts somewhere."}/></h2><p className="mt-6 max-w-md text-sm leading-8 text-white/70"><Tr text={"The right instrument makes every practice session feel like possibility. Explore our collection and begin your next chapter."}/></p><Link className="mt-8 inline-flex w-fit items-center gap-3 rounded-full bg-white dark:bg-slate-900 px-6 py-3.5 text-sm font-bold text-[#253043] dark:text-slate-100 hover:bg-indigo-100 dark:hover:bg-indigo-500/20" to="/shop"><Tr text={"Find your instrument"}/>{' '}<ArrowUpRight size={18}/></Link></div></div></section>

   {user&&recommended.length>0&&<section className="mx-auto max-w-[1280px] px-5 pb-16 sm:px-8 sm:pb-20"><div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="text-[11px] font-extrabold uppercase tracking-[.22em] text-indigo-600 dark:text-indigo-400"><Tr text={"For your next discovery"}/></p><h2 className="mt-2 font-['Georgia',serif] text-[33px] tracking-[-.04em]">{t(DEMO_MODE?'More to explore.':'Selected for you.')}</h2></div><Link to="/shop" className="text-sm font-bold text-indigo-600 dark:text-indigo-400"><Tr text={"Explore more"}/>{' '}<ArrowRight className="inline" size={16}/></Link></div><div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{recommended.map(p=><ProductCard key={p.id} product={p}/>)}</div></section>}

   <section className="mx-auto max-w-[1280px] px-5 pb-4 sm:px-8"><div className="grid gap-6 rounded-[22px] border border-[#e8e6e2] dark:border-slate-700 bg-white dark:bg-slate-900 p-8 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:p-10"><span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-[#f0efff] dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400"><CircleHelp size={26}/></span><div><h2 className="text-xl font-bold tracking-tight"><Tr text={"Not sure where to begin?"}/></h2><p className="mt-2 max-w-lg text-sm leading-7 text-slate-500 dark:text-slate-400"><Tr text={"Start with a favorite instrument, then explore what suits your playing style and budget."}/></p></div><Link className="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 dark:border-slate-700 px-6 py-3 text-sm font-bold hover:border-indigo-300 dark:hover:border-indigo-500/40 hover:text-indigo-600 dark:hover:text-indigo-400" to="/shop"><Tr text={"Browse the shop"}/>{' '}<ArrowRight size={17}/></Link></div></section>
  </main>
  <StoreFooter/>
 </div>;
}

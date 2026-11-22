import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Globe2, Menu, Moon, Sun, X } from 'lucide-react';
import { usePreferences } from '../context/PreferencesContext';

type MenuLink={to:string; label:string};

/** Accessible settings dropdown shared by the storefront and authentication pages. */
export default function PreferencesMenu({links=[]}:{links?:MenuLink[]}){
  const {theme,setTheme,language,setLanguage,t}=usePreferences();
  const [open,setOpen]=useState(false);
  const host=useRef<HTMLDivElement>(null);
  const trigger=useRef<HTMLButtonElement>(null);
  const panelId=useId();
  useEffect(()=>{
    if(!open)return;
    function outside(event:PointerEvent){if(!host.current?.contains(event.target as Node))setOpen(false)}
    function keyboard(event:KeyboardEvent){if(event.key==='Escape'){setOpen(false);trigger.current?.focus()}}
    document.addEventListener('pointerdown',outside);
    document.addEventListener('keydown',keyboard);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',keyboard)};
  },[open]);
  return <div ref={host} className="relative shrink-0">
    <button ref={trigger} type="button" className="header-icon border border-transparent dark:border-slate-700" aria-controls={panelId} aria-expanded={open} aria-haspopup="menu" aria-label={t(open?'Close settings menu':'Open settings menu')} onClick={()=>setOpen(current=>!current)}>
      {open?<X size={21}/>:<Menu size={21}/>}
    </button>
    {open&&<div id={panelId} role="menu" aria-label={t('Appearance & language')} className="absolute right-0 top-[calc(100%+12px)] z-[100] w-[min(320px,calc(100vw-24px))] overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 text-slate-900 shadow-[0_24px_60px_rgba(15,23,42,.18)] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:shadow-black/50">
      <div className="px-3 pb-2 pt-3"><p className="text-[11px] font-extrabold uppercase tracking-[.18em] text-slate-500 dark:text-slate-400">{t('Display settings')}</p></div>
      <label className="flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-3 transition hover:bg-slate-50 dark:hover:bg-slate-800">
        <span className="flex items-center gap-3"><span className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-400/10 dark:text-indigo-300">{theme==='dark'?<Moon size={18}/>:<Sun size={18}/>}</span><span className="text-sm font-semibold">{t('Dark mode')}</span></span>
        <span className="relative inline-flex shrink-0 items-center"><input type="checkbox" role="switch" checked={theme==='dark'} onChange={e=>setTheme(e.target.checked?'dark':'light')} className="peer sr-only" aria-label={t('Dark mode')}/><span aria-hidden="true" className="h-7 w-12 rounded-full bg-slate-300 transition peer-checked:bg-indigo-600 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-indigo-500 dark:bg-slate-600 dark:peer-checked:bg-indigo-500"/><span aria-hidden="true" className="pointer-events-none absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow-sm transition peer-checked:translate-x-5"/></span>
      </label>
      <button type="button" role="menuitem" className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800" onClick={()=>{setLanguage(language==='en'?'vi':'en');setOpen(false)}} aria-label={t(language==='en'?'Switch to Vietnamese':'Switch to English')}>
        <span className="flex items-center gap-3"><span className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-400/10 dark:text-indigo-300"><Globe2 size={18}/></span><span><span className="block text-sm font-semibold">{language==='en'?'Language: Vietnamese':'Ngôn ngữ: Tiếng Anh'}</span><span className="block text-[11px] text-slate-500 dark:text-slate-400">{language==='en'?'Vietnamese':'English'}</span></span></span>
        <Check size={17} className="text-indigo-500"/>
      </button>
      {links.length>0&&<div className="mt-1 border-t border-slate-100 px-2 pb-2 pt-3 dark:border-slate-700"><p className="px-2 pb-2 text-[11px] font-bold uppercase tracking-[.15em] text-slate-500 dark:text-slate-400">{t('Quick links')}</p><nav aria-label={t('Mobile product categories')} className="grid gap-1">{links.map(item=><Link key={`${item.to}-${item.label}`} to={item.to} onClick={()=>setOpen(false)} className="rounded-lg px-3 py-2.5 text-sm font-semibold text-slate-700 hover:bg-indigo-50 hover:text-indigo-600 dark:text-slate-200 dark:hover:bg-indigo-500/15 dark:hover:text-indigo-300">{t(item.label)}</Link>)}</nav></div>}
    </div>}
  </div>;
}

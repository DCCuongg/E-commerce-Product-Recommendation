import { Tr, usePreferences } from '../context/PreferencesContext';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Bell, LogOut, Menu, Package, Pencil, UserRound, X } from 'lucide-react';
import { useState } from 'react';
import StoreHeader, { StoreFooter } from './StoreHeader';
import { useAuth } from '../context/AuthContext';
const menu=[{to:'/profile',label:'My profile',icon:UserRound,end:true},{to:'/profile/edit',label:'Edit profile',icon:Pencil},{to:'/profile/purchases',label:'My purchases',icon:Package},{to:'/profile/notifications',label:'Notifications',icon:Bell}];
export default function AccountLayout(){
 const {t}=usePreferences();
 const {user,logout}=useAuth();const navigate=useNavigate();const [mobileOpen,setMobileOpen]=useState(false);
 const signout=()=>{logout();navigate('/signin',{replace:true})};
 return <div className="min-h-screen bg-[#f8f9fb] dark:bg-[#0b1322] text-slate-900 dark:text-slate-100"><StoreHeader announcement={false}/>
  <div className="mx-auto max-w-[1280px] px-5 pb-6 pt-8 sm:px-8"><div className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow"><Tr text={"YOUR SPACE"}/></p><h1 className="mt-1 font-['Georgia',serif] text-3xl tracking-tight text-[#273246] dark:text-slate-100 sm:text-[38px]"><Tr text={"Account center"}/></h1></div><button type="button" onClick={()=>setMobileOpen(v=>!v)} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3 text-sm font-semibold text-slate-600 dark:text-slate-300 lg:hidden">{mobileOpen?<X size={19}/>:<Menu size={19}/>} Account menu</button></div>
   <div className="grid items-start gap-7 lg:grid-cols-[260px_minmax(0,1fr)]"><aside className={`${mobileOpen?'block':'hidden'} lg:block`}><div className="overflow-hidden rounded-2xl border border-[#e9eaf0] dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm"><div className="flex items-center gap-3 border-b border-slate-100 dark:border-slate-800 p-5"><div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-indigo-100 dark:bg-indigo-500/20 text-lg font-extrabold uppercase text-indigo-700 dark:text-indigo-300">{user?.username.slice(0,2)}</div><div className="min-w-0"><p className="truncate text-sm font-bold">{user?.username}</p><p className="truncate text-xs text-slate-400 dark:text-slate-400"><Tr text={"Personal account"}/></p></div></div><nav className="space-y-1 p-3" aria-label={t("Account menu")}>{menu.map(({to,label,icon:Icon,end})=><NavLink key={to} end={end} to={to} onClick={()=>setMobileOpen(false)} className={({isActive})=>`nav-link ${isActive?'nav-link-active':''}`}><Icon size={19}/>{t(label)}</NavLink>)}<div className="my-3 border-t border-slate-100 dark:border-slate-800"/><button type="button" onClick={signout} className="nav-link w-full text-left text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10"><LogOut size={19}/>{' '}<Tr text={"Sign out"}/></button></nav></div></aside><main className="min-w-0 space-y-6"><Outlet/></main></div>
  </div><StoreFooter/></div>;
}

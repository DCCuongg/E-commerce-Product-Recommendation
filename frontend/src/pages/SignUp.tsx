import { Tr, usePreferences } from '../context/PreferencesContext';
import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ArrowRight, Eye, EyeOff, Check, X } from 'lucide-react';
import { AuthLayout, FormField } from '../components/UI';
import { useAuth } from '../context/AuthContext';

export default function SignUp() {
 const {t}=usePreferences();
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState({ username: '', email: '', password: '', confirm: '' });
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/profile" replace/>;
  const change = (key: keyof typeof values, value: string) => setValues(v => ({ ...v, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    if (values.username.trim().length < 3) { setError('Username must be at least 3 characters.'); return; }
    if (!/^(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}$/.test(values.password)) { setError('Password requires at least 8 characters, one number, and one special character.'); return; }
    if (values.password !== values.confirm) { setError('Passwords do not match.'); return; }
    setBusy(true);
    try { await register({ username: values.username.trim(), email: values.email.trim(), password: values.password }); navigate('/profile', { replace: true }); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to register.'); }
    finally { setBusy(false); }
  }
  return <AuthLayout heading="Create an account" subheading="Join Soundwave and discover gear made for you.">
    <form className="space-y-4" onSubmit={submit}>
      <FormField id="username" label="Username" placeholder="Choose a username" autoComplete="username" minLength={3} maxLength={50} required value={values.username} onChange={e => change('username', e.target.value)}/>
      <FormField id="email" label="Email address" type="email" placeholder="you@example.com" autoComplete="email" maxLength={100} required value={values.email} onChange={e => change('email', e.target.value)}/>
      <div className="relative"><FormField id="password" label="Password" type={visible ? 'text' : 'password'} placeholder="8+ characters, number & symbol" autoComplete="new-password" minLength={8} maxLength={128} required value={values.password} onChange={e => change('password', e.target.value)}/><button type="button" aria-label={t(visible ? 'Hide passwords' : 'Show passwords')} className="absolute bottom-3 right-3 text-slate-400 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400" onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={19}/> : <Eye size={19}/>}</button></div>
      <div className="grid gap-2 sm:grid-cols-3" aria-label={t("Password requirements")}>{([['8+ characters',values.password.length>=8],['One number',/[0-9]/.test(values.password)],['Special character',/[^A-Za-z0-9\s]/.test(values.password)]] as const).map(([label,ok])=><span key={label} className={`flex items-center gap-1.5 text-xs font-semibold ${ok?'text-emerald-700 dark:text-emerald-300':'text-slate-500 dark:text-slate-400'}`}>{ok?<Check size={14}/>:<X size={14}/>} {t(label)}</span>)}</div>
      <FormField id="confirm" label="Confirm password" type={visible ? 'text' : 'password'} placeholder="Re-enter your password" autoComplete="new-password" minLength={8} required value={values.confirm} onChange={e => change('confirm', e.target.value)}/>
      {error && <p role="alert" className="rounded-lg bg-red-50 dark:bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">{t(error)}</p>}
      <button className="primary-button w-full" disabled={busy} type="submit">{t(busy ? 'Creating account…' : 'Create account')}<ArrowRight size={18}/></button>
    </form>
    <p className="mt-7 text-center text-sm text-slate-500 dark:text-slate-400"><Tr text={"Already have an account?"}/>{' '}<Link to="/signin" className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"><Tr text={"Sign in"}/></Link></p>
  </AuthLayout>;
}

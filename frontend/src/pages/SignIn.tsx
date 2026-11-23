import { Tr, usePreferences } from '../context/PreferencesContext';
import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { AuthLayout, FormField } from '../components/UI';
import { useAuth } from '../context/AuthContext';

export default function SignIn() {
 const {t}=usePreferences();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requested = searchParams.get('next');
  const returnTo = requested && requested.startsWith('/') && !requested.startsWith('//') ? requested : '/profile';
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/profile" replace/>;
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true);
    try { await login({ username: username.trim(), password }); navigate(returnTo, { replace: true }); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to sign in.'); }
    finally { setBusy(false); }
  }
  return <AuthLayout heading="Welcome back" subheading="Sign in to your account to continue your journey.">
    <form onSubmit={submit} className="space-y-5">
      <FormField id="username" label="Username or email" autoComplete="username" placeholder="Enter your username or email" required value={username} onChange={e => setUsername(e.target.value)}/>
      <div><div className="relative"><FormField id="password" label="Password" autoComplete="current-password" placeholder="Enter your password" type={visible ? 'text' : 'password'} required value={password} onChange={e => setPassword(e.target.value)}/><button type="button" className="absolute bottom-3 right-3 text-slate-400 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400" aria-label={t(visible ? 'Hide password' : 'Show password')} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={19}/> : <Eye size={19}/>}</button></div></div>
      {error && <p role="alert" className="rounded-lg bg-red-50 dark:bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">{t(error)}</p>}
      <button className="primary-button w-full" disabled={busy} type="submit">{t(busy ? 'Signing in…' : 'Sign in')}<ArrowRight size={18}/></button>
    </form>
    <p className="mt-8 text-center text-sm text-slate-500 dark:text-slate-400"><Tr text={"Don't have an account?"}/>{' '}<Link className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline" to="/signup"><Tr text={"Create an account"}/></Link></p>
  </AuthLayout>;
}

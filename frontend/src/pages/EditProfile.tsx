import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save } from 'lucide-react';
import { BackLink, FormField } from '../components/UI';
import { useAuth } from '../context/AuthContext';
import { DEMO_MODE } from '../services/auth';

export default function EditProfile() {
  const { user, updateProfile } = useAuth();
  const navigate = useNavigate();
  const [username,setUsername] = useState(user?.username || '');
  const [email,setEmail] = useState(user?.email || '');
  const [error,setError] = useState('');
  if (!user) return null;
  const canEdit = DEMO_MODE && user.id !== 'DEMO_001';
  function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    if (!canEdit) return;
    try { updateProfile({ username: username.trim(), email: email.trim().toLowerCase() }); navigate('/profile'); }
    catch(e) { setError(e instanceof Error ? e.message : 'Unable to update profile.'); }
  }
  return <><div><BackLink/><h1 className="mt-4 text-3xl font-bold tracking-tight text-slate-900">Edit profile</h1><p className="mt-2 text-slate-500">Update your account details.</p></div>
    {!canEdit && <p className="text-sm text-slate-500">{DEMO_MODE ? 'This shared preview account is read-only.' : 'Profile changes are not yet supported by the account service.'}</p>}
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"><h2 className="text-lg font-bold text-slate-900">Basic information</h2><p className="mt-1 text-sm text-slate-500">These fields are supported by the current user database.</p>
      <form onSubmit={submit} className="mt-7 max-w-xl space-y-6"><FormField label="Username" id="edit-username" required minLength={3} maxLength={50} disabled={!canEdit} autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/><FormField label="Email address" id="edit-email" required type="email" maxLength={100} disabled={!canEdit} autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/><div><label className="mb-2 block text-sm font-semibold text-slate-700">User ID</label><div className="input-base bg-slate-50 text-slate-400">{user.id}</div><p className="mt-2 text-xs text-slate-400">Your unique identifier cannot be changed.</p></div>
        {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-6"><button className="primary-button" disabled={!canEdit} type="submit"><Save size={18}/> Save changes</button><button className="secondary-button" type="button" onClick={()=>navigate('/profile')}>Cancel</button></div>
      </form>
    </section></>;
}

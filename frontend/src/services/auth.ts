import type { AuthResponse, Credentials, Registration, User } from '../types';

export const DEMO_MODE = import.meta.env.DEV && import.meta.env.VITE_DEMO_MODE === 'true';
const API_URL = (import.meta.env.VITE_AUTH_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const DEMO_USERS_KEY = 'ecommerce-demo-users';
const demoSeed: User = { id: 'DEMO_001', username: 'alexmusic', email: 'alex@example.com', role: 'customer', created_at: '2026-01-15T09:30:00Z' };

type DemoAccount = { user: User; password: string };
function readAccounts(): DemoAccount[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(DEMO_USERS_KEY) || '[]') as DemoAccount[];
    return Array.isArray(parsed) ? parsed : [];
  } catch { return []; }
}
function demoAccounts(): DemoAccount[] {
  return [{ user: demoSeed, password: 'Demo123!' }, ...readAccounts()];
}
function fakeToken(user: User): AuthResponse {
  return { access_token: `demo-token-${user.id}`, token_type: 'bearer', expires_in: 86400, user };
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    });
  } catch {
    throw new Error('Cannot reach the authentication service. Check VITE_AUTH_API_URL and whether the backend is running.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const details = typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`;
    throw new Error(details);
  }
  return response.json() as Promise<T>;
}
export async function signIn(credentials: Credentials): Promise<AuthResponse> {
  if (!DEMO_MODE) return request('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(credentials) });
  await new Promise(resolve => setTimeout(resolve, 350));
  const found = demoAccounts().find(a =>
    (a.user.username.toLowerCase() === credentials.username.trim().toLowerCase() || a.user.email.toLowerCase() === credentials.username.trim().toLowerCase()) && a.password === credentials.password
  );
  if (!found) throw new Error('Invalid username/email or password. Try the demo account.');
  return fakeToken(found.user);
}
export async function signUp(data: Registration): Promise<AuthResponse> {
  if (!/^(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}$/.test(data.password)) throw new Error('Password must have at least 8 characters, one number, and one special character.');
  if (!DEMO_MODE) return request('/api/v1/auth/register', { method: 'POST', body: JSON.stringify({ username: data.username, email: data.email, password: data.password }) });
  await new Promise(resolve => setTimeout(resolve, 350));
  const accounts = demoAccounts();
  if (accounts.some(a => a.user.username.toLowerCase() === data.username.trim().toLowerCase() || a.user.email.toLowerCase() === data.email.trim().toLowerCase())) {
    throw new Error('Username or email already exists.');
  }
  const user: User = { id: `DEMO_${Date.now()}`, username: data.username.trim(), email: data.email.trim().toLowerCase(), role: 'customer', created_at: new Date().toISOString() };
  localStorage.setItem(DEMO_USERS_KEY, JSON.stringify([...readAccounts(), { user, password: data.password }]));
  return fakeToken(user);
}
export async function getMe(token: string): Promise<User> {
  if (!DEMO_MODE) return request('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } });
  const id = token.replace(/^demo-token-/, '');
  const found = demoAccounts().find(a => a.user.id === id);
  if (!found) throw new Error('Session expired. Please sign in again.');
  return found.user;
}
export function updateDemoUser(id: string, changes: Pick<User, 'username'|'email'>): User {
  if (!DEMO_MODE) throw new Error('The backend does not provide a profile-update endpoint yet.');
  const accounts = readAccounts();
  if (id === demoSeed.id) throw new Error('The shared demo account cannot be modified. Sign up for a new demo account to test editing.');
  if (demoAccounts().some(a => a.user.id !== id && (a.user.username.toLowerCase() === changes.username.toLowerCase() || a.user.email.toLowerCase() === changes.email.toLowerCase()))) {
    throw new Error('Username or email already exists.');
  }
  const index = accounts.findIndex(a => a.user.id === id);
  if (index < 0) throw new Error('Demo account not found.');
  accounts[index].user = { ...accounts[index].user, ...changes };
  localStorage.setItem(DEMO_USERS_KEY, JSON.stringify(accounts));
  return accounts[index].user;
}

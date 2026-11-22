import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Credentials, Registration, User } from '../types';
import { getMe, signIn, signUp, updateDemoUser } from '../services/auth';

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (data: Credentials) => Promise<void>;
  register: (data: Registration) => Promise<void>;
  logout: () => void;
  updateProfile: (changes: Pick<User, 'username'|'email'>) => void;
};
const AuthContext = createContext<AuthContextValue | null>(null);
export const TOKEN_KEY = 'ecommerce-session-token';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) { setLoading(false); return; }
    getMe(token).then(setUser).catch(() => sessionStorage.removeItem(TOKEN_KEY)).finally(() => setLoading(false));
  }, []);
  const save = useCallback((token: string, newUser: User) => {
    sessionStorage.setItem(TOKEN_KEY, token);
    setUser(newUser);
  }, []);
  const login = useCallback(async (data: Credentials) => { const result = await signIn(data); save(result.access_token, result.user); }, [save]);
  const register = useCallback(async (data: Registration) => { const result = await signUp(data); save(result.access_token, result.user); }, [save]);
  const logout = useCallback(() => { sessionStorage.removeItem(TOKEN_KEY); setUser(null); }, []);
  const updateProfile = useCallback((changes: Pick<User, 'username'|'email'>) => { if (!user) return; setUser(updateDemoUser(user.id, changes)); }, [user]);
  return <AuthContext.Provider value={{ user, loading, login, register, logout, updateProfile }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

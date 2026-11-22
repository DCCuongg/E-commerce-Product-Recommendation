export type User = {
  id: string;
  username: string;
  email: string;
  role: string;
  created_at?: string | null;
};
export type AuthResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
};
export type Credentials = { username: string; password: string };
export type Registration = Credentials & { email: string };

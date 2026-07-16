import { create } from 'zustand';
import api, { getAccessToken, setTokens, clearTokens } from './api';

export interface AuthState {
  /* ── State ────────────────────────────────────────────────────── */
  token: string | null;
  user: { id: number; email: string; full_name: string } | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  /* ── Actions ──────────────────────────────────────────────────── */
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, full_name: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  /* ── Initial state ────────────────────────────────────────────── */
  token: getAccessToken(),
  user: null,
  isAuthenticated: !!getAccessToken(),
  isLoading: false,
  error: null,

  /* ── Login ────────────────────────────────────────────────────── */
  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await api.post('/auth/login', { email, password });
      setTokens(data.access_token, data.refresh_token);
      set({ token: data.access_token, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      const message = err.normalizedMessage || 'Login failed';
      set({ error: message, isLoading: false });
      throw new Error(message);
    }
  },

  /* ── Register ─────────────────────────────────────────────────── */
  register: async (email: string, password: string, full_name: string) => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await api.post('/auth/register', { email, password, full_name });
      // After registration, log the user in automatically
      await api.post('/auth/login', { email, password }).then((res) => {
        setTokens(res.data.access_token, res.data.refresh_token);
        set({ token: res.data.access_token, isAuthenticated: true, isLoading: false, user: data });
      });
    } catch (err: any) {
      const message = err.normalizedMessage || 'Registration failed';
      set({ error: message, isLoading: false });
      throw new Error(message);
    }
  },

  /* ── Logout ───────────────────────────────────────────────────── */
  logout: () => {
    clearTokens();
    set({ token: null, user: null, isAuthenticated: false, error: null });
  },

  /* ── Clear error ──────────────────────────────────────────────── */
  clearError: () => set({ error: null }),
}));

// ── Listen for auth expiry events from the API interceptor ──────────
// This avoids a circular dependency (api.ts → authStore.ts → api.ts)
// by using a custom DOM event instead of a direct import.
if (typeof window !== 'undefined') {
  window.addEventListener('auth:expired', () => {
    useAuthStore.getState().logout();
  });
}

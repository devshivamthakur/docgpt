import { create } from 'zustand';
import api from './api';

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
  token: localStorage.getItem('docgpt-token'),
  user: null,
  isAuthenticated: !!localStorage.getItem('docgpt-token'),
  isLoading: false,
  error: null,

  /* ── Login ────────────────────────────────────────────────────── */
  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await api.post('/auth/login', { email, password });
      const token: string = data.access_token;
      localStorage.setItem('docgpt-token', token);
      localStorage.setItem('refresh-token', data.refresh_token);
      set({ token, isAuthenticated: true, isLoading: false });
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
        const token: string = res.data.access_token;
        localStorage.setItem('docgpt-token', token);
        localStorage.setItem('refresh-token', res.data.refresh_token);
        set({ token, isAuthenticated: true, isLoading: false, user: data });
      });
    } catch (err: any) {
      const message = err.normalizedMessage || 'Registration failed';
      set({ error: message, isLoading: false });
      throw new Error(message);
    }
  },

  /* ── Logout ───────────────────────────────────────────────────── */
  logout: () => {
    localStorage.removeItem('docgpt-token');
    localStorage.removeItem('refresh-token');
    set({ token: null, user: null, isAuthenticated: false, error: null });
  },

  /* ── Clear error ──────────────────────────────────────────────── */
  clearError: () => set({ error: null }),
}));

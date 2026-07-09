import axios, { AxiosError } from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor: attach auth token ─────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('docgpt-token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: normalize errors ─────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ message?: string }>) => {
    // Extract the message from the backend's consistent error response
    const message =
      error.response?.data?.message ||
      (error.response?.status === 401 ? 'Session expired. Please log in again.' : null) ||
      'Something went wrong. Please try again.';

    // Attach the normalized message for consumers
    (error as any).normalizedMessage = message;

    // Auto-redirect on 401 for non-auth routes
    if (error.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('docgpt-token');
      window.location.href = '/login';
    }

    return Promise.reject(error);
  },
);

export default api;

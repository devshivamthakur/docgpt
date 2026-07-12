import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

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

// ── Token refresh state ───────────────────────────────────────────────
let isRefreshing = false;
let pendingQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processQueue(token: string | null, err: unknown = null) {
  pendingQueue.forEach(({ resolve, reject }) => {
    if (err) {
      reject(err);
    } else {
      resolve(token!);
    }
  });
  pendingQueue = [];
}

// ── Response interceptor: normalize errors + auto-refresh on 401 ──────
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ message?: string }>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // ── Extract / normalize message ──────────────────────────────
    const message =
      error.response?.data?.message ||
      (error.response?.status === 401 ? 'Session expired. Please log in again.' : null) ||
      'Something went wrong. Please try again.';
    (error as any).normalizedMessage = message;

    // ── 401 handling with refresh token ──────────────────────────
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't intercept the refresh endpoint itself
      if (originalRequest.url?.includes('/auth/refresh')) {
        return Promise.reject(error);
      }

      const storedRefreshToken = localStorage.getItem('refresh-token');
      if (!storedRefreshToken) {
        // No refresh token available — redirect immediately
        localStorage.removeItem('docgpt-token');
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }

      // If a refresh is already in progress, queue this request
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          pendingQueue.push({ resolve, reject });
        }).then((newToken) => {
          originalRequest.headers = originalRequest.headers || {};
          (originalRequest.headers as Record<string, string>)['Authorization'] = `Bearer ${newToken}`;
          return api(originalRequest);
        });
      }

      // Start the refresh process
      isRefreshing = true;
      originalRequest._retry = true;

      try {
        const { data } = await axios.post(
          `${api.defaults.baseURL}/auth/refresh`,
          { refresh_token: storedRefreshToken },
          { headers: { 'Content-Type': 'application/json' } },
        );

        const newToken: string = data.access_token;
        localStorage.setItem('docgpt-token', newToken);
        if (data.refresh_token) {
          localStorage.setItem('refresh-token', data.refresh_token);
        }

        // Process the queue — all queued requests now have a valid token
        processQueue(newToken);

        // Retry the original request
        originalRequest.headers = originalRequest.headers || {};
        (originalRequest.headers as Record<string, string>)['Authorization'] = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(null, refreshError);
        // Refresh failed — clear everything and redirect
        localStorage.removeItem('docgpt-token');
        localStorage.removeItem('refresh-token');
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // ── Non-401 or already retried ───────────────────────────────
    return Promise.reject(error);
  },
);

export default api;

import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

// ── Constants ─────────────────────────────────────────────────────────
const REQUEST_TIMEOUT_MS = 30_000;       // 30s default timeout
const UPLOAD_TIMEOUT_MS = 300_000;       // 5min for uploads
const MAX_RETRIES = 2;                   // retry on network errors
const TOKEN_KEY = 'docgpt-token';
const REFRESH_TOKEN_KEY = 'refresh-token';

// ── Token helpers (centralised to prevent typos) ─────────────────────
export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh?: string): void {
  localStorage.setItem(TOKEN_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Returns the new access token on success, or throws on failure.
 * Shared so fetch-based streams (useChatStream) can also refresh.
 */
export async function tryRefreshToken(): Promise<string> {
  const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!storedRefreshToken) {
    throw new Error('No refresh token available');
  }

  const { data } = await axios.post(
    `${api.defaults.baseURL}/auth/refresh`,
    { refresh_token: storedRefreshToken },
    { headers: { 'Content-Type': 'application/json' } },
  );

  const newToken: string = data.access_token;
  setTokens(newToken, data.refresh_token);
  return newToken;
}

// ── Create Axios instance ─────────────────────────────────────────────
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  timeout: REQUEST_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',          // CSRF protection
    'X-Frame-Options': 'DENY',
  },
  // Use default validateStatus (reject on non-2xx) so the response
  // error interceptor can handle 401s with token refresh
});

// ── Request interceptor: attach auth token + security headers ─────────
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Extend timeout for upload requests
  if (config.data instanceof FormData) {
    config.timeout = UPLOAD_TIMEOUT_MS;
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

/** Dispatch a custom event so React Router / auth store can react */
function dispatchAuthExpired() {
  clearTokens();
  window.dispatchEvent(new CustomEvent('auth:expired'));
}

// ── Response interceptor: normalize errors + auto-refresh on 401 ──────
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ message?: string }>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean; _retryCount?: number };

    // ── Network error → optional retry ───────────────────────────
    if (!error.response && !error.code?.startsWith('ERR_')) {
      originalRequest._retryCount = (originalRequest._retryCount ?? 0) + 1;
      if (originalRequest._retryCount <= MAX_RETRIES) {
        // Exponential backoff: 1s, 2s
        const delay = 1000 * Math.pow(2, originalRequest._retryCount - 1);
        await new Promise((r) => setTimeout(r, delay));
        return api(originalRequest);
      }
    }

    // ── Extract / normalize message ──────────────────────────────
    const message =
      error.response?.data?.message ||
      (error.response?.status === 401 ? 'Session expired. Please log in again.' : null) ||
      (error.code === 'ECONNABORTED' ? 'Request timed out. Please try again.' : null) ||
      'Something went wrong. Please try again.';
    (error as any).normalizedMessage = message;

    // ── 401 handling with refresh token ──────────────────────────
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't intercept the refresh endpoint itself
      if (originalRequest.url?.includes('/auth/refresh')) {
        return Promise.reject(error);
      }

      const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!storedRefreshToken) {
        // No refresh token available — dispatch auth expired
        dispatchAuthExpired();
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
        setTokens(newToken, data.refresh_token);

        // Process the queue — all queued requests now have a valid token
        processQueue(newToken);

        // Retry the original request
        originalRequest.headers = originalRequest.headers || {};
        (originalRequest.headers as Record<string, string>)['Authorization'] = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(null, refreshError);
        // Refresh failed — clear everything and signal auth expiry
        dispatchAuthExpired();
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

import { useEffect, useRef, useCallback } from 'react';
import { useDocumentStore, type ProgressPayload } from '../store/documentStore';
import { getAccessToken } from '../store/api';

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/api';

/**
 * Opens a single WebSocket connection per document for progress updates.
 * Automatically reconnects if the connection drops before a terminal state.
 *
 * Guards against duplicate connections caused by React Strict Mode (dev),
 * rapid re-renders, and reconnection races.
 */
export function useDocumentProgress(docId: number | null) {
  const updateProgress = useDocumentStore((s) => s.updateProgress);

  // ── Refs (no re-render when they change) ───────────────────────
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalClose = useRef(false);
  const docIdRef = useRef(docId);
  const mountedRef = useRef(false);
  const connectRef = useRef<(() => void) | null>(null);

  docIdRef.current = docId;

  // ── Stable connect function (reads deps from refs) ─────────────
  const connect = useCallback(() => {
    const id = docIdRef.current;
    if (id === null) return;

    // ── Don't open if document is already in a terminal state ──
    const docs = useDocumentStore.getState().documents;
    const doc = docs.find((d) => d.id === id);
    if (doc && (doc.status === 'ready' || doc.status === 'failed')) return;

    // ── Don't duplicate an active connection ────────────────────
    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }

    // ── Auth check ──────────────────────────────────────────────
    const token = getAccessToken();
    if (!token) return;

    // ── Open connection ──────────────────────────────────────────
    intentionalClose.current = false;

    // Use protocol-based auth instead of query-param to avoid
    // token leaking in server logs / referrer headers
    const url = `${WS_BASE}/documents/${id}/progress-ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    // Send auth token as the first message (server validates before
    // sending any progress data)
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token }));
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const payload: ProgressPayload = JSON.parse(event.data);
        updateProgress(id, payload);

        // Terminal states — close the connection intentionally
        if (payload.status === 'ready' || payload.status === 'failed') {
          intentionalClose.current = true;
          ws.close();
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      // Only clear wsRef if this WS hasn't already been replaced
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      // Reconnect only if the close was unintentional and component is alive
      if (!intentionalClose.current && docIdRef.current !== null && mountedRef.current) {
        reconnectTimer.current = setTimeout(connect, 2000);
      }
    };

    // No onerror needed — browser fires onclose after onerror automatically
  }, [updateProgress]);

  // Keep a ref to the latest connect so the timer always calls the
  // current version even if the component re-renders.
  connectRef.current = connect;

  // ── Effect: connect when docId changes ──────────────────────────
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      intentionalClose.current = true;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);
}



import { useEffect, useRef, useCallback } from 'react';
import { useDocumentStore, type ProgressPayload } from '../store/documentStore';

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/api';

/**
 * Opens a WebSocket connection for a single document's progress updates.
 * Automatically reconnects if the connection drops before a terminal state.
 */
export function useDocumentProgress(docId: number | null) {
  const updateProgress = useDocumentStore((s) => s.updateProgress);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (docId === null) return;

    const token = localStorage.getItem('docgpt-token');
    if (!token) return;

    // Close any existing connection
    wsRef.current?.close();

    const url = `${WS_BASE}/documents/${docId}/progress-ws?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const payload: ProgressPayload = JSON.parse(event.data);
        updateProgress(docId, payload);

        // Terminal states — close the connection
        if (payload.status === 'ready' || payload.status === 'failed') {
          ws.close();
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = (event) => {
      // Reconnect if not intentionally closed (not a terminal state)
      if (event.code !== 1000 && event.code !== 1001) {
        reconnectTimer.current = setTimeout(connect, 2000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [docId, updateProgress]);

  useEffect(() => {
    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}



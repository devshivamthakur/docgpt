import { useCallback, useRef } from 'react';
import { useConversationStore, type SourceItem } from '../store/conversationStore';
import { getAccessToken, tryRefreshToken, clearTokens } from '../store/api';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/**
 * Hook that manages a streaming RAG response via fetch + ReadableStream (POST).
 *
 * Advantages over the previous EventSource approach:
 * - Uses POST (content in body, JWT in Authorization header)
 * - No URL length limits for long messages
 * - Better security (no token in URL / server logs)
 * - Full HTTP error code handling
 *
 * Usage:
 * ```ts
 * const { startStream, abortStream } = useChatStream();
 * await startStream(convId, "What is this document about?");
 * ```
 */

/** Parse a single SSE ``data: ...`` line from the stream buffer. */
function parseSSELine(line: string): Record<string, unknown> | null {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith(':')) return null; // skip comments & empty
  if (trimmed.startsWith('data: ')) {
    try {
      return JSON.parse(trimmed.slice(6));
    } catch {
      return null;
    }
  }
  return null;
}

export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null);
  const completedRef = useRef(false);

  const startStream = useCallback(
    async (conversationId: string, content: string) => {
      const store = useConversationStore.getState();

      // Abort any existing stream
      abortRef.current?.abort();
      completedRef.current = false;

      // Set streaming state & add optimistic user message
      store.sendMessage(conversationId, content);
      store.addOptimisticUserMessage(content);

      const token = getAccessToken();
      if (!token) {
        store.resetStream();
        return;
      }

      const abortController = new AbortController();
      abortRef.current = abortController;

      /**
       * Read the SSE stream and dispatch events to the conversation store.
       * Extracted as a named function so it can be reused after a token-refresh retry.
       */
      const processStream = async (
        res: Response,
        _store: ReturnType<typeof useConversationStore.getState>,
        controller: AbortController,
      ) => {
        const reader = res.body?.getReader();
        if (!reader) {
          _store.setStreamError('Stream not supported by the browser');
          return;
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process all complete SSE messages in the buffer
          const lines = buffer.split('\n');
          // Keep the last partial line in the buffer
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            const payload = parseSSELine(line);
            if (!payload) continue;

            // Abort check — don't process events after abort
            if (controller.signal.aborted) return;

            switch (payload.type) {
              case 'token':
                useConversationStore
                  .getState()
                  .appendStreamToken(payload.content as string);
                break;

              case 'sources':
                useConversationStore
                  .getState()
                  .setStreamSources(payload.sources as SourceItem[]);
                break;

              case 'done':
                completedRef.current = true;

                useConversationStore.getState().finalizeStream(
                  payload.content as string,
                  payload.sources as SourceItem[] | undefined,
                );
                // Refresh lists to show updated title and get real IDs
                useConversationStore.getState().fetchConversations();
                return; // stream complete — exit normally

              case 'error':
                completedRef.current = true;
                console.error('Stream error:', payload.message);
                useConversationStore.getState().setStreamError(
                  (payload.message as string) ||
                    'An error occurred during generation',
                );
                return;
            }
          }
        }

        // Stream ended without a done/error event (unexpected)
        if (!completedRef.current) {
          const currentState = useConversationStore.getState();
          if (currentState.isStreaming) {
            currentState.setStreamError('Connection closed unexpectedly');
          }
        }
      };

      try {
        const response = await fetch(
          `${API_URL}/conversations/${conversationId}/stream`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ content }),
            signal: abortController.signal,
          },
        );

        // ── Handle 401 with token refresh (mirrors api.ts interceptor) ──
        if (response.status === 401) {
          try {
            const newToken = await tryRefreshToken();
            // Retry the stream with the new token
            const retryResponse = await fetch(
              `${API_URL}/conversations/${conversationId}/stream`,
              {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  Authorization: `Bearer ${newToken}`,
                },
                body: JSON.stringify({ content }),
                signal: abortController.signal,
              },
            );
            if (!retryResponse.ok) {
              throw new Error(`Retry failed with status ${retryResponse.status}`);
            }
            // Replace response with the retried one and continue below
            return processStream(retryResponse, store, abortController);
          } catch (refreshError) {
            // Refresh failed — clear tokens and signal auth expiry
            clearTokens();
            window.dispatchEvent(new CustomEvent('auth:expired'));
            store.setStreamError('Session expired. Please log in again.');
            return;
          }
        }

        if (!response.ok) {
          store.setStreamError(`Server error (${response.status})`);
          return;
        }

        // Process the stream response (extracted so it can be reused on retry)
        await processStream(response, store, abortController);
      } catch (err: unknown) {
        // Don't report errors from intentional aborts
        if (err instanceof DOMException && err.name === 'AbortError') return;

        console.error('Stream fetch failed:', err);
        const currentState = useConversationStore.getState();
        if (currentState.isStreaming) {
          currentState.setStreamError(
            'Connection lost. Please try again.',
          );
        }
      }
    },
    [],
  );

  const abortStream = useCallback(() => {
    completedRef.current = true;
    abortRef.current?.abort();
    abortRef.current = null;
    useConversationStore.getState().resetStream();
  }, []);

  return { startStream, abortStream };
}

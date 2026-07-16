import React, { useCallback, useRef, useState, memo } from 'react';
import { Send, Square, AlertTriangle } from 'lucide-react';
import { sanitizeQuery } from '../utils/sanitize';

// ── Rate limiting ───────────────────────────────────────────────────
const RATE_LIMIT_WINDOW_MS = 2_000;   // 2 seconds between messages
const MAX_MESSAGE_LENGTH = 8_000;     // Max characters per message

interface ChatInputProps {
  onSend: (message: string) => void;
  onAbort: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

const ChatInput = memo(function ChatInput({ onSend, onAbort, isStreaming, disabled }: ChatInputProps) {
  const [value, setValue] = useState('');
  const [sanitizeError, setSanitizeError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastSendRef = useRef(0);

  const handleSubmit = useCallback(
    (e?: React.FormEvent) => {
      e?.preventDefault();
      setSanitizeError(null);
      const trimmed = value.trim();
      if (!trimmed || isStreaming) return;

      // Client-side rate limiting
      const now = Date.now();
      if (now - lastSendRef.current < RATE_LIMIT_WINDOW_MS) {
        setSanitizeError('Please wait a moment before sending another message.');
        return;
      }

      // Length enforcement
      if (trimmed.length > MAX_MESSAGE_LENGTH) {
        setSanitizeError(`Message is too long (max ${MAX_MESSAGE_LENGTH.toLocaleString()} characters).`);
        return;
      }

      // Client-side sanitization
      const result = sanitizeQuery(trimmed);
      if (!result.valid) {
        setSanitizeError(result.reason ?? 'Message was rejected');
        return;
      }

      lastSendRef.current = now;
      onSend(result.cleaned);
      setValue('');
      setSanitizeError(null);

      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    },
    [value, isStreaming, onSend],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Enter sends, Shift+Enter adds newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    // Clear sanitization error when user modifies input
    setSanitizeError(null);
  }, []);

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-3 rounded-2xl border border-slate-700/60 bg-slate-900/90 p-3 backdrop-blur-sm focus-within:border-cyan-500/50 transition-colors"
    >
      {/* Textarea */}
      <div className="flex-1 min-w-0">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Ask a question about your documents…"
          disabled={disabled}
          rows={1}
          className="w-full resize-none bg-transparent text-sm text-slate-200 placeholder-slate-500 outline-none scrollbar-thin disabled:opacity-50"
          style={{ maxHeight: '160px' }}
        />

        {/* Sanitization error */}
        {sanitizeError && (
          <div className="flex items-center gap-1.5 mt-2 text-xs text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span>{sanitizeError}</span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {isStreaming ? (
          <button
            type="button"
            onClick={onAbort}
            className="flex items-center gap-1.5 rounded-full bg-red-500/15 px-3 py-2 text-xs font-medium text-red-300 border border-red-500/30 hover:bg-red-500/25 transition-colors"
          >
            <Square className="h-3.5 w-3.5 fill-red-300" />
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!value.trim() || disabled}
            className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-xs font-medium text-white shadow-lg shadow-cyan-500/20 transition-all hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Send className="h-3.5 w-3.5" />
            Send
          </button>
        )}
      </div>
    </form>
  );
});

export default ChatInput;

import { useState, useCallback, memo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Bot, AlertCircle, Check, Copy } from 'lucide-react';
import type { Message } from '../store/conversationStore';

// ── Code block component (defined before MARKDOWN_COMPONENTS) ───────

const CodeBlock = memo(function CodeBlock({
  codeText,
  language,
}: {
  codeText: string;
  language: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(codeText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = codeText;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [codeText]);

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-slate-700 bg-slate-800/80 px-4 py-1.5">
        <span className="text-xs font-mono text-slate-500">
          {language || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              Copy
            </>
          )}
        </button>
      </div>
      {/* Code content */}
      <div className="overflow-x-auto p-4">
        <code className="block text-sm font-mono text-slate-200 leading-relaxed whitespace-pre">
          {codeText}
        </code>
      </div>
    </div>
  );
});

// ── Static Markdown components (never changes between renders) ───────

const MARKDOWN_COMPONENTS: Record<string, React.FC<any>> = {
  code({ className, children, ...props }) {
    const isInline = !className;
    const codeText = String(children).replace(/\n$/, '');

    if (isInline) {
      return (
        <code
          className="rounded bg-slate-700 px-1.5 py-0.5 text-xs font-mono text-cyan-200"
          {...props}
        >
          {children}
        </code>
      );
    }

    return <CodeBlock codeText={codeText} language={(className || '').replace('language-', '')} />;
  },
  h1({ children }: any) {
    return <h1 className="mt-5 mb-3 text-xl font-bold text-white first:mt-0">{children}</h1>;
  },
  h2({ children }: any) {
    return <h2 className="mt-4 mb-2 text-lg font-semibold text-white">{children}</h2>;
  },
  h3({ children }: any) {
    return <h3 className="mt-3 mb-1.5 text-base font-semibold text-white">{children}</h3>;
  },
  p({ children }: any) {
    return <p className="my-2 text-sm leading-relaxed text-slate-200 last:mb-0">{children}</p>;
  },
  ul({ children }: any) {
    return <ul className="my-2 ml-5 list-disc space-y-1 text-sm text-slate-200">{children}</ul>;
  },
  ol({ children }: any) {
    return <ol className="my-2 ml-5 list-decimal space-y-1 text-sm text-slate-200">{children}</ol>;
  },
  li({ children }: any) {
    return <li className="leading-relaxed">{children}</li>;
  },
  blockquote({ children }: any) {
    return <blockquote className="my-3 border-l-2 border-slate-600 pl-4 italic text-slate-400">{children}</blockquote>;
  },
  a({ children, href, ...props }: any) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-cyan-400 underline decoration-cyan-400/30 underline-offset-2 hover:decoration-cyan-400 transition-colors"
        {...props}
      >
        {children}
      </a>
    );
  },
  hr() {
    return <hr className="my-4 border-slate-700" />;
  },
  table({ children }: any) {
    return (
      <div className="my-3 overflow-x-auto rounded-lg border border-slate-700">
        <table className="min-w-full divide-y divide-slate-700 text-sm">{children}</table>
      </div>
    );
  },
  thead({ children }: any) {
    return <thead className="bg-slate-800/80">{children}</thead>;
  },
  tbody({ children }: any) {
    return <tbody className="divide-y divide-slate-800">{children}</tbody>;
  },
  tr({ children }: any) {
    return <tr>{children}</tr>;
  },
  th({ children }: any) {
    return <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-300">{children}</th>;
  },
  td({ children }: any) {
    return <td className="px-4 py-2 text-sm text-slate-300">{children}</td>;
  },
  strong({ children }: any) {
    return <strong className="font-semibold text-white">{children}</strong>;
  },
  em({ children }: any) {
    return <em className="italic text-slate-200">{children}</em>;
  },
};

// ── Types ────────────────────────────────────────────────────────────

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

const ChatMessage = memo(function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start`}>
      {/* Avatar */}
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border ${
          isUser
            ? 'border-cyan-500/30 bg-cyan-500/15 text-cyan-300'
            : 'border-violet-500/30 bg-violet-500/15 text-violet-300'
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'rounded-tr-md bg-cyan-500/10 border border-cyan-500/20'
            : 'rounded-tl-md bg-slate-800/60 border border-slate-700/50'
        }`}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed text-slate-200 whitespace-pre-wrap">
            {message.content}
          </p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
              {message.content}
            </Markdown>
            {isStreaming && (
              <span className="inline-flex ml-0.5">
                <span className="animate-pulse text-cyan-400">▊</span>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

// ── Error message bubble ─────────────────────────────────────────────

const ErrorMessage = memo(function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex gap-4 items-start">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-red-500/30 bg-red-500/15 text-red-300">
        <AlertCircle className="h-4 w-4" />
      </div>
      <div className="max-w-[80%] rounded-2xl rounded-tl-md bg-red-500/5 border border-red-500/20 px-4 py-3">
        <p className="text-sm text-red-300">{message}</p>
      </div>
    </div>
  );
});

// ── Exports ──────────────────────────────────────────────────────────

export { ErrorMessage };
export default ChatMessage;

import { memo } from 'react';
import { Bot } from 'lucide-react';

const DOT_STYLES = [
  { animationDelay: '0ms' },
  { animationDelay: '150ms' },
  { animationDelay: '300ms' },
];

const TypingIndicator = memo(function TypingIndicator() {
  return (
    <div className="flex gap-4 items-start">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-violet-500/30 bg-violet-500/15 text-violet-300">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-2xl rounded-tl-md bg-slate-800/60 border border-slate-700/50 px-5 py-4">
        <div className="flex items-center gap-1.5">
          {DOT_STYLES.map((style, i) => (
            <span
              key={i}
              className="h-2 w-2 rounded-full bg-slate-500 animate-bounce"
              style={style}
            />
          ))}
        </div>
      </div>
    </div>
  );
});

export default TypingIndicator;

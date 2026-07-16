import { memo } from 'react';
import { FileText, ChevronDown, ChevronUp, Layers } from 'lucide-react';
import type { SourceItem } from '../store/conversationStore';

interface SourcePanelProps {
  sources: SourceItem[];
  isOpen: boolean;
  onToggle: () => void;
}

const SourcePanel = memo(function SourcePanel({ sources, isOpen, onToggle }: SourcePanelProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-sm text-slate-400 hover:text-slate-200 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-violet-400" />
          <span className="font-medium text-slate-300">
            {sources.length} Source{sources.length !== 1 ? 's' : ''}
          </span>
        </span>
        {isOpen ? (
          <ChevronUp className="h-4 w-4" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </button>

      {/* Content */}
      {isOpen && (
        <div className="border-t border-slate-700/50 divide-y divide-slate-800/50 max-h-64 overflow-y-auto">
          {sources.map((source, idx) => (
            <div key={`${source.document_id}-${source.chunk_index ?? idx}`} className="px-4 py-3">
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-cyan-400" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-200 truncate">
                    {source.document_name}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {source.page_index !== null && `Page ${source.page_index}`}
                    {source.page_index !== null && source.score !== null && ' · '}
                    {source.score !== null && `Score: ${(source.score * 100).toFixed(0)}%`}
                  </p>
                  <p className="mt-1 text-xs text-slate-400 line-clamp-2 leading-relaxed">
                    {source.content}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default SourcePanel;

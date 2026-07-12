import React, { useEffect, useMemo } from 'react';
import {
  X,
  FileSearch,
  GitCommit,
  Network,
  Database,
  CheckCircle2,
  Loader2,
  XCircle,
  Clock,
} from 'lucide-react';
import { useDocumentStore, type Document, type DocumentStatus, STATUS_LABELS } from '../store/documentStore';
import { useDocumentProgress } from '../hooks/useWebSocket';

// ── Timeline stage definitions ───────────────────────────────────────

interface Stage {
  key: DocumentStatus;
  icon: React.ReactNode;
  label: string;
}

const STAGES: Stage[] = [
  { key: 'parsing', icon: <FileSearch className="h-4 w-4" />, label: 'Parsing — extracting text & running OCR' },
  { key: 'chunking', icon: <GitCommit className="h-4 w-4" />, label: 'Chunking — splitting into semantic segments' },
  { key: 'embedding', icon: <Network className="h-4 w-4" />, label: 'Embedding — generating vector representations' },
  { key: 'indexing', icon: <Database className="h-4 w-4" />, label: 'Indexing — adding to vector database' },
];

// ── Helpers ──────────────────────────────────────────────────────────

function stageState(
  stageKey: DocumentStatus,
  currentStatus: DocumentStatus,
): 'completed' | 'active' | 'pending' | 'failed' {
  const order: DocumentStatus[] = ['uploaded', 'parsing', 'chunking', 'embedding', 'indexing', 'ready', 'failed'];
  const stageIdx = order.indexOf(stageKey);
  const currentIdx = order.indexOf(currentStatus);

  if (currentStatus === 'failed') {
    // If the failed stage is before or at this stage, mark as failed
    // Otherwise it's pending
    return 'failed';
  }

  if (currentIdx > stageIdx) return 'completed';
  if (currentIdx === stageIdx) return 'active';
  return 'pending';
}

// ── ProcessingModal ──────────────────────────────────────────────────

interface ProcessingModalProps {
  docId: number | null;
  onClose: () => void;
}

function ProcessingModal({ docId, onClose }: ProcessingModalProps) {
  const documents = useDocumentStore((s) => s.documents);
  const liveProgress = useDocumentStore((s) => s.liveProgress);

  // Connect WebSocket for real-time updates
  useDocumentProgress(docId);

  const doc = useMemo<Document | undefined>(
    () => documents.find((d) => d.id === docId),
    [documents, docId],
  );

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (docId !== null) {
      document.addEventListener('keydown', handler);
      return () => document.removeEventListener('keydown', handler);
    }
  }, [docId, onClose]);

  if (docId === null || !doc) return null;

  const progressPayload = liveProgress[doc.id];
  const currentStatus: DocumentStatus = progressPayload?.status || doc.status;
  const currentProgress = progressPayload?.progress ?? doc.progress;
  const progressMessage = progressPayload?.message || STATUS_LABELS[currentStatus];
  const isFailed = currentStatus === 'failed';
  const isReady = currentStatus === 'ready';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-3xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-100">
            {doc.original_filename}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-800 hover:text-slate-300 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* ── Body ──────────────────────────────────────────────── */}
        <div className="space-y-6 px-6 py-6">

          {/* Overall progress bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-slate-300">{progressMessage}</span>
              <span className="text-slate-500">{currentProgress}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full transition-all duration-700 ease-out ${
                  isFailed
                    ? 'bg-red-500'
                    : isReady
                      ? 'bg-emerald-500'
                      : 'bg-gradient-to-r from-cyan-500 to-violet-500'
                } ${!isReady && !isFailed ? 'animate-pulse' : ''}`}
                style={{ width: `${Math.min(currentProgress, 100)}%` }}
              />
            </div>
          </div>

          {/* Timeline */}
          <div className="space-y-0">
            {STAGES.map((stage, idx) => {
              const state = stageState(stage.key, currentStatus);

              let icon: React.ReactNode;
              let textColor: string;
              let lineColor: string;

              switch (state) {
                case 'completed':
                  icon = <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
                  textColor = 'text-emerald-300';
                  lineColor = 'bg-emerald-500/30';
                  break;
                case 'active':
                  icon = <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />;
                  textColor = 'text-cyan-200';
                  lineColor = 'bg-cyan-500/50';
                  break;
                case 'failed':
                  icon = <XCircle className="h-4 w-4 text-red-400" />;
                  textColor = 'text-red-300';
                  lineColor = 'bg-red-500/30';
                  break;
                default:
                  icon = <Clock className="h-4 w-4 text-slate-600" />;
                  textColor = 'text-slate-600';
                  lineColor = 'bg-slate-800';
              }

              return (
                <div key={stage.key} className="flex gap-4">
                  {/* Timeline gutter */}
                  <div className="flex flex-col items-center">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 ring-1 ring-slate-800">
                      {icon}
                    </div>
                    {idx < STAGES.length - 1 && (
                      <div className={`mt-1 h-8 w-0.5 ${lineColor}`} />
                    )}
                  </div>

                  {/* Stage content */}
                  <div className={`flex items-center pb-8 text-sm ${textColor}`}>
                    <span>{stage.label}</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Terminal state info */}
          {isReady && (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-center">
              <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-400" />
              <p className="mt-2 text-sm font-medium text-emerald-300">Document ready for conversation</p>
            </div>
          )}

          {isFailed && doc.error_message && (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-4">
              <div className="flex items-start gap-2 text-sm text-red-300">
                <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{doc.error_message}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default React.memo(ProcessingModal);

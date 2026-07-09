import { useState } from 'react';
import {
  FileText,
  Trash2,
  AlertCircle,
  Loader2,
  CheckCircle2,
  Clock,
  FileSearch,
  XCircle,
} from 'lucide-react';
import {
  useDocumentStore,
  type Document,
  type DocumentStatus,
  STATUS_LABELS,
} from '../store/documentStore';
import ProcessingModal from './ProcessingModal.js';

// ── Status badge styling ─────────────────────────────────────────────

const STATUS_BADGE: Record<DocumentStatus, { icon: React.ReactNode; className: string }> = {
  uploading: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  },
  uploaded: {
    icon: <Clock className="h-3.5 w-3.5" />,
    className: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  },
  parsing: {
    icon: <FileSearch className="h-3.5 w-3.5 animate-pulse" />,
    className: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  },
  chunking: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  },
  embedding: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  },
  indexing: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  },
  ready: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  },
  failed: {
    icon: <XCircle className="h-3.5 w-3.5" />,
    className: 'bg-red-500/15 text-red-300 border-red-500/30',
  },
};

// ── Progress bar ─────────────────────────────────────────────────────

function ProgressBar({ progress, status }: { progress: number; status: DocumentStatus }) {
  const isTerminal = status === 'ready' || status === 'failed';
  const color =
    status === 'failed'
      ? 'bg-red-500'
      : status === 'ready'
        ? 'bg-emerald-500'
        : 'bg-cyan-500';

  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
      <div
        className={`h-full rounded-full transition-all duration-700 ease-out ${color} ${isTerminal ? '' : 'animate-pulse'}`}
        style={{ width: `${Math.min(progress, 100)}%` }}
      />
    </div>
  );
}

// ── Format helpers ───────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── DocumentCard ─────────────────────────────────────────────────────

function DocumentCard({
  doc,
  onDelete,
  onClick,
}: {
  doc: Document;
  onDelete: (id: number) => void;
  onClick: (id: number) => void;
}) {
  const badge = STATUS_BADGE[doc.status];
  const isProcessing = !['ready', 'failed', 'uploading'].includes(doc.status);

  return (
    <div
      onClick={() => onClick(doc.id)}
      className="group relative cursor-pointer rounded-2xl border border-slate-800 bg-slate-900/80 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/95 hover:shadow-lg"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="shrink-0 rounded-xl bg-slate-800 p-2.5 text-slate-400">
            <FileText className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-200" title={doc.original_filename}>
              {doc.original_filename}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              {formatFileSize(doc.file_size)} &middot; {formatDate(doc.created_at)}
            </p>
          </div>
        </div>

        <button
          onClick={(e) => { e.stopPropagation(); onDelete(doc.id); }}
          className="shrink-0 rounded-lg p-1.5 text-slate-600 opacity-0 transition hover:bg-red-500/15 hover:text-red-400 group-hover:opacity-100"
          title="Delete document"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {/* Status badge */}
      <div className="mt-4 flex items-center gap-3">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${badge.className}`}
        >
          {badge.icon}
          {STATUS_LABELS[doc.status]}
        </span>

        {doc.status === 'failed' && doc.error_message && (
          <span className="truncate text-xs text-red-400/70" title={doc.error_message}>
            {doc.error_message}
          </span>
        )}
      </div>

      {/* Progress bar (only for active states) */}
      {(isProcessing || doc.status === 'uploaded') && (
        <div className="mt-3">
          <ProgressBar progress={doc.progress} status={doc.status} />
          <p className="mt-1 text-right text-xs text-slate-500">{doc.progress}%</p>
        </div>
      )}

      {doc.status === 'ready' && (
        <div className="mt-3">
          <ProgressBar progress={100} status={doc.status} />
        </div>
      )}
    </div>
  );
}

// ── DocumentGrid ─────────────────────────────────────────────────────

export default function DocumentGrid() {
  const documents = useDocumentStore((s) => s.documents);
  const isLoading = useDocumentStore((s) => s.isLoading);
  const deleteDocument = useDocumentStore((s) => s.deleteDocument);

  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());

  const handleDelete = async (id: number) => {
    setDeleting((prev) => new Set(prev).add(id));
    await deleteDocument(id);
    setDeleting((prev) => { const next = new Set(prev); next.delete(id); return next; });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
        <span className="ml-3 text-sm text-slate-400">Loading documents…</span>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 py-16 text-center">
        <FileText className="h-12 w-12 text-slate-700" />
        <p className="mt-4 text-base font-medium text-slate-400">No documents yet</p>
        <p className="mt-1 text-sm text-slate-600">
          Upload a PDF, DOCX, or markdown file to get started
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {documents.map((doc) => (
          <DocumentCard
            key={doc.id}
            doc={doc}
            onDelete={handleDelete}
            onClick={setSelectedDocId}
          />
        ))}
      </div>

      {/* Processing detail modal */}
      <ProcessingModal
        docId={selectedDocId}
        onClose={() => setSelectedDocId(null)}
      />
    </>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  MessageSquare,
  Trash2,
  RefreshCw,
  Search,
  X,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock,
  Loader2,
  AlertCircle,
  FileSearch,
  HardDrive,
  SlidersHorizontal,
} from 'lucide-react';
import { useDocumentStore, STATUS_LABELS, type Document, type DocumentStatus } from '../store/documentStore';

// ── Helpers ──────────────────────────────────────────────────────────

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── Status config ────────────────────────────────────────────────────

const STATUS_CONFIG: Record<DocumentStatus, { icon: React.ReactNode; className: string; label: string }> = {
  uploading: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-blue-500/10 text-blue-400 border-blue-500/25',
    label: 'Uploading…',
  },
  uploaded: {
    icon: <Clock className="h-3.5 w-3.5" />,
    className: 'bg-slate-500/10 text-slate-400 border-slate-500/25',
    label: 'Queued',
  },
  parsing: {
    icon: <FileSearch className="h-3.5 w-3.5 animate-pulse" />,
    className: 'bg-amber-500/10 text-amber-400 border-amber-500/25',
    label: 'Parsing…',
  },
  chunking: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/25',
    label: 'Chunking…',
  },
  embedding: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-violet-500/10 text-violet-400 border-violet-500/25',
    label: 'Embedding…',
  },
  indexing: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/25',
    label: 'Indexing…',
  },
  ready: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25',
    label: 'Ready',
  },
  failed: {
    icon: <AlertCircle className="h-3.5 w-3.5" />,
    className: 'bg-red-500/10 text-red-400 border-red-500/25',
    label: 'Failed',
  },
};

// ── Status filter options ────────────────────────────────────────────

const STATUS_FILTERS = [
  { value: 'all', label: 'All Documents' },
  { value: 'ready', label: 'Ready' },
  { value: 'processing', label: 'Processing' },
  { value: 'failed', label: 'Failed' },
] as const;

type StatusFilter = (typeof STATUS_FILTERS)[number]['value'];

const PROCESSING_STATUSES: DocumentStatus[] = ['uploading', 'uploaded', 'parsing', 'chunking', 'embedding', 'indexing'];

// ── DocumentRow ──────────────────────────────────────────────────────

function DocumentRow({
  doc,
  isDeleting,
  onChat,
  onDelete,
  onReprocess,
}: {
  doc: Document;
  isDeleting?: boolean;
  onChat: (id: number) => void;
  onDelete: (id: number) => void;
  onReprocess: (id: number) => void;
}) {
  const cfg = STATUS_CONFIG[doc.status];
  const isReady = doc.status === 'ready';
  const isFailed = doc.status === 'failed';
  const isProcessing = PROCESSING_STATUSES.includes(doc.status);

  return (
    <div className={`group flex items-center gap-4 border-b border-slate-800/60 px-4 py-3.5 transition hover:bg-slate-800/40 sm:px-6 ${isDeleting ? 'opacity-50 pointer-events-none' : ''}`}>
      {/* Icon */}
      <div className="hidden shrink-0 sm:block">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 text-slate-500">
          <FileText className="h-4.5 w-4.5" />
        </div>
      </div>

      {/* Name + meta */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-200" title={doc.original_filename}>
          {doc.original_filename}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
          <span>{formatSize(doc.file_size)}</span>
          <span className="text-slate-700">·</span>
          <span>{formatDate(doc.created_at)}</span>
          {doc.mime_type && (
            <>
              <span className="text-slate-700">·</span>
              <span className="uppercase">{doc.mime_type.split('/').pop()}</span>
            </>
          )}
        </p>
      </div>

      {/* Status badge */}
      <div className="hidden shrink-0 md:block">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.className}`}
        >
          {cfg.icon}
          {cfg.label}
        </span>
      </div>

      {/* Error tooltip (failed only) */}
      {isFailed && doc.error_message && (
        <div className="hidden max-w-[180px] truncate text-xs text-red-400/70 lg:block" title={doc.error_message}>
          {doc.error_message}
        </div>
      )}

      {/* Progress for active docs */}
      {isProcessing && (
        <div className="hidden w-20 sm:block">
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 transition-all duration-700 ease-out"
              style={{ width: `${Math.min(doc.progress, 100)}%` }}
            />
          </div>
          <p className="mt-0.5 text-right text-[10px] text-slate-500">{doc.progress}%</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-1">
        {isReady && (
          <button
            onClick={() => onChat(doc.id)}
            disabled={isDeleting}
            className="rounded-lg p-2 text-emerald-400/60 transition hover:bg-emerald-500/15 hover:text-emerald-400 disabled:opacity-40"
            title="Chat with this document"
          >
            <MessageSquare className="h-4 w-4" />
          </button>
        )}
        {isFailed && (
          <button
            onClick={() => onReprocess(doc.id)}
            disabled={isDeleting}
            className="rounded-lg p-2 text-amber-400/60 transition hover:bg-amber-500/15 hover:text-amber-400 disabled:opacity-40"
            title="Retry processing"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        )}
        <button
          onClick={() => onDelete(doc.id)}
          disabled={isDeleting}
          className="rounded-lg p-2 text-red-400/40 transition hover:bg-red-500/15 hover:text-red-400 disabled:opacity-40"
          title="Delete document"
        >
          {isDeleting ? (
            <Loader2 className="h-4 w-4 animate-spin text-red-400" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}

// ── Skeleton row ─────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 border-b border-slate-800/60 px-4 py-3.5 sm:px-6">
      <div className="hidden h-9 w-9 animate-pulse rounded-lg bg-slate-800 sm:block" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-3/5 animate-pulse rounded bg-slate-800" />
        <div className="h-3 w-1/4 animate-pulse rounded bg-slate-800/60" />
      </div>
      <div className="hidden h-5 w-20 animate-pulse rounded-full bg-slate-800 md:block" />
      <div className="flex gap-1">
        <div className="h-8 w-8 animate-pulse rounded-lg bg-slate-800" />
        <div className="h-8 w-8 animate-pulse rounded-lg bg-slate-800" />
      </div>
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-4 rounded-2xl bg-slate-800/50 p-4">
        <FileText className="h-10 w-10 text-slate-600" />
      </div>
      <p className="text-base font-medium text-slate-400">
        {hasFilters ? 'No documents match your filters' : 'No documents yet'}
      </p>
      <p className="mt-1 text-sm text-slate-600">
        {hasFilters
          ? 'Try adjusting your search or filter criteria.'
          : 'Upload a document from the dashboard to get started.'}
      </p>
      {!hasFilters && (
        <button
          onClick={() => navigate('/')}
          className="mt-5 flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 px-5 py-2 text-sm font-medium text-white shadow-lg shadow-cyan-500/20 transition hover:opacity-90"
        >
          <HardDrive className="h-4 w-4" />
          Go to Dashboard
        </button>
      )}
    </div>
  );
}

// ── Pagination ───────────────────────────────────────────────────────

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}) {
  // Build page number list with ellipsis
  const pages = useMemo(() => {
    const items: (number | 'ellipsis')[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) items.push(i);
    } else {
      items.push(1);
      if (page > 3) items.push('ellipsis');
      for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) {
        items.push(i);
      }
      if (page < totalPages - 2) items.push('ellipsis');
      items.push(totalPages);
    }
    return items;
  }, [page, totalPages]);

  if (totalPages <= 1) return null;

  const start = page * pageSize + 1;
  const end = Math.min((page + 1) * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-800/60 px-4 py-4 sm:px-6">
      <p className="text-xs text-slate-500">
        Showing <span className="font-medium text-slate-400">{start}–{end}</span> of{' '}
        <span className="font-medium text-slate-400">{total}</span> documents
      </p>

      <div className="flex items-center gap-1.5">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 0}
          className="flex items-center gap-1 rounded-lg border border-slate-700/50 px-2.5 py-1.5 text-xs font-medium text-slate-400 transition hover:border-slate-600 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Prev
        </button>

        {pages.map((p, idx) =>
          p === 'ellipsis' ? (
            <span key={`ellipsis-${idx}`} className="px-1 text-xs text-slate-600">
              …
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p - 1)}
              className={`flex h-7 min-w-[28px] items-center justify-center rounded-lg px-2 text-xs font-medium transition ${
                p - 1 === page
                  ? 'bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/40'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              {p}
            </button>
          ),
        )}

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages - 1}
          className="flex items-center gap-1 rounded-lg border border-slate-700/50 px-2.5 py-1.5 text-xs font-medium text-slate-400 transition hover:border-slate-600 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// ── DocumentListPage ─────────────────────────────────────────────────

const PAGE_SIZE = 15;

function DocumentListPage() {
  const navigate = useNavigate();
  const documents = useDocumentStore((s) => s.documents) ?? [];
  const total = useDocumentStore((s) => s.total);
  const isLoading = useDocumentStore((s) => s.isLoading);
  const fetchDocumentsPage = useDocumentStore((s) => s.fetchDocumentsPage);
  const deleteDocument = useDocumentStore((s) => s.deleteDocument);
  const reprocessDocument = useDocumentStore((s) => s.reprocessDocument);
  const deletingIds = useDocumentStore((s) => s.deletingIds);

  const [page, setPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [showFilters, setShowFilters] = useState(false);

  // ── Fetch on mount & page change ────────────────────────────────
  useEffect(() => {
    fetchDocumentsPage(page * PAGE_SIZE, PAGE_SIZE);
  }, [page, fetchDocumentsPage]);

  // Reset to page 0 when filters change
  useEffect(() => {
    setPage(0);
  }, [searchQuery, statusFilter]);

  // ── Filtered + searched documents ────────────────────────────────
  const filteredDocuments = useMemo(() => {
    let list = documents;

    // Status filter
    if (statusFilter === 'ready') {
      list = list.filter((d) => d.status === 'ready');
    } else if (statusFilter === 'processing') {
      list = list.filter((d) => PROCESSING_STATUSES.includes(d.status));
    } else if (statusFilter === 'failed') {
      list = list.filter((d) => d.status === 'failed');
    }

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter(
        (d) =>
          d.original_filename.toLowerCase().includes(q) ||
          d.mime_type.toLowerCase().includes(q),
      );
    }

    return list;
  }, [documents, statusFilter, searchQuery]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const hasFilters = statusFilter !== 'all' || searchQuery.trim().length > 0;

  // ── Actions ──────────────────────────────────────────────────────
  const handleChat = useCallback(
    (docId: number) => {
      navigate(`/chat?documentId=${docId}`);
    },
    [navigate],
  );

  const handleDelete = useCallback(
    async (id: number) => {
      await deleteDocument(id);
      // Re-fetch current page after deletion
      fetchDocumentsPage(page * PAGE_SIZE, PAGE_SIZE);
    },
    [deleteDocument, page, PAGE_SIZE, fetchDocumentsPage],
  );

  const handleReprocess = useCallback(
    async (id: number) => {
      await reprocessDocument(id);
    },
    [reprocessDocument],
  );

  const handleRetryAllFailed = useCallback(async () => {
    const failed = documents.filter((d) => d.status === 'failed');
    await Promise.allSettled(failed.map((d) => reprocessDocument(d.id)));
  }, [documents, reprocessDocument]);

  // ── Stats for header ─────────────────────────────────────────────
  const stats = useMemo(() => {
    const ready = documents.filter((d) => d.status === 'ready').length;
    const processing = documents.filter((d) => PROCESSING_STATUSES.includes(d.status)).length;
    const failed = documents.filter((d) => d.status === 'failed').length;
    return { ready, processing, failed };
  }, [documents]);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.12),_transparent_40%),linear-gradient(135deg,_#020617,_#0f172a)] text-white">
      {/* Grid overlay */}
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.015]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />

      <div className="relative mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
        {/* ══════════════════════════════════════════════════════════
            HEADER
           ══════════════════════════════════════════════════════════ */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-1.5 rounded-full border border-slate-700/50 bg-slate-800/50 px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:bg-slate-700/50"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Dashboard
            </button>
            <div>
              <h1 className="text-xl font-semibold sm:text-2xl">All Documents</h1>
              <p className="text-xs text-slate-500 sm:text-sm">
                {total} document{total !== 1 ? 's' : ''} · {stats.ready} ready · {stats.processing} processing ·{' '}
                {stats.failed} failed
              </p>
            </div>
          </div>

          {/* Retry all button */}
          {stats.failed > 0 && (
            <button
              onClick={handleRetryAllFailed}
              className="flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-3.5 py-2 text-xs font-medium text-red-300 transition hover:bg-red-500/20"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry All Failed
            </button>
          )}
        </div>

        {/* ══════════════════════════════════════════════════════════
            FILTER BAR
           ══════════════════════════════════════════════════════════ */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search documents…"
              className="w-full rounded-xl border border-slate-700/50 bg-slate-800/60 py-2 pl-9 pr-8 text-sm text-slate-200 placeholder-slate-500 outline-none transition focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-500 hover:text-slate-300"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Status pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                  statusFilter === f.value
                    ? 'border-cyan-500/40 bg-cyan-500/15 text-cyan-300'
                    : 'border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-slate-300'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Mobile filter toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-1.5 rounded-full border border-slate-700/50 px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:border-slate-600 hover:text-slate-300 sm:hidden"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Filters
          </button>
        </div>

        {/* ══════════════════════════════════════════════════════════
            TABLE
           ══════════════════════════════════════════════════════════ */}
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl">
          {/* Column headers */}
          <div className="hidden border-b border-slate-800/60 bg-slate-900/80 px-6 py-3 text-xs font-medium uppercase tracking-wider text-slate-500 sm:flex sm:items-center sm:gap-4">
            <div className="w-9 shrink-0" />
            <div className="flex-1">Name</div>
            <div className="hidden w-28 shrink-0 md:block">Status</div>
            <div className="hidden w-24 shrink-0 sm:block">Progress</div>
            <div className="w-20 shrink-0 text-right">Actions</div>
          </div>

          {/* Body */}
          {isLoading ? (
            <>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </>
          ) : filteredDocuments.length === 0 ? (
            <EmptyState hasFilters={hasFilters} />
          ) : (
            <div className="divide-y-0">
              {filteredDocuments.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  doc={doc}
                  isDeleting={!!deletingIds[doc.id]}
                  onChat={handleChat}
                  onDelete={handleDelete}
                  onReprocess={handleReprocess}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          <Pagination
            page={page}
            totalPages={totalPages}
            total={total}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        </div>
      </div>
    </div>
  );
}

export default DocumentListPage;
